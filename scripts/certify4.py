#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
certify4.py —— k 色認證 (UNSAT: solver + drat-trim VERIFIED; SAT: 逐邊覆核染色)

用法:
  python3 certify4.py <edge> --out DIR [--k 4] [--tag NAME] [--solver kissat|cadical] [--timeout 1800]
                      [--same-AB <cvtx>]      # 用精確坐標喺 cvtx 入面對認 A=(0,0), B=(0,√3), 加「同色」子句
                      [--same U V]            # (備用) 直接俾 1-based 索引
                      [--no-symbreak] [--expect unsat|sat] [--progress 60]
編碼 (同 Phase 1 shrink.py): var(v,c) = (v-1)*k + c, 每點至少一色, 每邊每色唔可以同時, 對稱破除: 第一個三角形釘 1,2,3。
「A,B 同色」= 每色 c: (¬x_{A,c} ∨ x_{B,c}) ∧ (x_{A,c} ∨ ¬x_{B,c})。
輸出: DIR/<tag>.cnf, .drat (UNSAT), .col (SAT), .json (摘要), 進度打落 stdout。
"""
import sys, os, time, argparse, subprocess, json, threading

if not __debug__:
    sys.exit("!! 唔准用 python -O")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from exactfield import load_edges, read_cvtx

KISSAT   = os.path.expanduser("~/hadwiger/kissat/build/kissat")
CADICAL  = os.path.expanduser("~/hadwiger/cadical/build/cadical")
DRATTRIM = os.path.expanduser("~/hadwiger/drat-trim/drat-trim")
DRATTRIM_TIMEOUT = 6 * 3600

def find_triangle(n, edges):
    adj = [set() for _ in range(n + 1)]
    for u, v in edges:
        adj[u].add(v); adj[v].add(u)
    for u, v in edges:
        c = adj[u] & adj[v]
        if c:
            return (u, v, min(c))
    return None

def build(n, edges, k, same=None, symbreak=True):
    var = lambda v, c: (v - 1) * k + c          # c = 1..k
    cl = [[var(v, c) for c in range(1, k + 1)] for v in range(1, n + 1)]
    for u, v in edges:
        for c in range(1, k + 1):
            cl.append([-var(u, c), -var(v, c)])
    tri = find_triangle(n, edges) if symbreak and k >= 3 else None
    if tri:
        for i, v in enumerate(tri):
            cl.append([var(v, i + 1)])
    if same:
        U, V = same
        for c in range(1, k + 1):
            cl.append([-var(U, c), var(V, c)])
            cl.append([var(U, c), -var(V, c)])
    return cl, n * k, tri

def locate_AB(cvtx):
    F, pts = read_cvtx(cvtx)
    A = F.zero()
    B = F.i_unit() * F.sqrt_int(3)
    ia = [i + 1 for i, z in enumerate(pts) if z == A]
    ib = [i + 1 for i, z in enumerate(pts) if z == B]
    assert len(ia) == 1 and len(ib) == 1, f"A/B 對認唔到或者唔唯一: {ia} {ib}"
    return ia[0], ib[0]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edge"); ap.add_argument("--out", required=True)
    ap.add_argument("--k", type=int, default=4); ap.add_argument("--tag", default=None)
    ap.add_argument("--solver", default="kissat", choices=["kissat", "cadical"])
    ap.add_argument("--timeout", type=float, default=1800)
    ap.add_argument("--same-AB", default=None); ap.add_argument("--same", nargs=2, type=int, default=None)
    ap.add_argument("--no-symbreak", action="store_true")
    ap.add_argument("--expect", choices=["unsat", "sat"], default=None)
    ap.add_argument("--progress", type=float, default=60)
    a = ap.parse_args()
    out = os.path.expanduser(a.out); os.makedirs(out, exist_ok=True)
    tag = a.tag or (os.path.basename(a.edge).replace(".edge", "") + f"-{a.k}" + ("-sameAB" if (a.same_AB or a.same) else ""))
    n, edges = load_edges(a.edge)
    same = None
    if a.same_AB:
        same = locate_AB(a.same_AB)
        print(f"[{tag}] 精確對認: A=(0,0) 係頂點 #{same[0]}, B=(0,√3) 係頂點 #{same[1]} (由 {os.path.basename(a.same_AB)})", flush=True)
    elif a.same:
        same = tuple(a.same)
    cl, nvars, tri = build(n, edges, a.k, same, not a.no_symbreak)
    cnf = os.path.join(out, tag + ".cnf"); drat = os.path.join(out, tag + ".drat")
    with open(cnf, "w") as f:
        f.write(f"p cnf {nvars} {len(cl)}\n")
        for c in cl:
            f.write(" ".join(map(str, c)) + " 0\n")
    print(f"[{tag}] {n} 點 {len(edges)} 邊, k={a.k}: CNF {nvars} 變量 {len(cl)} 子句, 三角形釘色 {tri}, "
          f"同色對 {same}; solver={a.solver}, timeout={a.timeout:.0f}s", flush=True)
    exe = KISSAT if a.solver == "kissat" else CADICAL
    t0 = time.time()
    proc = subprocess.Popen([exe, "-q", "--no-binary", cnf, drat], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stop = threading.Event()
    def ticker():
        while not stop.wait(a.progress):
            sz = os.path.getsize(drat) if os.path.exists(drat) else 0
            print(f"[{tag}]   ... 仲跑緊 {time.time() - t0:.0f}s, DRAT 暫時 {sz / 1e6:.1f} MB, load {os.getloadavg()[0]:.1f}", flush=True)
    th = threading.Thread(target=ticker, daemon=True); th.start()
    try:
        so, se = proc.communicate(timeout=a.timeout)
    except subprocess.TimeoutExpired:
        proc.kill(); stop.set()
        print(f"[{tag}] !! TIMEOUT {a.timeout:.0f}s —— 冇證書, 唔算數", flush=True)
        json.dump({"tag": tag, "status": "timeout", "timeout": a.timeout}, open(os.path.join(out, tag + ".json"), "w"))
        sys.exit(3)
    stop.set()
    dt = time.time() - t0
    rc = proc.returncode
    summ = {"tag": tag, "n": n, "m": len(edges), "k": a.k, "same": same, "tri": tri, "solver": a.solver,
            "nvars": nvars, "clauses": len(cl), "solve_s": round(dt, 2)}
    if rc == 20:
        t1 = time.time()
        dr = subprocess.run([DRATTRIM, cnf, drat], capture_output=True, text=True, timeout=DRATTRIM_TIMEOUT)
        ok = any(l.strip() == "s VERIFIED" for l in dr.stdout.splitlines())
        lines = sum(1 for _ in open(drat, errors="ignore"))
        summ.update({"status": "UNSAT", "verified": ok, "drat_lines": lines, "drat_bytes": os.path.getsize(drat),
                     "drattrim_s": round(time.time() - t1, 1)})
        print(f"[{tag}] {a.solver} UNSAT ({dt:.1f}s); DRAT {lines} 行 / {os.path.getsize(drat) / 1e6:.1f} MB; "
              f"drat-trim {'s VERIFIED ✓' if ok else '!! 冇 VERIFIED'} ({summ['drattrim_s']}s)", flush=True)
        if not ok:
            print(dr.stdout[-800:]); sys.exit(2)
        if a.expect == "sat":
            print(f"[{tag}] !! 預期 SAT 但係 UNSAT"); sys.exit(4)
    elif rc == 10:
        model = set()
        for line in so.splitlines():
            if line.startswith("v"):
                model.update(int(t) for t in line.split()[1:] if int(t) > 0)
        col = {}
        for v in range(1, n + 1):
            cs = [c for c in range(1, a.k + 1) if ((v - 1) * a.k + c) in model]
            assert len(cs) >= 1, f"頂點 {v} 冇色"
            col[v] = cs[0]                       # 多過一色嘅話揀第一個 (仍然合法: 每條邊都會覆核)
        bad = [(u, v) for u, v in edges if col[u] == col[v]]
        assert not bad, f"!! 染色覆核失敗: {len(bad)} 條邊同色, 例如 {bad[:5]}"
        if same:
            assert col[same[0]] == col[same[1]], "同色約束冇滿足?"
        with open(os.path.join(out, tag + ".col"), "w") as f:
            for v in range(1, n + 1):
                f.write(f"{v} {col[v]}\n")
        used = sorted(set(col.values()))
        summ.update({"status": "SAT", "colours_used": used, "edges_checked": len(edges)})
        print(f"[{tag}] {a.solver} SAT ({dt:.1f}s); {a.k} 色染色 {len(edges)}/{len(edges)} 條邊逐條覆核異色 ✓ "
              f"(實際用咗 {len(used)} 色) → {tag}.col", flush=True)
        if os.path.exists(drat):
            os.remove(drat)
        if a.expect == "unsat":
            print(f"[{tag}] !! 預期 UNSAT 但係 SAT"); sys.exit(4)
    else:
        print(f"[{tag}] !! solver rc={rc}: {(se or so)[-500:]}"); sys.exit(5)
    json.dump(summ, open(os.path.join(out, tag + ".json"), "w"), indent=1)

if __name__ == "__main__":
    main()
