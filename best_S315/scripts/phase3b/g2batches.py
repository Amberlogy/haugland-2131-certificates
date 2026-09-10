#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
g2batches.py —— Phase 3b 第 1 步: G₂ 保護集 P₂ + 批次選點 (唔跑任何 solver)
  P₂ = {u=(−1,0), v=(1,0), (0,√3)} ∪ {w ∈ V(G₂) : w 或 ρ(w) 係 G₃ 特殊點 {(−1,0),(1,0),ρ(1,0),(0,0),ρ(0,0)} 或兩條交叉邊嘅端點}
  候選 = V(G₂) \\ P₂; 排序 key = (G₂ 度數升序, 離 u–v 軸線 (直線 y=0) 距離 |Im z| 降序, 索引升序); 批次 k=30
  每剪一粒 G₂ 頂點 w, G₃′ = G₂′ ∪ ρ(G₂′) 少 2 粒 (w 同 ρ(w)); |G₃′| = 2|G₂′| − 1
  目標: |G₃′| < 1441 ⇔ |G₂′| ≤ 720 ⇔ 累計剪 ≥ 346 粒 (12 批 × 30 = 360)
用法: python3 g2batches.py --out DIR [--k 30] [--nbatches 12] [--target 1441]
輸出: DIR/batches_g2.json, DIR/batches_g2.md
"""
import sys, os, json, argparse, time, math
if not __debug__:
    sys.exit("!! 唔准用 python -O")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from g2common import G2, G3, protected_set, build_cnf

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--k", type=int, default=30); ap.add_argument("--nbatches", type=int, default=12)
    ap.add_argument("--target", type=int, default=1441)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True); t0 = time.time()
    g2 = G2(); g3 = G3(g2)
    P2, why = protected_set(g2, g3)
    cands = sorted((w for w in range(1, g2.n + 1) if w not in why), key=lambda w: (g2.deg[w], -g2.axis[w], w))
    assert len(cands) + len(P2) == g2.n
    batches = [cands[i * a.k:(i + 1) * a.k] for i in range(a.nbatches)]
    assert all(len(b) == a.k for b in batches), "候選唔夠分 %d 批" % a.nbatches
    # 目標
    x_target = next(m for m in range(0, g2.n) if 2 * (g2.n - m) - 1 < a.target)
    cum = [{"round": r, "removed": r * a.k, "G2p": g2.n - r * a.k, "G3p": 2 * (g2.n - r * a.k) - 1} for r in range(1, a.nbatches + 1)]
    # 刪晒全部批次之後 u 仍有三角形可以釘色?
    S_all = set(cands[:a.nbatches * a.k])
    cl, E, tri = build_cnf(g2, S_all, protected=P2)
    # 度數分佈
    deg_hist = {}
    for w in range(1, g2.n + 1):
        deg_hist[g2.deg[w]] = deg_hist.get(g2.deg[w], 0) + 1
    deg_hist_c = {}
    for w in cands:
        deg_hist_c[g2.deg[w]] = deg_hist_c.get(g2.deg[w], 0) + 1
    out = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "inputs_sha": {**g2.sha, **g3.sha}, "n": g2.n, "m": len(g2.E),
           "u": g2.u, "v": g2.v, "b_sqrt3": g2.b, "origin": g2.o, "rho_v": g3.rho_idx[g2.v], "rho_b": g3.rho_idx[g2.b], "rho_o": g3.rho_idx[g2.o],
           "special_G3": {k: g3.sp3[k] for k in ("(-1,0)", "(1,0)", "(3/4,√15/4)", "(0,0)", "rho(0,0)")}, "cross_edges": g3.cross,
           "P2": P2, "P2_why": {str(w): why[w] for w in P2}, "n_P2": len(P2), "n_candidates": len(cands), "k": a.k, "nbatches": a.nbatches,
           "sort_key": "(degree_G2 asc, |Im z| desc, index asc)", "batches": batches, "ordering": cands, "cumulative": cum, "target": a.target,
           "x_target": x_target, "G2p_at_target": g2.n - x_target, "G3p_at_target": 2 * (g2.n - x_target) - 1,
           "degree_hist_all": {str(k): v for k, v in sorted(deg_hist.items())}, "degree_hist_candidates": {str(k): v for k, v in sorted(deg_hist_c.items())},
           "pin_triangle_after_all": [g2.u, tri[0], tri[1]], "cnf_clauses_after_all": len(cl),
           "table": [{"w": w, "deg": g2.deg[w], "axis": round(g2.axis[w], 6), "protected": w in why, "rho": g3.rho_idx[w]} for w in range(1, g2.n + 1)],
           "t_s": round(time.time() - t0, 1)}
    json.dump(out, open(os.path.join(a.out, "batches_g2.json"), "w"), indent=1, ensure_ascii=False)
    L = ["# batches_g2.md —— Phase 3b 第 1 步: G₂ 保護集 + 批次選點 (%s)" % out["created"], "",
         "輸入 (sha 頭 16 位): %s" % {f: s[:16] for f, s in out["inputs_sha"].items()}, "",
         "## 對象", "- G₂: %d 點 %d 邊; u = (−1,0) = #%d, v = (1,0) = #%d, (0,√3) = #%d, (0,0) = #%d (全部精確對認)" % (g2.n, len(g2.E), g2.u, g2.v, g2.b, g2.o),
         "- G₃ = G₂ ∪ ρ(G₂), ρ(z) = (z+1)(7+i√15)/8 − 1; G₂ #w = G₃ #w (identity 嵌入逐點核對), ρ(G₂ #w) 索引精確對認 (rho_idx); G₂ ∩ ρ(G₂) = {u} ✓",
         "- ρ(v) = #%d = (3/4,√15/4), ρ((0,√3)) = #%d, ρ((0,0)) = #%d; 交叉邊 %s" % (g3.rho_idx[g2.v], g3.rho_idx[g2.b], g3.rho_idx[g2.o], g3.cross), "",
         "## 保護集 P₂ (永遠唔剪): %d 粒" % len(P2)]
    for w in P2:
        L.append("- #%d (%.4f, %.4f): %s" % (w, g2.P[w - 1].to_float().real, g2.P[w - 1].to_float().imag, "; ".join(why[w])))
    L += ["", "解釋: 引理 L3″ 用到 u, v, ρ(v) 同交叉邊 (1,0)–ρ(1,0); 題目另外指定保護 (0,√3) (第二條交叉邊端點); (0,0) 同 ρ(0,0) 係 G₃ 特殊點 (Phase 2 特殊點名單), 照題目規則一併保護. "
          "冇其他 G₂ 頂點映到特殊點, 所以 P₂ 只有 %d 粒, 候選 %d 粒." % (len(P2), len(cands)), "",
          "## 選法", "- 候選 = V(G₂) \\ P₂ (%d 粒); 排序 key = %s; 批次 k = %d, 唔重疊; 每粒 w 剪走令 G₃′ 少 2 粒 (w 同 ρ(w))" % (len(cands), out["sort_key"], a.k),
          "- G₂ 度數分佔 (全部): %s; 候選: %s" % (out["degree_hist_all"], out["degree_hist_candidates"]), ""]
    for i, b in enumerate(batches, 1):
        L += ["### 批次 %d (%d 粒)" % (i, len(b)), "| w | deg | |Im z| | ρ(w) (G₃ 索引) |", "|---|---|---|---|"]
        L += ["| %d | %d | %.4f | %d |" % (w, g2.deg[w], g2.axis[w], g3.rho_idx[w]) for w in b]
        L.append("")
    L += ["## 累計剪點 → |G₂′| / |G₃′| = 2|G₂′| − 1 (純點數, 唔計 pair 性質成唔成立)", "| 輪 | 累計剪 | G₂′ | G₃′ |", "|---|---|---|---|"]
    L += ["| %d | %d | %d | %d |" % (c["round"], c["removed"], c["G2p"], c["G3p"]) for c in cum]
    L += ["", "目標 |G₃′| < %d ⇔ |G₂′| ≤ %d ⇔ 累計剪 ≥ **%d** 粒 (約 %d 批); 剪晒 %d 批 (%d 粒) 之後 u 仍有三角形 (u,p,q) = %s 可以釘色 ✓, CNF %d 子句" % (
        a.target, out["G2p_at_target"], x_target, math.ceil(x_target / a.k), a.nbatches, a.nbatches * a.k, out["pin_triangle_after_all"], len(cl)),
          "", "用時 %.1f s (全部精確代數, 冇 solver)" % out["t_s"]]
    open(os.path.join(a.out, "batches_g2.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L[:22] + ["…"] + L[-6:]))

if __name__ == "__main__":
    main()
