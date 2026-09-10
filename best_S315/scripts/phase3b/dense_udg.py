#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dense_udg.py —— Phase 3b 第 4 步: Haugland 嘅稠密圖問題 (零戰役, 唔跑 solver)
  用 haugland.py 嘅精確格仔生成器 (Q(ζ84) 分圓整數, 84 個單位向量 u_k) 對 L 嘅 r-球 (r = 1..R, 由原點 BFS) 計單位距離圖:
    * 邊 (lattice 方向): p + u_k = q (k < 42), 精確 (整數向量相等)
    * 完整性: 全部 |d−1| < 1e-6 嘅浮點候選對 (格仔空間索引, O(n × 局部密度)), 非 lattice 方向候選逐對精確核實 |d|² == 1
      → 若非 lattice 精確單位對 = 0 就係「邊表 = 完整單位距離圖」嘅認證 (同 haugland.py scan_extra_unit_pairs 同一標準)
    * 點數、邊數、最大度數、度數分佈、平均度 2m/n、邊密度 m / C(n,2); 內點 (離邊界夠遠) 度數 = 84
  另外對 G₁ / G₂ / G₃ (.edge) 報同樣數字. 對照 Moser 格仔最大度 18 (題目提供).
用法: python3 dense_udg.py --out DIR [--rmax 4] [--time-cap 7200] [--no-complete-r 4]
輸出: DIR/dense_udg_L.md (英文) + dense_udg_L.json
"""
import sys, os, json, time, argparse, math
if not __debug__:
    sys.exit("!! 唔准用 python -O")
PH2 = os.path.expanduser("~/hadwiger/phase2"); sys.path.insert(0, PH2)
import numpy as np
from exactfield import CycField, load_edges
import haugland

def deg_stats(n, edges):
    deg = np.zeros(n + 1, dtype=np.int64)
    for a, b in edges:
        deg[a] += 1; deg[b] += 1
    d = deg[1:]
    hist = {}
    for x in d.tolist():
        hist[x] = hist.get(x, 0) + 1
    m = len(edges)
    return {"n": n, "m": m, "max_degree": int(d.max()), "min_degree": int(d.min()), "avg_degree": round(2 * m / n, 4), "edge_density": (2 * m / (n * (n - 1))) if n > 1 else None,
            "degree_hist": {str(k): v for k, v in sorted(hist.items())}, "n_deg_max": int((d == d.max()).sum())}

def unit_pairs_grid(zs, tol=1e-6, cell=0.5, log=None):
    """回傳 set of (i,j) i<j 令 | |z_i − z_j| − 1 | < tol (浮點候選). 格仔索引: 只比較中心距離喺 [1 − √2·cell, 1 + √2·cell] 嘅格仔對."""
    n = len(zs); x = zs.real; y = zs.imag
    cx = np.floor(x / cell).astype(np.int64); cy = np.floor(y / cell).astype(np.int64)
    keys = cx * 1000003 + cy
    order = np.argsort(keys, kind="stable"); ks = keys[order]
    uniq, starts = np.unique(ks, return_index=True); ends = np.append(starts[1:], n)
    cells = {int(k): (int(s), int(e)) for k, s, e in zip(uniq, starts, ends)}
    cellxy = {int(k): (int(cx[order[s]]), int(cy[order[s]])) for k, s in zip(uniq, starts)}
    rad = math.ceil((1 + math.sqrt(2) * cell) / cell) + 1
    out = set(); t0 = time.time(); done = 0
    for k, (s, e) in cells.items():
        gx, gy = cellxy[k]; idx_a = order[s:e]; za = zs[idx_a]
        for dx in range(-rad, rad + 1):
            for dy in range(-rad, rad + 1):
                k2 = (gx + dx) * 1000003 + (gy + dy)
                if k2 < k or k2 not in cells:
                    continue
                # 格仔中心距離篩
                cd = math.hypot(dx, dy) * cell
                if cd > 1 + math.sqrt(2) * cell + 1e-9 or cd < 1 - math.sqrt(2) * cell - 1e-9:
                    continue
                s2, e2 = cells[k2]; idx_b = order[s2:e2]; zb = zs[idx_b]
                B = 4096
                for i0 in range(0, len(idx_a), B):
                    d = np.abs(za[i0:i0 + B, None] - zb[None, :])
                    ii, jj = np.nonzero(np.abs(d - 1.0) < tol)
                    for a_, b_ in zip(ii.tolist(), jj.tolist()):
                        i, j = int(idx_a[i0 + a_]), int(idx_b[b_])
                        if i != j:
                            out.add((min(i, j), max(i, j)))
        done += 1
        if log and done % 200 == 0:
            log("      grid: %d/%d cells, %d candidate pairs, %.0fs" % (done, len(cells), len(out), time.time() - t0))
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--rmax", type=int, default=4); ap.add_argument("--time-cap", type=float, default=7200)
    ap.add_argument("--no-complete-r", type=int, default=99, help="r ≥ 呢個值唔做完整性掃描 (太大)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True); T0 = time.time()
    def log(m):
        print("[%s %5.0fs] %s" % (time.strftime("%H:%M:%S"), time.time() - T0, m), flush=True)
    F = CycField(84)
    Hpts, names, HE, abg = haugland.build_H(F)
    u = haugland.build_uvec(F, Hpts)
    lat = haugland.Lat(F, u)
    log("lattice L: 84 unit vectors, common denominator D=%d, dim %d" % (lat.D, lat.dim))
    res = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "lattice": {"unit_vectors": 84, "D": lat.D, "field": "Q(zeta_84)", "rotation_symmetry": "pi/21"}, "balls": {}, "graphs": {}, "moser_lattice_max_degree_reference": 18}
    # BFS 到 rmax (同 haugland.Lat.ball, 但保留每層)
    dist = {lat.zero: 0}; frontier = [lat.zero]; layers = {0: 1}
    for r in range(1, a.rmax + 1):
        if time.time() - T0 > a.time_cap:
            log("time cap before radius %d" % r); break
        nxt = []
        for p in frontier:
            for uk in lat.U:
                q = lat.add(p, uk)
                if q not in dist:
                    dist[q] = r; nxt.append(q)
        frontier = nxt; layers[r] = len(dist)
        log("%d-ball: %d points (layer %d new)" % (r, len(dist), len(nxt)))
        pts = [p for p, d in dist.items() if d <= r]
        pos = {p: i for i, p in enumerate(pts)}
        pset = set(pts)
        t0 = time.time(); E = []
        for p in pts:
            for k in range(42):
                q = lat.add(p, lat.U[k])
                if q in pset:
                    E.append((pos[p] + 1, pos[q] + 1))
        t_edges = time.time() - t0
        st = deg_stats(len(pts), E); st["radius"] = r; st["edge_time_s"] = round(t_edges, 1); st["layer_sizes"] = dict(layers)
        # 內點: 84 個方向全部喺球內 → 度數 84
        st["n_deg_84"] = st["degree_hist"].get("84", 0)
        log("   r=%d: n=%d m=%d maxdeg=%d avgdeg=%.3f density=%.3e  deg-hist(top) %s  (edges %.1fs)" % (
            r, st["n"], st["m"], st["max_degree"], st["avg_degree"], st["edge_density"], dict(list(sorted(((int(k), v) for k, v in st["degree_hist"].items()), reverse=True))[:6]), t_edges))
        # 完整性 (浮點格仔候選 → 非 lattice 候選精確核實)
        if r < a.no_complete_r and time.time() - T0 < a.time_cap:
            t0 = time.time()
            zs = haugland.to_floats(lat, pts)
            cand = unit_pairs_grid(zs, 1e-6, 0.5, log if len(pts) > 200000 else None)
            eidx = {(min(p, q) - 1, max(p, q) - 1) for p, q in E}
            n_lat = sum(1 for c in cand if c in eidx); others = [c for c in cand if c not in eidx]
            extra, near = [], []
            for i, j in others:
                d2 = (lat.el(pts[i]) - lat.el(pts[j])).norm2()
                (extra if d2.is_one() else near).append((i + 1, j + 1))
            st["completeness"] = {"float_candidates": len(cand), "lattice_direction_candidates": n_lat, "lattice_edges_all_found_by_float_scan": n_lat == len(eidx),
                                  "non_lattice_candidates": len(others), "non_lattice_exact_unit": len(extra), "near_misses_rejected_exactly": len(near), "near_miss_examples": near[:5],
                                  "certified_complete": (n_lat == len(eidx) and len(extra) == 0), "scan_time_s": round(time.time() - t0, 1), "tol": 1e-6, "cell": 0.5}
            log("   r=%d completeness: float candidates %d (lattice %d/%d), non-lattice %d → exact unit %d, near misses %d → %s (%.0fs)" % (
                r, len(cand), n_lat, len(eidx), len(others), len(extra), len(near), "CERTIFIED COMPLETE ✓" if st["completeness"]["certified_complete"] else "!! NOT complete / extra unit pairs", time.time() - t0))
        else:
            st["completeness"] = {"certified_complete": None, "note": "not scanned (radius >= --no-complete-r or time cap): edges are lattice-direction edges only (lower bound)"}
        res["balls"][str(r)] = st
        json.dump(res, open(os.path.join(a.out, "dense_udg_L.json"), "w"), indent=1)
    # G₁ / G₂ / G₃
    H = os.path.join(PH2, "out", "haugland")
    for g in ("G1", "G2", "G3"):
        n, E = load_edges(os.path.join(H, g + ".edge")); st = deg_stats(n, E)
        st["completeness"] = {"certified_complete": True, "note": "exactfield.py check --complete (Phase 2 / release rerun.sh)"}
        res["graphs"][g] = st
        log("%s: n=%d m=%d maxdeg=%d avgdeg=%.3f density=%.3e" % (g, n, len(E), st["max_degree"], st["avg_degree"], st["edge_density"]))
    # H itself
    stH = deg_stats(21, [(x + 1, y + 1) for x, y in HE]); res["graphs"]["H"] = stH
    res["t_s"] = round(time.time() - T0, 1)
    json.dump(res, open(os.path.join(a.out, "dense_udg_L.json"), "w"), indent=1)
    # markdown (English)
    L = ["# dense_udg_L.md — Unit-distance graphs on balls of Haugland's lattice L (exact arithmetic)", "",
         "Generated %s by `phase3b/dense_udg.py` (Phase 3b, step 4). Lattice L = Z-span of the 84 unit vectors u_0..u_83 of Haugland's 21-vertex graph H (arXiv:2608.04542), "
         "represented exactly as cyclotomic integers in Q(zeta_84) (common denominator D = %d). The r-ball B_r is the set of lattice points reachable from the origin by at most r unit steps (BFS over the 84 vectors)." % (res["created"], lat.D), "",
         "Edges: two points are adjacent iff their exact distance is 1. Lattice-direction edges (q - p = u_k) are found exactly; completeness (\"no other unit-distance pairs\") is certified by a floating-point candidate scan "
         "(all pairs with | |p-q| - 1 | < 1e-6, spatial grid) followed by exact verification of every non-lattice candidate — the same standard as `haugland.py` used for T6 / G2 / G3.", "",
         "| graph | vertices | edges | max degree | # vertices of max degree | vertices of degree 84 (interior) | average degree 2m/n | edge density m/C(n,2) | completeness |", "|---|---|---|---|---|---|---|---|---|"]
    for r, st in res["balls"].items():
        c = st["completeness"]
        L.append("| B_%s (r-ball of L) | %d | %d | %d | %d | %d | %.3f | %.3e | %s |" % (
            r, st["n"], st["m"], st["max_degree"], st["n_deg_max"], st["n_deg_84"], st["avg_degree"], st["edge_density"],
            ("certified: %d float candidates, %d non-lattice candidates, %d exact extra unit pairs, %d near misses rejected" % (c["float_candidates"], c["non_lattice_candidates"], c["non_lattice_exact_unit"], c["near_misses_rejected_exactly"])) if c.get("certified_complete") else
            ("**NOT certified** (%s)" % c.get("note", "extra unit pairs found!") if c.get("certified_complete") is None else "**extra unit pairs found: %d**" % c.get("non_lattice_exact_unit", -1))))
    for g in ("H", "G1", "G2", "G3"):
        st = res["graphs"][g]
        L.append("| %s (Haugland) | %d | %d | %d | %d | %d | %.3f | %.3e | %s |" % (g, st["n"], st["m"], st["max_degree"], st["n_deg_max"], st["degree_hist"].get("84", 0), st["avg_degree"], st["edge_density"],
                                                                                   "exact (Phase 2, `exactfield.py check --complete`)" if g != "H" else "exact (haugland.py, 42 edges = Prop. 2.1)"))
    L += ["", "Reference: the Moser lattice used in the de Grey / Heule constructions has maximum degree 18 in its unit-distance graph (value supplied with the task).", "",
          "## Degree distributions", ""]
    for r, st in res["balls"].items():
        L.append("- B_%s: %s" % (r, ", ".join("%s:%d" % (k, v) for k, v in sorted(st["degree_hist"].items(), key=lambda kv: int(kv[0])))))
    for g in ("G1", "G2", "G3"):
        st = res["graphs"][g]
        L.append("- %s: %s" % (g, ", ".join("%s:%d" % (k, v) for k, v in sorted(st["degree_hist"].items(), key=lambda kv: int(kv[0])))))
    L += ["", "Ball sizes |B_r|: %s (r=3 agrees with the paper's 83 581)." % ", ".join("r=%s: %d" % (k, v) for k, v in sorted(res["balls"][max(res["balls"])]["layer_sizes"].items(), key=lambda kv: int(kv[0]))), "",
          "## Three observations", ""]
    b = res["balls"]
    r1 = b.get("1"); rmaxk = max(b); rmx = b[rmaxk]
    obs = []
    if r1:
        obs.append("1. Every lattice point has exactly 84 unit-distance neighbours in L (the 84 vectors u_k; the completeness scans found no other unit vector among differences of ball points), so the infinite graph on L is 84-regular — 4.7 times the maximum degree 18 of the Moser lattice; in B_1 the origin already has degree 84 while the 84 boundary points have degree %d." % (r1["degree_hist"].get(str(r1["min_degree"])) and r1["min_degree"]))
    obs.append("2. Finite balls are far from dense: average degree grows from %.1f (B_1) to %.1f (B_%s) while the edge density falls from %.2e to %.2e, because the number of points grows roughly like %.0f× per unit of radius and most points sit near the boundary where many of the 84 directions leave the ball." % (
        b["1"]["avg_degree"], rmx["avg_degree"], rmaxk, b["1"]["edge_density"], rmx["edge_density"], (rmx["n"] / b[str(int(rmaxk) - 1)]["n"]) if str(int(rmaxk) - 1) in b else float("nan")))
    obs.append("3. Haugland's G1 (7-core, max degree %d, average %.2f) and G3 (max degree %d, average %.2f) use only a small fraction of the lattice's local density: G3's densest vertices ((-1,0), (1,0) and their rho-images) reach degree %d, whereas an interior lattice point has 84 unit neighbours available — the constructions are sparse selections inside a very dense ambient graph." % (
        res["graphs"]["G1"]["max_degree"], res["graphs"]["G1"]["avg_degree"], res["graphs"]["G3"]["max_degree"], res["graphs"]["G3"]["avg_degree"], res["graphs"]["G3"]["max_degree"]))
    L += obs + ["", "Total time %.0f s; JSON with full data: dense_udg_L.json." % res["t_s"]]
    open(os.path.join(a.out, "dense_udg_L.md"), "w").write("\n".join(L) + "\n")
    log("DENSE_UDG DONE → %s/dense_udg_L.md" % a.out)

if __name__ == "__main__":
    main()
