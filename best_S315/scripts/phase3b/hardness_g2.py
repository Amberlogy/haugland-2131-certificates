#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hardness_g2.py —— Phase 3b 閘門: G₂ 「越剪越貴」曲線 + 外推到 |G₂′| = 720 (x_target = 346 粒) + 判定 (唔跑 solver)
  輸入: runs/<id>/rounds.json (probe3b), batches_g2.json
  點: 每張 certified 證書 (x = |S|, y = 該張證書 wall 小時 / 每 cube solve+verify 秒); SAT 嘗試另標 (唔入擬合); x=0 用 Phase 4 G₂ 偵察外推 1.43 h 做參考錨點 (唔係證書, 唔入擬合)
  外推: 三模型 (指數 / 冪 / 線性) 擬合 wall(x), 由最後一張證書起每 --step 粒一輪直到 x_target, CPU-h = Σ wall × workers
  判定 (題目規則): 綠燈 ⇔ 三模型外推未來總成本全部 ≤ --green CPU-h 且 頭 3 輪至少 --need-rounds 輪淨剪 ≥ --min-net 粒 (且冇證書超輪上限未完); 否則 STOP
用法: python3 hardness_g2.py --probe DIR --batches batches_g2.json --out DIR [--workers 14] [--green 200] [--step 30] [--min-net 20] [--need-rounds 2]
輸出: DIR/hardness_curve_g2.png, DIR/hardness_g2.json, DIR/gate_g2.md
"""
import sys, os, json, math, argparse, time
if not __debug__:
    sys.exit("!! 唔准用 python -O")
G2RECON = {"x": 0, "wall_h": 1.43, "sv": 4.4, "cubes": 16350, "tag": "G₂ recon x=0 (Phase 4 抽樣外推, 唔係證書)"}

def fit_loglin(xs, ys):
    n = len(xs); ly = [math.log(y) for y in ys]; mx = sum(xs) / n; my = sum(ly) / n
    sxx = sum((x - mx) ** 2 for x in xs); b = sum((x - mx) * (y - my) for x, y in zip(xs, ly)) / sxx if sxx else 0.0; a = my - b * mx
    return {"model": "exp", "a": a, "b": b, "pred": (lambda x: math.exp(a + b * x)), "doubling_x": (math.log(2) / b) if b > 0 else None}

def fit_power(xs, ys):
    lx = [math.log(max(x, 1)) for x in xs]; ly = [math.log(y) for y in ys]; n = len(xs); mx = sum(lx) / n; my = sum(ly) / n
    sxx = sum((x - mx) ** 2 for x in lx); b = sum((x - mx) * (y - my) for x, y in zip(lx, ly)) / sxx if sxx else 0.0; a = my - b * mx
    return {"model": "power", "a": a, "b": b, "pred": lambda x: math.exp(a + b * math.log(max(x, 1)))}

def fit_linear(xs, ys):
    n = len(xs); mx = sum(xs) / n; my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs); b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0.0; a = my - b * mx
    return {"model": "linear", "a": a, "b": b, "pred": lambda x: max(1e-3, a + b * x)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", required=True); ap.add_argument("--batches", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=14); ap.add_argument("--green", type=float, default=200); ap.add_argument("--step", type=int, default=30)
    ap.add_argument("--min-net", type=int, default=20); ap.add_argument("--need-rounds", type=int, default=2)
    a = ap.parse_args()
    rounds = json.load(open(os.path.join(a.probe, "rounds.json"))); bj = json.load(open(a.batches)); W = a.workers
    x_target = bj["x_target"]; n = bj["n"]
    attempts = [x for r in rounds for x in r.get("attempts", [])]
    cert = [x for x in attempts if x["status"] == "certified"]; sat = [x for x in attempts if x["status"] == "SAT"]
    unfinished = [x for x in attempts if x["status"] in ("budget-stop", "hard-killed", "stuck", "march-refuted-root")]
    pts = [{"x": x["removed"], "sv": x.get("mean_sv_s"), "solve": x.get("mean_solve_s"), "wall_h": x["wall_s"] / 3600, "cubes": x.get("n_cubes"), "leaves": x.get("leaves"),
            "cpu_h": ((x.get("cpu_solve_s") or 0) + (x.get("cpu_verify_s") or 0)) / 3600, "G2p": x["cnf"]["n_remaining"], "G3p": x.get("G3p_n"), "tag": x["tag"]} for x in cert]
    satpts = [{"x": x["removed"], "sv": x.get("mean_sv_s"), "wall_h": x["wall_s"] / 3600, "leaves": x.get("leaves"), "cubes": x.get("n_cubes"), "tag": x["tag"], "B": x.get("B_size")} for x in sat]
    cens = [{"x": x["removed"], "sv": x.get("mean_sv_s"), "wall_h_lower": x["wall_s"] / 3600, "projected_wall_h": (x["wall_s"] / 3600 + (x.get("eta_remaining_h") or 0)), "leaves": x.get("leaves"), "cubes": x.get("n_cubes"), "status": x["status"], "tag": x["tag"]} for x in unfinished]
    nets = [{"round": r["round"], "status": r.get("status"), "net_removed": r.get("net_removed", 0), "S_acc_after": len(r.get("S_acc_after", r["S_acc_before"])), "G2p_n": r.get("G2p_n"), "wall_h": (r.get("wall_s") or 0) / 3600} for r in rounds]
    first3 = nets[:3]; good = [q for q in first3 if (q["net_removed"] or 0) >= a.min_net]
    res = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "workers": W, "x_target": x_target, "G2p_at_target": n - x_target, "G3p_at_target": 2 * (n - x_target) - 1,
           "points": pts, "sat_points": satpts, "censored": cens, "rounds": nets, "green": a.green, "step": a.step, "min_net": a.min_net, "need_rounds": a.need_rounds,
           "anchor": G2RECON, "measured_cpu_h": round(sum(((x.get("cpu_solve_s") or 0) + (x.get("cpu_verify_s") or 0) + (x.get("wasted_s") or 0)) for x in attempts) / 3600, 1),
           "measured_wall_h": round(sum(x["wall_s"] for x in attempts) / 3600, 2)}
    fits = {}; est = {}
    x_max = max([p["x"] for p in pts] or [0])
    if len(pts) >= 2 and x_max < x_target:
        xs = [p["x"] for p in pts]; yw = [p["wall_h"] for p in pts]; ysv = [p["sv"] for p in pts]
        future_x = list(range(x_max + a.step, x_target + 1, a.step))
        if not future_x or future_x[-1] < x_target:
            future_x.append(x_target)
        for name, fn in (("exp", fit_loglin), ("power", fit_power), ("linear", fit_linear)):
            fw = fn(xs, yw); fs = fn(xs, ysv); per = [fw["pred"](x) for x in future_x]
            fits[name] = {"wall": {k: v for k, v in fw.items() if k != "pred"}, "sv": {k: v for k, v in fs.items() if k != "pred"}, "future_x": future_x,
                          "future_wall_h": [round(v, 3) for v in per], "final_cert_wall_h": round(fw["pred"](x_target), 3), "final_cert_cpu_h": round(fw["pred"](x_target) * W, 1),
                          "total_future_wall_h": round(sum(per), 2), "total_future_cpu_h": round(sum(per) * W, 1), "sv_at_target_s": round(fs["pred"](x_target), 2), "n_future_rounds": len(future_x),
                          "max_round_wall_h": round(max(per), 2)}
        fw0 = fit_loglin([0] + xs, [G2RECON["wall_h"]] + yw)
        fits["exp_with_recon_anchor"] = {"wall": {k: v for k, v in fw0.items() if k != "pred"}, "total_future_cpu_h": round(sum(fw0["pred"](x) for x in future_x) * W, 1), "final_cert_cpu_h": round(fw0["pred"](x_target) * W, 1)}
        est = {"headline_model": "exp", "headline_total_cpu_h": fits["exp"]["total_future_cpu_h"],
               "range_total_cpu_h": [min(fits[m]["total_future_cpu_h"] for m in ("exp", "power", "linear")), max(fits[m]["total_future_cpu_h"] for m in ("exp", "power", "linear"))],
               "n_future_rounds": len(future_x), "rounds_over_3h": {m: sum(1 for v in fits[m]["future_wall_h"] if v > 3) for m in ("exp", "power", "linear")}}
    elif len(pts) == 1 and x_max < x_target:
        # 只有一張證書: 用 x=0 偵察錨點補一點 (標明 anchor-assisted, 唔係正式外推)
        xs = [0, pts[0]["x"]]; yw = [G2RECON["wall_h"], pts[0]["wall_h"]]
        future_x = list(range(x_max + a.step, x_target + 1, a.step))
        fw = fit_loglin(xs, yw); per = [fw["pred"](x) for x in future_x]
        fits["exp_anchor_assisted"] = {"wall": {k: v for k, v in fw.items() if k != "pred"}, "future_x": future_x, "future_wall_h": [round(v, 3) for v in per], "total_future_cpu_h": round(sum(per) * W, 1), "note": "only one certified point; x=0 anchor is a sampled extrapolation, not a certificate"}
        est = {"headline_model": "exp_anchor_assisted", "headline_total_cpu_h": fits["exp_anchor_assisted"]["total_future_cpu_h"], "range_total_cpu_h": [fits["exp_anchor_assisted"]["total_future_cpu_h"]] * 2, "n_future_rounds": len(future_x), "insufficient": True}
    res["fits"] = fits; res["estimate"] = est
    # 判定
    reasons = []
    if x_max >= x_target:
        verdict = "TARGET"; why = "已到達 x_target=%d (|G₂′| ≤ %d)" % (x_target, n - x_target)
    else:
        if unfinished:
            reasons.append("有證書超輪上限未完: %s" % [(c["tag"], c["status"], "leaf %s/%s" % (c["leaves"], c["cubes"])) for c in cens])
        if not est:
            reasons.append("完成嘅證書少過 2 張 (%d), 冇法外推" % len(pts))
        elif est.get("insufficient"):
            reasons.append("只有 1 張證書, 外推靠 x=0 偵察錨點 (%.0f CPU-h), 唔算數" % est["headline_total_cpu_h"])
        elif est["range_total_cpu_h"][1] > a.green:
            reasons.append("三模型外推未來總成本 %.0f–%.0f CPU-h, 最大 > %.0f" % (est["range_total_cpu_h"][0], est["range_total_cpu_h"][1], a.green))
        if len(good) < a.need_rounds:
            reasons.append("頭 3 輪淨剪 ≥ %d 粒嘅只有 %d 輪 (要 ≥ %d): %s" % (a.min_net, len(good), a.need_rounds, [(q["round"], q["status"], q["net_removed"]) for q in first3]))
        if len(nets) < 3:
            reasons.append("未夠 3 輪 (%d)" % len(nets))
        if reasons:
            verdict = "STOP"; why = "; ".join(reasons)
        else:
            verdict = "GREEN"; why = "三模型外推未來總成本 %.0f–%.0f CPU-h 全部 ≤ %.0f; 頭 3 輪淨剪 ≥ %d 粒嘅有 %d 輪 %s; 冇證書超輪上限" % (
                est["range_total_cpu_h"][0], est["range_total_cpu_h"][1], a.green, a.min_net, len(good), [(q["round"], q["net_removed"]) for q in first3])
            if est.get("rounds_over_3h", {}).get("exp"):
                why += "; 注意: 指數模型預測有 %d 輪 wall > 3 h (輪上限), 屆時會 cap-hit" % est["rounds_over_3h"]["exp"]
        if sat:
            why += "; SAT 嘗試 %s (每個都有逐邊覆核嘅染色證書 + 擋住集 B) 證實所剪批次含必要頂點, 外推假設之後每輪都 certified, 只係下界" % [(s["tag"], "B=%s" % s["B"]) for s in satpts]
    res["verdict"] = verdict; res["why"] = why
    json.dump(res, open(os.path.join(a.out, "hardness_g2.json"), "w"), indent=1, ensure_ascii=False)
    # 圖
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, axs = plt.subplots(1, 2, figsize=(12.5, 4.8))
        xmax = max([x_target] + [p["x"] for p in pts] + [s["x"] for s in satpts] + [c["x"] for c in cens]) * 1.05
        x0 = min([p["x"] for p in pts] or [30]); grid = list(range(x0, int(xmax) + 1))
        ax = axs[0]
        ax.scatter([p["x"] for p in pts], [p["sv"] for p in pts], c="tab:blue", zorder=5, label="certified (G2 - S mono-pair)")
        for p in pts:
            ax.annotate("%s\n%d cubes" % (p["tag"], p["cubes"]), (p["x"], p["sv"]), textcoords="offset points", xytext=(5, 5), fontsize=7)
        ax.scatter([0], [G2RECON["sv"]], c="gray", marker="s", zorder=5, label="G2 recon x=0 (sampled, not certified, not fitted)")
        for s in satpts:
            if s["sv"]:
                ax.scatter([s["x"]], [s["sv"]], c="tab:purple", marker="^", zorder=5)
                ax.annotate("%s SAT\n%s/%s leaves, |B|=%s" % (s["tag"], s["leaves"], s["cubes"], s["B"]), (s["x"], s["sv"]), textcoords="offset points", xytext=(5, -14), fontsize=6.5, color="tab:purple")
        for c in cens:
            if c["sv"]:
                ax.scatter([c["x"]], [c["sv"]], c="tab:red", marker="x", zorder=5, label="unfinished (%s)" % c["status"])
        if len(pts) >= 2:
            xs = [p["x"] for p in pts]; ysv = [p["sv"] for p in pts]
            for name, fn, ls in (("exp", fit_loglin, "-"), ("power", fit_power, "--"), ("linear", fit_linear, ":")):
                f = fn(xs, ysv); ax.plot(grid, [f["pred"](x) for x in grid], ls, lw=1, label="%s fit" % name)
        ax.axvline(x_target, color="k", lw=0.8, ls="--"); ax.text(x_target, ax.get_ylim()[1] * 0.85, " x_target=%d\n (|G2'|=720, |G3'|=1439)" % x_target, fontsize=7)
        ax.set_yscale("log"); ax.set_xlabel("cumulative G2 vertices removed |S|"); ax.set_ylabel("mean solve+verify per cube (s), log"); ax.set_title("G2 shrink: hardness per cube"); ax.legend(fontsize=6.5); ax.grid(alpha=0.3)
        ax = axs[1]
        ax.scatter([p["x"] for p in pts], [p["wall_h"] for p in pts], c="tab:blue", zorder=5, label="certified certificate wall (14 workers)")
        ax.scatter([0], [G2RECON["wall_h"]], c="gray", marker="s", zorder=5, label="G2 recon x=0 extrapolated 1.43 h (anchor)")
        for s in satpts:
            ax.scatter([s["x"]], [s["wall_h"]], c="tab:purple", marker="^", zorder=5)
        for c in cens:
            ax.errorbar([c["x"]], [c["wall_h_lower"]], yerr=[[0], [max(0.0, c["projected_wall_h"] - c["wall_h_lower"])]], fmt="x", c="tab:red", label="unfinished: lower bound -> projected")
        if len(pts) >= 2:
            xs = [p["x"] for p in pts]; yw = [p["wall_h"] for p in pts]
            for name, fn, ls in (("exp", fit_loglin, "-"), ("power", fit_power, "--"), ("linear", fit_linear, ":")):
                f = fn(xs, yw); ax.plot(grid, [f["pred"](x) for x in grid], ls, lw=1, label="%s fit -> future total %.0f CPU-h" % (name, fits[name]["total_future_cpu_h"]))
        ax.axhline(3, color="tab:red", lw=0.8, ls="--"); ax.text(1, 3.05, "3 h round cap", fontsize=7, color="tab:red")
        ax.axvline(x_target, color="k", lw=0.8, ls="--")
        ax.set_yscale("log"); ax.set_xlabel("cumulative G2 vertices removed |S|"); ax.set_ylabel("certificate wall time (h, %d workers), log" % W); ax.set_title("Cost per certificate - verdict: %s" % verdict); ax.legend(fontsize=6.5); ax.grid(alpha=0.3)
        fig.tight_layout(); fig.savefig(os.path.join(a.out, "hardness_curve_g2.png"), dpi=130); plt.close(fig)
        res["png"] = os.path.join(a.out, "hardness_curve_g2.png")
    except Exception as e:
        res["png_error"] = repr(e)
    json.dump(res, open(os.path.join(a.out, "hardness_g2.json"), "w"), indent=1, ensure_ascii=False)
    # gate_g2.md
    L = ["# gate_g2.md —— Phase 3b 閘門判定 (%s)" % res["created"], "",
         "## 證書數據 (每張: G₂ − S + 反 pair 子句, march_cu d=14, kissat T=600 → 2T → 再拆, %d workers, ext4 binary DRAT 驗完即刪, cover + 5%% 審計)" % W,
         "| 嘗試 | |S| | G₂′ | G₃′ | cube | leaf | 每 cube solve (s) | 每 cube solve+verify (s) | ×L1 (0.78 s) | ×G₂recon (4.4 s) | wall | CPU (s+v) | 狀態 |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
         "| G₂ recon x=0 (對照, 抽樣外推) | 0 | 1066 | 2131 | 16350 | 30 抽樣 | 2.7 | 4.4 | 5.6 | 1 | 1.43 h (外推) | — | 唔係證書 |"]
    for x in attempts:
        L.append("| %s | %d | %s | %s | %s | %s | %s | %s | %s | %s | %s s (%.2f h) | %s h | %s%s |" % (
            x["tag"], x["removed"], x["cnf"]["n_remaining"] if x.get("cnf") else "—", x.get("G3p_n", "—"), x.get("n_cubes"), x.get("leaves"), x.get("mean_solve_s", "—"), x.get("mean_sv_s", "—"),
            x.get("x_L1_sv", "—"), x.get("x_G2recon_sv", "—"), x.get("wall_s"), (x.get("wall_s") or 0) / 3600, round(((x.get("cpu_solve_s") or 0) + (x.get("cpu_verify_s") or 0)) / 3600, 2), x["status"],
            (" (L2″/L3″ %s)" % ("✓" if x.get("l3_ok") else "!!")) if x["status"] == "certified" else ((" |B|=%s" % x.get("B_size")) if x["status"] == "SAT" else "")))
    L += ["", "## 每輪淨剪", "| 輪 | 結果 | 淨剪 | S_acc 之後 | G₂′ | 輪 wall (h) |", "|---|---|---|---|---|---|"]
    L += ["| %d | %s | %s | %d | %s | %.2f |" % (q["round"], q["status"], q["net_removed"], q["S_acc_after"], q["G2p_n"], q["wall_h"]) for q in nets]
    L += ["", "外推目標: 累計剪 x_target = **%d** 粒 (|G₂′| = %d, |G₃′| = %d < 1441); 由最後一張證書起每 %d 粒一輪; 已量度 CPU %.1f h, wall %.2f h" % (x_target, n - x_target, 2 * (n - x_target) - 1, a.step, res["measured_cpu_h"], res["measured_wall_h"]), ""]
    if fits and not est.get("insufficient"):
        L += ["## 外推 (只用 certified 證書 x = %s; y = 該張證書 wall 小時; CPU-h = wall × %d)" % ([p["x"] for p in pts], W),
              "| 模型 | 參數 | 未來輪數 | 每輪 wall (h) | 未來總 wall (h) | **未來總 CPU-小時** | 最後一張證書 CPU-h | 目標處每 cube s | 預測 > 3 h 嘅輪數 |", "|---|---|---|---|---|---|---|---|---|"]
        for name in ("exp", "power", "linear"):
            f = fits[name]
            L.append("| %s | a=%.3g b=%.3g%s | %d | %s | %.1f | **%.0f** | %.0f | %.1f | %d |" % (
                name, f["wall"]["a"], f["wall"]["b"], (" (wall 每 %.0f 粒翻倍)" % f["wall"]["doubling_x"]) if f["wall"].get("doubling_x") else "", f["n_future_rounds"],
                ", ".join("%.2f" % v for v in f["future_wall_h"][:6]) + (" …" if len(f["future_wall_h"]) > 6 else ""), f["total_future_wall_h"], f["total_future_cpu_h"], f["final_cert_cpu_h"], f["sv_at_target_s"], est["rounds_over_3h"][name]))
        L += ["| exp + recon 錨點 (x=0, 1.43 h) 敏感度 | a=%.3g b=%.3g | — | — | — | %.0f | %.0f | — | — |" % (fits["exp_with_recon_anchor"]["wall"]["a"], fits["exp_with_recon_anchor"]["wall"]["b"], fits["exp_with_recon_anchor"]["total_future_cpu_h"], fits["exp_with_recon_anchor"]["final_cert_cpu_h"]), ""]
    L += ["## 判定 (規則: 綠燈 ⇔ 三模型外推未來總成本全部 ≤ %.0f CPU-h 且 頭 3 輪至少 %d 輪淨剪 ≥ %d 粒 且 冇證書超輪上限; 否則停)" % (a.green, a.need_rounds, a.min_net), "",
          "**判定: %s** —— %s" % (verdict, why), "", "曲線: hardness_curve_g2.png (左: 每 cube solve+verify; 右: 每張證書 wall; 三個擬合延伸到 x_target; 3 h 輪上限線)"]
    open(os.path.join(a.out, "gate_g2.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L))

if __name__ == "__main__":
    main()
