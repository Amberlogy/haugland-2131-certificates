#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probe3e.py —— Phase 3e「小步慢行」: 由 Phase 3c r09a (S_acc = 270, |G₂′| = 796, |G₃′| = 1591) 接力, **每輪剪 20 粒** (796 → 776 → 756 → 736 → 716)
  Phase 3d 讀法 (Amber 2026-09-08): 由 796 一刀剪 80, 三次全部 SAT, 三個擋路集各 30 粒而且互不重疊 ⇒ 唔係「有幾粒地雷」, 而係喺呢個深度任何 80 粒嘅選法都約有三成剪唔得 ⇒ 一刀太大, 退返細步幅。
  流程 (每輪, 最多 --rounds 6 輪):
    attempt a: S = S_acc + 候選表下 step 粒 → buildg2 → march_cu d=14 → cnc2k (leaf 證明全部保留 keep-dir)
      UNSAT/certified → 完整認證 (l3g2 --engine-b: L2″ + L3″ + exactfield --complete + spindle 引擎 A 同 B; 再 certify4 --k 5 逐邊覆核 5 色) → S_acc += step; keep 換新輪 (舊輪 keep 喺新輪 certified 之後先刪) → 下一輪
      SAT → 4 色染色證書逐邊覆核 + witness_g2 貪心放返 → 擋路集 B (零 solver)
    attempt b: 排除 B, 由候選表補足返到 |S| = |S_acc| + step → 再證一次; SAT → B′
    自適應步幅: 同一輪兩張都 SAT ⇒ 步幅減半 (20 → 10 → 5), 用新步幅開下一輪 (仍然計入 --rounds 上限); 步幅去到 --min-step 5 仍然兩張都 SAT → 停
  排除集**逐輪重置**: 一粒點喺 |S| = 350 擋路, 唔代表喺 |S| = 290 擋路 ⇒ 只喺當輪排除, 唔准永久排除 (同 Phase 3c 嘅 perma_excluded 唔同, 呢度冇)
  RECORD: 任何一輪 certified 之後 |G₂′| ≤ RECORD_G2P (720 ⇔ |G₃′| = 2|G₂′| − 1 ≤ 1439 < 1441) ⇒ 即刻停, 交俾 finalize3e 做 RECORD 程序 (完整認證每輪都做咗, 見 certify())
    Amber 講明嘅目標係 |G₂′| ≤ 716 (|G₃′| ≤ 1431); 呢度用 720 做觸發線係**更闊**嘅條件 (720 ⇒ 1439 已經 < 1441), 716 一定包含喺內, 唔會漏
  預算: 總 --cpu-cap-h 500 CPU-h (= Σ 每張證書 wall × workers; Amber 2026-09-08 由 160 放寬), 總 --total-cap 60 h wall (由 24 放寬); 每**輪** --cap 6 h (a + b 共用), 每輪自動延長總額 ≤ --extend 1 h (cnc2k budget-stop 之後估計剩 ≤ --extend-eta-h 0.5 h 先延長)
  磁碟: keep-dir /mnt/d/hadwiger/phase3e/keep/<tag>; SAT 即刪; budget-stop / hard-killed **保留** (cnc2k --resume 嘅本錢); certified 保留到下一輪 certified 為止; D: < 300 GB 即停
  重用 (唔重寫現成腳本): campaign / colouring_cert / pick_S / load_seed / certify_final 全部由 phase3d/probe3d.py 直接繼承 (連 extend_decision、keep 政策、keep-repair 一齊)
用法: python3 probe3e.py --run-id p3e1_step --seed-run ~/hadwiger/phase3c/runs/p3c1_shrink --batches ~/hadwiger/phase3b/batches_g2.json --out ~/hadwiger/phase3e/runs/p3e1_step
                         [--rounds 6] [--step 20] [--min-step 5] [--attempts-per-round 2] [--workers 14] [--cap 21600] [--extend 3600] [--extend-eta-h 0.5]
                         [--total-cap 86400] [--cpu-cap-h 160] [--timeout 900] [--depth 14] [--proof-dir /dev/shm/p3e1_step] [--keep-root /mnt/d/hadwiger/phase3e/keep]
                         [--resume] [--ack-operator] [--dry-run]
"""
import sys, os, json, time, argparse, subprocess, shutil

if not __debug__:
    sys.exit("!! 唔准用 python -O")

PH2 = os.path.expanduser("~/hadwiger/phase2")
PH3B = os.path.expanduser("~/hadwiger/phase3b")
PH3C = os.path.expanduser("~/hadwiger/phase3c")
PH3D = os.path.expanduser("~/hadwiger/phase3d")
PH3E = os.path.expanduser("~/hadwiger/phase3e")
sys.path.insert(0, PH3D)
import probe3d                                                              # noqa: E402  (Phase 3d 審核過: campaign + extend_decision + keep 政策 + certify_final)
from probe3d import dir_stats, free_gb, log, RECORD_G2P, PROJ_FACTOR, PY    # noqa: E402
import witness_g2                                                           # noqa: E402  (probe3d 已經 sys.path.insert PH3B)

TARGET_G2P_AMBER = 716          # Amber 講明嘅目標 (|G₃′| = 1431); 觸發線用更闊嘅 RECORD_G2P = 720 (|G₃′| = 1439 < 1441)


class Probe3E(probe3d.Probe):
    """Phase 3c 嘅輪結構 + Phase 3d 嘅證書機器 (延長 / keep 保留 / keep-repair) + 自適應步幅。"""

    # ---------------- 起手 ----------------
    def __init__(self, a):
        self.a = a
        self.out = os.path.abspath(a.out); os.makedirs(self.out, exist_ok=True)
        self.bj = json.load(open(a.batches)); self.ordering = self.bj["ordering"]; self.P2 = set(self.bj["P2"])
        self.g2 = probe3d.G2()
        self.state_p = os.path.join(self.out, "state.json"); self.rounds_p = os.path.join(self.out, "rounds.json")
        self.att_p = os.path.join(self.out, "attempts.json"); self.status_p = os.path.join(self.out, "status.json")
        self.extend_round_max = float(a.extend)                              # 每輪嘅延長總額 (a + b 共用)
        if a.resume and os.path.exists(self.state_p):
            self.st = json.load(open(self.state_p))
            raw = json.load(open(self.rounds_p)) if os.path.exists(self.rounds_p) else []
            self.rounds = [x for x in raw if x["round"] <= self.st["round_done"]]
            if len(raw) != len(self.rounds):
                log("resume: 掉走 %d 個未結算嘅輪記錄 (round > round_done=%d); 該輪由頭再開 (已有 cnc_<tag>/state.json 嘅嘗試會 cnc2k --resume, keep 目錄照用)" % (
                    len(raw) - len(self.rounds), self.st["round_done"]))
            if self.st.get("needs_operator") and not a.ack_operator:
                sys.exit("!! 上次停係要人手睇: %s —— 唔准自動 --resume; 人手睇完要續跑就加 --ack-operator" % self.st.get("stop_reason"))
            if self.st.get("target_reached"):
                sys.exit("!! 已到目標 (record candidate): %s —— 唔准再剪, 跟住行 finalize3e" % self.st.get("stop_reason"))
            self.st["needs_operator"] = False
            self.st.setdefault("prior_wall_by_tag", {})
            for rr_ in [x for x in raw if x["round"] > self.st["round_done"]]:   # 掉走嘅輪入面已完成嘅嘗試, wall 唔可以消失 (計返入 CPU 預算)
                for x in rr_.get("attempts", []):
                    if x.get("wall_s"):
                        self.st["prior_wall_by_tag"][x["tag"]] = max(float(x["wall_s"]), float(self.st["prior_wall_by_tag"].get(x["tag"], 0)))
            self.st["elapsed_before_s"] = self.st.get("elapsed_s", 0)
            self.st["stop_reason"] = None
            for k in ("paused", "finished"):
                self.st.pop(k, None)
            self.st["resumes"] = self.st.get("resumes", 0) + 1; self.st["config_resume"] = dict(vars(a))
            log("resume #%d: round_done %d, 步幅 %d, S_acc %d 粒 (|G₂′| %d), 之前用時 %.2f h, CPU 已用 %.1f / %.0f CPU-h, kept_certified %s" % (
                self.st["resumes"], self.st["round_done"], self.st["step"], len(self.st["S_acc"]), self.g2.n - len(self.st["S_acc"]),
                self.st["elapsed_before_s"] / 3600, self.cpu_h_used(), a.cpu_cap_h, self.st.get("kept_certified")))
        else:
            assert not os.path.exists(self.state_p), "out 已有 state.json (要 --resume 或者換 run-id)"
            assert a.seed_run, "首跑要 --seed-run (Phase 3c run 目錄)"
            seed = self.load_seed(a.seed_run)                                # 繼承 probe3d.load_seed: 認 certified + l3_ok + S == S_acc + bundle/summary 對數
            self.st = {"run_id": a.run_id, "started": time.strftime("%Y-%m-%d %H:%M:%S"), "elapsed_before_s": 0.0,
                       "S_acc": seed["S_acc"], "round_done": 0, "step": a.step, "step_history": [], "B_sets": [],
                       "stop_reason": None, "best": None, "target_reached": False, "record_candidate": False,
                       "config": dict(vars(a)), "seed": seed["prov"], "resumes": 0, "needs_operator": False,
                       "prior_wall_by_tag": {}, "kept_certified": []}
            self.rounds = []
            log("seed: 由 %s 接力 —— %s (S_acc %d 粒, |G₂′| %d, |G₃′| %d; bundle sha %s…, l3 all_ok %s, leaf 證明 %s)" % (
                seed["prov"]["run_id"], seed["prov"]["last_certified_tag"], len(self.st["S_acc"]), seed["prov"]["G2p_n"], seed["prov"]["G3p_n"],
                seed["prov"]["bundle_sha256"][:16], seed["prov"]["l3_all_ok"], seed["prov"]["leaf_proofs_dir"]))
            log("計劃: 每輪剪 %d 粒 → %s; 目標 |G₂′| ≤ %d (Amber) / 觸發線 %d (⇔ |G₃′| ≤ 1439 < 1441); 最多 %d 輪, 每輪最多 %d 張證書" % (
                a.step, " → ".join(str(self.g2.n - (len(self.st["S_acc"]) + a.step * i)) for i in range(1, 5)),
                TARGET_G2P_AMBER, RECORD_G2P, a.rounds, a.attempts_per_round))
        self.T0 = time.time(); self.cur = {}

    # ---------------- 帳 (輪為單位) ----------------
    def cpu_h_used(self):
        return round(sum((x.get("wall_s") or 0) for r in self.rounds for x in r.get("attempts", [])) * self.a.workers / 3600, 2)

    def last_certified_wall_h(self):
        w = [x["wall_s"] for r in self.rounds for x in r.get("attempts", []) if x.get("status") == "certified" and x.get("wall_s")]
        return (w[-1] / 3600) if w else None

    def proj_wall_h(self):
        w = self.last_certified_wall_h()
        return round(PROJ_FACTOR * w, 3) if w else self.a.proj_first_h

    def all_attempts(self):
        return [x for r in self.rounds for x in r.get("attempts", [])]

    def step(self, msg):
        try:
            open(os.path.join(PH3E, "STEP.txt"), "w").write(msg)
        except Exception:
            pass

    # ---------------- 存檔 ----------------
    def save(self, light=False):
        st = self.st; st["elapsed_s"] = round(self.elapsed(), 1); st["updated_str"] = time.strftime("%Y-%m-%d %H:%M:%S")
        st["cpu_h_used"] = self.cpu_h_used()
        json.dump(st, open(self.state_p + ".tmp", "w"), indent=1); os.replace(self.state_p + ".tmp", self.state_p)
        if light:                                                            # cnc2k 等待期間: 只寫 state.json (elapsed_s 保鮮), 唔行 D:
            return
        json.dump(self.rounds, open(self.rounds_p + ".tmp", "w"), indent=1); os.replace(self.rounds_p + ".tmp", self.rounds_p)
        json.dump(self.all_attempts(), open(self.att_p + ".tmp", "w"), indent=1); os.replace(self.att_p + ".tmp", self.att_p)
        keys = ("tag", "round", "attempt", "removed", "status", "n_cubes", "leaves", "mean_solve_s", "mean_sv_s", "max_solve_s",
                "wall_s", "extended_s", "B_size", "l3_ok", "engine_b_run", "col5_ok", "G2p_n", "G3p_n", "keep", "settled")
        summ = [{k: r.get(k) for k in ("round", "step", "status", "net_removed", "G2p_n", "G3p_n", "wall_s", "cap_s", "certified_tag")}
                | {"attempts": [{k: x.get(k) for k in keys} for x in r.get("attempts", [])], "B_sets": r.get("B_sets"), "B_sizes": [len(b) for b in (r.get("B_sets") or [])]}
                for r in self.rounds]
        status = {"run_id": st["run_id"], "started": st["started"], "updated_str": st["updated_str"], "elapsed_s": st["elapsed_s"], "total_cap_s": self.a.total_cap,
                  "round_done": st["round_done"], "rounds_max": self.a.rounds, "step": st["step"], "step_history": st.get("step_history"),
                  "attempts_per_round": self.a.attempts_per_round, "S_acc_size": len(st["S_acc"]),
                  "G2p_n": self.g2.n - len(st["S_acc"]), "G3p_n": 2 * (self.g2.n - len(st["S_acc"])) - 1,
                  "target_G2p_amber": TARGET_G2P_AMBER, "record_G2p": RECORD_G2P,
                  "current": self.cur, "stop_reason": st["stop_reason"], "best": st.get("best") or {},
                  "target_reached": st.get("target_reached"), "record_candidate": st.get("record_candidate"),
                  "cpu_h_used": st["cpu_h_used"], "cpu_cap_h": self.a.cpu_cap_h, "cpu_h_remaining": round(self.cpu_h_remaining(), 2),
                  "proj_next_round_wall_h": self.proj_wall_h(), "B_sets": st.get("B_sets"),
                  "kept_certified": st.get("kept_certified"), "keep_root": self.a.keep_root,
                  "keep_stats": {t: dir_stats(os.path.join(self.a.keep_root, t)) for t in (st.get("kept_certified") or [])},
                  "seed": st.get("seed"), "resumes": st.get("resumes", 0), "rounds": summ}
        json.dump(status, open(self.status_p + ".tmp", "w"), indent=1, ensure_ascii=False); os.replace(self.status_p + ".tmp", self.status_p)
        self.write_ledger()

    def write_ledger(self):
        W = self.a.workers; st = self.st; g2 = self.g2
        L = ["# ledger_g2.md —— Phase 3e 小步慢行帳 (run %s, 接力 %s %s; 更新 %s)" % (
                st["run_id"], (st.get("seed") or {}).get("run_id"), (st.get("seed") or {}).get("last_certified_tag"), time.strftime("%Y-%m-%d %H:%M:%S")), "",
             "S_acc (已認證可成集剪走) = %d 粒 → |G₂′| = %d, |G₃′| = %d; 而今步幅 %d (歷史 %s); round_done %d / %d; 用時 %.2f h / %.0f h; CPU-h (Σ 證書 wall × %d) %.1f / %.0f; 目標 |G₂′| ≤ %d (觸發線 %d); keep %s%s" % (
                 len(st["S_acc"]), g2.n - len(st["S_acc"]), 2 * (g2.n - len(st["S_acc"])) - 1, st["step"], st.get("step_history"), st["round_done"], self.a.rounds,
                 self.elapsed() / 3600, self.a.total_cap / 3600, W, self.cpu_h_used(), self.a.cpu_cap_h, TARGET_G2P_AMBER, RECORD_G2P, st.get("kept_certified"),
                 ("; **停: %s**" % st["stop_reason"]) if st["stop_reason"] else ""), "",
             "| 輪 | 步幅 | 嘗試 | |S| | 結果 | cube | leaf | 每 cube solve (s) | 每 cube s+v (s) | ×G₂recon | 最長 cube (s) | wall (延長) | CPU-h | leaf 證明保留 | B (擋路集) | |G₂′| | |G₃′| | L2″/L3″/完整/spindle | 5 色 |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in self.rounds:
            for x in r.get("attempts", []):
                kp = x.get("keep") or {}
                L.append("| %d | %d | %s | %d | %s | %s | %s | %s | %s | %s | %s | %s s (%.2f h%s) | %.1f | %s | %s | %s | %s | %s | %s |" % (
                    r["round"], r["step"], x["tag"], x["removed"], x["status"], x.get("n_cubes", "—"), x.get("leaves", "—"), x.get("mean_solve_s", "—"),
                    x.get("mean_sv_s", "—"), x.get("x_G2recon_sv", "—"), x.get("max_solve_s", "—"), x.get("wall_s", "—"), (x.get("wall_s") or 0) / 3600,
                    (", 延長 %.2f h" % ((x.get("extended_s") or 0) / 3600)) if x.get("extended_s") else "", (x.get("wall_s") or 0) * W / 3600,
                    ("%s/%s (%s GB)%s" % (kp.get("kept_leaves"), x.get("leaves"), kp.get("gb"),
                                          (" 已刪(%s 已認證)" % kp["deleted_after_next_certified"]) if kp.get("deleted_after_next_certified") else ("" if kp.get("on_disk", True) else " 已刪"))) if kp else "—",
                    ("|B|=%d %s" % (x["B_size"], x["witness"]["blocked_min"])) if x.get("witness") else "—",
                    x["cnf"]["n_remaining"] if x.get("cnf") else "—", x.get("G3p_n", "—"),
                    (("✓" + (" (A+B)" if x.get("engine_b_run") else " (A)")) if x.get("l3_ok") else "!!") if x["status"] == "certified" else "—",
                    ("✓ (%s 條邊)" % (x.get("col5") or {}).get("edges_checked")) if x.get("col5_ok") else ("—" if x.get("col5_ok") is None else "!!")))
            L.append("| %d | %d | **輪結算** | — | **%s** | — | — | — | — | — | — | %.2f h | — | — | B 集合 %s | %s | %s | 淨剪 %s (S_acc %d → %d) | — |" % (
                r["round"], r["step"], r.get("status"), (r.get("wall_s") or 0) / 3600, [len(b) for b in (r.get("B_sets") or [])], r.get("G2p_n", "—"), r.get("G3p_n", "—"),
                r.get("net_removed"), len(r["S_acc_before"]), len(r.get("S_acc_after", r["S_acc_before"]))))
        if st.get("B_sets"):
            L += ["", "## 擋路集 (每個都有逐邊覆核嘅 4 色染色證書: G₂ − B 有 col(u) ≠ col(v) 嘅染色 ⇒ B 唔可以成集剪走)"]
            L += ["- round %d %s (步幅 %d, |S| = %d): |B| = %d, B = %s" % (b["round"], b["tag"], b["step"], b["S_size"], len(b["B"]), b["B"]) for b in st["B_sets"]]
        open(os.path.join(self.out, "ledger_g2.md"), "w").write("\n".join(L) + "\n")

    # ---------------- 認證 (certified 之後) ----------------
    def certify(self, rec):
        """每一輪都做**完整**認證, 直接用 Phase 3d 審核過嘅 certify_final:
             l3g2 --engine-b —— L2″ + L3″ + exactfield --complete + spindle 引擎 A **同** 引擎 B
             certify4 --k 5  —— G₃′ 5 色染色, 逐邊覆核
        Amber 嘅 Phase 3e 規格淨係要求每輪「引擎 A」, RECORD 先要「兩個引擎 + 5 色」。呢度每輪都做齊,
        係**多做咗**唔係少做: 兩樣加埋大約 3 分鐘 (Phase 3c 量過 l3g2 --engine-b ≈ 134 s), 對 4–6 h 一輪嚟講可以忽略,
        換嚟嘅係「無論停喺邊度,最後一個 certified 圖都已經係完整認證」—— 停機規則要求嘅封存唔使補做。"""
        return self.certify_final(rec)

    # ---------------- 主循環 ----------------
    def run(self):
        a = self.a; st = self.st; g2 = self.g2
        while st["round_done"] < a.rounds and not st["stop_reason"]:
            if os.path.exists(os.path.join(self.out, "PAUSE")):                     # 乾淨暫停旗 (輪與輪之間停, 唔收爐; resume3e.sh 續)
                os.remove(os.path.join(self.out, "PAUSE"))
                st["paused"] = True; st["stop_reason"] = "PAUSED by operator after round %d (PAUSE 旗) —— 用 resume3e.sh 續" % st["round_done"]; break
            r = st["round_done"] + 1; step = int(st["step"])
            proj = self.proj_wall_h(); rem_cpu_h = self.cpu_h_remaining(); rem_wall_h = self.remaining_total() / 3600
            if r > 1 and rem_cpu_h / a.workers < proj:
                st["stop_reason"] = "CPU 預算: 已用 %.1f / %.0f CPU-h, 剩 %.1f CPU-h = %.2f h wall < 預測下一輪 %.2f h → 唔開 round %d" % (
                    self.cpu_h_used(), a.cpu_cap_h, rem_cpu_h, rem_cpu_h / a.workers, proj, r); break
            if r > 1 and rem_wall_h < proj + 0.5:
                st["stop_reason"] = "總 wall 上限 %.0f h: 已用 %.2f h, 剩 %.2f h < 預測下一輪 %.2f h + 0.5 → 唔開 round %d" % (
                    a.total_cap / 3600, self.elapsed() / 3600, rem_wall_h, proj, r); break
            cf = free_gb("/mnt/c"); df = free_gb("/mnt/d")
            if (cf is not None and cf < 25) or (df is not None and df < 300) or not os.path.ismount("/mnt/d"):
                st["stop_reason"] = "磁碟紀律: C: 剩 %s GB (要 ≥ 25) / D: 剩 %s GB (要 ≥ 300, keep 所在, ismount %s) → 停" % (cf, df, os.path.ismount("/mnt/d")); break
            S_acc = set(st["S_acc"]); a.target_removed = len(S_acc) + step
            if a.target_removed > len(self.ordering):
                st["needs_operator"] = True
                st["stop_reason"] = "!! 候選表得 %d 粒, 開唔到 |S| = %d 嘅一輪 —— 停, 要人手睇" % (len(self.ordering), a.target_removed); break
            cap_round = min(a.cap, self.remaining_total() - 600, max(600.0, rem_cpu_h * 3600 / a.workers))
            if r == 1:
                cap_round = min(a.cap, self.remaining_total() - 600)                # 第一輪: 唔俾預算細規則斬 (CPU 上限係用嚟決定開唔開新一輪)
            t_round = time.time()
            rr = {"round": r, "step": step, "S_acc_before": sorted(S_acc), "attempts": [], "B_sets": [], "excluded_this_round": [],
                  "started": time.strftime("%Y-%m-%d %H:%M:%S"), "cap_s": round(cap_round), "extend_max_s": self.extend_round_max,
                  "target_removed": a.target_removed, "target_G2p": g2.n - a.target_removed, "target_G3p": 2 * (g2.n - a.target_removed) - 1,
                  "budget_before": {"cpu_h_used": self.cpu_h_used(), "cpu_h_remaining": round(rem_cpu_h, 2),
                                    "wall_used_h": round(self.elapsed() / 3600, 3), "wall_remaining_h": round(rem_wall_h, 3), "proj_wall_h": proj}}
            self.rounds.append(rr); self.save()
            log("===== round %d/%d (步幅 %d): S_acc %d + %d → |S| = %d, |G₂′| = %d, |G₃′| = %d %s; 輪上限 %.2f h (+延長 ≤ %.2f h, 預測 %.2f h); CPU 已用 %.1f / %.0f; wall 剩 %.1f h =====" % (
                r, a.rounds, step, len(S_acc), step, a.target_removed, g2.n - a.target_removed, 2 * (g2.n - a.target_removed) - 1,
                "✓ < 1441" if 2 * (g2.n - a.target_removed) - 1 < 1441 else "(未到 1441)", cap_round / 3600, self.extend_round_max / 3600, proj,
                self.cpu_h_used(), a.cpu_cap_h, rem_wall_h))
            excl = set(); ext_used_round = 0.0; status = None; certified_rec = None
            for ai in range(a.attempts_per_round):
                rem = cap_round - (time.time() - t_round)
                if rem < 900:
                    status = "cap-exhausted"; log("round %d: 輪上限剩 %.0f s < 900 s, 唔開第 %d 張證書" % (r, rem, ai + 1)); break
                tag = "r%02d%s" % (r, "abcdefgh"[ai])
                if ai == 0:
                    S_try, added = self.pick_S(S_acc, excl)
                    kind = "第一刀 (S_acc %d + 候選表下 %d 粒)" % (len(S_acc), len(added))
                else:
                    prev = rr["attempts"][-1]
                    S_try, added = self.pick_S(set(prev["S"]) - excl, excl)
                    kind = "排除本輪擋路集 %d 粒後由候選表補足 %d 粒" % (len(excl), len(added))
                if len(S_try) != a.target_removed:                                  # 補唔足唔可以靜靜雞縮水
                    status = "error"; st["needs_operator"] = True
                    st["stop_reason"] = "!! round %d %s: 補唔足到 |S| = %d (實際 %d; S_acc %d, 本輪排除 %d 粒, 候選表共 %d) —— 停, 要人手睇" % (
                        r, tag, a.target_removed, len(S_try), len(S_acc), len(excl), len(self.ordering)); break
                self.step("Phase 3e round %d/%d 嘗試 %s (%s, 步幅 %d): 剪 %d 粒 → |G₂′| %d |G₃′| %d; buildg2 → march d=%d → cnc2k %d workers (leaf 證明保留 %s); 輪上限剩 %.1f h + 延長剩 %.1f h; CPU %.1f / %.0f CPU-h; wall %.1f / %.0f h" % (
                    r, a.rounds, tag, kind, step, len(S_try), g2.n - len(S_try), 2 * (g2.n - len(S_try)) - 1, a.depth, a.workers,
                    os.path.join(a.keep_root, tag), rem / 3600, (self.extend_round_max - ext_used_round) / 3600,
                    self.cpu_h_used(), a.cpu_cap_h, self.elapsed() / 3600, a.total_cap / 3600))
                log("--- round %d 嘗試 %s (%d/%d): %s ---" % (r, tag, ai + 1, a.attempts_per_round, kind))
                a.extend = max(0.0, self.extend_round_max - ext_used_round)          # 延長額度: 每輪 ≤ --extend, a + b 共用
                try:
                    rec = self.campaign(tag, S_try, rem)
                except Exception as e:
                    rec = {"tag": tag, "removed": len(S_try), "S": sorted(S_try), "status": "error", "error": repr(e)[-600:],
                           "wall_s": round(time.time() - t_round, 1), "dir": os.path.join(self.out, tag), "settled": False}
                    subprocess.run(["pkill", "-x", "kissat"], capture_output=True); subprocess.run(["pkill", "-x", "drat-trim"], capture_output=True)
                    kd = os.path.join(a.keep_root, tag)
                    if os.path.isdir(kd):                                            # 例外之後唔敢刪: cnc2k 可能已經 certified
                        rec["keep"] = {"dir": kd, "on_disk": True, "retained_after_exception": True} | dir_stats(kd)
                finally:
                    a.extend = self.extend_round_max
                ext_used_round += float(rec.get("extended_s") or 0.0)
                rec["round"] = r; rec["step"] = step; rec["attempt"] = ai + 1; rec["kind"] = kind; rec["added_candidates"] = added
                rec["excluded_before"] = sorted(excl)
                rr["attempts"].append(rec); rr["excluded_this_round"] = sorted(excl); self.save()
                if a.dry_run:
                    status = "dry-run"; rec["settled"] = True
                    st["stop_reason"] = "DRY RUN: round %d %s 建咗 CNF 就停 (%s)" % (r, tag, rec["dir"]); break
                if rec["status"] in ("error", "cnc2-error", "march-refuted-root", "stuck"):
                    status = "error"; rec["settled"] = True; st["needs_operator"] = True
                    st["stop_reason"] = "!! round %d %s %s —— 停, 要人手睇 %s: %s" % (
                        r, tag, rec["status"], rec["dir"], (rec.get("error") or (rec.get("cnc_log_tail") or "")[-300:]).replace("\n", " | ")); break
                if rec["status"] in ("budget-stop", "hard-killed"):
                    status = "cap-hit"; rec["settled"] = False; st["needs_operator"] = True     # 唔 settle + keep 保留 ⇒ --resume --ack-operator 會 cnc2k --resume 續
                    st["stop_reason"] = ("round %d %s 超輪上限未完 (%s: leaf %s/%s 已驗, 證明保住喺 %s, 估計仲要 %s h; 輪上限 %.2f h + 已延長 %.0f s) —— 停, 等人手決定。"
                                         "續跑: `python3 probe3e.py --resume --ack-operator …` (或者 resume3e.sh 之前人手清 state.needs_operator), cnc2k --resume 會由已完成嘅 %s 個 cube 續落去") % (
                        r, tag, rec["status"], rec.get("leaves"), rec.get("n_cubes"), os.path.join(a.keep_root, tag), rec.get("eta_remaining_h"),
                        rec["cap_s"] / 3600, rec.get("extended_s") or 0, rec.get("leaves")); break
                if rec["status"] == "certified-keep-incomplete":
                    status = "keep-incomplete"; rec["settled"] = True; st["needs_operator"] = True
                    st["stop_reason"] = "!! round %d %s L1″ certified 但 %d 個證明搬去 D: 失敗而且修唔到 (%s) —— 封存規則要求全套證明喺碟上, S_acc 唔郁, 停, 要人手睇 %s" % (
                        r, tag, len(rec["keep_repair"]["failed"]), rec["keep_repair"]["failed"][:10], os.path.join(rec["dir"], "cnc_" + tag, "keep_repair.json")); break
                if rec["status"] == "certified":
                    self.certify(rec); rec["settled"] = True; self.save()             # 每輪都齊: L2″/L3″/完整性/spindle A+B + 5 色逐邊覆核
                    if not (rec.get("l3_ok") and rec.get("col5_ok")):
                        status = "l3-failed"; st["needs_operator"] = True
                        st["stop_reason"] = "!! round %d %s L1″ certified 但完整認證有步驟失敗 (l3_ok=%s, col5_ok=%s) —— 停, 要人手睇 %s" % (
                            r, tag, rec.get("l3_ok"), rec.get("col5_ok"), os.path.join(rec["dir"], "l3g2.log")); break
                    certified_rec = rec; status = "certified"; break
                if rec["status"] == "SAT":
                    if not rec.get("witness"):
                        status = "error"; rec["settled"] = True; st["needs_operator"] = True
                        st["stop_reason"] = "!! round %d %s SAT 但染色證書覆核失敗 (%s) —— 編碼/解碼有 bug, 停" % (r, tag, rec.get("colouring")); break
                    B = sorted(rec["witness"]["blocked_min"]); rec["settled"] = True
                    rr["B_sets"].append(B)
                    st["B_sets"].append({"round": r, "tag": tag, "step": step, "S_size": len(S_try), "B": B, "size": len(B),
                                         "B_in_S_acc": sorted(set(B) & S_acc), "B_in_batch": sorted(set(B) - S_acc),
                                         "col_file": rec["colouring"]["col_file"], "witness_col": rec["witness"]["out"]})
                    excl |= set(B); rr["excluded_this_round"] = sorted(excl)
                    log("round %d %s: SAT → 擋路集 B (|B| = %d, 其中 %d 粒喺 S_acc 入面) = %s; 本輪累計排除 %d 粒" % (
                        r, tag, len(B), len(set(B) & S_acc), B, len(excl)))
                    self.save(); continue
                status = "error"; rec["settled"] = True; st["needs_operator"] = True
                st["stop_reason"] = "!! round %d %s 未知狀態 %s" % (r, tag, rec["status"]); break
            else:
                status = status or "blocked"                                          # 兩張都試完都冇 certified ⇒ 兩張都 SAT
            # ---------------- 輪結算 ----------------
            rr["status"] = status; rr["wall_s"] = round(time.time() - t_round, 1); rr["extended_s"] = round(ext_used_round, 1)
            rr["B_sizes"] = [len(b) for b in rr["B_sets"]]
            if status == "certified":
                st["S_acc"] = sorted(certified_rec["S"]); rr["S_acc_after"] = sorted(certified_rec["S"]); rr["net_removed"] = len(certified_rec["S"]) - len(S_acc)
                rr["G2p_n"] = certified_rec["cnf"]["n_remaining"]; rr["G3p_n"] = certified_rec.get("G3p_n"); rr["certified_tag"] = certified_rec["tag"]
                st["best"] = {"tag": certified_rec["tag"], "dir": certified_rec["dir"], "round": r, "removed": certified_rec["removed"],
                              "G2p_n": certified_rec.get("G2p_n"), "G2p_m": certified_rec.get("G2p_m"), "G3p_n": certified_rec.get("G3p_n"), "G3p_m": certified_rec.get("G3p_m"),
                              "keep_dir": os.path.join(a.keep_root, certified_rec["tag"]), "leaves": certified_rec["leaves"],
                              "base_sha256": certified_rec["cnf"]["cnf_sha256"], "engine_b_run": certified_rec.get("engine_b_run"),
                              "col5_ok": certified_rec.get("col5_ok"), "when": time.strftime("%Y-%m-%d %H:%M:%S")}
                for prev in list(st.get("kept_certified") or []):                     # 封存規則: 本輪 certified (L1″+L2″+L3″ 全過) 之後, 先刪上一輪嘅 keep
                    if prev == certified_rec["tag"]:
                        continue
                    pdir = os.path.join(a.keep_root, prev); ks = dir_stats(pdir)
                    if os.path.isdir(pdir):
                        shutil.rmtree(pdir, ignore_errors=True)
                    for r_ in self.rounds:
                        for x in r_.get("attempts", []):
                            if x["tag"] == prev and x.get("keep"):
                                x["keep"]["on_disk"] = False; x["keep"]["deleted_after_next_certified"] = certified_rec["tag"]
                                x["keep"]["deleted_when"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    log("封存: %s 已認證 ⇒ 刪上一輪 %s 嘅 keep 目錄 %s (%d 檔, %.2f GB)" % (certified_rec["tag"], prev, pdir, ks["n_files"], ks["gb"]))
                st["kept_certified"] = [certified_rec["tag"]]
            else:
                rr["S_acc_after"] = sorted(S_acc); rr["net_removed"] = 0
                rr["G2p_n"] = g2.n - len(S_acc); rr["G3p_n"] = 2 * (g2.n - len(S_acc)) - 1
            st["round_done"] = r; rr["budget_after"] = {"cpu_h_used": self.cpu_h_used(), "wall_used_h": round(self.elapsed() / 3600, 3)}
            self.save()
            log("round %d 結算: %s; 淨剪 %s (S_acc %d → %d, |G₂′| %d, |G₃′| %d); B 集合大小 %s; 輪 wall %.2f h (延長 %.0f s); 用時 %.2f h; CPU %.1f / %.0f CPU-h; keep %s" % (
                r, status, rr["net_removed"], len(S_acc), len(st["S_acc"]), rr["G2p_n"], rr["G3p_n"], rr["B_sizes"], rr["wall_s"] / 3600,
                ext_used_round, self.elapsed() / 3600, self.cpu_h_used(), a.cpu_cap_h, st.get("kept_certified")))
            if st["stop_reason"]:
                break
            if status == "certified" and rr["G2p_n"] <= RECORD_G2P:
                st["target_reached"] = True; st["record_candidate"] = True
                st["stop_reason"] = ("RECORD_CANDIDATE: |G₂′| = %d ≤ %d ⇒ |G₃′| = %d < 1441 (round %d, %s; L1″+L2″+L3″+完整性+spindle A/B+5 色 全部 ✓%s) —— 即刻停, 唔再剪; "
                                     "finalize3e 做獨立重驗 + 封存 + RECORD_CANDIDATE.md") % (
                    rr["G2p_n"], RECORD_G2P, rr["G3p_n"], r, rr["certified_tag"],
                    "; 已到 Amber 目標 716" if rr["G2p_n"] <= TARGET_G2P_AMBER else "; 未到 Amber 目標 716 但已 < 1441")
                log("*** %s ***" % st["stop_reason"]); break
            if status == "blocked":                                                   # 同一輪兩張都 SAT ⇒ 步幅減半
                st["step_history"] = (st.get("step_history") or []) + [{"round": r, "step": step, "why": "兩張證書都 SAT", "B_sizes": rr["B_sizes"]}]
                if step <= a.min_step:
                    st["stop_reason"] = "步幅去到 %d 仍然兩張都 SAT (round %d, |B| = %s) —— 停, 報告" % (step, r, rr["B_sizes"]); break
                st["step"] = max(a.min_step, step // 2)
                log("自適應步幅: round %d 兩張都 SAT (|B| = %s) ⇒ 步幅 %d → %d, 下一輪用新步幅" % (r, rr["B_sizes"], step, st["step"]))
            elif status == "cap-exhausted":
                st["stop_reason"] = "round %d 用完輪上限 %.2f h 都未拎到證書 (已試 %d 張, B 集合大小 %s) —— 停" % (r, cap_round / 3600, len(rr["attempts"]), rr["B_sizes"]); break
        if not st["stop_reason"]:
            st["stop_reason"] = "%d 輪完成 (輪數上限 --rounds %d, 唔准自動加)" % (st["round_done"], a.rounds)
        self.cur = {}; self.save()
        if st.get("paused"):
            self.step("Phase 3e PAUSED (PAUSE 旗, round %d 之後): 用 resume3e.sh 續跑" % st["round_done"]); log("PROBE3E PAUSED: %s" % st["stop_reason"]); return
        st["finished"] = time.strftime("%Y-%m-%d %H:%M:%S"); self.save()
        self.step("Phase 3e 小步慢行完 (%s): S_acc %d 粒, |G₂′| %d, |G₃′| %d; 最佳 %s; CPU %.1f / %.0f CPU-h; 用時 %.2f h; 跟住 finalize3e (獨立重驗 + 封存 + 報告)" % (
            st["stop_reason"][:200], len(st["S_acc"]), g2.n - len(st["S_acc"]), 2 * (g2.n - len(st["S_acc"])) - 1,
            (st.get("best") or {}).get("tag") or "冇新證書", self.cpu_h_used(), a.cpu_cap_h, self.elapsed() / 3600))
        log("PROBE3E DONE: %s" % st["stop_reason"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True); ap.add_argument("--batches", required=True); ap.add_argument("--out", required=True); ap.add_argument("--seed-run", default=None)
    ap.add_argument("--rounds", type=int, default=6); ap.add_argument("--step", type=int, default=20); ap.add_argument("--min-step", type=int, default=5)
    ap.add_argument("--attempts-per-round", type=int, default=2); ap.add_argument("--tag-prefix", default="r")
    ap.add_argument("--workers", type=int, default=14); ap.add_argument("--cap", type=float, default=6 * 3600); ap.add_argument("--extend", type=float, default=3600)
    ap.add_argument("--extend-eta-h", type=float, default=0.5); ap.add_argument("--total-cap", type=float, default=60 * 3600); ap.add_argument("--cpu-cap-h", type=float, default=500.0)
    ap.add_argument("--timeout", type=float, default=900); ap.add_argument("--depth", type=int, default=14); ap.add_argument("--proof-dir", default=None)
    ap.add_argument("--keep-root", default="/mnt/d/hadwiger/phase3e/keep"); ap.add_argument("--proj-first-h", type=float, default=4.5)
    ap.add_argument("--resume", action="store_true"); ap.add_argument("--ack-operator", action="store_true"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    assert a.step >= a.min_step >= 1, "--step 要 ≥ --min-step ≥ 1"
    assert a.attempts_per_round >= 1, "--attempts-per-round 要 ≥ 1"
    a.target_removed = None                                                  # 每輪由 run() 設 (pick_S 用)
    a.proof_dir = os.path.abspath(os.path.expanduser(a.proof_dir or os.path.join("/dev/shm", a.run_id))); os.makedirs(a.proof_dir, exist_ok=True)
    a.keep_root = os.path.abspath(os.path.expanduser(a.keep_root)); os.makedirs(a.keep_root, exist_ok=True)
    a.batches = os.path.abspath(a.batches)
    Probe3E(a).run()


if __name__ == "__main__":
    main()
