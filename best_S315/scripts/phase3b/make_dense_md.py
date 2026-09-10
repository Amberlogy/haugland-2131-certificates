#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_dense_md.py —— Phase 3b 第 4 步 (改題) 出 dense_udg_L.md (英文): beam search 喺 L 搵到嘅 n 點最多邊 UDG (n = 10..N) 逐 n 對照 arXiv:2406.15317 Table 2 (Moser 格仔, n ≤ 100)
  + 同算法 Moser 對照 run (n > 100 用) + 邊啲 n 打贏/打輸/打和 + 附錄 (舊 r-ball 統計)
用法: python3 make_dense_md.py --beam-dir DIR --dense-json dense/dense_udg_L.json --out dense_udg_L.md
"""
import sys, os, json, argparse, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from beam_udg import PAPER_MOSER

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--beam-dir", required=True); ap.add_argument("--dense-json", default=None); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    import glob
    def merge(pattern):
        """合併多個 run 嘅 JSON: 每個 n 取邊數最大 (記低來自邊個 run); runs/elapsed 相加."""
        files = sorted(glob.glob(os.path.join(a.beam_dir, pattern)) + glob.glob(os.path.join(a.beam_dir, "*", pattern)))
        best = {}; runs = []; el = 0.0; params = None; final = True
        for f in files:
            j = json.load(open(f)); tag = os.path.relpath(f, a.beam_dir)
            params = params or j.get("params"); el += j.get("elapsed_s", 0); final &= bool(j.get("final")); runs += [dict(r, file=tag, alpha=j["params"]["alpha"]) for r in j.get("runs", [])]
            for k, v in j["best"].items():
                n = int(k); ee = v.get("edges_exact", v.get("edges"))
                if n not in best or ee > best[n].get("edges_exact", best[n].get("edges")):
                    best[n] = dict(v, found="%s (alpha %d, %s)" % (v.get("found", ""), j["params"]["alpha"], tag))
        return {"best": {str(n): v for n, v in best.items()}, "runs": runs, "elapsed_s": el, "final": final, "params": params or {"m": 0, "alpha": 0, "lam": 1.0}, "files": files}
    bl = merge("beam_L.json"); bm = merge("beam_moser.json")
    BL = {int(k): v for k, v in bl["best"].items()}; BM = {int(k): v for k, v in bm["best"].items()}
    nmax = max(BL) if BL else 0
    def e(v):
        return v.get("edges_exact", v.get("edges"))
    win = [n for n in range(10, 101) if n in BL and n in PAPER_MOSER and e(BL[n]) > PAPER_MOSER[n]]
    lose = [n for n in range(10, 101) if n in BL and n in PAPER_MOSER and e(BL[n]) < PAPER_MOSER[n]]
    tie = [n for n in range(10, 101) if n in BL and n in PAPER_MOSER and e(BL[n]) == PAPER_MOSER[n]]
    win2 = [n for n in range(10, nmax + 1) if n in BL and n in BM and e(BL[n]) > e(BM[n])]
    lose2 = [n for n in range(10, nmax + 1) if n in BL and n in BM and e(BL[n]) < e(BM[n])]
    tie2 = [n for n in range(10, nmax + 1) if n in BL and n in BM and e(BL[n]) == e(BM[n])]
    gap_m = [PAPER_MOSER[n] - e(BM[n]) for n in range(10, 101) if n in BM]
    all_verified_L = all(v.get("verified") for n, v in BL.items() if n >= 10); all_verified_M = all(v.get("verified") for n, v in BM.items() if n >= 10)
    L = ["# dense_udg_L.md — Densest unit-distance subgraphs of Haugland's lattice L by beam search, versus the Moser lattice (arXiv:2406.15317)", "",
         "Generated %s (Phase 3b, step 4 as redefined). Question: for n = 10..300, how many edges can a unit-distance graph on n points of the lattice L (the Z-span of the 84 unit vectors of Haugland's 21-vertex graph H, arXiv:2608.04542, exact coordinates in Q(zeta_84)) have, compared with the densest known unit-distance graphs on the Moser lattice ML = Z<1, omega_1, omega_3, omega_1 omega_3> found by Engel, Hammond-Lee, Su, Varga and Zsámboki, *Diverse beam search to find densest-known planar unit distance graphs*, arXiv:2406.15317 (Table 2, n <= 100)?" % time.strftime("%Y-%m-%d %H:%M"), "",
         "## Method", "",
         "A beam search of the same kind as in arXiv:2406.15317, implemented in `phase3b/beam_udg.py` and run identically on both lattices:",
         "- **State** = a set of lattice points (exact integer coordinates: 24-vectors over Q(zeta_84) with common denominator 7 for L; 4-vectors (a,b,c,d) for ML), its edge count, and a *gain* table (for every lattice point q adjacent to the set, the number of set points at unit distance from q). Candidates are all points `p + u_k` (existing point + unit vector), which contains the paper's operations 1–3 (edge, triangle and parallelogram completion).",
         "- **Forward step**: every state proposes its m = %d highest-gain candidates; children are ranked by edge count, canonized under the lattice's symmetry group (%d transforms for L: 42 rotations by 2π/42 and 42 reflections z ↦ u_1·z̄; 12 for ML: 6 rotations by π/3 and 6 reflections z ↦ ω_3·z̄ — closure of the unit-vector set under every transform is self-tested), duplicates dropped, a visitation penalty (λ = %g, as in the paper's diverse search) subtracted, and the best α = %d kept." % (bl["params"]["m"], 84, bl["params"]["lam"], bl["params"]["alpha"]),
         "- **Backward sweep**: from the beam at n_max, vertices of lowest degree are deleted one at a time (top-α by edges, canonized), updating the record for every smaller n. The forward+backward pass is restarted with accumulated visitation counts (L: %d restarts, %.0f s; ML: %d restarts, %.0f s)." % (len(bl["runs"]), bl["elapsed_s"], len(bm["runs"]), bm["elapsed_s"]),
         "- **Exactness**: unit distance is decided exactly. For L every reported graph is re-verified by a floating-point candidate scan (| |p−q| − 1 | < 1e-6) followed by exact cyclotomic arithmetic on every non-lattice-direction candidate (the `extra unit pairs` column; 0 throughout means all edges are lattice-direction edges and no unit pair was missed). For ML all pairs are re-checked exactly in Q(√3, √11). Exact re-verification agreed with the search counts for every n (L: %s; ML: %s)." % ("all verified" if all_verified_L else "MISMATCHES, see JSON", "all verified" if all_verified_M else "MISMATCHES, see JSON"),
         "- **Caveats**: beam search is a heuristic, so every number below is a *lower bound* on the true maximum for that lattice; the paper's Table 2 values are the densest *known* (their search is stronger: larger database, backtracking over 60 million graphs). Our own re-run on ML with the same code reaches the paper's value for small n and falls short by %s edges for n = 10..100 (max gap %d), which calibrates how much of a shortfall on L may be due to the search rather than the lattice." % (("0–%d" % max(gap_m)) if gap_m else "?", max(gap_m) if gap_m else 0), "",
         "## Results (n = 10..%d)" % nmax, "",
         "| n | L: edges (exact) | Moser lattice, paper Table 2 | L − paper | Moser lattice, our re-run | L − our Moser | found by (L) |", "|---|---|---|---|---|---|---|"]
    for n in range(10, nmax + 1):
        if n not in BL:
            continue
        el = e(BL[n]); pm = PAPER_MOSER.get(n); em = e(BM[n]) if n in BM else None
        L.append("| %d | %d | %s | %s | %s | %s | %s |" % (n, el, pm if pm is not None else "—", ("%+d" % (el - pm)) if pm is not None else "—", em if em is not None else "—", ("%+d" % (el - em)) if em is not None else "—", BL[n].get("found", "")))
    L += ["", "## Where L wins, loses or ties (n = 10..100, against the paper's Moser-lattice values)", "",
          "- **L wins (more edges than the densest known Moser-lattice graph): %d values of n** — %s" % (len(win), win if win else "none"),
          "- **Ties: %d values of n** — %s" % (len(tie), tie if tie else "none"),
          "- **L loses: %d values of n** — %s" % (len(lose), lose if lose else "none"), "",
          "Against our own same-algorithm Moser run (n = 10..%d): L wins at %d, ties at %d, loses at %d values of n%s." % (nmax, len(win2), len(tie2), len(lose2), (" (wins: %s)" % win2) if win2 and len(win2) <= 60 else ""), "",
          "Reading: the small-n optima (triangular-lattice patches, u(n) for n ≤ 30 per OEIS A186705) exist in both lattices because L contains the hexagonal lattice (u_14 = e^{iπ/3}); the Moser lattice's advantage, where it has one, comes from the Moser-spindle angle arccos(5/6), which L does not contain (its 84 directions are the multiples of 2π/42 and their shift by θ_1 ≈ 3.63°), while L's 84 directions offer more ways to close rhombi and triangles as n grows. Whether L truly beats ML at a given n needs a stronger search on both sides; the exact edge counts above are certified, the comparison is between search results.", "",
          "Data: `phase3b/beam/beam_L.json`, `beam_moser.json` (points of every record graph, exact verification columns), logs `beam_L.log`, `beam_moser.log`."]
    if a.dense_json and os.path.exists(a.dense_json):
        d = json.load(open(a.dense_json))
        L += ["", "## Appendix: r-balls of L (earlier version of this step; exact, completeness certified)", "", "| graph | vertices | edges | max degree | vertices of degree 84 | average degree | edge density | completeness |", "|---|---|---|---|---|---|---|---|"]
        for r, st in d["balls"].items():
            c = st["completeness"]
            L.append("| B_%s | %d | %d | %d | %d | %.3f | %.3e | certified (%d float candidates, %d near misses rejected exactly, %d extra unit pairs) |" % (r, st["n"], st["m"], st["max_degree"], st["n_deg_84"], st["avg_degree"], st["edge_density"], c.get("float_candidates", 0), c.get("near_misses_rejected_exactly", 0), c.get("non_lattice_exact_unit", 0)))
        for g in ("G1", "G2", "G3"):
            st = d["graphs"][g]; L.append("| %s | %d | %d | %d | 0 | %.3f | %.3e | exact (Phase 2) |" % (g, st["n"], st["m"], st["max_degree"], st["avg_degree"], st["edge_density"]))
        L += ["", "Within the 8-ball of any lattice point (differences of B_4) the only unit vectors of L are the 84 generators (16 943 892 float candidates, 203 616 near misses all rejected exactly), so the unit-distance graph of L is 84-regular there — 4.7× the Moser lattice's degree 18 — yet finite balls are sparse (B_4: average degree 27.9, 7 % interior points). In Haugland's graphs the densest vertices are (−1,0) in G3 (degree 116 = 2·58) and (0,0) in G2 (72); (0,√3) has degree 9."]
    open(a.out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("[make_dense_md] n_max %d; vs paper (10..100): win %d tie %d lose %d; vs own Moser: win %d tie %d lose %d → %s" % (nmax, len(win), len(tie), len(lose), len(win2), len(tie2), len(lose2), a.out))

if __name__ == "__main__":
    main()
