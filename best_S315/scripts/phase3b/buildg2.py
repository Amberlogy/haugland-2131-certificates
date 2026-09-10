#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
buildg2.py —— L1″ CNF: G₂ − S 嘅 4 色 (ALO + AMO + 邊, 釘含 u 嘅三角形 (u,p,q)=(1,2,3)) + 反 pair 子句 ∀c (¬x_{u,c} ∨ ¬x_{v,c})
  UNSAT 證書 ⇒ G₂ − S 仍有 mono-pair 性質 (任何 4 色染色 col(u) = col(v)).
  編碼同 phase4/g2recon.py 一字不改: S=∅ 必須同 Phase 4 g2_mono.cnf byte 級一致 (sha 9bfbffbc…).
用法: python3 buildg2.py (--remove 1,2,3 | --batches batches_g2.json --round r) --out DIR [--tag base] [--protected batches_g2.json]
      python3 buildg2.py --selftest --out DIR    # S=∅ sha 對數; 毒藥 S∋u / S∋v / S∩P₂ 必須被拒; 去反 pair 子句 → kissat SAT 且 col(u)=col(v) (重跑一次記錄)
"""
import sys, os, json, argparse, time, subprocess
if not __debug__:
    sys.exit("!! 唔准用 python -O")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from g2common import G2, G3, protected_set, build_cnf, write_cnf, decode_model, verify_colouring, sha, G2_MONO_SHA, G2_PLAIN_SHA, KISSAT, K

def build_and_write(g2, S, out, tag, protected):
    cl, E, tri = build_cnf(g2, S, amo=True, anti=True, protected=protected)
    p = os.path.join(out, tag + ".cnf"); s = write_cnf(p, g2.n * K, cl)
    meta = {"removed": sorted(S), "n_removed": len(S), "u": g2.u, "v": g2.v, "tri": [g2.u, tri[0], tri[1]], "n": g2.n, "n_remaining": g2.n - len(S),
            "n_edges": len(E), "edges_removed": len(g2.E) - len(E), "nvars": g2.n * K, "clauses": len(cl), "cnf_sha256": s,
            "edge_sha256": g2.sha["G2.edge"], "cvtx_sha256": g2.sha["G2.cvtx"],
            "claim": "UNSAT ⇒ G2 minus %d vertices %s still has the mono-pair property col(-1,0) = col(1,0)" % (len(S), sorted(S))}
    json.dump(meta, open(p[:-4] + ".json", "w"), indent=1, ensure_ascii=False)
    return p, meta

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--remove", default=None); ap.add_argument("--batches", default=None); ap.add_argument("--round", type=int, default=None)
    ap.add_argument("--tag", default=None); ap.add_argument("--protected", default=None, help="batches_g2.json (讀 P₂)"); ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    g2 = G2()
    if a.protected:
        P2 = json.load(open(a.protected))["P2"]
    elif a.batches:
        P2 = json.load(open(a.batches))["P2"]
    else:
        P2 = protected_set(g2, G3(g2))[0]
    if a.selftest:
        return selftest(g2, P2, a.out)
    if a.remove is not None:
        S = sorted({int(x) for x in a.remove.split(",") if x.strip()})
    else:
        bj = json.load(open(a.batches)); S = sorted({w for b in bj["batches"][:a.round] for w in b})
    tag = a.tag or ("G2minus_%dv" % len(S))
    p, meta = build_and_write(g2, S, a.out, tag, P2)
    print("[buildg2] S=%d 粒 %s: G₂′ %d 點 %d 邊 (刪 %d 邊), %d 子句, 釘 (%d,%d,%d)=(1,2,3), 反 pair 4 條, sha %s → %s" % (
        len(S), S if len(S) <= 12 else str(S[:6])[:-1] + ", …]", meta["n_remaining"], meta["n_edges"], meta["edges_removed"], meta["clauses"],
        meta["tri"][0], meta["tri"][1], meta["tri"][2], meta["cnf_sha256"][:16], p), flush=True)

def selftest(g2, P2, out):
    t0 = time.time()
    # 1. S=∅ 同 Phase 4 g2_mono.cnf byte 級一致
    p, meta = build_and_write(g2, [], out, "selftest_mono", P2)
    assert meta["clauses"] == 32525 and meta["cnf_sha256"] == G2_MONO_SHA, "S=∅ CNF 同 Phase 4 g2_mono.cnf 唔一致: %d 子句 sha %s" % (meta["clauses"], meta["cnf_sha256"][:16])
    print("[selftest 1] S=∅: %d 子句, sha %s == Phase 4 g2_mono.cnf ✓ (釘 %s)" % (meta["clauses"], meta["cnf_sha256"][:16], meta["tri"]))
    # 2. 毒藥: S∋u, S∋v, S∩P₂ 全部要被拒
    for S, name in (([g2.u], "S∋u=(−1,0)"), ([g2.v], "S∋v=(1,0)"), ([g2.b], "S∋(0,√3) ∈ P₂"), ([g2.o], "S∋(0,0) ∈ P₂")):
        try:
            build_cnf(g2, S, protected=P2); raise SystemExit("!! selftest: 毒藥 %s 冇被拒" % name)
        except AssertionError as e:
            print("[selftest 2] 毒藥 %s 被拒 ✓ (%s)" % (name, str(e)[:60]))
    # 3. 剪一粒普通候選: 子句數 = 32525 − 1 (ALO) − 6 (AMO) − 4·deg
    w = next(x for x in range(1, g2.n + 1) if x not in P2)
    cl, E, tri = build_cnf(g2, [w], protected=P2)
    assert len(cl) == 32525 - 1 - 6 - 4 * g2.deg[w], len(cl)
    print("[selftest 3] S={%d} (deg %d): %d 子句 = 32525 − 7 − 4·%d ✓" % (w, g2.deg[w], len(cl), g2.deg[w]))
    # 4. 去反 pair 子句 → kissat SAT, 染色逐邊覆核, col(u) == col(v) (mono-pair 喺呢個染色成立; 重跑 Phase 4 selftest 一次記錄)
    clp, Ep, trip = build_cnf(g2, [], amo=True, anti=False, protected=P2)
    pp = os.path.join(out, "selftest_plain.cnf"); sp = write_cnf(pp, g2.n * K, clp)
    assert len(clp) == 32521 and sp == G2_PLAIN_SHA, "plain CNF 同 Phase 4 g2_plain.cnf 唔一致"
    t1 = time.time()
    r = subprocess.run([KISSAT, "-q", "--time=600", pp], capture_output=True, text=True, timeout=900)
    dt = time.time() - t1
    assert r.returncode == 10, "!! g2_plain 預期 SAT, 得 rc=%d (%.1fs)" % (r.returncode, dt)
    col = decode_model([int(t) for line in r.stdout.splitlines() if line.startswith("v") for t in line.split()[1:]], g2.n)
    vc = verify_colouring(g2, [], col)
    assert vc["missing"] == 0 and vc["bad_edges"] == 0, vc
    assert vc["col_u"] == vc["col_v"], "!! 去咗反 pair 子句嘅染色 col(u) != col(v) —— mono-pair 性質喺呢個染色唔成立?!"
    print("[selftest 4] 去反 pair 子句: kissat SAT %.1fs; 染色 %d/%d 條邊異色 ✓, col(u)=col(v)=%d → mono-pair 喺呢個染色成立 ✓ (同 Phase 4 一致)" % (dt, vc["edges_checked"], vc["edges_checked"], vc["col_u"]))
    json.dump({"selftest_plain": {"status": "SAT", "solve_s": round(dt, 1), **vc}, "mono_sha_match": True, "plain_sha_match": True, "poison_rejected": ["u", "v", "(0,sqrt3)", "(0,0)"],
               "single_removal_clause_count_ok": True, "t_s": round(time.time() - t0, 1)}, open(os.path.join(out, "buildg2_selftest.json"), "w"), indent=1)
    for f in ("selftest_mono.cnf", "selftest_mono.json", "selftest_plain.cnf"):
        os.remove(os.path.join(out, f))
    print("[buildg2 selftest] 全部通過 ✓ (%.1fs)" % (time.time() - t0))

if __name__ == "__main__":
    main()
