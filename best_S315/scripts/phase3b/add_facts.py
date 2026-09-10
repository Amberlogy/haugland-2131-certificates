#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
add_facts.py —— Phase 3b 第 7 步: 將新認證嘅數字 (連來源) 加入 paper/facts.json (幂等: 同 key 覆寫; 唔刪舊項)
  來源: phase3b/dense_udg_L.json (稠密圖), phase3b/extra_facts.json (硬尾巴等), Phase 3b 縮圖循環 (runs/<id>/rounds.json + state.json + hardness_g2.json, 由 Windows 鏡像讀), step0 Zenodo, 論文編譯
用法: python add_facts.py --facts paper/facts.json --phase3b-dir phase3b [--run p3br1_shrink]
"""
import sys, os, json, time, argparse

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--facts", required=True); ap.add_argument("--phase3b-dir", required=True); ap.add_argument("--run", default="p3br1_shrink")
    a = ap.parse_args()
    F = json.load(open(a.facts, encoding="utf-8")); facts = F["facts"]; n0 = len(facts)
    P = a.phase3b_dir
    def add(key, value, unit, source, note=None, verified=True):
        facts[key] = {"value": value, "unit": unit, "source": source, "note": note, "verified": verified}
    # 稠密圖
    dp = os.path.join(P, "dense_udg_L.json")
    if os.path.exists(dp):
        d = json.load(open(dp, encoding="utf-8"))
        for r, st in d["balls"].items():
            c = st.get("completeness", {})
            add("dense.B%s" % r, {"n": st["n"], "m": st["m"], "max_degree": st["max_degree"], "n_deg_84": st["n_deg_84"], "avg_degree": st["avg_degree"], "edge_density": st["edge_density"],
                                  "certified_complete": c.get("certified_complete"), "float_candidates": c.get("float_candidates"), "near_misses_rejected": c.get("near_misses_rejected_exactly"), "extra_unit_pairs": c.get("non_lattice_exact_unit")},
                None, "phase3b/dense_udg_L.json (dense_udg.py, exact Q(zeta_84) lattice, r-ball of L)", "unit-distance graph on the r-ball of Haugland's lattice L; completeness = float scan + exact rejection")
        for g in ("H", "G1", "G2", "G3"):
            st = d["graphs"][g]
            add("dense.%s_degree" % g, {"max_degree": st["max_degree"], "n_deg_max": st["n_deg_max"], "avg_degree": st["avg_degree"], "edge_density": st["edge_density"], "min_degree": st["min_degree"]}, None,
                "phase3b/dense_udg_L.json (from %s.edge)" % g)
        add("dense.special_degrees", {"G1": {"A": 58, "B": 58, "max65_at": [172, 569]}, "G2": {"u": 58, "v": 58, "(0,sqrt3)": 8, "(0,0)": 72}, "G3": {"u": 116, "v": 59, "rho_v": 59, "(0,sqrt3)": 9, "rho_b": 9, "(0,0)": 72, "rho_o": 72}},
            None, "phase3b 2026-09-06 exact degree check (load_edges on G1/G2/G3.edge)")
        add("dense.moser_lattice_max_degree", 18, None, "supplied with the Phase 3b task (reference value, not recomputed here)", verified=False)
    # extra facts (硬尾巴等)
    ep = os.path.join(P, "extra_facts.json")
    if os.path.exists(ep):
        for k, v in json.load(open(ep, encoding="utf-8")).items():
            facts[k] = v
    # Zenodo / 論文
    add("release.zenodo_published", {"record": 22435778, "status": "published", "version": "1.0", "publication_date": "2026-09-06", "doi": "10.5281/zenodo.22435778", "concept_doi": "10.5281/zenodo.22435777", "files": 8, "bytes": 7893903124},
        None, "GET https://zenodo.org/api/records/22435778 (2026-09-06 13:25, phase3b/step0_zenodo.md)")
    add("paper.note_v1_pdf", {"pages": 6, "bytes": 311607, "engine": "pdflatex TeX Live 2026 (TinyTeX, WSL user dir)", "syntax_fix": "\\newtheorem{proposition}{Proposition}[section] added to preamble"}, None, "paper/note_v1.pdflatex.log (phase3b/tex_build.sh 2026-09-06 13:56)")
    add("paper.facts_check", {"numbers_extracted": 360, "consistent": 234, "derived_consistent": 10, "manual_discrepancies": ["45-90 MB/min vs 41.5-90.5", "about 10% conflict-rate spread vs ±11-13%"], "wording": ["227 = timeout events not cubes"]}, None, "paper/facts_check.md")
    # G₂ 縮圖循環 (Windows 鏡像 runs/<id>/)
    R = os.path.join(P, "runs", a.run)
    bj = json.load(open(os.path.join(P, "batches_g2.json"), encoding="utf-8")) if os.path.exists(os.path.join(P, "batches_g2.json")) else None
    if bj:
        add("g2shrink.P2", bj["P2"], None, "phase3b/batches_g2.json (protected_set: u, v, (0,sqrt3), (0,0))")
        add("g2shrink.n_candidates", bj["n_candidates"], None, "phase3b/batches_g2.json")
        add("g2shrink.x_target", bj["x_target"], None, "phase3b/batches_g2.json (|G2'| <= 720 <=> |G3'| = 2|G2'|-1 < 1441)")
        add("g2shrink.sort_key", bj["sort_key"], None, "phase3b/batches_g2.json")
        add("g2shrink.batch1", bj["batches"][0], None, "phase3b/batches_g2.json")
    pr = os.path.join(P, "price", "r01", "sample", "summary.json")
    if os.path.exists(pr):
        t = json.load(open(pr, encoding="utf-8"))["tiers"][0]
        add("g2shrink.price_round1", {k: t.get(k) for k in ("n_cubes", "refuted_leaves", "march_s", "sampled", "done", "timeout", "solve_mean_s", "solve_median_s", "solve_p90_s", "solve_max_s", "verify_mean_s", "proof_mb_mean", "proof_mb_max", "E_floor_h", "E_floor_ci90_h", "reliable")},
            None, "phase3b/price/r01/sample/summary.json (cubes.py, run p3b_price)")
    if os.path.exists(os.path.join(R, "rounds.json")):
        rounds = json.load(open(os.path.join(R, "rounds.json"), encoding="utf-8")); st = json.load(open(os.path.join(R, "state.json"), encoding="utf-8"))
        rows = []
        for r in rounds:
            for x in r["attempts"]:
                rows.append({"round": r["round"], "tag": x["tag"], "removed": x["removed"], "status": x["status"], "n_cubes": x.get("n_cubes"), "leaves": x.get("leaves"), "mean_solve_s": x.get("mean_solve_s"), "mean_sv_s": x.get("mean_sv_s"),
                             "max_solve_s": x.get("max_solve_s"), "wall_s": x.get("wall_s"), "cpu_solve_s": x.get("cpu_solve_s"), "cpu_verify_s": x.get("cpu_verify_s"), "proof_total_mb": x.get("proof_total_mb"), "G2p_n": (x.get("cnf") or {}).get("n_remaining"), "G3p_n": x.get("G3p_n"),
                             "l3_ok": x.get("l3_ok"), "B": (x.get("witness") or {}).get("blocked_min"), "split_events": x.get("split_events"), "solver_errors": x.get("solver_errors")})
        add("g2shrink.attempts", rows, None, "phase3b/runs/%s/rounds.json" % a.run)
        add("g2shrink.rounds", [{k: r.get(k) for k in ("round", "status", "net_removed", "G2p_n", "G3p_n", "wall_s", "B_sets")} for r in rounds], None, "phase3b/runs/%s/rounds.json" % a.run)
        add("g2shrink.S_acc_final", st["S_acc"], None, "phase3b/runs/%s/state.json" % a.run, "certified removable set (all certificates in release_v1_1_staging/reduction/phase3b_G2_shrink)")
        add("g2shrink.G2p_final", 1066 - len(st["S_acc"]), None, "phase3b/runs/%s/state.json" % a.run); add("g2shrink.G3p_final", 2 * (1066 - len(st["S_acc"])) - 1, None, "derived: 2|G2'| - 1")
        add("g2shrink.stop_reason", st.get("stop_reason"), None, "phase3b/runs/%s/state.json" % a.run); add("g2shrink.target_reached", bool(st.get("target_reached")), None, "phase3b/runs/%s/state.json" % a.run)
        add("g2shrink.elapsed_h", round(st.get("elapsed_s", 0) / 3600, 2), "h", "phase3b/runs/%s/state.json" % a.run)
        if st.get("gate"):
            add("g2shrink.gate", {"verdict": st["gate"].get("verdict"), "why": st["gate"].get("why"), "estimate": st["gate"].get("estimate")}, None, "phase3b/runs/%s/gate_g2.md" % a.run)
        hj = os.path.join(R, "hardness_g2.json")
        if os.path.exists(hj):
            h = json.load(open(hj, encoding="utf-8"))
            add("g2shrink.hardness", {"verdict": h.get("verdict"), "estimate": h.get("estimate"), "measured_cpu_h": h.get("measured_cpu_h"), "measured_wall_h": h.get("measured_wall_h"), "fits": {k: {kk: vv for kk, vv in v.items() if kk in ("total_future_cpu_h", "final_cert_cpu_h", "n_future_rounds", "max_round_wall_h")} for k, v in (h.get("fits") or {}).items()}},
                None, "phase3b/runs/%s/hardness_g2.json" % a.run)
    # beam search (第 4 步改題): 合併 JSON → 每 n 邊數 (L / 論文 Moser / 自跑 Moser), 輸贏統計
    bdir = os.path.join(P, "beam")
    if os.path.isdir(bdir):
        import glob
        import ast, re
        src = open(os.path.join(P, "beam_udg.py"), encoding="utf-8").read()       # 唔 import (Windows 冇 numpy/exactfield 路徑), 直接由源碼抽 dict 字面值
        m = re.search(r"PAPER_MOSER = (\{.*?\})\n", src, re.S)
        PAPER_MOSER = ast.literal_eval(m.group(1)) if m else {}
        def merge(pattern):
            best = {}; files = sorted(glob.glob(os.path.join(bdir, pattern)) + glob.glob(os.path.join(bdir, "*", pattern)))
            for f in files:
                j = json.load(open(f, encoding="utf-8"))
                for k, v in j["best"].items():
                    n = int(k); ee = v.get("edges_exact", v.get("edges"))
                    if n not in best or ee > best[n]:
                        best[n] = ee
            return best, files
        BL, fl = merge("beam_L.json"); BM, fm = merge("beam_moser.json")
        if BL:
            add("dense.beam.L_edges", {str(n): BL[n] for n in sorted(BL) if n >= 10}, None, "phase3b/beam/**/beam_L.json (beam_udg.py, exact re-verified; merged max over runs %s)" % [os.path.relpath(f, P) for f in fl], "lower bounds on max edges of an n-vertex unit-distance subgraph of L")
            add("dense.beam.moser_edges_ours", {str(n): BM[n] for n in sorted(BM) if n >= 10}, None, "phase3b/beam/**/beam_moser.json (same code on the Moser lattice; merged %s)" % [os.path.relpath(f, P) for f in fm])
            add("dense.beam.paper_moser_table2", {str(n): PAPER_MOSER[n] for n in sorted(PAPER_MOSER)}, None, "arXiv:2406.15317 Table 2 (transcribed via WebFetch 2026-09-06)", verified=False)
            win = [n for n in range(10, 101) if n in BL and n in PAPER_MOSER and BL[n] > PAPER_MOSER[n]]; tie = [n for n in range(10, 101) if n in BL and n in PAPER_MOSER and BL[n] == PAPER_MOSER[n]]; lose = [n for n in range(10, 101) if n in BL and n in PAPER_MOSER and BL[n] < PAPER_MOSER[n]]
            add("dense.beam.L_vs_paper", {"win": win, "tie": tie, "lose_count": len(lose), "n_range": "10..100"}, None, "derived from dense.beam.L_edges vs dense.beam.paper_moser_table2")
            add("dense.beam.moser_ours_vs_paper_ties", [n for n in range(10, 101) if n in BM and n in PAPER_MOSER and BM[n] == PAPER_MOSER[n]], None, "derived: n where our Moser run reaches the paper's value (search-strength calibration)")
    # 第 6 步 tail6 (硬尾巴換招)
    tj = os.path.join(P, "runs_tail", "p3bt6_tail", "tail6.json")
    if os.path.exists(tj):
        t = json.load(open(tj, encoding="utf-8"))
        add("part3.tail6.summary", {"status": t.get("status"), "roots": t.get("roots"), "depth": t.get("depth"), "timeout": t.get("timeout"), "elapsed_s": t.get("elapsed_s"), "all_roots_certified": t.get("all_roots_certified")}, None, "phase3b/runs_tail/p3bt6_tail/tail6.json (tail6.py, run p3bt6_tail)")
        add("part3.tail6.per_root", {r: {k: v.get(k) for k in ("n_sub", "leaves", "stuck", "mean_solve_s", "median_solve_s", "max_solve_s", "wall_s", "cover_verified", "status", "wasted_s")} for r, v in (t.get("per_root") or {}).items()}, None, "phase3b/runs_tail/p3bt6_tail/tail6.json")
    F["generated"] = time.strftime("%Y-%m-%d %H:%M:%S"); F["note"] = F.get("note", "") + " | Phase 3b additions (dense.*, g2shrink.*, part3.tail.*, release.zenodo_published, paper.*) by phase3b/add_facts.py."
    json.dump(F, open(a.facts, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("[add_facts] %d → %d facts (+%d) → %s" % (n0, len(facts), len(facts) - n0, a.facts))

if __name__ == "__main__":
    main()
