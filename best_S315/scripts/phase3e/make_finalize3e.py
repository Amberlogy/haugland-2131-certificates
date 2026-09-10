#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_finalize3e.py —— 機械生成 phase3e/finalize3e.py = phase3d/finalize3d.py + 「輪」改動 (同 make_cnc2k.py 一樣嘅做法: 唔手抄, 出 diff 俾人審)
  為咩:  finalize3d.py 嘅獨立重驗鏈 (rebuild_base + verify_final 全部 leaf drat-trim + crosscheck3d cake_lpr/lrat-check + 5 色逐邊 + 封存 + SHA256SUMS + RECORD 程序)
         已經審核過而且係最強嗰個; Phase 3e 唔重寫佢, 只係 (1) 改名/改路徑, (2) 加返「輪」嘅帳同 Amber 要嘅擋路集分析。
  改乜:  A. 名/路徑: PH3D→PH3E (phase3d 目錄改叫 PH3D 保留俾 crosscheck3d.py 同封存源碼), phase3d→phase3e, probe3d→probe3e, finalize3d→finalize3e,
            g2shrink3d.→g2shrink3e., Phase 3d→Phase 3e, 最後一刀→小步慢行, phase3d_results→phase3e_results, PHASE3D_README→PHASE3E_README, resume3d.sh→resume3e.sh
            保留唔改: crosscheck3d.py (phase3e 唔會複製一份), phase3c/verify_final.py, PREV_G3P = 1591 (Phase 3c r09a 仍然係上一個認證圖)
         B. 讀 rounds.json (按 state.round_done 截尾), 封存/細檔都抄埋
         C. 報告加「## 每輪帳」表 + 步幅歷史; 擋路集section 換成「雷區密度隨深度」分析 (每輪 |B|、兩兩重疊 Jaccard、同 Phase 3d 三個 B 對照)
         D. facts 加 g2shrink3e.rounds / .step_history / .B_analysis
         E. 設計段、PHASE3E_README、DECISION、MEMORY 嘅文字由「一刀剪 80」改成「每輪剪 20 + 自適應步幅」
  出:    phase3e/finalize3e.py + phase3e/finalize3e.diff (unified diff, 俾人審)
用法: python3 make_finalize3e.py [--src ~/hadwiger/phase3d/finalize3d.py] [--out ~/hadwiger/phase3e/finalize3e.py] [--check]
"""
import sys, os, re, argparse, difflib, py_compile

SENT = {}


def protect(txt, key, s):
    """把「唔准改」嘅字串換做 sentinel"""
    n = txt.count(s)
    assert n >= 1, "!! protect %s: 搵唔到 %r" % (key, s[:80])
    SENT[key] = s
    return txt.replace(s, "@@%s@@" % key)


def sub(txt, old, new, n_expect=None):
    n = txt.count(old)
    assert n > 0, "!! 搵唔到 %r" % (old[:120],)
    if n_expect is not None:
        assert n == n_expect, "!! %r 出現 %d 次, 預期 %d 次" % (old[:60], n, n_expect)
    return txt.replace(old, new)


def one(txt, old, new):
    return sub(txt, old, new, 1)


HELPERS = '''

# ---------------- Phase 3e 加: 擋路集分析 (Amber 要嘅「雷區密度隨深度點變」) ----------------
N_G2 = 1066                      # |V(G₂)| (phase3b/g2common.py G2().n); |G₂′| = N_G2 − |S|


def phase3d_B_sets():
    """Phase 3d 一刀剪 80 (|S| = 350) 嗰三個擋路集, 用嚟同 Phase 3e 對照。讀唔到就當冇。"""
    try:
        return json.load(open(os.path.join(PH3D, "runs", "p3d1_final", "state.json"))).get("B_sets") or []
    except Exception:
        return []


def b_analysis(B_sets, prev_sets=None):
    """每個擋路集嘅大小 + 兩兩重疊 (交集 / Jaccard) + 同 Phase 3d 三個 B 嘅重疊。純函數, 冇 solver, 冇 I/O。"""
    S = [{"round": b.get("round"), "tag": b.get("tag"), "step": b.get("step"), "S_size": b.get("S_size"),
          "G2p": (N_G2 - b["S_size"]) if b.get("S_size") else None,
          "size": b.get("size") if b.get("size") is not None else len(b.get("B") or []),
          "in_S_acc": len(b.get("B_in_S_acc") or []), "in_batch": len(b.get("B_in_batch") or []),
          "B": sorted(b.get("B") or [])} for b in (B_sets or [])]
    pw = []
    for i in range(len(S)):
        for j in range(i + 1, len(S)):
            a, c = set(S[i]["B"]), set(S[j]["B"])
            pw.append({"a": S[i]["tag"], "b": S[j]["tag"], "inter": len(a & c), "union": len(a | c),
                       "jaccard": (round(len(a & c) / len(a | c), 4) if (a | c) else None)})
    vs = []
    for b in (prev_sets or []):
        pb = set(b.get("B") or [])
        for x in S:
            a = set(x["B"])
            vs.append({"phase3e": x["tag"], "phase3d": b.get("tag"), "inter": len(a & pb),
                       "jaccard": (round(len(a & pb) / len(a | pb), 4) if (a | pb) else None)})
    u = set().union(*[set(x["B"]) for x in S]) if S else set()
    pu = set().union(*[set(b.get("B") or []) for b in (prev_sets or [])]) if prev_sets else set()
    return {"n": len(S), "mean_size": (round(sum(x["size"] for x in S) / len(S), 2) if S else None),
            "by_set": S, "pairwise": pw, "vs_phase3d": vs,
            "union_size": len(u), "union": sorted(u),
            "phase3d_n": len(prev_sets or []), "phase3d_union_size": len(pu),
            "inter_with_phase3d_union": len(u & pu),
            "note": "|B| = minimal blocking subset found by witness_g2 greedy put-back; each has an edge-checked 4-colouring of G2 - B with col(u) != col(v). Jaccard = |A n B| / |A u B|."}
'''


def build(src_txt):
    t = src_txt
    # ---------- 0. 保護 (呢啲要繼續指住真正嘅 phase3d) ----------
    t = protect(t, "XC", 'os.path.join(PH3D, "crosscheck3d.py")')
    t = protect(t, "XCSH", "/home/user/hadwiger/phase3d/crosscheck3d.py")
    t = protect(t, "XCRM", "scripts/phase3d/crosscheck3d.py")
    t = protect(t, "ENVLIST", "~/hadwiger/{phase2,phase2b,phase3b,phase3c,phase3d}")
    t = protect(t, "SCRIPTS", 'for sub, src in (("phase3d", PH3D), ("phase3c", PH3C), ("phase3b", PH3B)):')
    t = protect(t, "HDR", 'PH3B = os.path.expanduser("~/hadwiger/phase3b"); PH3C = os.path.expanduser("~/hadwiger/phase3c"); PH3D = os.path.expanduser("~/hadwiger/phase3d")')
    # ---------- 1. 全域改名 ----------
    t = t.replace("PH3D", "PH3E")
    t = t.replace("PHASE3D_README", "PHASE3E_README")
    t = t.replace("FINALIZE3D", "FINALIZE3E")
    t = t.replace("probe3d", "probe3e")
    t = t.replace("finalize3d", "finalize3e")
    t = t.replace("g2shrink3d.", "g2shrink3e.")
    t = t.replace("phase3d", "phase3e")
    t = t.replace("Phase 3d", "Phase 3e")
    t = t.replace("最後一刀", "小步慢行")
    t = t.replace("resume3d.sh", "resume3e.sh")
    t = t.replace("p3d1_final", "p3e1_step")
    # ---------- 2. 還原保護 ----------
    t = t.replace("@@XC@@", 'os.path.join(PH3D, "crosscheck3d.py")')
    t = t.replace("@@XCSH@@", SENT["XCSH"])
    t = t.replace("@@XCRM@@", SENT["XCRM"])
    t = t.replace("@@ENVLIST@@", "~/hadwiger/{phase2,phase2b,phase3b,phase3c,phase3d,phase3e}")
    t = t.replace("@@SCRIPTS@@", 'for sub, src in (("phase3e", PH3E), ("phase3d", PH3D), ("phase3c", PH3C), ("phase3b", PH3B)):')
    t = t.replace("@@HDR@@",
                  'PH3B = os.path.expanduser("~/hadwiger/phase3b"); PH3C = os.path.expanduser("~/hadwiger/phase3c")\n'
                  'PH3D = os.path.expanduser("~/hadwiger/phase3d")     # crosscheck3d.py + probe3e 繼承嘅 probe3d.py 都喺呢度 (封存源碼要抄埋)\n'
                  'PH3E = os.path.expanduser("~/hadwiger/phase3e")')
    assert "@@" not in t, "!! 仲有 sentinel 冇還原"
    # ---------- 3. 加 helper (擋路集分析) ----------
    t = one(t, "\nclass Fin:\n", HELPERS + "\n\nclass Fin:\n")
    # ---------- 4. 讀 rounds.json ----------
    t = one(t,
            '        self.attempts = json.load(open(os.path.join(self.rdir, "attempts.json"))) if os.path.exists(os.path.join(self.rdir, "attempts.json")) else []\n',
            '        self.attempts = json.load(open(os.path.join(self.rdir, "attempts.json"))) if os.path.exists(os.path.join(self.rdir, "attempts.json")) else []\n'
            '        rp = os.path.join(self.rdir, "rounds.json")                                       # Phase 3e: 輪; 未結算嘅尾巴輪 (round > round_done) 唔算\n'
            '        self.rounds = [r for r in (json.load(open(rp)) if os.path.exists(rp) else []) if (r.get("round") or 0) <= (self.st.get("round_done") or 0)]\n')
    # ---------- 5. 封存 / 細檔都抄 rounds.json ----------
    t = sub(t,
            '("state.json", "attempts.json", "ledger_g2.md", "status.json", "probe3e.log", "finalize_status.json")',
            '("state.json", "attempts.json", "rounds.json", "ledger_g2.md", "status.json", "probe3e.log", "finalize_status.json")', 2)
    # ---------- 6. PHASE3E_README: 一刀 → 每輪 ----------
    t = one(t,
            '             "Same certificate types as `../REDUCTION_README.md` §A (L1″ cube-and-conquer bundle, L2″/L3″ assembly, blocking colourings), continuing Phase 3c. "\n'
            '             "Difference: **one cut of %d vertices instead of several rounds of 30** (a certificate costs the same whether we delete 30 or 80 — march_cu always splits into ~16 384 cubes), "\n'
            '             "per-certificate cap 8 h + up to 1 h automatic extension when a run is nearly finished, at most 3 certificates (a/b/c). "\n'
            '             "The complete certificate set of the final graph, including every leaf proof, is in `%s`." % (\n'
            '                 (best.get("removed") or 0) - 270, (self.fs.get("archive") or {}).get("dir", ARCH_ROOT)), "",\n'
            '             "Seed: Phase 3c `%s` %s — S_acc = 270, |G2′| = 796, |G3′| = %d." % ((self.st.get("seed") or {}).get("run_id"), (self.st.get("seed") or {}).get("last_certified_tag"), PREV_G3P), "",\n',
            '             "Same certificate types as `../REDUCTION_README.md` §A (L1″ cube-and-conquer bundle, L2″/L3″ assembly, blocking colourings), continuing Phase 3c and Phase 3e. "\n'
            '             "Difference from Phase 3d: **small steps again** — %d further vertices removed over %d rounds of %s (Phase 3d tried one cut of 80 and hit SAT three times, with three disjoint 30-vertex blocking sets). "\n'
            '             "Per round: at most 2 certificates (a, b); if both are SAT the step is halved (20 → 10 → 5). Round cap %.0f h shared by a and b, plus up to %.0f h automatic extension when a run is nearly finished. "\n'
            '             "Every certified round is fully certified on the spot (l3g2 --engine-b: spindle engines A and B; certify4 --k 5: 5-colouring checked edge by edge). "\n'
            '             "The complete certificate set of the final graph, including every leaf proof, is in `%s`." % (\n'
            '                 (best.get("removed") or 0) - 270, len(self.rounds), "/".join(str(s) for s in sorted({r.get("step") for r in self.rounds if r.get("step")}, reverse=True)) or "?",\n'
            '                 ((self.st.get("config") or {}).get("cap") or 0) / 3600, ((self.st.get("config") or {}).get("extend") or 0) / 3600,\n'
            '                 (self.fs.get("archive") or {}).get("dir", ARCH_ROOT)), "",\n'
            '             "Seed: Phase 3c `%s` %s — S_acc = 270, |G2′| = 796, |G3′| = %d." % ((self.st.get("seed") or {}).get("run_id"), (self.st.get("seed") or {}).get("last_certified_tag"), PREV_G3P), "",\n')
    # ---------- 7. RECORD_README: one shot → rounds ----------
    t = one(t,
            '             "* Phase 3e cut %d further G2 vertices in one shot (candidate order: G2 degree ascending, |Im z| descending, index ascending; protected set P2 = {172, 187, 646, 994} never touched)." % (len(fa["S"]) - 270),',
            '             "* Phase 3e cut %d further G2 vertices in %d certified rounds of %s (candidate order: G2 degree ascending, |Im z| descending, index ascending; protected set P2 = {172, 187, 646, 994} never touched)." % (\n'
            '                 len(fa["S"]) - 270, len([r for r in self.rounds if r.get("status") == "certified"]),\n'
            '                 "/".join(str(r.get("step")) for r in self.rounds if r.get("status") == "certified") or "?"),')
    # ---------- 8. 報告: 標題 + 設計段 + 每輪帳 ----------
    t = one(t,
            '        L = ["# phase3e_results.md —— Phase 3e: 小步慢行 (一刀剪 %s 粒; run %s, 接力 Phase 3c %s)" % (\n'
            '                (len(fa["S"]) - 270) if fa else "?", self.rid, (st.get("seed") or {}).get("last_certified_tag")), "",\n',
            '        cfg = st.get("config") or {}\n'
            '        n_cert = len([r for r in self.rounds if r.get("status") == "certified"])\n'
            '        steps_used = "/".join(str(s) for s in sorted({r.get("step") for r in self.rounds if r.get("step")}, reverse=True)) or str(cfg.get("step"))\n'
            '        L = ["# phase3e_results.md —— Phase 3e: 小步慢行 (每輪剪 %s 粒; %d 輪, %d 輪 certified, 淨剪 %s 粒; run %s, 接力 Phase 3c %s)" % (\n'
            '                steps_used, len(self.rounds), n_cert, (len(fa["S"]) - 270) if fa else 0, self.rid, (st.get("seed") or {}).get("last_certified_tag")), "",\n')
    t = one(t,
            '        L += ["", "## 設計修正 (Amber 2026-09-08) 同今次點做", "",\n'
            '              "- **成本按證書計,唔係按粒數計**:march_cu d=14 每次都切約 16 384 個 cube,剪 30 同剪 80 一樣貴 ⇒ 今次**一刀剪 80 粒**(Phase 3c 用咗 6 輪 × 30 粒 = 271.9 CPU-h 先剪到 180 粒)。",\n'
            '              "- **唔用細規則殺死接近完成嘅 run**:每張證書輪上限 8 h,cnc2k budget-stop 之後如果剩餘估計 ≤ 0.5 h 就自動 `--resume` 延長(累計 ≤ 1 h)。Phase 3c round 10 就係喺 15 698/16 384(差 ~9 分鐘)撞 3.5 h 上限而報廢。",\n'
            '              "- 預算:%.0f CPU-h、%.0f h wall、最多 3 張證書(a/b/c);SAT 就 witness 分析出擋路集 B,排除之後由候選表補足返到 |S| = %d 再證。" % (\n'
            '                  (st.get("config") or {}).get("cpu_cap_h", 160), (st.get("config") or {}).get("total_cap", 86400) / 3600, (st.get("config") or {}).get("target_removed", 350)), "",\n'
            '              "## 帳 (每張證書)", "",\n',
            '        L += ["", "## 設計 (Amber Phase 3e mega-prompt 2026-09-08) 同今次點做", "",\n'
            '              "- **點解退返細步幅**:Phase 3d 由 796 一刀剪 80 粒,三張證書全部 SAT,三個擋路集各 30 粒而且互不重疊(90 個索引全部唔同)⇒ 唔係「有幾粒地雷」,而係喺嗰個深度任何 80 粒嘅選法都約有三成剪唔得 ⇒ 一刀太大。",\n'
            '              "- **每輪剪 %s 粒**(796 → 776 → 756 → 736 → 716,四輪到目標);每輪最多 %s 張證書(a、b);**兩張都 SAT ⇒ 步幅減半**(20 → 10 → 5),用新步幅開下一輪(仍然計入輪數上限);步幅去到 %s 仍然兩張都 SAT 就停。" % (\n'
            '                  cfg.get("step"), cfg.get("attempts_per_round"), cfg.get("min_step")),\n'
            '              "- **排除集逐輪重置**:一粒點喺 |S| = 350 擋路,唔代表喺 |S| = 290 擋路 ⇒ 只喺當輪排除,冇永久排除(Phase 3c 嘅 `perma_excluded` 呢度冇)。",\n'
            '              "- **唔用細規則殺死接近完成嘅 run**(沿用 Phase 3d 嘅規矩):每輪上限 %.0f h(a + b 共用),cnc2k budget-stop 之後如果剩餘估計 ≤ %.1f h 就自動 `--resume` 延長(每輪累計 ≤ %.0f h)。Phase 3c round 10 就係喺 15 698/16 384(差 ~9 分鐘)撞 3.5 h 上限而報廢。" % (\n'
            '                  (cfg.get("cap") or 0) / 3600, cfg.get("extend_eta_h") or 0.5, (cfg.get("extend") or 0) / 3600),\n'
            '              "- **每輪都做完整認證(比規格多做)**:規格只要求每輪 spindle 引擎 A,呢度每輪 certified 都行 `l3g2 --engine-b`(引擎 A + B)加 `certify4 --k 5`(5 色逐邊覆核),大約 3 分鐘一輪 ⇒ 無論停喺邊度,最後一個 certified 圖都已經係完整認證,唔使補做。",\n'
            '              "- **RECORD 觸發線**:Amber 講明目標 |G₂′| ≤ 716(|G₃′| = 1431);程式用嘅觸發線係 |G₂′| ≤ 720(⇔ |G₃′| = 2|G₂′| − 1 ≤ 1439 < 1441),**更闊**,716 一定包含喺內,唔會漏。",\n'
            '              "- 預算:%.0f CPU-h、%.0f h wall、最多 %s 輪。%s" % (cfg.get("cpu_cap_h", 160), (cfg.get("total_cap") or 86400) / 3600, cfg.get("rounds"),\n'
            '                  "".join("(%s Amber 授權放寬:CPU %s → %s CPU-h、wall %s → %s h)" % (c.get("when"), c.get("cpu_cap_h_from"), c.get("cpu_cap_h_to"), c.get("wall_h_from"), c.get("wall_h_to"))\n'
            '                          for c in (st.get("budget_changes") or []))), "",\n'
            '              "## 每輪帳", "",\n'
            '              "| 輪 | 步幅 | 目標 \\\\|S\\\\| | 結果 | 淨剪 | S_acc | \\\\|G₂′\\\\| | \\\\|G₃′\\\\| | 輪 wall (延長) | CPU-h | 擋路集大小 |",\n'
            '              "|---|---|---|---|---|---|---|---|---|---|---|"]\n'
            '        for r in self.rounds:\n'
            '            rw = r.get("wall_s") or 0\n'
            '            L.append("| %s | %s | %s | %s | %s | %s → %s | %s | %s | %.2f h%s | %.1f | %s |" % (\n'
            '                r.get("round"), r.get("step"), r.get("target_removed"), r.get("status"), r.get("net_removed"),\n'
            '                len(r.get("S_acc_before") or []), len(r.get("S_acc_after") or r.get("S_acc_before") or []),\n'
            '                r.get("G2p_n"), r.get("G3p_n"), rw / 3600,\n'
            '                (" (+%.2f)" % ((r.get("extended_s") or 0) / 3600)) if r.get("extended_s") else "", rw * W / 3600, r.get("B_sizes")))\n'
            '        if st.get("step_history"):\n'
            '            L += ["", "步幅減半歷史 (同一輪兩張都 SAT 就減半): %s" % st["step_history"]]\n'
            '        L += ["", "## 帳 (每張證書)", "",\n')
    # ---------- 9. 報告: 擋路集 → 雷區密度分析 ----------
    t = one(t,
            '        if st.get("B_sets"):\n'
            '            L += ["## 擋路集 (SAT 嘅收穫: 下一步嘅地圖)", "",\n'
            '                  "每個 B 都有一張逐邊覆核嘅 4 色染色證書 —— G₂ − B 有一個 col(u) ≠ col(v) 嘅 4 色染色 ⇒ **B 唔可以成集剪走**(入面至少一粒係 mono-pair 性質嘅必要頂點)。", ""]\n'
            '            L += ["- **%s**: |B| = %d, B = `%s`(染色證書 `%s`)" % (b["tag"], b["size"], b["B"], os.path.basename(b.get("witness_col") or "")) for b in st["B_sets"]]\n'
            '            L += [""]\n',
            '        prev_B = phase3d_B_sets(); ba = b_analysis(st.get("B_sets") or [], prev_B)\n'
            '        L += ["## 擋路集: 雷區密度隨深度點變 (Amber 要嘅數據)", "",\n'
            '              "每個 B 都有一張逐邊覆核嘅 4 色染色證書 —— G₂ − B 有一個 col(u) ≠ col(v) 嘅 4 色染色 ⇒ **B 唔可以成集剪走**(入面至少一粒係 mono-pair 性質嘅必要頂點)。", ""]\n'
            '        if st.get("B_sets"):\n'
            '            L += ["| 輪 | 嘗試 | 步幅 | \\\\|S\\\\| | \\\\|G₂′\\\\| | \\\\|B\\\\| | 其中喺 S_acc | 其中喺當輪新批 |", "|---|---|---|---|---|---|---|---|"]\n'
            '            L += ["| %s | %s | %s | %s | %s | %s | %s | %s |" % (x["round"], x["tag"], x["step"], x["S_size"], x["G2p"], x["size"], x["in_S_acc"], x["in_batch"]) for x in ba["by_set"]]\n'
            '            L += ["", "- Phase 3e: %d 個擋路集,平均 |B| = %s,並集 %d 粒。" % (ba["n"], ba["mean_size"], ba["union_size"])]\n'
            '            if ba["pairwise"]:\n'
            '                L += ["- Phase 3e 內部兩兩重疊(交集 / Jaccard):%s" % "; ".join("%s∩%s = %d (J = %s)" % (p["a"], p["b"], p["inter"], p["jaccard"]) for p in ba["pairwise"])]\n'
            '            else:\n'
            '                L += ["- 得一個擋路集,冇得計內部重疊。"]\n'
            '        else:\n'
            '            L += ["**Phase 3e 冇一個 SAT** —— 每一輪嘅第一張證書都 certified,所以冇擋路集。呢個本身就係數據:同 Phase 3d 一刀剪 80 三次全 SAT 對比,步幅細咗就冇撞到雷。", ""]\n'
            '        if prev_B:\n'
            '            L += ["- Phase 3d(|S| = 350 一刀剪 80)三個擋路集各 %s 粒,三個**互不重疊**,並集 %d 粒。" % ([b.get("size") for b in prev_B], ba["phase3d_union_size"])]\n'
            '            if ba["vs_phase3d"]:\n'
            '                L += ["- Phase 3e × Phase 3d 逐對重疊:%s" % "; ".join("%s∩%s = %d (J = %s)" % (p["phase3e"], p["phase3d"], p["inter"], p["jaccard"]) for p in ba["vs_phase3d"]),\n'
            '                      "- 兩個階段嘅擋路集並集交集 = **%d** 粒(Phase 3e 並集 %d,Phase 3d 並集 %d)⇒ %s。" % (\n'
            '                          ba["inter_with_phase3d_union"], ba["union_size"], ba["phase3d_union_size"],\n'
            '                          "同一批點反覆擋路" if ba["inter_with_phase3d_union"] > 0 else "擋路嘅唔係同一批點:同深度有關,唔係固定幾粒地雷")]\n'
            '        L += [""]\n'
            '        if st.get("B_sets"):\n'
            '            L += ["詳細名單:"]\n'
            '            L += ["- **%s** (round %s, 步幅 %s, |S| = %s): |B| = %d, B = `%s`(染色證書 `%s`)" % (\n'
            '                b["tag"], b.get("round"), b.get("step"), b.get("S_size"), b["size"], b["B"], os.path.basename(b.get("witness_col") or "")) for b in st["B_sets"]]\n'
            '            L += [""]\n')
    # ---------- 10. facts: 加 rounds / step_history / B_analysis ----------
    t = one(t,
            '            add("g2shrink3e.stop_reason", st.get("stop_reason"), None, "phase3e/runs/%s/state.json" % self.rid)\n',
            '            add("g2shrink3e.rounds", [{k: r.get(k) for k in ("round", "step", "status", "target_removed", "net_removed", "G2p_n", "G3p_n",\n'
            '                                                             "wall_s", "cap_s", "extended_s", "certified_tag", "B_sizes", "budget_before", "budget_after")} for r in self.rounds],\n'
            '                None, "phase3e/runs/%s/rounds.json" % self.rid)\n'
            '            add("g2shrink3e.step_history", st.get("step_history"), None, "phase3e/runs/%s/state.json" % self.rid,\n'
            '                "adaptive step: halved (20 -> 10 -> 5) whenever both certificates of a round came back SAT")\n'
            '            add("g2shrink3e.budget_changes", st.get("budget_changes") or [], None, "phase3e/runs/%s/state.json" % self.rid,\n'
            '                "operator-authorised budget changes during the run (probe3e was cleanly paused and resumed; cnc2k --resume kept every verified cube)")\n'
            '            add("g2shrink3e.B_analysis", b_analysis(st.get("B_sets") or [], phase3d_B_sets()), None,\n'
            '                "phase3e/runs/%s/state.json + phase3d/runs/p3d1_final/state.json" % self.rid,\n'
            '                "blocking-set density vs depth: |B| per round, pairwise Jaccard within Phase 3e, and overlap against the three Phase 3d sets at |S| = 350")\n'
            '            add("g2shrink3e.stop_reason", st.get("stop_reason"), None, "phase3e/runs/%s/state.json" % self.rid)\n')
    t = one(t,
            '            add("g2shrink3e.params", {"one_cut_removed": (st.get("config") or {}).get("target_removed"), "attempts_max": (st.get("config") or {}).get("attempts"),',
            '            add("g2shrink3e.params", {"step": (st.get("config") or {}).get("step"), "min_step": (st.get("config") or {}).get("min_step"),\n'
            '                                      "rounds_max": (st.get("config") or {}).get("rounds"), "attempts_per_round": (st.get("config") or {}).get("attempts_per_round"),')
    # ---------- 11. DECISION 段 ----------
    t = one(t,
            '            para = ("%s(%s;run %s,接力 Phase 3c r09a;Amber 設計修正:成本按證書計 ⇒ 一刀剪 80 粒,唔再分輪;輪上限 8 h + 自動延長 1 h;最多 3 張證書;預算 %.0f CPU-h / %.0f h wall;只加呢一段,其他原文不動):** %s。%s "\n'
            '                    "嘗試 %s;CPU-h %.1f / %.0f,wall %.2f h;停機原因:%s。%s報告 `phase3e/phase3e_results.md`。**未公開、未寄信、未 push、未上 Zenodo。**" % (\n'
            '                        marker, self.now, self.rid, (st.get("config") or {}).get("cpu_cap_h", 160), ((st.get("config") or {}).get("total_cap") or 86400) / 3600,\n'
            '                        head, body, [(x["tag"], x["status"], round((x.get("wall_s") or 0) / 3600, 2)) for x in self.attempts],\n',
            '            cfg = st.get("config") or {}\n'
            '            para = ("%s(%s;run %s,接力 Phase 3c r09a;Phase 3d 一刀剪 80 三次全 SAT ⇒ 退返細步幅:每輪剪 %s 粒、每輪最多 2 張證書、兩張都 SAT 就步幅減半(20→10→5)、排除集逐輪重置;"\n'
            '                    "每輪上限 %.0f h + 自動延長 ≤ %.0f h;最多 %s 輪;預算 %.0f CPU-h / %.0f h wall;只加呢一段,其他原文不動):** %s。%s "\n'
            '                    "每輪:%s;嘗試 %s;CPU-h %.1f / %.0f,wall %.2f h;停機原因:%s。%s報告 `phase3e/phase3e_results.md`。**未公開、未寄信、未 push、未上 Zenodo。**" % (\n'
            '                        marker, self.now, self.rid, cfg.get("step"), (cfg.get("cap") or 0) / 3600, (cfg.get("extend") or 0) / 3600, cfg.get("rounds"),\n'
            '                        cfg.get("cpu_cap_h", 160), (cfg.get("total_cap") or 86400) / 3600,\n'
            '                        head, body, [(r.get("round"), r.get("step"), r.get("status"), r.get("net_removed"), r.get("G2p_n")) for r in self.rounds],\n'
            '                        [(x["tag"], x["status"], round((x.get("wall_s") or 0) / 3600, 2)) for x in self.attempts],\n')
    t = one(t, '                head = "冇新證書(%d 次嘗試)" % len(self.attempts); body = "最新認證圖仍然係 Phase 3c 嘅 |G₃′| = %d。" % PREV_G3P',
            '                head = "冇新證書(%d 輪, %d 次嘗試)" % (len(self.rounds), len(self.attempts)); body = "最新認證圖仍然係 Phase 3c 嘅 |G₃′| = %d。" % PREV_G3P')
    # ---------- 12. MEMORY 段 ----------
    t = one(t,
            '                one = ("Phase 3e 完 (%s): run %s 一刀剪 %d 粒 (%s), **|G₂′| %d, |G₃′| %d**%s; 獨立重驗 %s (全部 %s 個 leaf drat-trim + %s 個 cake_lpr + cover + 審計 + L2″/L3″/完整性/spindle 兩引擎 + 5 色逐邊); "\n'
            '                       "CPU %.1f/%.0f CPU-h, wall %.2f h; 全套證書封存 %s; 報告 phase3e/phase3e_results.md; 未公開") % (\n'
            '                    self.now[:16], self.rid, len(fa["S"]) - 270, ", ".join("%s:%s" % (x["tag"], x["status"]) for x in self.attempts), fa["G2p_n"], fa["G3p_n"],\n',
            '                one = ("Phase 3e 完 (%s): run %s 小步慢行剪多 %d 粒 (%d 輪: %s), **|G₂′| %d, |G₃′| %d**%s; 獨立重驗 %s (全部 %s 個 leaf drat-trim + %s 個 cake_lpr + cover + 審計 + L2″/L3″/完整性/spindle 兩引擎 + 5 色逐邊); "\n'
            '                       "CPU %.1f/%.0f CPU-h, wall %.2f h; 全套證書封存 %s; 報告 phase3e/phase3e_results.md; 未公開") % (\n'
            '                    self.now[:16], self.rid, len(fa["S"]) - 270, len(self.rounds),\n'
            '                    ", ".join("r%s(步幅%s):%s" % (r.get("round"), r.get("step"), r.get("status")) for r in self.rounds), fa["G2p_n"], fa["G3p_n"],\n')
    t = one(t,
            '                one = "Phase 3e 完 (%s): run %s %d 次嘗試冇新證書 (%s); 最新認證圖仍然係 Phase 3c |G₃′| %d; 停: %s; 報告 phase3e/phase3e_results.md" % (\n'
            '                    self.now[:16], self.rid, len(self.attempts), ", ".join("%s:%s" % (x["tag"], x["status"]) for x in self.attempts), PREV_G3P, (st.get("stop_reason") or "")[:120])\n',
            '                one = "Phase 3e 完 (%s): run %s %d 輪 %d 次嘗試冇新證書 (%s); 最新認證圖仍然係 Phase 3c |G₃′| %d; 停: %s; 報告 phase3e/phase3e_results.md" % (\n'
            '                    self.now[:16], self.rid, len(self.rounds), len(self.attempts),\n'
            '                    ", ".join("r%s(步幅%s):%s" % (r.get("round"), r.get("step"), r.get("status")) for r in self.rounds), PREV_G3P, (st.get("stop_reason") or "")[:120])\n')
    t = one(t,
            '            block = ("**Phase 3e(%s;Mega-Prompt「小步慢行」;源碼 `Desktop\\\\spindle\\\\phase3e\\\\`,WSL `~/hadwiger/phase3e/`;run `%s`):** %s。"\n'
            '                     "設計修正:成本按證書計(march d=14 每次都係 ~16 384 cube)⇒ 一刀剪 80 粒;輪上限 8 h + 剩餘 ≤ 0.5 h 自動延長 ≤ 1 h(Phase 3c round 10 就係差 9 分鐘被 3.5 h 上限殺死);最多 3 張證書 a/b/c,SAT 就 witness 出擋路集 B 再補足重試。"\n'
            '                     "%s重跑收爐:`phase3e/resume3e.sh`(probe3e --resume → finalize3e 幂等)。") % (\n'
            '                         st.get("started"), self.rid, one,\n'
            '                         ("擋路集 %s。" % [(b["tag"], b["size"]) for b in st.get("B_sets") or []]) if st.get("B_sets") else "")\n',
            '            block = ("**Phase 3e(%s;Mega-Prompt「小步慢行」;源碼 `Desktop\\\\spindle\\\\phase3e\\\\`,WSL `~/hadwiger/phase3e/`;run `%s`):** %s。"\n'
            '                     "設計:Phase 3d 一刀剪 80 三次全 SAT ⇒ 退返每輪剪 %s 粒;每輪最多 2 張證書(a、b),兩張都 SAT 就**步幅減半**(20→10→5),減到 5 仲失敗就停;"\n'
            '                     "排除集**逐輪重置**(一粒點喺 |S|=350 擋路唔代表喺 |S|=290 擋路,冇永久排除);每輪上限 6 h(a+b 共用)+ 剩餘 ≤ 0.5 h 自動延長 ≤ 1 h;每輪 certified 都即場行齊 l3g2 --engine-b + certify4 --k 5。"\n'
            '                     "%s重跑收爐:`phase3e/resume3e.sh`(probe3e --resume → finalize3e 幂等);probe3e.py 係 probe3d.Probe 嘅子類(campaign / keep 政策 / 延長邏輯一字不改)。") % (\n'
            '                         st.get("started"), self.rid, one, (st.get("config") or {}).get("step"),\n'
            '                         ("擋路集 %s。" % [(b.get("round"), b["tag"], b["size"]) for b in st.get("B_sets") or []]) if st.get("B_sets") else "")\n')
    t = one(t,
            '            b2 = ("**Phase 3e(%s,`phase3e/`)—— 一刀剪 80 粒:** %d/%d 張證書 certified;每張 wall %s h、每 cube s+v %s s、最長 cube %s s;%s。"\n'
            '                  "教訓:剪 30 同剪 80 一樣貴(cube 數一樣),所以應該一刀剪到目標;cnc2k budget-stop 之後 `--resume` 可以無損續(cnc2k 會 drain 住嘅 cube 先停)。") % (\n'
            '                self.now[:10], len(cert), len(self.attempts), [round((x.get("wall_s") or 0) / 3600, 2) for x in cert], [x.get("mean_sv_s") for x in cert], [x.get("max_solve_s") for x in cert],\n'
            '                ("|G₃′| = %d%s" % (fa["G3p_n"], " < %d 紀錄候選" % RECORD_G3P if self.rec_ok else "")) if fa else "三次都 SAT / 冇證書, 擋路集 %s" % [(b["tag"], b["size"]) for b in st.get("B_sets") or []])\n',
            '            ba2 = b_analysis(st.get("B_sets") or [], phase3d_B_sets())\n'
            '            b2 = ("**Phase 3e(%s,`phase3e/`)—— 每輪剪 %s 粒(步幅 %s):** %d/%d 張證書 certified,%d/%d 輪 certified;每張 wall %s h、每 cube s+v %s s、最長 cube %s s;%s。"\n'
            '                  "雷區密度:每輪 |B| = %s,Phase 3e 並集 %d 粒,同 Phase 3d(|S|=350 一刀)三個 B 嘅並集交集 %d 粒 ⇒ %s。"\n'
            '                  "教訓:cube 數同剪幾多粒無關(march d=14 都係 ~16 384),但**SAT 風險同步幅有關**;cnc2k budget-stop 之後 `--resume` 可以無損續。") % (\n'
            '                self.now[:10], (st.get("config") or {}).get("step"), [r.get("step") for r in self.rounds],\n'
            '                len(cert), len(self.attempts), len([r for r in self.rounds if r.get("status") == "certified"]), len(self.rounds),\n'
            '                [round((x.get("wall_s") or 0) / 3600, 2) for x in cert], [x.get("mean_sv_s") for x in cert], [x.get("max_solve_s") for x in cert],\n'
            '                ("|G₃′| = %d%s" % (fa["G3p_n"], " < %d 紀錄候選" % RECORD_G3P if self.rec_ok else "")) if fa else "冇證書, 擋路集 %s" % [(b.get("round"), b["tag"], b["size"]) for b in st.get("B_sets") or []],\n'
            '                [x["size"] for x in ba2["by_set"]], ba2["union_size"], ba2["inter_with_phase3d_union"],\n'
            '                "同一批點反覆擋路" if ba2["inter_with_phase3d_union"] > 0 else "擋路嘅唔係同一批固定點")\n')
    # ---------- 13. MEMORY.md 索引行 (要保住 Phase 3d 嘅 trim, 加 Phase 3e) ----------
    t = one(t,
            '                    head = l.split(";Phase 3b 三輪")[0].split(";**Phase 3c")[0].split(";Phase 3c")[0].split(";**Phase 3e")[0].split(";Phase 3b/3c")[0]',
            '                    head = l.split(";Phase 3b 三輪")[0].split(";**Phase 3c")[0].split(";Phase 3c")[0].split(";**Phase 3d")[0].split(";**Phase 3e")[0].split(";Phase 3b/3c")[0]')
    t = one(t,
            '                    lines[i] = head + ";Phase 3b/3c 已收爐(|G₃′| 1591,`phase3c/phase3c_results.md`);**Phase 3e 完(%s)**:%s;報告 `phase3e/phase3e_results.md`;冇背景任務" % (self.now[:16], tail_txt)',
            '                    lines[i] = head + ";Phase 3b/3c 已收爐(|G₃′| 1591,`phase3c/phase3c_results.md`);Phase 3d 一刀剪 80 三次全 SAT(冇新證書);**Phase 3e 完(%s)**:%s;報告 `phase3e/phase3e_results.md`;冇背景任務" % (self.now[:16], tail_txt)')
    # ---------- 14. 冇新證書分支: 報告要有輪數 ----------
    t = one(t,
            '            L += ["**冇新證書**:%d 次嘗試全部冇拎到 certified;最新認證圖仍然係 Phase 3c 嘅 |G₃′| = %d(封存喺 `../final/`)。停機原因:%s" % (\n'
            '                len(self.attempts), PREV_G3P, st.get("stop_reason"))]',
            '            L += ["**冇新證書**:%d 輪 / %d 次嘗試全部冇拎到 certified;最新認證圖仍然係 Phase 3c 嘅 |G₃′| = %d(封存喺 `../final/`)。停機原因:%s" % (\n'
            '                len(self.rounds), len(self.attempts), PREV_G3P, st.get("stop_reason"))]')
    # ---------- 14b. 修 write_reverify 嘅格式化 bug (由 finalize3d.py 原封不動繼承落嚟) ----------
    #   reverify.sh template 入面嘅佔位符次序係: %d(leaf 數) → %s(S) → %d(leaf 數) → %s(tag) → %s(tag) → %s(S), 共 6 個;
    #   但原本淨係俾 5 個 argument 而且次序倒轉 (S 撞正第一個 %d) ⇒ TypeError: %d format: a real number is required, not str。
    #   Phase 3d 三次全 SAT、冇拎到證書, 所以永遠冇行到 archive() → write_reverify(), 個 bug 一直冇爆出嚟;
    #   Phase 3e round 5 拎到證書, 收爐封存嗰陣就爆咗 (2026-09-10 00:08, finalize3e rc=1)。phase3d/finalize3d.py 仲有同一個 bug。
    t = one(t, '""" % (S, fa["leaves"], tag, tag, S)', '""" % (fa["leaves"], S, fa["leaves"], tag, tag, S)')
    # ---------- 15. 文件頭 ----------
    t = one(t, "finalize3e.py —— Phase 3e 收爐 / RECORD 程序 (probe3e 停機之後自動跑; 幂等, 可重跑):",
            "finalize3e.py —— Phase 3e 收爐 / RECORD 程序 (probe3e 停機之後自動跑; 幂等, 可重跑)\n"
            "  **機械生成**: 由 phase3d/finalize3d.py 經 phase3e/make_finalize3e.py 改名 + 加「輪」帳而成; diff 喺 phase3e/finalize3e.diff。唔好手改呢個檔, 改 make_finalize3e.py 再生成。")
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.expanduser("~/hadwiger/phase3d/finalize3d.py"))
    ap.add_argument("--out", default=os.path.expanduser("~/hadwiger/phase3e/finalize3e.py"))
    ap.add_argument("--check", action="store_true", help="只係生成同對比, 唔覆寫 (rc=1 代表同碟上唔同)")
    a = ap.parse_args()
    src = open(a.src, encoding="utf-8").read()
    out = build(src)
    d = "".join(difflib.unified_diff(src.splitlines(True), out.splitlines(True), fromfile="phase3d/finalize3d.py", tofile="phase3e/finalize3e.py"))
    dp = os.path.join(os.path.dirname(a.out), "finalize3e.diff")
    if a.check:
        old = open(a.out, encoding="utf-8").read() if os.path.exists(a.out) else None
        same = (old == out)
        print("check: %s (%d 行 diff)" % ("一樣" if same else "!! 唔一樣", d.count("\n")))
        sys.exit(0 if same else 1)
    open(a.out, "w", encoding="utf-8", newline="\n").write(out)
    open(dp, "w", encoding="utf-8", newline="\n").write(d)
    py_compile.compile(a.out, doraise=True)
    print("生成 %s (%d 位元組, py_compile ok); diff %s (%d 行)" % (a.out, len(out), dp, d.count("\n")))


if __name__ == "__main__":
    main()
