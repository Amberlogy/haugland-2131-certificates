#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
l3g2.py —— 剪走 G₂ 頂點集 S 之後嘅 G₃′ = G₂′ ∪ ρ(G₂′): 重組 + 機器核對 (秒級)
  (1) 精確坐標 + 完整性: G2p.{cvtx,edge} (Q(ζ84)), G3p.{cvtx,edge} (Q(ζ420), G₃ 誘導子圖, 重新編號) 經 exactfield.py check --complete
  (2) L2″: identity 同 ρ 都將 V(G₂′) 精確映入 V(G₃′) (injective), E(G₂′) 每條邊映落 E(G₃′) (精確分圓代數重算 ρ, 唔靠索引表); G₃′ = G₂′ ∪ ρ(G₂′), |G₃′| = 2|G₂′| − 1
  (3) L3″: G₃′ 4 色 CNF + 引理子句 col(u)=col(v) 同 col(u)=col(ρv) (每色 c 雙向蘊含, 16 條) → kissat UNSAT → drat-trim s VERIFIED
  (4) spindle-free: 由 G₃ 遺傳 (subgraph), 但引擎 A (枚舉) 照跑一次記 copies=0; --engine-b 再加 SAT 引擎 (UNSAT + drat-trim)
  L1″ (G₂−S mono-pair, cnc2 戰役證書) + L2″ + L3″ ⇒ G₃′ 冇 4 色染色.
用法: python3 l3g2.py (--remove 1,2,3 | --batches batches_g2.json --round r) --out DIR [--engine-b] [--timeout 1800]
      python3 l3g2.py --selftest --out DIR   # S=∅ 全過 (G₃′ == G₃); 毒藥 drop-cross-edges → 完整性 FAIL + L3″ SAT; drop-v-rho-v → 完整性 FAIL; bad-edge → 完整性 FAIL; S∋u 被拒
      [--poison none|drop-cross-edges|drop-v-rho-v|bad-edge] (內部用)
輸出: DIR/G2p.{cvtx,edge} G3p.{cvtx,edge} L3pp.{cnf,drat,json} maps.json summary.json
"""
import sys, os, json, time, argparse, subprocess
if not __debug__:
    sys.exit("!! 唔准用 python -O")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from g2common import G2, G3, write_cvtx, write_edge, sha, KISSAT, DRATTRIM, PH2, K
import certify4
sys.path.insert(0, PH2)
import spindlefind

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--remove", default=None); ap.add_argument("--batches", default=None); ap.add_argument("--round", type=int, default=None)
    ap.add_argument("--out", required=True); ap.add_argument("--poison", default="none", choices=["none", "drop-cross-edges", "drop-v-rho-v", "bad-edge"])
    ap.add_argument("--selftest", action="store_true"); ap.add_argument("--timeout", type=float, default=1800); ap.add_argument("--engine-b", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest(a)
    out = a.out; os.makedirs(out, exist_ok=True); T0 = time.time()
    g2 = G2(); g3 = G3(g2)
    if a.remove is not None:
        S = sorted({int(x) for x in a.remove.split(",") if x.strip()})
    elif a.batches:
        bj = json.load(open(a.batches)); S = sorted({w for b in bj["batches"][:a.round] for w in b})
    else:
        S = []
    S = set(S); assert g2.u not in S and g2.v not in S, "!! S 含 u 或 v"
    badS = sorted(w for w in S if not (isinstance(w, int) and 1 <= w <= g2.n))
    assert not badS, "!! S 有越界/非整數索引: %s" % badS                    # 審查 finding: --remove 1067 之類唔可以靜靜變 no-op
    u, v, b = g2.u, g2.v, g2.b
    V2p = [w for w in range(1, g2.n + 1) if w not in S]; new2 = {w: i + 1 for i, w in enumerate(V2p)}
    assert len(V2p) == g2.n - len(S), "S 冇全部剪走 (|V2p|=%d, n−|S|=%d)" % (len(V2p), g2.n - len(S))
    V3p = sorted(set(V2p) | {g3.rho_idx[w] for w in V2p}); new3 = {w: i + 1 for i, w in enumerate(V3p)}
    assert len(V3p) == 2 * len(V2p) - 1, "|G₃′| != 2|G₂′| − 1"
    E2p = sorted((min(new2[x], new2[y]), max(new2[x], new2[y])) for x, y in g2.E if x not in S and y not in S)
    E3p = sorted((min(new3[x], new3[y]), max(new3[x], new3[y])) for x, y in g3.E if x in new3 and y in new3)
    poison_note = None
    if a.poison == "drop-cross-edges":
        ces = {tuple(sorted((new3[x], new3[y]))) for x, y in g3.cross if x in new3 and y in new3}
        assert len(ces) == 2, "兩條交叉邊唔齊喺 G₃′: %s" % ces
        E3p = [e for e in E3p if tuple(e) not in ces]; poison_note = "removed both cross edges %s from G3p.edge" % sorted(ces)
    elif a.poison == "drop-v-rho-v":
        ce = tuple(sorted((new3[v], new3[g3.rho_idx[v]])))
        assert ce in set(E3p); E3p = [e for e in E3p if tuple(e) != ce]; poison_note = "removed the spindle edge (1,0)–ρ(1,0) = %s from G3p.edge" % (ce,)
    elif a.poison == "bad-edge":
        Eset = {frozenset(e) for e in E3p}
        x = next(x for x in range(2, len(V3p) + 1) if frozenset((1, x)) not in Eset)
        E3p = sorted(E3p + [(1, x)]); poison_note = "added fake edge (1,%d) to G3p.edge" % x
    write_cvtx(os.path.join(out, "G2p.cvtx"), g2.F, [g2.P[w - 1] for w in V2p]); write_edge(os.path.join(out, "G2p.edge"), len(V2p), E2p)
    write_cvtx(os.path.join(out, "G3p.cvtx"), g3.F, [g3.P[w - 1] for w in V3p]); write_edge(os.path.join(out, "G3p.edge"), len(V3p), E3p)
    print("[G3″] S = %d 粒 G₂ 頂點刪走 → G₂′ %d 點 %d 邊; G₃′ = G₂′ ∪ ρ(G₂′) %d 點 %d 邊 (G₃ 少咗 %d 點 %d 邊)%s" % (
        len(S), len(V2p), len(E2p), len(V3p), len(E3p), g3.n - len(V3p), len(g3.E) - len(E3p), (" [POISON: %s]" % poison_note) if poison_note else ""), flush=True)
    res = {"removed": sorted(S), "n_removed": len(S), "G2p": {"n": len(V2p), "m": len(E2p)}, "G3p": {"n": len(V3p), "m": len(E3p)}, "poison": poison_note,
           "inputs_sha": {**g2.sha, **g3.sha}, "sha": {f: sha(os.path.join(out, f)) for f in ("G2p.cvtx", "G2p.edge", "G3p.cvtx", "G3p.edge")}}
    ok_all = True
    # (1) 完整性
    for g in ("G2p", "G3p"):
        r = subprocess.run([sys.executable, os.path.join(PH2, "exactfield.py"), "check", os.path.join(out, g + ".cvtx"), os.path.join(out, g + ".edge"), "--complete"],
                           capture_output=True, text=True, timeout=3600)
        last = (r.stdout.strip().split("\n")[-1] if r.stdout.strip() else "") + (("" if r.returncode == 0 else " | " + r.stderr.strip().split("\n")[-1][:200]))
        res["complete_" + g] = {"rc": r.returncode, "last": last[:300]}; ok_all &= r.returncode == 0
        print("[complete %s] %s %s" % (g, "✓" if r.returncode == 0 else "!! FAIL", last[:220]), flush=True)
    # (2) L2″: identity + ρ (ρ 精確重算, 唔靠 rho_idx)
    E3pset = {frozenset(e) for e in E3p}; F = g3.F
    idm = {w: new3[w] for w in V2p}
    rhom = {}
    for w in V2p:
        z = F.embed(g2.P[w - 1]); r = g3.rho(z); j = g3.idx.get((r.num, r.den))
        assert j is not None and j in new3, "ρ(G₂′ #%d) 唔喺 V(G₃′)" % w
        assert g3.P[w - 1] == z, "identity 嵌入: G₂ #%d 同 G₃ #%d 坐標唔同" % (w, w)     # 真正嘅 identity 檢查 (審查前係 no-op)
        rhom[w] = new3[j]
    assert len(set(idm.values())) == len(V2p) and len(set(rhom.values())) == len(V2p), "L2″ 映射唔 injective"
    assert set(idm.values()) | set(rhom.values()) == set(range(1, len(V3p) + 1)), "G₂′ ∪ ρ(G₂′) != V(G₃′)"
    assert set(idm.values()) & set(rhom.values()) == {new3[u]}, "G₂′ ∩ ρ(G₂′) 唔係只有 u"
    bad_id = [(x, y) for x, y in g2.E if x not in S and y not in S and frozenset((idm[x], idm[y])) not in E3pset]
    bad_rho = [(x, y) for x, y in g2.E if x not in S and y not in S and frozenset((rhom[x], rhom[y])) not in E3pset]
    up, vp, rvp, bp, rbp = new3[u], new3[v], rhom[v], new3[b] if b in new3 else None, rhom.get(b)
    spindle_edge = frozenset((vp, rvp)) in E3pset
    res["L2"] = {"u": up, "v": vp, "rho_v": rvp, "b_sqrt3": bp, "rho_b": rbp, "identity_edges_missing": len(bad_id), "rho_edges_missing": len(bad_rho),
                 "edges_checked_per_map": len(E2p), "spindle_edge_v_rhov_present": spindle_edge, "note": "G3' 1-based indices"}
    ok_all &= (not bad_id and not bad_rho and (spindle_edge or a.poison in ("drop-v-rho-v", "drop-cross-edges")))
    print("[L2″] identity: V(G₂′) ⊂ V(G₃′) (%d 點 injective) ✓, E(G₂′) %d/%d 映落 E(G₃′) %s; ρ: %d 點 injective ✓, E(G₂′) %d/%d 映落 E(G₃′) %s; u′=#%d v′=#%d ρ(v)′=#%d; 邊 v′–ρ(v)′ %s" % (
        len(V2p), len(E2p) - len(bad_id), len(E2p), "✓" if not bad_id else "!! 缺 %d" % len(bad_id), len(V2p), len(E2p) - len(bad_rho), len(E2p),
        "✓" if not bad_rho else "!! 缺 %d" % len(bad_rho), up, vp, rvp, "✓" if spindle_edge else "!! 唔存在"), flush=True)
    json.dump({"identity": idm, "rho": rhom, "u": up, "v": vp, "rho_v": rvp}, open(os.path.join(out, "maps.json"), "w"))
    # (3) L3″
    n = len(V3p); var = lambda w, c: (w - 1) * K + c
    cl = [[var(w, c) for c in range(1, K + 1)] for w in range(1, n + 1)]
    for x, y in E3p:
        for c in range(1, K + 1):
            cl.append([-var(x, c), -var(y, c)])
    tri = certify4.find_triangle(n, E3p)
    for i, w in enumerate(tri):
        cl.append([var(w, i + 1)])
    nlem = 0
    for (p, q) in ((up, vp), (up, rvp)):
        for c in range(1, K + 1):
            cl.append([-var(p, c), var(q, c)]); cl.append([var(p, c), -var(q, c)]); nlem += 2
    cnf = os.path.join(out, "L3pp.cnf"); drat = os.path.join(out, "L3pp.drat")
    with open(cnf, "w") as f:
        f.write("p cnf %d %d\n" % (n * K, len(cl)))
        for c in cl:
            f.write(" ".join(map(str, c)) + " 0\n")
    t0 = time.time()
    try:
        r = subprocess.run([KISSAT, "-q", "--no-binary", "--time=%d" % int(a.timeout), cnf, drat], capture_output=True, text=True, timeout=a.timeout + 120)
        rc = r.returncode
    except subprocess.TimeoutExpired:
        rc = -999; r = None
    dt = time.time() - t0
    l3 = {"nvars": n * K, "clauses": len(cl), "tri": list(tri), "lemma_clauses": nlem, "lemmas": "col(u)=col(v), col(u)=col(rho v) (bi-implication per colour)", "rc": rc, "solve_s": round(dt, 2)}
    if rc == 20:
        dr = subprocess.run([DRATTRIM, cnf, drat], capture_output=True, text=True, timeout=6 * 3600)
        ok = any(l.strip() == "s VERIFIED" for l in dr.stdout.splitlines())
        lines = sum(1 for _ in open(drat, errors="ignore"))
        l3.update({"status": "UNSAT", "verified": ok, "drat_lines": lines, "drat_bytes": os.path.getsize(drat), "sha": {"L3pp.cnf": sha(cnf), "L3pp.drat": sha(drat)}})
        ok_all &= ok
        print("[L3″] G₃′ 4 色 CNF + %d 引理 (%d 變量 %d 子句, 釘 %s): kissat UNSAT %.2fs; DRAT %d 行; drat-trim %s" % (nlem, n * K, len(cl), tri, dt, lines, "s VERIFIED ✓" if ok else "!! NOT VERIFIED"), flush=True)
    elif rc == 10:
        model = {int(t) for line in r.stdout.splitlines() if line.startswith("v") for t in line.split()[1:] if int(t) > 0}
        col = {w: next(c for c in range(1, K + 1) if var(w, c) in model) for w in range(1, n + 1)}
        badE = [(x, y) for x, y in E3p if col[x] == col[y]]
        l3.update({"status": "SAT", "verified": False, "colouring_checked": not badE, "colouring_bad_edges": len(badE), "col_u": col[up], "col_v": col[vp], "col_rho_v": col[rvp]}); ok_all = False
        print("[L3″] !! kissat SAT %.2fs —— G₃′ + 引理有 4 色染色 (逐邊覆核: %s; col u/v/ρv = %d/%d/%d); 拼合唔成立" % (dt, "全部異色" if not badE else "%d 條同色" % len(badE), col[up], col[vp], col[rvp]), flush=True)
        if os.path.exists(drat):
            os.remove(drat)
    else:
        l3.update({"status": "rc=%d (timeout/other)" % rc, "verified": False}); ok_all = False
        print("[L3″] !! kissat rc=%d (%.1fs)" % (rc, dt), flush=True)
        if os.path.exists(drat):
            os.remove(drat)
    json.dump(l3, open(os.path.join(out, "L3pp.json"), "w"), indent=1)
    # (4) spindle-free 引擎 A
    t0 = time.time()
    copies, nrh, _ = spindlefind.enumerate_spindles(n, E3p)
    res["spindle_A"] = {"copies": copies, "rhombi": nrh, "t_s": round(time.time() - t0, 2)}; ok_all &= copies == 0
    print("[spindle A] G₃′ %d 點 %d 邊: 菱形 %d 個, Moser spindle copies = %d %s (%.2fs; 由 G₃ 遺傳, 照跑記錄)" % (n, len(E3p), nrh, copies, "✓" if copies == 0 else "!!", res["spindle_A"]["t_s"]), flush=True)
    if a.engine_b:
        t0 = time.time()
        rb = subprocess.run([sys.executable, os.path.join(PH2, "spindlefind.py"), "both", os.path.join(out, "G3p.edge"), "--out", os.path.join(out, "spindle_B"), "--timeout", "3600"],
                            capture_output=True, text=True, timeout=4 * 3600)
        open(os.path.join(out, "spindle_B.log"), "w").write(rb.stdout + rb.stderr)
        okb = rb.returncode == 0 and "UNSAT" in rb.stdout and "VERIFIED" in rb.stdout and "一致" in rb.stdout
        res["spindle_B"] = {"rc": rb.returncode, "ok": okb, "t_s": round(time.time() - t0, 1), "lines": [l for l in rb.stdout.splitlines() if l.startswith("[")][-4:]}
        ok_all &= okb
        print("[spindle B] spindlefind both: rc=%d %s\n   %s" % (rb.returncode, "✓" if okb else "!!", "\n   ".join(res["spindle_B"]["lines"])), flush=True)
    res["L3"] = l3; res["all_ok"] = ok_all; res["t_s"] = round(time.time() - T0, 1)
    json.dump(res, open(os.path.join(out, "summary.json"), "w"), indent=1, ensure_ascii=False)
    print("[l3g2] %s: G₂′ %d 點, G₃′ %d 點 %d 邊; 完整性 %s/%s, L2″ %s, L3″ %s, spindle A copies=%d (%.1fs)" % (
        "全部通過 ✓" if ok_all else "!! 有步驟失敗", len(V2p), n, len(E3p), "✓" if res["complete_G2p"]["rc"] == 0 else "FAIL", "✓" if res["complete_G3p"]["rc"] == 0 else "FAIL",
        "✓" if (not bad_id and not bad_rho) else "FAIL", ("UNSAT VERIFIED ✓" if l3.get("verified") else l3.get("status")), copies, res["t_s"]), flush=True)
    sys.exit(0 if ok_all else 4)

def selftest(a):
    base = [sys.executable, os.path.abspath(__file__)]
    def run(args):
        r = subprocess.run(base + args, capture_output=True, text=True, timeout=3 * 3600); return r
    # 1. S=∅: G₃′ == G₃ 全部通過
    r = run(["--out", os.path.join(a.out, "st_none")])
    assert r.returncode == 0 and "全部通過" in r.stdout and "G₃′ = G₂′ ∪ ρ(G₂′) 2131 點 12530 邊" in r.stdout, "selftest S=∅ 應該通過:\n" + r.stdout[-1500:] + r.stderr[-800:]
    assert sha(os.path.join(a.out, "st_none", "G3p.edge")) == sha(os.path.join(os.path.expanduser("~/hadwiger/phase2/out/haugland"), "G3.edge")), "S=∅ 嘅 G3p.edge 應該同 G3.edge byte 級一致"
    print("[selftest 1] S=∅: G₃′ == G₃ (edge 檔 byte 級一致), 完整性 ✓ L2″ ✓ L3″ UNSAT VERIFIED ✓ spindle A=0 ✓ (rc 0)")
    # 2. 毒藥 A: 刪兩條交叉邊 → 完整性 FAIL + L3″ SAT (兩個 G₂ copy 只喺 u 黐住, 各自 4 色可染而且 mono-pair)
    r = run(["--out", os.path.join(a.out, "st_cross"), "--poison", "drop-cross-edges", "--timeout", "900"])
    assert r.returncode != 0 and "[complete G3p] !! FAIL" in r.stdout and "[L3″] !! kissat SAT" in r.stdout, "毒藥 drop-cross-edges 冇被捉:\n" + r.stdout[-1500:] + r.stderr[-400:]
    print("[selftest 2] 毒藥 drop-cross-edges: 完整性 FAIL ✓ 而且 L3″ 變 SAT ✓: %s" % [l for l in r.stdout.splitlines() if l.startswith("[L3″]")][0][:150])
    # 3. 毒藥 B: 只刪 (1,0)–ρ(1,0) → 完整性 FAIL (L3″ 結果照記, 唔要求)
    r = run(["--out", os.path.join(a.out, "st_vrv"), "--poison", "drop-v-rho-v", "--timeout", "300"])
    assert r.returncode != 0 and "[complete G3p] !! FAIL" in r.stdout, "毒藥 drop-v-rho-v 冇被捉:\n" + r.stdout[-1500:]
    print("[selftest 3] 毒藥 drop-v-rho-v: 完整性 FAIL ✓; L3″: %s" % [l for l in r.stdout.splitlines() if l.startswith("[L3″]")][0][:150])
    # 4. 毒藥 C: 加假邊 → 完整性 FAIL
    r = run(["--out", os.path.join(a.out, "st_bad"), "--poison", "bad-edge"])
    assert r.returncode != 0 and "[complete G3p] !! FAIL" in r.stdout, "毒藥 bad-edge 冇被捉:\n" + r.stdout[-1500:]
    print("[selftest 4] 毒藥 bad-edge: 完整性 FAIL ✓ → rc %d" % r.returncode)
    # 5. S∋u 被拒
    r = run(["--out", os.path.join(a.out, "st_u"), "--remove", "172"])
    assert r.returncode != 0 and "S 含 u 或 v" in (r.stdout + r.stderr), "S∋u 冇被拒"
    print("[selftest 5] S∋u=(−1,0) 被拒 ✓")
    # 6. 剪一粒普通候選 (Phase 4 SAT 快測第一粒 947) → 全部通過, G₃′ 2129 點
    r = run(["--out", os.path.join(a.out, "st_one"), "--remove", "947"])
    assert r.returncode == 0 and "全部通過" in r.stdout and "2129 點" in r.stdout, "selftest S={947} 應該通過:\n" + r.stdout[-1500:] + r.stderr[-800:]
    print("[selftest 6] S={947}: %s → 全部通過 ✓" % [l for l in r.stdout.splitlines() if l.startswith("[G3″]")][0][:130])
    print("[l3g2 selftest] 全部通過 ✓")

if __name__ == "__main__":
    main()
