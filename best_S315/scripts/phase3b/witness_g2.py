#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
witness_g2.py —— 由 SAT 輪嘅染色證書 (G₂−S 嘅 4 色染色, col(u) ≠ col(v)) 做零 solver 分析 (同 phase3/witness_blocked.py 一樣嘅方法):
  貪心將 S 入面嘅頂點逐粒放返去 (有可用色就染), 放唔返嘅集合 B ⊆ S = 「呢個染色擋住嘅集合」;
  結果係另一張機器可覆核嘅證書: G₂ − B 有 4 色染色而且 col(u) ≠ col(v)  ⇒  B 唔可以成集剪走 (B 入面至少一粒係 mono-pair 性質嘅必要頂點).
  試 4 種固定次序 + N 種隨機次序, 報最細 B; 每個 B 都逐邊覆核.
用法: python3 witness_g2.py --col DIR/G2minus_60v.col [--col ...] --out DIR [--random 200] [--seed 20260906]
"""
import sys, os, json, argparse, random, time
if not __debug__:
    sys.exit("!! 唔准用 python -O")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from g2common import G2, read_col, verify_colouring, write_col, sha, K

def greedy(order, col, adj):
    col = dict(col); blocked = []
    for w in order:
        used = {col[x] for x in adj[w] if x in col}
        free = [c for c in range(1, K + 1) if c not in used]
        if free:
            col[w] = free[0]
        else:
            blocked.append(w)
    return blocked, col

def analyse(g2, col_path, out, n_random=200, seed=20260906):
    S, col = read_col(col_path)
    assert set(col) == set(range(1, g2.n + 1)) - set(S), "染色頂點集 != V(G₂) − S"
    v0 = verify_colouring(g2, S, col)
    assert v0["ok"], "!! 輸入染色本身覆核失敗: %s" % v0
    orders = {"index_asc": sorted(S), "index_desc": sorted(S, reverse=True), "deg_asc": sorted(S, key=lambda w: (g2.deg[w], w)), "deg_desc": sorted(S, key=lambda w: (-g2.deg[w], w))}
    rng = random.Random(seed)
    for i in range(n_random):
        o = list(S); rng.shuffle(o); orders["random_%d" % i] = o
    best = None; sizes = {}
    for name, o in orders.items():
        blocked, col2 = greedy(o, col, g2.adj)
        v2 = verify_colouring(g2, blocked, col2)
        assert v2["ok"] and set(col2) == set(range(1, g2.n + 1)) - set(blocked), "貪心放返之後覆核失敗?!"
        sizes[name] = len(blocked)
        if best is None or len(blocked) < len(best[1]):
            best = (name, blocked, col2)
    name, blocked, col2 = best
    v2 = verify_colouring(g2, blocked, col2)
    tag = os.path.basename(os.path.dirname(os.path.abspath(col_path))) + "_" + os.path.basename(col_path)[:-4]
    os.makedirs(out, exist_ok=True); outp = os.path.join(out, "%s_minus_blocked.col" % tag)
    s = write_col(outp, blocked, col2, "c 4-colouring of G2 minus %s with col(-1,0) != col(1,0) (u=#%d, v=#%d; greedy re-insertion of the other removed vertices, order %s): certificate that this set cannot be removed as a whole (it contains a vertex necessary for the mono-pair property)" % (sorted(blocked), g2.u, g2.v, name))
    hist = {}
    for x in sizes.values():
        hist[x] = hist.get(x, 0) + 1
    rec = {"witness": col_path, "S_size": len(S), "S": sorted(S), "blocked_min": sorted(blocked), "blocked_min_size": len(blocked), "order": name,
           "blocked_size_hist": {str(k): v for k, v in sorted(hist.items())}, "orders_tried": len(orders), "verified": v2["ok"], "edges_checked": v2["edges_checked"],
           "bad_edges": v2["bad_edges"], "col_u": v2["col_u"], "col_v": v2["col_v"], "coloured": len(col2), "out": outp, "sha256_out": s,
           "blocked_deg": {str(w): g2.deg[w] for w in blocked}}
    print("[%s] S=%d 粒 → 貪心放返 (試 %d 種次序, |B| 分佈 %s) 最細擋住集 B = %s (|B|=%d, 次序 %s); 證書: G₂−B 染色 %d 點, %d/%d 條邊異色 ✓, col(u)=%d ≠ col(v)=%d → %s" % (
        tag, len(S), len(orders), rec["blocked_size_hist"], sorted(blocked), len(blocked), name, len(col2), v2["edges_checked"] - v2["bad_edges"], v2["edges_checked"], v2["col_u"], v2["col_v"], outp), flush=True)
    if len(blocked) == 1:
        print("   ⇒ 頂點 %d 係 mono-pair 性質嘅必要頂點 (G₂ − {%d} 有 col(u)≠col(v) 嘅 4 色染色, 機器證書)" % (blocked[0], blocked[0]), flush=True)
    return rec

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--col", action="append", required=True); ap.add_argument("--out", required=True); ap.add_argument("--random", type=int, default=200); ap.add_argument("--seed", type=int, default=20260906)
    a = ap.parse_args()
    g2 = G2(); report = [analyse(g2, p, a.out, a.random, a.seed) for p in a.col]
    json.dump(report, open(os.path.join(a.out, "witness_g2.json"), "w"), indent=1)

if __name__ == "__main__":
    main()
