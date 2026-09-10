#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
spindlefind.py —— Phase 2 Step 2: Moser spindle 偵測器 (雙引擎, 互相對數)

Moser spindle (pattern, 7 點 11 邊):  hub a; 菱形 1 = {a, b1, c1, d1} (邊 ab1 ac1 b1c1 b1d1 c1d1);
菱形 2 = {a, b2, c2, d2} (同樣 5 條邊); 兩個 tip 相連 d1d2。「含 spindle」= 作為 **subgraph** (非誘導)。

引擎 A (枚舉):  搵晒所有菱形 (兩個三角形共邊: 邊 {b,c} + 兩個公共鄰居 {a,d}), 每個菱形按長對角線
                兩端 a / d 各入一個桶 (tip = 另一端)。同一 hub 桶入面每對菱形, 若 tip 相鄰而且除 hub 外
                6 粒頂點全部相異 → 一隻 spindle copy。每個 copy 剛好數一次 (hub 係唯一同屬兩個菱形嘅點)。
引擎 B (SAT):  subgraph monomorphism CNF: 7 個 pattern 頂點各自映去圖頂點 (exactly-one), injective,
                11 條 pattern 邊每條都要映落圖邊 (x[p][v] → ∨_{w∈N(v)} x[q][w])。
                UNSAT + drat-trim VERIFIED = 認證級 spindle-free 證書;
                SAT → 解碼映射, 逐條 pattern 邊喺圖邊表覆核 (SAT 主張要逐邊覆核先算數)。
                預設加 pattern 對稱破除 (b1<c1, b2<c2, d1<d2, 用 AMO ladder 變量), --no-symbreak 可關。

用法:
  python3 spindlefind.py enumerate <edge>
  python3 spindlefind.py sat <edge> --out DIR [--solver kissat|cadical] [--timeout 1800] [--no-symbreak]
  python3 spindlefind.py both <edge> --out DIR [...]        # 兩引擎必須一致 (A>0 ⟺ B SAT), 否則大聲死
  python3 spindlefind.py selftest [--work DIR]              # 對數測試 + 毒藥
"""
import sys, os, time, argparse, subprocess, json, random, itertools

if not __debug__:
    sys.exit("!! 唔准用 python -O 跑呢個檢查器 (assert 會被剝走, 檢查形同虛設)")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from exactfield import load_edges          # 加固版 loader (self-loop / 重複 / 越界 / 空表 全擋)

KISSAT   = os.path.expanduser("~/hadwiger/kissat/build/kissat")
CADICAL  = os.path.expanduser("~/hadwiger/cadical/build/cadical")
DRATTRIM = os.path.expanduser("~/hadwiger/drat-trim/drat-trim")
DRATTRIM_TIMEOUT = 6 * 3600   # drat-trim 都要有 timeout (大證明可以行幾個鐘; 超時 = 冇證書, 唔算數)

# pattern: 0=a(hub) 1=b1 2=c1 3=d1 4=b2 5=c2 6=d2
PATTERN_EDGES = [(0, 1), (0, 2), (1, 2), (1, 3), (2, 3),
                 (0, 4), (0, 5), (4, 5), (4, 6), (5, 6),
                 (3, 6)]
PATTERN_NAMES = ["a", "b1", "c1", "d1", "b2", "c2", "d2"]
assert len(PATTERN_EDGES) == 11

def adjacency(n, edges):
    adj = [set() for _ in range(n + 1)]          # 1-based
    for u, v in edges:
        adj[u].add(v); adj[v].add(u)
    return adj

# ============================================================
# 引擎 A: 枚舉
# ============================================================

def find_rhombi(n, edges, adj):
    """回傳 list of (a, d, b, c): 長對角線 {a,d} (a<d), 共邊 {b,c} (b<c)"""
    rh = []
    for b, c in edges:
        if b > c:
            b, c = c, b
        common = sorted(adj[b] & adj[c])
        for i in range(len(common)):
            for j in range(i + 1, len(common)):
                rh.append((common[i], common[j], b, c))
    return rh

def enumerate_spindles(n, edges, adj=None, want_list=0):
    """回傳 (copies, rhombi 數, 例子 list [(a,b1,c1,d1,b2,c2,d2), ...])"""
    if adj is None:
        adj = adjacency(n, edges)
    assert len({frozenset(e) for e in edges}) == len(edges) and all(u != v for u, v in edges), "edges 有重複/self-loop"
    rh = find_rhombi(n, edges, adj)
    bucket = {}
    for (a, d, b, c) in rh:
        bucket.setdefault(a, []).append((d, b, c))
        bucket.setdefault(d, []).append((a, b, c))
    copies = 0
    examples = []
    for hub, lst in bucket.items():
        for i in range(len(lst)):
            t1, b1, c1 = lst[i]
            for j in range(i + 1, len(lst)):
                t2, b2, c2 = lst[j]
                if t1 == t2 or t2 not in adj[t1]:
                    continue
                if len({b1, c1, t1, b2, c2, t2}) != 6:
                    continue
                copies += 1
                if len(examples) < want_list:
                    examples.append((hub, b1, c1, t1, b2, c2, t2))
    return copies, len(rh), examples

def verify_copy(copy, adj):
    """逐條 pattern 邊覆核: 7 點相異, 11 條邊全部喺圖入面"""
    assert len(set(copy)) == 7, f"copy 頂點唔相異: {copy}"
    for p, q in PATTERN_EDGES:
        assert copy[q] in adj[copy[p]], f"copy {copy}: pattern 邊 {PATTERN_NAMES[p]}-{PATTERN_NAMES[q]} 唔喺圖入面"
    return True

# ============================================================
# 引擎 B: SAT
# ============================================================

def build_cnf(n, edges, adj, symbreak=True):
    """回傳 (clauses, nvars, meta)。變量: x[p][v] = p*n + v (v 1-based) ; ladder s[p][v] 之後。"""
    def x(p, v):
        return p * n + v
    nx = 7 * n
    def s(p, v):                                  # v = 1..n-1 ; s[p][v] ⇐ (x[p][1] ∨ ... ∨ x[p][v])
        return nx + p * (n - 1) + v
    nvars = nx + 7 * (n - 1)
    cl = []
    for p in range(7):
        cl.append([x(p, v) for v in range(1, n + 1)])                     # at least one
        # Sinz sequential AMO
        for v in range(1, n + 1):
            if v < n:
                cl.append([-x(p, v), s(p, v)])
            if 1 < v < n:
                cl.append([-s(p, v - 1), s(p, v)])
            if v > 1:
                cl.append([-x(p, v), -s(p, v - 1)])
    for v in range(1, n + 1):                                             # injective
        for p in range(7):
            for q in range(p + 1, 7):
                cl.append([-x(p, v), -x(q, v)])
    for p, q in PATTERN_EDGES:                                            # 邊要映落邊
        for v in range(1, n + 1):
            nb = sorted(adj[v])
            cl.append([-x(p, v)] + [x(q, w) for w in nb])
            cl.append([-x(q, v)] + [x(p, w) for w in nb])
    nsb = 0
    if symbreak:
        # img(p) < img(q): x[p][v] → ¬s[q][v]  (s[q][v] 真 ⇐ q 映落 ≤ v)
        for p, q in ((1, 2), (4, 5), (3, 6)):
            for v in range(1, n):
                cl.append([-x(p, v), -s(q, v)])
                nsb += 1
            cl.append([-x(p, n)])                                         # p 唔可以係最大 index
            nsb += 1
    meta = {"n": n, "m": len(edges), "nvars": nvars, "clauses": len(cl), "symbreak": symbreak,
            "symbreak_clauses": nsb}
    return cl, nvars, meta

def write_dimacs(path, nvars, clauses):
    with open(path, "w") as f:
        f.write(f"p cnf {nvars} {len(clauses)}\n")
        for c in clauses:
            f.write(" ".join(map(str, c)) + " 0\n")

def run_solver(solver, cnf, drat, timeout):
    if solver == "kissat":
        cmd = [KISSAT, "-q", "--no-binary", cnf, drat]
    elif solver == "cadical":
        cmd = [CADICAL, "-q", "--no-binary", cnf, drat]
    else:
        raise ValueError(solver)
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r, time.time() - t0

def parse_model(stdout):
    vals = set()
    for line in stdout.splitlines():
        if line.startswith("v"):
            for t in line.split()[1:]:
                x = int(t)
                if x > 0:
                    vals.add(x)
    return vals

def drat_verified(stdout):
    """drat-trim 判定: 要有一整行剛好係 's VERIFIED' (唔用 substring)"""
    return any(line.strip() == "s VERIFIED" for line in stdout.splitlines())

def sat_engine(n, edges, outdir, solver="kissat", timeout=1800, symbreak=True, tag="spindle"):
    """回傳 dict: status 'UNSAT'(+verified) / 'SAT'(+copy) / 'timeout'。全部檔案落 outdir。"""
    os.makedirs(outdir, exist_ok=True)
    for stale in (tag + ".sol", tag + ".drat", tag + ".cnf"):        # 清走舊 run 嘅殘留, 唔好俾人溝亂證書
        if os.path.exists(os.path.join(outdir, stale)):
            os.remove(os.path.join(outdir, stale))
    adj = adjacency(n, edges)
    cl, nvars, meta = build_cnf(n, edges, adj, symbreak)
    cnf = os.path.join(outdir, tag + ".cnf")
    drat = os.path.join(outdir, tag + ".drat")
    write_dimacs(cnf, nvars, cl)
    try:
        r, dt = run_solver(solver, cnf, drat, timeout)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "meta": meta, "timeout": timeout}
    res = {"meta": meta, "solver": solver, "solve_s": round(dt, 2), "cnf": cnf}
    if r.returncode == 20:
        t1 = time.time()
        dr = subprocess.run([DRATTRIM, cnf, drat], capture_output=True, text=True, timeout=DRATTRIM_TIMEOUT)
        verified = drat_verified(dr.stdout)
        res.update({"status": "UNSAT", "drat": drat, "verified": verified,
                    "drat_lines": sum(1 for _ in open(drat, errors="ignore")),
                    "drattrim_s": round(time.time() - t1, 1), "drattrim_tail": dr.stdout[-300:]})
        assert verified, "!! drat-trim 冇 s VERIFIED, 唔可以信呢份 UNSAT:\n" + dr.stdout[-800:]
    elif r.returncode == 10:
        model = parse_model(r.stdout)
        copy = []
        for p in range(7):
            imgs = [v for v in range(1, n + 1) if (p * n + v) in model]
            assert len(imgs) == 1, f"pattern 頂點 {PATTERN_NAMES[p]} 映咗 {len(imgs)} 個圖頂點 (應該啱啱 1 個)"
            copy.append(imgs[0])
        copy = tuple(copy)
        verify_copy(copy, adj)                     # 逐邊覆核 —— 唔過就 assert 死
        with open(os.path.join(outdir, tag + ".sol"), "w") as f:
            json.dump({"copy": dict(zip(PATTERN_NAMES, copy)), "pattern_edges": PATTERN_EDGES}, f)
        res.update({"status": "SAT", "copy": copy})
        if os.path.exists(drat):
            os.remove(drat)
    else:
        raise AssertionError(f"solver rc={r.returncode}: {(r.stderr or r.stdout)[-400:]}")
    return res

# ============================================================
# 對數 / 測試圖生成
# ============================================================

def moser_spindle_edges():
    return 7, [(p + 1, q + 1) for p, q in PATTERN_EDGES]

def triangular_patch(k):
    """三角格仔 patch: 點 (i, j) ↦ i + j·e^{iπ/3}, 0 ≤ i, j < k; 單位邊 = 6 個格仔方向 (整數座標, 精確)"""
    idx = {}
    pts = []
    for i in range(k):
        for j in range(k):
            idx[(i, j)] = len(pts) + 1
            pts.append((i, j))
    edges = []
    for (i, j), u in idx.items():
        for di, dj in ((1, 0), (0, 1), (-1, 1)):
            v = idx.get((i + di, j + dj))
            if v:
                edges.append((u, v))
    return len(pts), edges

def write_edge(path, n, edges):
    with open(path, "w") as f:
        f.write(f"p edge {n} {len(edges)}\n")
        for u, v in edges:
            f.write(f"e {u} {v}\n")

def both(n, edges, outdir, **kw):
    adj = adjacency(n, edges)
    t0 = time.time()
    copies, nrh, ex = enumerate_spindles(n, edges, adj, want_list=3)
    tA = time.time() - t0
    for c in ex:
        verify_copy(c, adj)
    res = sat_engine(n, edges, outdir, **kw)
    if res["status"] == "timeout":
        return copies, nrh, tA, res
    a_pos = copies > 0
    b_pos = res["status"] == "SAT"
    assert a_pos == b_pos, f"!! 兩引擎唔一致: 枚舉 {copies} 隻, SAT 話 {res['status']} —— 有 bug, 停"
    return copies, nrh, tA, res

def _expect_reject(label, fn):
    try:
        fn()
    except AssertionError as e:
        print(f"    毒藥「{label}」被拒 ✓  ({str(e).splitlines()[0][:80]})")
        return
    raise AssertionError(f"!! 毒藥「{label}」竟然通過")

def selftest(work):
    os.makedirs(work, exist_ok=True)
    print("== 1. Moser spindle 本身 (7 點 11 邊) ==")
    n, e = moser_spindle_edges()
    for sb in (True, False):
        copies, nrh, tA, res = both(n, e, os.path.join(work, f"moser_sb{int(sb)}"), symbreak=sb)
        assert copies == 1, f"Moser spindle 應該啱啱 1 隻, 得 {copies}"
        assert res["status"] == "SAT"
        print(f"    引擎 A: {copies} 隻 (菱形 {nrh} 個); 引擎 B: SAT, 映射 {dict(zip(PATTERN_NAMES, res['copy']))}, "
              f"11 條邊逐條覆核 ✓ (symbreak={sb}, {res['solve_s']}s)")
    print("== 2. 三角格仔 patch 8×8 (單位邊, 有菱形但無 spindle) ==")
    n, e = triangular_patch(8)
    for sb in (True, False):
        copies, nrh, tA, res = both(n, e, os.path.join(work, f"tri_sb{int(sb)}"), symbreak=sb)
        assert copies == 0 and res["status"] == "UNSAT" and res["verified"]
        print(f"    {n} 點 {len(e)} 邊: 引擎 A: 0 隻 (菱形 {nrh} 個); 引擎 B: UNSAT + drat-trim VERIFIED "
              f"({res['drat_lines']} 行, solve {res['solve_s']}s, symbreak={sb}) ✓")
    print("== 3. 紀錄世系 G510 / G553 (M 型, 靠 spindle 起家) ==")
    for g in ("510", "553"):
        n, e = load_edges(os.path.expanduser(f"~/hadwiger/CNP-SAT/edge/{g}.edge"))
        copies, nrh, tA, res = both(n, e, os.path.join(work, f"g{g}"))
        assert copies > 0 and res["status"] == "SAT"
        print(f"    G{g}: 引擎 A: {copies} 隻 spindle (菱形 {nrh} 個, {tA:.2f}s); "
              f"引擎 B: SAT {res['solve_s']}s, 映射 {dict(zip(PATTERN_NAMES, res['copy']))} 逐邊覆核 ✓")
    print("== 4. 負面對照 ==")
    n, e = moser_spindle_edges()
    e_notip = [x for x in e if x != (4, 7)]
    copies, nrh, tA, res = both(n, e_notip, os.path.join(work, "notip"))
    assert copies == 0 and res["status"] == "UNSAT" and res["verified"]
    print(f"    spindle 減 tip 邊 d1d2 (7 點 10 邊): A=0, B=UNSAT VERIFIED ✓")
    # 退化 spindle: 兩個菱形共用 hub 兼共用 b (6 點): a=1, b=2 共用, c1=3,d1=4, c2=5,d2=6, tip 4-6
    e_deg = [(1, 2), (1, 3), (2, 3), (2, 4), (3, 4), (1, 5), (2, 5), (2, 6), (5, 6), (4, 6)]
    copies, nrh, tA, res = both(6, e_deg, os.path.join(work, "degenerate"))
    assert copies == 0 and res["status"] == "UNSAT" and res["verified"]
    print(f"    退化 spindle (兩菱形共用 hub + 一個底點, 6 點 10 邊): A=0, B=UNSAT VERIFIED ✓ (injectivity 有效)")
    print("== 4b. 審核員補充 (盲點) ==")
    # (a) 反轉標籤嘅 spindle: 對稱破除必須仍然 SAT (否則 symbreak 唔 sound)
    n, e = moser_spindle_edges()
    for name, perm in (("reversed", list(range(7, 0, -1))), ("shuffled", [4, 7, 1, 6, 2, 5, 3])):
        e2 = [(perm[u - 1], perm[v - 1]) for u, v in e]
        copies, nrh, tA, res = both(7, e2, os.path.join(work, f"perm_{name}"), symbreak=True)
        assert copies == 1 and res["status"] == "SAT"
        print(f"    {name} 標籤 spindle: A=1, B=SAT (symbreak=True) ✓ 映射 {res['copy']}")
    # (b) 暴力計數對數: 所有 7 點 injective 映射 / |Aut| = 8, 同引擎 A 對數 (細圖 + G510 hub-anchored)
    def brute(n, edges):
        adj = adjacency(n, edges)
        cnt = 0
        verts = list(range(1, n + 1))
        for hub in verts:
            nb = sorted(adj[hub])
            for b1 in nb:
                for c1 in nb:
                    if c1 == b1 or c1 not in adj[b1]:
                        continue
                    for d1 in adj[b1] & adj[c1]:
                        if d1 == hub:
                            continue
                        for b2 in nb:
                            for c2 in nb:
                                if c2 == b2 or c2 not in adj[b2]:
                                    continue
                                for d2 in adj[b2] & adj[c2]:
                                    if d2 == hub or d2 not in adj[d1]:
                                        continue
                                    if len({hub, b1, c1, d1, b2, c2, d2}) == 7:
                                        cnt += 1
        return cnt // 8            # (b1,c1) 序 ×2, (b2,c2) 序 ×2, 兩菱形互換 ×2
    rng = random.Random(7)
    for trial in range(30):
        nn = rng.randint(7, 14)
        ee = [(u, v) for u in range(1, nn + 1) for v in range(u + 1, nn + 1) if rng.random() < 0.55]
        if not ee:
            continue
        a_cnt = enumerate_spindles(nn, ee)[0]
        b_cnt = brute(nn, ee)
        assert a_cnt == b_cnt, f"隨機圖 {trial}: 引擎 A {a_cnt} vs 暴力 {b_cnt}"
    n510, e510 = load_edges(os.path.expanduser("~/hadwiger/CNP-SAT/edge/510.edge"))
    a_cnt, b_cnt = enumerate_spindles(n510, e510)[0], brute(n510, e510)
    assert a_cnt == b_cnt
    print(f"    暴力計數 (injective 映射 / 8): 30 個隨機圖 + G510 ({b_cnt}) 同引擎 A 完全一致 ✓")
    # (c) DRAT 損毀 → drat-trim 必須話唔 VERIFIED (sat_engine 內部 assert 要死)
    n, e = triangular_patch(5)
    res = sat_engine(n, e, os.path.join(work, "drat_poison"))
    assert res["status"] == "UNSAT"
    drat = res["drat"]
    lines = open(drat).read().splitlines()
    open(drat, "w").write("\n".join(lines[: len(lines) // 2]) + "\n")
    dr = subprocess.run([DRATTRIM, res["cnf"], drat], capture_output=True, text=True, timeout=DRATTRIM_TIMEOUT)
    assert "s VERIFIED" not in dr.stdout, "!! 斬半嘅 DRAT 竟然 VERIFIED"
    print(f"    毒藥「DRAT 斬半」: drat-trim 話 {'s NOT VERIFIED' if 's NOT VERIFIED' in dr.stdout else '唔 VERIFIED'} ✓")
    # (d) cadical 第二把刀
    copies, nrh, tA, res = both(n, e, os.path.join(work, "tri_cadical"), solver="cadical")
    assert res["status"] == "UNSAT" and res["verified"]
    n, e = moser_spindle_edges()
    copies, nrh, tA, res = both(n, e, os.path.join(work, "moser_cadical"), solver="cadical")
    assert res["status"] == "SAT"
    print(f"    cadical: 三角格仔 UNSAT+VERIFIED ✓, spindle SAT+覆核 ✓")
    # (e) python -O
    r = subprocess.run([sys.executable, "-O", os.path.abspath(__file__), "enumerate",
                        os.path.expanduser("~/hadwiger/CNP-SAT/edge/510.edge")], capture_output=True, text=True)
    assert r.returncode != 0 and "唔准用 python -O" in (r.stdout + r.stderr)
    print("    毒藥「python -O」被拒 ✓")
    print("== 5. 毒藥 ==")
    p = os.path.join(work, "poison.edge")
    open(p, "w").write("p edge 7 1\ne 3 3\n")
    _expect_reject("self-loop 邊表", lambda: load_edges(p))
    open(p, "w").write("p edge 7 0\n")
    _expect_reject("空邊表", lambda: load_edges(p))
    adj = adjacency(7, moser_spindle_edges()[1])
    _expect_reject("假 copy (頂點重複)", lambda: verify_copy((1, 2, 3, 4, 2, 6, 7), adj))
    adj_notip = adjacency(7, e_notip)
    _expect_reject("假 copy (7 點相異但 tip 邊唔存在)", lambda: verify_copy((1, 2, 3, 4, 5, 6, 7), adj_notip))
    _expect_reject("假 copy (hub 錯)", lambda: verify_copy((4, 2, 3, 1, 5, 6, 7), adj))
    print("== selftest 全部通過 ✓ ==")

# ============================================================

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("enumerate", "sat", "both"):
        s = sub.add_parser(name)
        s.add_argument("edge")
        if name != "enumerate":
            s.add_argument("--out", required=True)
            s.add_argument("--solver", default="kissat", choices=["kissat", "cadical"])
            s.add_argument("--timeout", type=float, default=1800)
            s.add_argument("--no-symbreak", action="store_true")
    s = sub.add_parser("selftest")
    s.add_argument("--work", default=os.path.expanduser("~/hadwiger/phase2/out/spindle_selftest"))
    a = ap.parse_args()
    if a.cmd == "selftest":
        selftest(a.work)
        return
    n, edges = load_edges(a.edge)
    adj = adjacency(n, edges)
    if a.cmd in ("enumerate", "both"):
        t0 = time.time()
        copies, nrh, ex = enumerate_spindles(n, edges, adj, want_list=3)
        for c in ex:
            verify_copy(c, adj)
        print(f"[A 枚舉] {n} 點 {len(edges)} 邊: 菱形 {nrh} 個, Moser spindle copies = {copies} "
              f"({time.time() - t0:.2f}s)" + (f"; 例子 {ex[0]}" if ex else ""))
    if a.cmd in ("sat", "both"):
        res = sat_engine(n, edges, os.path.expanduser(a.out), a.solver, a.timeout, not a.no_symbreak)
        m = res["meta"]
        print(f"[B SAT] CNF {m['nvars']} 變量 / {m['clauses']} 子句 (symbreak={m['symbreak']})")
        if res["status"] == "UNSAT":
            print(f"[B SAT] {a.solver} UNSAT {res['solve_s']}s; DRAT {res['drat_lines']} 行; "
                  f"drat-trim {'s VERIFIED ✓' if res['verified'] else 'FAILED'} ({res['drattrim_s']}s)")
            print(f"[B SAT] 證書: {res['cnf']} + {res['drat']}")
        elif res["status"] == "SAT":
            print(f"[B SAT] {a.solver} SAT {res['solve_s']}s; copy = {dict(zip(PATTERN_NAMES, res['copy']))} (11 條邊逐條覆核 ✓)")
        else:
            print(f"[B SAT] TIMEOUT ({a.timeout}s) —— 冇證書")
            sys.exit(3)
        if a.cmd == "both" and res["status"] != "timeout":
            assert (copies > 0) == (res["status"] == "SAT"), "!! 兩引擎唔一致"
            print(f"[對數] 引擎 A ({copies} 隻) 同引擎 B ({res['status']}) 一致 ✓")

if __name__ == "__main__":
    main()
