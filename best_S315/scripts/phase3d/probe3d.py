#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probe3d.py —— Phase 3d「最後一刀」: 由 Phase 3c r09a (S_acc = 270, |G₂′| = 796, |G₃′| = 1591) 接力, **一刀剪 80 粒** → |S| = 350, |G₂′| = 716, |G₃′| = 1431 < 1441 (Heule 2021 無-spindle 紀錄)
  設計修正 (Amber 2026-09-08):
    * 成本按「證書」計唔係按「粒數」計: march_cu d=14 每次都係約 16 384 個 cube, 剪 30 同剪 80 一樣貴 ⇒ 一刀剪 80, 唔再分輪
    * 唔准用細規則殺死接近完成嘅 run: 輪上限 8 h; cnc2k budget-stop 之後如果剩餘估計 ≤ --extend-eta-h (0.5 h) 就自動 --resume 延長 (總延長 ≤ --extend 1 h), 唔係即刻報廢
  流程 (最多三張證書 a/b/c, 之後無論成敗都停):
    attempt a: S = S_acc(270) + 候選表下 80 粒 → buildg2 → march_cu d=14 → cnc2k (leaf 證明全部保留)
      UNSAT/certified → 即刻完整認證 (l3g2 --engine-b: L2″/L3″/exactfield --complete/spindle A+B) + 5 色染色逐邊覆核 (certify4 --k 5) → 停, 交俾 finalize3d 做 RECORD 程序
      SAT → 染色證書逐邊覆核 + witness_g2 貪心放返 → 擋路集 B
    attempt b: S = (S_a ∖ B) 由候選表補足返到 |S| = 350 (排除 B) → 再證; SAT → B′
    attempt c: 排除 B ∪ B′, 補足到 350 → 最後一次; 三次都 SAT → 停, 報告三個 B 集合
  任何一張 certified 證書都算數: |G₂′| ≤ 720 ⇒ RECORD 程序; 720 < |G₂′| < 796 ⇒ 「有進步」照樣認證封存報告
  預算: 總 --cpu-cap-h 160 CPU-h (= Σ 每張證書 wall × workers), 總 --total-cap 24 h wall; 每張證書 --cap 8 h (+ 自動延長 ≤ 1 h); 開新一張證書之前先查預算夠唔夠 (中途唔會斬)
  磁碟: keep-dir /mnt/d/hadwiger/phase3d/keep/<tag> (每張約 150 GB); 唔係 certified 嘅嘗試即刪; D: < 300 GB 即停; 證明暫存 /dev/shm 驗完即搬 D:
用法: python3 probe3d.py --run-id p3d1_final --seed-run ~/hadwiger/phase3c/runs/p3c1_shrink --batches ~/hadwiger/phase3b/batches_g2.json --out ~/hadwiger/phase3d/runs/p3d1_final
                         [--attempts 3] [--target-removed 350] [--workers 14] [--cap 28800] [--extend 3600] [--extend-eta-h 0.5]
                         [--total-cap 86400] [--cpu-cap-h 160] [--timeout 900] [--depth 14] [--proof-dir /dev/shm/p3d1_final] [--keep-root /mnt/d/hadwiger/phase3d/keep]
                         [--resume] [--ack-operator] [--dry-run]
"""
import sys, os, json, time, argparse, subprocess, signal, statistics, re, shutil
if not __debug__:
    sys.exit("!! 唔准用 python -O")
PH2 = os.path.expanduser("~/hadwiger/phase2"); PH3B = os.path.expanduser("~/hadwiger/phase3b")
PH3C = os.path.expanduser("~/hadwiger/phase3c"); PH3D = os.path.expanduser("~/hadwiger/phase3d")
sys.path.insert(0, PH3B)
from g2common import G2, decode_model, verify_colouring, write_col, sha, MARCH   # noqa: E402  (Phase 3b 審核過嘅共用層, 一字不改)
import witness_g2                                                                 # noqa: E402
sys.path.insert(0, PH3C)
from probe3c import repair_keep_dir                                               # noqa: E402  (Phase 3c 審核過嘅 keep 修補: leaf + audit)
PY = sys.executable
CNC = os.path.join(PH3C, "cnc2k.py")            # = v1.0 cnc2.py + --keep-dir (make_cnc2k.py 機械生成, diff 喺 phase3c/cnc2k.diff)
L1_MEAN_SV = 0.78                               # Phase 2b L1 每 cube solve+verify, 對照
G2RECON_SV = 4.4                                # Phase 4 G₂ 偵察 (x=0) 每 cube solve+verify, 對照
RECORD_G2P = 720                                # |G₂′| ≤ 720 ⇔ |G₃′| = 2|G₂′| − 1 ≤ 1439 < 1441
PROJ_FACTOR = 1.10                              # 下一張證書 wall 預測 = 1.10 × 上一張 (同一個 |S|, 只係換頂點)

def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)

def free_gb(path):
    try:
        st = os.statvfs(path); return st.f_bavail * st.f_frsize / 1e9
    except Exception:
        return None

def extend_decision(stn, workers, extend_eta_h, ext_used, extend_max):
    """cnc2k budget-stop 之後應唔應該自動延長 (Amber: 唔准用細規則殺死接近完成嘅 run)?
    stn = cnc2k 嘅 state.json. 回傳 dict: extend(bool), add(秒), eta_h, pend, done, stuck, per_leaf_s, why. 純函數, selftest 直接測。"""
    done = stn.get("done") or {}; pend = len(stn.get("pending") or []) + len(stn.get("running_at_save") or []); stuck = len(stn.get("stuck") or [])
    per = ((sum(x["solve_s"] for x in done.values()) + sum((x.get("verify_s") or 0) for x in done.values()) + (stn.get("wasted_s") or 0)) / len(done)) if done else None
    eta_h = (pend * per / max(1, workers) / 3600) if per is not None else None
    left = max(0.0, extend_max - ext_used)
    r = {"extend": False, "add": 0.0, "eta_h": (round(eta_h, 4) if eta_h is not None else None), "pend": pend, "done": len(done), "stuck": stuck,
         "per_leaf_s": (round(per, 3) if per is not None else None), "left_s": round(left, 1)}
    if pend == 0:
        r["why"] = "冇 pending cube (唔係 budget-stop)"; return r
    if stuck:
        r["why"] = "有 %d 個 stuck cube —— 要人手睇, 唔延長" % stuck; return r
    if per is None:
        r["why"] = "一個 leaf 都未完, 估唔到 ETA"; return r
    if eta_h > extend_eta_h:
        r["why"] = "剩 %d 個 cube, 估計仲要 %.2f h > %.2f h 上限" % (pend, eta_h, extend_eta_h); return r
    if left < 300:
        r["why"] = "延長額度淨返 %.0f s < 300 s (已用 %.0f / %.0f s)" % (left, ext_used, extend_max); return r
    r["extend"] = True; r["add"] = min(left, max(900.0, eta_h * 3600 * 1.6))
    r["why"] = "剩 %d 個 cube, 估計 %.2f h ≤ %.2f h → 延長 %.0f s (額度剩 %.0f s)" % (pend, eta_h, extend_eta_h, r["add"], left)
    return r

def dir_stats(d):
    n = 0; b = 0
    if os.path.isdir(d):
        for root, _, files in os.walk(d):
            for f in files:
                try:
                    b += os.path.getsize(os.path.join(root, f)); n += 1
                except OSError:
                    pass
    return {"n_files": n, "gb": round(b / 1e9, 2)}

class Probe:
    def __init__(self, a):
        self.a = a; self.out = os.path.abspath(a.out); os.makedirs(self.out, exist_ok=True)
        self.bj = json.load(open(a.batches)); self.ordering = self.bj["ordering"]; self.P2 = set(self.bj["P2"])
        self.g2 = G2()
        self.state_p = os.path.join(self.out, "state.json"); self.att_p = os.path.join(self.out, "attempts.json"); self.status_p = os.path.join(self.out, "status.json")
        if a.resume and os.path.exists(self.state_p):
            self.st = json.load(open(self.state_p)); self.attempts = json.load(open(self.att_p)) if os.path.exists(self.att_p) else []
            if self.st.get("needs_operator") and not a.ack_operator:
                sys.exit("!! 上次停係要人手睇: %s —— 唔准自動 --resume; 人手睇完要續跑就加 --ack-operator" % self.st.get("stop_reason"))
            if self.st.get("best"):
                sys.exit("!! 已經有 certified 最終圖 (%s, |G₂′| %s) —— 唔准再剪, 跟住行 finalize3d" % (self.st["best"]["tag"], self.st["best"]["G2p_n"]))
            self.st["needs_operator"] = False
            done_tags = {x["tag"] for x in self.attempts if x.get("settled")}
            self.st.setdefault("prior_wall_by_tag", {})
            for x in self.attempts:                                    # 未結算嘅嘗試: 記低已花嘅 wall, 之後 cnc2k --resume 會計返
                if not x.get("settled") and x.get("wall_s"):
                    self.st["prior_wall_by_tag"][x["tag"]] = max(float(x["wall_s"]), float(self.st["prior_wall_by_tag"].get(x["tag"], 0)))
            self.attempts = [x for x in self.attempts if x.get("settled")]
            self.st["elapsed_before_s"] = self.st.get("elapsed_s", 0)
            self.st["stop_reason"] = None; self.st.pop("paused", None); self.st.pop("finished", None)
            self.st["resumes"] = self.st.get("resumes", 0) + 1; self.st["config_resume"] = vars(a)
            log("resume #%d: 已結算嘗試 %s, S_acc %d 粒, 排除 %d 粒, 之前用時 %.2f h, CPU 已用 %.1f / %.0f CPU-h" % (
                self.st["resumes"], sorted(done_tags), len(self.st["S_acc"]), len(self.st["excluded"]), self.st["elapsed_before_s"] / 3600, self.cpu_h_used(), a.cpu_cap_h))
        else:
            assert not os.path.exists(self.state_p), "out 已有 state.json (要 --resume 或者換 run-id)"
            assert a.seed_run, "首跑要 --seed-run (Phase 3c run 目錄)"
            seed = self.load_seed(a.seed_run)
            self.st = {"run_id": a.run_id, "started": time.strftime("%Y-%m-%d %H:%M:%S"), "elapsed_before_s": 0.0, "S_acc": seed["S_acc"], "excluded": [], "B_sets": [],
                       "stop_reason": None, "best": None, "record_candidate": False, "config": vars(a), "seed": seed["prov"], "resumes": 0,
                       "needs_operator": False, "prior_wall_by_tag": {}, "kept_certified": []}
            self.attempts = []
            log("seed: 由 %s 接力 —— %s (S_acc %d 粒, |G₂′| %d, |G₃′| %d; bundle sha %s…, l3 all_ok %s, leaf 證明 %s)" % (
                seed["prov"]["run_id"], seed["prov"]["last_certified_tag"], len(self.st["S_acc"]), seed["prov"]["G2p_n"], seed["prov"]["G3p_n"],
                seed["prov"]["bundle_sha256"][:16], seed["prov"]["l3_all_ok"], seed["prov"]["leaf_proofs_dir"]))
        self.T0 = time.time(); self.cur = {}

    # ---------------- seed ----------------
    def load_seed(self, seed_run):
        seed_run = os.path.abspath(os.path.expanduser(seed_run))
        st0 = json.load(open(os.path.join(seed_run, "state.json"))); r0 = json.load(open(os.path.join(seed_run, "rounds.json")))
        r0 = [x for x in r0 if x["round"] <= st0["round_done"]]
        cert = [(r, x) for r in r0 for x in r["attempts"] if x.get("status") == "certified" and x.get("l3_ok") is True and sorted(x["S"]) == sorted(st0["S_acc"])]
        assert cert, "seed 冇 S == S_acc 嘅 certified + l3_ok 嘗試"
        r, x = cert[-1]; tag = x["tag"]; d = x.get("dir") or os.path.join(seed_run, tag)
        assert not st0.get("target_reached"), "seed 已到目標?!"
        bundle_p = os.path.join(d, "cnc_" + tag, "bundle.json"); l3_p = os.path.join(d, "l3", "summary.json")
        cb = json.load(open(bundle_p)); sm = json.load(open(l3_p))
        assert cb["base_sha"] == x["cnf"]["cnf_sha256"] and cb["leaves"] == x["leaves"] and cb["audit"]["all_ok"], "seed bundle 對唔上"
        assert sm["all_ok"] is True and sm["G3p"]["n"] == x.get("G3p_n") == 2 * x["cnf"]["n_remaining"] - 1, "seed l3 summary 對唔上"
        # 已封存嘅 leaf 證明 (Phase 3c final/): 對數 base sha, 唔會用嚟做 Phase 3d 嘅證書, 只係記錄出處
        fin = "/mnt/d/hadwiger/release_v1_1_staging/final"
        lp = os.path.join(fin, "L1pp", "leaf_proofs"); li = os.path.join(fin, "L1pp", "LEAF_INDEX.json")
        leaf_dir = None
        if os.path.isdir(lp) and os.path.exists(li):
            ix = json.load(open(li))
            if ix.get("tag") == tag and ix.get("base_sha256") == cb["base_sha"]:
                leaf_dir = lp
        prov = {"run_id": st0["run_id"], "run_dir": seed_run, "round_done": st0["round_done"], "last_certified_tag": tag, "attempt_dir": d,
                "base_sha256": cb["base_sha"], "bundle_sha256": sha(bundle_p), "l3_summary_sha256": sha(l3_p), "l3_all_ok": sm["all_ok"],
                "G2p_n": x["cnf"]["n_remaining"], "G2p_m": x["cnf"]["n_edges"], "G3p_n": x.get("G3p_n"), "G3p_m": sm["G3p"]["m"],
                "leaf_proofs_dir": leaf_dir, "n_leaves": cb["leaves"], "seed_stop_reason": st0.get("stop_reason")}
        return {"S_acc": sorted(st0["S_acc"]), "prov": prov}

    # ---------------- 帳 ----------------
    def elapsed(self):
        return self.st["elapsed_before_s"] + time.time() - self.T0

    def remaining_total(self):
        return self.a.total_cap - self.elapsed()

    def cpu_h_used(self):
        return round(sum((x.get("wall_s") or 0) for x in self.attempts) * self.a.workers / 3600, 2)

    def cpu_h_remaining(self):
        return self.a.cpu_cap_h - self.cpu_h_used()

    def proj_wall_h(self):
        w = [x["wall_s"] for x in self.attempts if x.get("wall_s")]
        return round(PROJ_FACTOR * max(w) / 3600, 3) if w else self.a.proj_first_h

    def step(self, msg):
        try:
            open(os.path.join(PH3D, "STEP.txt"), "w").write(msg)
        except Exception:
            pass

    def save(self, light=False):
        st = self.st; st["elapsed_s"] = round(self.elapsed(), 1); st["updated_str"] = time.strftime("%Y-%m-%d %H:%M:%S")
        st["cpu_h_used"] = self.cpu_h_used()
        json.dump(st, open(self.state_p + ".tmp", "w"), indent=1); os.replace(self.state_p + ".tmp", self.state_p)
        if light:                                                        # cnc2k 等待期間: 只寫 state.json (elapsed_s 保鮮), 唔行 D:
            return
        json.dump(self.attempts, open(self.att_p + ".tmp", "w"), indent=1); os.replace(self.att_p + ".tmp", self.att_p)
        best = st.get("best") or {}
        summ = [{k: x.get(k) for k in ("tag", "removed", "status", "n_cubes", "leaves", "mean_solve_s", "mean_sv_s", "max_solve_s", "wall_s", "extended_s", "B_size", "l3_ok", "col5_ok", "G2p_n", "G3p_n", "keep", "settled")} for x in self.attempts]
        status = {"run_id": st["run_id"], "started": st["started"], "updated_str": st["updated_str"], "elapsed_s": st["elapsed_s"], "total_cap_s": self.a.total_cap,
                  "attempts_done": len([x for x in self.attempts if x.get("settled")]), "attempts_max": self.a.attempts,
                  "S_acc_size": len(st["S_acc"]), "G2p_seed": self.g2.n - len(st["S_acc"]), "G3p_seed": 2 * (self.g2.n - len(st["S_acc"])) - 1,
                  "target_removed": self.a.target_removed, "target_G2p": self.g2.n - self.a.target_removed, "target_G3p": 2 * (self.g2.n - self.a.target_removed) - 1,
                  "current": self.cur, "stop_reason": st["stop_reason"], "best": best, "record_candidate": st.get("record_candidate"), "excluded": len(st["excluded"]), "B_sets": st["B_sets"],
                  "cpu_h_used": st["cpu_h_used"], "cpu_cap_h": self.a.cpu_cap_h, "cpu_h_remaining": round(self.cpu_h_remaining(), 2), "proj_next_wall_h": self.proj_wall_h(),
                  "keep_root": self.a.keep_root, "kept_certified": st.get("kept_certified"),
                  "keep_stats": {t: dir_stats(os.path.join(self.a.keep_root, t)) for t in (st.get("kept_certified") or [])},
                  "seed": st.get("seed"), "resumes": st.get("resumes", 0), "attempts_list": summ}
        json.dump(status, open(self.status_p + ".tmp", "w"), indent=1, ensure_ascii=False); os.replace(self.status_p + ".tmp", self.status_p)
        self.write_ledger()

    def write_ledger(self):
        W = self.a.workers; st = self.st
        L = ["# ledger_g2.md —— Phase 3d 最後一刀帳 (run %s, 接力 %s %s; 更新 %s)" % (
                st["run_id"], (st.get("seed") or {}).get("run_id"), (st.get("seed") or {}).get("last_certified_tag"), time.strftime("%Y-%m-%d %H:%M:%S")), "",
             "起點 S_acc = %d 粒 (|G₂′| %d, |G₃′| %d); 目標 |S| = %d (|G₂′| %d, |G₃′| %d < 1441); 排除 (B ∪ B′) %d 粒; 用時 %.2f h / %.0f h; CPU-h (Σ 證書 wall × %d) %.1f / %.0f%s%s" % (
                 len(st["S_acc"]), self.g2.n - len(st["S_acc"]), 2 * (self.g2.n - len(st["S_acc"])) - 1, self.a.target_removed, self.g2.n - self.a.target_removed,
                 2 * (self.g2.n - self.a.target_removed) - 1, len(st["excluded"]), self.elapsed() / 3600, self.a.total_cap / 3600, W, self.cpu_h_used(), self.a.cpu_cap_h,
                 ("; **最佳: %s |G₂′| %s |G₃′| %s**" % (st["best"]["tag"], st["best"]["G2p_n"], st["best"]["G3p_n"])) if st.get("best") else "",
                 ("; **停: %s**" % st["stop_reason"]) if st["stop_reason"] else ""), "",
             "| 嘗試 | |S| | 結果 | cube | leaf | 每 cube solve (s) | 每 cube s+v (s) | ×G₂recon | 最長 cube (s) | wall (延長) | CPU-h | leaf 證明保留 | B (擋路集) | |G₂′| | |G₃′| | L2″/L3″/完整/spindle A+B | 5 色 |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for x in self.attempts:
            kp = x.get("keep") or {}
            L.append("| %s | %d | %s | %s | %s | %s | %s | %s | %s | %s s (%.2f h%s) | %.1f | %s | %s | %s | %s | %s | %s |" % (
                x["tag"], x["removed"], x["status"], x.get("n_cubes", "—"), x.get("leaves", "—"), x.get("mean_solve_s", "—"), x.get("mean_sv_s", "—"), x.get("x_G2recon_sv", "—"),
                x.get("max_solve_s", "—"), x.get("wall_s", "—"), (x.get("wall_s") or 0) / 3600, (", 延長 %.2f h" % ((x.get("extended_s") or 0) / 3600)) if x.get("extended_s") else "",
                (x.get("wall_s") or 0) * W / 3600,
                ("%s/%s (%s GB)%s" % (kp.get("kept_leaves"), x.get("leaves"), kp.get("gb"), "" if kp.get("on_disk") else " 已刪")) if kp else "—",
                ("|B|=%d %s" % (x["B_size"], x["witness"]["blocked_min"])) if x.get("witness") else "—",
                x["cnf"]["n_remaining"] if x.get("cnf") else "—", x.get("G3p_n", "—"),
                ("✓" if x.get("l3_ok") else "!!") if x["status"] == "certified" else "—",
                ("✓ (%s 條邊)" % (x.get("col5") or {}).get("edges_checked")) if x.get("col5_ok") else ("!!" if x["status"] == "certified" else "—")))
        if st["B_sets"]:
            L += ["", "## 擋路集 (每個都有逐邊覆核嘅 4 色染色證書: G₂ − B 有 col(u) ≠ col(v) 嘅染色 ⇒ B 唔可以成集剪走)"]
            L += ["- %s: |B| = %d, B = %s" % (b["tag"], len(b["B"]), b["B"]) for b in st["B_sets"]]
        open(os.path.join(self.out, "ledger_g2.md"), "w").write("\n".join(L) + "\n")

    # ---------------- 一張證書 ----------------
    def campaign(self, tag, S, cap):
        a = self.a; d = os.path.join(self.out, tag); os.makedirs(d, exist_ok=True)
        S = sorted(S)
        rec = {"tag": tag, "removed": len(S), "S": S, "cap_s": round(cap), "extend_max_s": a.extend, "started": time.strftime("%Y-%m-%d %H:%M:%S"), "dir": d, "settled": False, "extended_s": 0.0}
        t_round = time.time()
        cdir = os.path.join(d, "cnc_" + tag); keep_dir = os.path.join(a.keep_root, tag)
        self.cur = {"tag": tag, "stage": "build", "S_size": len(S), "cnc_status": os.path.join(cdir, "status.json"), "cap_s": round(cap), "started": rec["started"], "keep_dir": keep_dir}; self.save()
        # 1. CNF (buildg2: 拒絕 u / v / P₂)
        r = subprocess.run([PY, os.path.join(PH3B, "buildg2.py"), "--remove", ",".join(map(str, S)), "--out", d, "--tag", "base", "--protected", a.batches], capture_output=True, text=True, timeout=600)
        assert r.returncode == 0, "buildg2 失敗: " + r.stdout[-500:] + r.stderr[-500:]
        log(r.stdout.strip()); cnf = os.path.join(d, "base.cnf"); rec["cnf"] = json.load(open(os.path.join(d, "base.json")))
        if a.dry_run:
            rec["status"] = "dry-run"; rec["wall_s"] = round(time.time() - t_round, 1); log("%s: --dry-run, 唔跑 march/cnc2k" % tag); return rec
        # 2. march_cu (新拆 / 沿用舊 campaign)
        icnf = os.path.join(d, "cubes_d%d.icnf" % a.depth)
        resumed = os.path.exists(os.path.join(cdir, "state.json"))
        if not resumed:
            t0 = time.time()
            r = subprocess.run([MARCH, cnf, "-d", str(a.depth), "-o", icnf], capture_output=True, text=True, timeout=7200)
            rec["march_s"] = round(time.time() - t0, 1); open(os.path.join(d, "march.log"), "w").write(r.stdout + r.stderr)
            m = re.search(r"number of cubes (\d+), including (\d+) refuted lea(?:f|ves)", r.stdout)
            assert r.returncode in (0, 20) and m, "march_cu rc=%d: %s" % (r.returncode, (r.stdout + r.stderr)[-400:])
            rec["n_cubes"] = int(m.group(1)); rec["march_refuted"] = int(m.group(2)); rec["icnf_sha"] = sha(icnf)
            log("%s: march_cu -d %d → %d 個 cube (含 refuted leaves %d), %.1f s" % (tag, a.depth, rec["n_cubes"], rec["march_refuted"], rec["march_s"]))
            if r.returncode == 20:
                rec["status"] = "march-refuted-root"; rec["wall_s"] = round(time.time() - t_round, 1); return rec   # 唔信 march 單方面 refute
        # 3. cnc2k (keep-dir) + 自動延長
        prior = float((self.st.get("prior_wall_by_tag") or {}).get(tag, 0.0))
        if resumed:
            try:
                prior = max(prior, float(json.load(open(os.path.join(cdir, "state.json"))).get("wall_s") or 0.0))
            except Exception:
                pass
        rec["prior_wall_s"] = round(prior, 1)
        logp = os.path.join(d, "cnc.log")
        t_pre = time.time() - t_round                                   # build + march 用咗嘅時間 (唔計入 cnc2k 嘅 budget)
        ext_used = 0.0; killed = False; rc = None; launches = 0
        while True:
            st_old = json.load(open(os.path.join(cdir, "state.json"))) if os.path.exists(os.path.join(cdir, "state.json")) else None
            if st_old is not None:
                assert st_old.get("base_sha") == rec["cnf"]["cnf_sha256"], "!! %s: 舊 cnc2k campaign base_sha %s != 而今 S 嘅 base.cnf sha %s (S 變咗?), 拒絕 resume" % (
                    tag, st_old.get("base_sha"), rec["cnf"]["cnf_sha256"])
                assert st_old.get("keep_dir") == keep_dir, "!! %s: 舊 campaign keep_dir %s != %s" % (tag, st_old.get("keep_dir"), keep_dir)
                rec["n_cubes"] = st_old["n_cubes0"]; rec["icnf_sha"] = st_old["icnf_sha"]
                if st_old.get("status") == "certified" and os.path.exists(os.path.join(cdir, "bundle.json")):
                    log("%s: 舊 campaign 已 certified, 直接讀" % tag); break
                if st_old.get("sat"):
                    log("%s: 舊 campaign 已有 SAT, 直接讀" % tag); break
            cnc_budget = cap + ext_used - t_pre                          # cnc2k 嘅 time-budget 係累計 cnc2k wall (resume 會加返 base_wall)
            base_wall = float((st_old or {}).get("wall_s") or 0.0)
            if cnc_budget - base_wall < 60:
                log("%s: cnc2k budget 剩 %.0f s < 60 s, 唔再開" % (tag, cnc_budget - base_wall)); break
            if st_old is not None:
                if os.path.exists(os.path.join(cdir, "lock")):
                    os.remove(os.path.join(cdir, "lock"))
                argv = [PY, CNC, "--resume", "--out", cdir, "--workers", str(a.workers), "--time-budget", str(int(cnc_budget)), "--progress", "120", "--keep-dir", keep_dir]
                rec["resumed"] = True
            else:
                argv = [PY, CNC, "--cnf", cnf, "--icnf", icnf, "--out", cdir, "--workers", str(a.workers), "--timeout", str(a.timeout), "--solver", "kissat",
                        "--proof-dir", a.proof_dir, "--binary", "--time-budget", str(int(cnc_budget)), "--split-depth", "3", "--max-split", "4",
                        "--audit-frac", "0.05", "--progress", "120", "--keep-dir", keep_dir]
            launches += 1; self.cur["stage"] = "cnc2k" + (" (延長 %.2f h)" % (ext_used / 3600) if ext_used else ""); self.save()
            # 審查: cnc2k 去到 time-budget 之後會停止派新 cube 但要 drain 住緊嘅 cube (最長 2T + 驗證), 硬殺邊界唔可以喺呢段正常收尾期間開火
            drain = max(1800.0, 2 * a.timeout + 900)
            log("%s: cnc2k 第 %d 次啟動 (time-budget %.0f s 累計, 已用 %.0f s, 硬殺 +%.0f s = budget + drain, keep-dir %s)" % (tag, launches, cnc_budget, base_wall, cnc_budget - base_wall + drain, keep_dir))
            t0 = time.time()
            with open(logp, "a") as lf:
                p = subprocess.Popen(argv, stdout=lf, stderr=subprocess.STDOUT, start_new_session=True)
                hard = t0 + (cnc_budget - base_wall) + drain; last_save = time.time()
                while True:
                    try:
                        rc = p.wait(timeout=30); break
                    except subprocess.TimeoutExpired:
                        if time.time() - last_save > 600:
                            self.save(light=True); last_save = time.time()
                        if time.time() > hard:
                            killed = True; log("!! %s: 超硬上限, 硬殺 cnc2k process group" % tag)
                            try:
                                os.killpg(p.pid, signal.SIGTERM); time.sleep(5); os.killpg(p.pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                            try:
                                rc = p.wait(timeout=120)
                            except subprocess.TimeoutExpired:
                                rc = -9
                            break
            subprocess.run(["pkill", "-x", "kissat"], capture_output=True); subprocess.run(["pkill", "-x", "drat-trim"], capture_output=True)
            rec["cnc_rc"] = rc; rec["cnc_wall_s"] = round(time.time() - t0, 1)
            stn = json.load(open(os.path.join(cdir, "state.json"))) if os.path.exists(os.path.join(cdir, "state.json")) else {}
            if killed or rc not in (0, 10) or stn.get("sat") or stn.get("status") == "certified":
                break
            # budget-stop: 剩返幾多? 夠近就自動延長 (Amber: 唔准用細規則殺死接近完成嘅 run)
            dec = extend_decision(stn, a.workers, a.extend_eta_h, ext_used, a.extend)
            room = max(0.0, self.remaining_total() - 600)                                  # 審查: 延長都要受 24 h 總 wall 上限管
            if dec["extend"] and dec["add"] > room:
                dec["add"] = room
                if room < 300:
                    dec["extend"] = False; dec["why"] += " —— 但總 wall 淨返 %.0f s, 唔延長" % room
            rec["extend_decisions"] = (rec.get("extend_decisions") or []) + [dec]
            if dec["extend"]:
                ext_used += dec["add"]; rec["extended_s"] = round(ext_used, 1)
                log("%s: budget-stop 但 %s (完成 %d/%s), cnc2k --resume 續 (累計延長 %.0f s / %.0f s)" % (tag, dec["why"], dec["done"], rec.get("n_cubes"), ext_used, a.extend))
                self.save(); continue
            log("%s: budget-stop, 唔延長 —— %s (完成 %d/%s)" % (tag, dec["why"], dec["done"], rec.get("n_cubes")))
            break
        rec["hard_killed"] = killed; rec["cnc_launches"] = launches
        lock = os.path.join(cdir, "lock")
        if os.path.exists(lock):
            os.remove(lock)
        left = [f for f in os.listdir(a.proof_dir) if f.startswith("cnc_%s_" % tag) and os.path.isfile(os.path.join(a.proof_dir, f))]
        rec["leftover_proofs_deleted"] = len(left); rec["leftover_proofs_mb"] = round(sum(os.path.getsize(os.path.join(a.proof_dir, f)) for f in left) / 1e6, 1)
        for f in left:
            os.remove(os.path.join(a.proof_dir, f))
        # 4. 結果
        st = json.load(open(os.path.join(cdir, "state.json"))) if os.path.exists(os.path.join(cdir, "state.json")) else {}
        done = st.get("done", {}); solve = [x["solve_s"] for x in done.values()]; ver = [x.get("verify_s", 0) or 0 for x in done.values()]
        rec["leaves"] = len(done); rec["pending"] = len(st.get("pending", [])) + len(st.get("running_at_save", [])); rec["stuck"] = len(st.get("stuck", []))
        rec["split_events"] = st.get("split_events"); rec["solver_errors"] = st.get("solver_errors"); rec["wasted_s"] = st.get("wasted_s"); rec["keep_errors"] = st.get("keep_errors", 0)
        if solve:
            rec["mean_solve_s"] = round(statistics.mean(solve), 3); rec["median_solve_s"] = round(statistics.median(solve), 3); rec["max_solve_s"] = max(solve)
            rec["mean_verify_s"] = round(statistics.mean(ver), 3); rec["mean_sv_s"] = round(statistics.mean(solve) + statistics.mean(ver), 3)
            rec["x_L1_sv"] = round(rec["mean_sv_s"] / L1_MEAN_SV, 2); rec["x_G2recon_sv"] = round(rec["mean_sv_s"] / G2RECON_SV, 2)
            rec["cpu_solve_s"] = round(sum(solve), 1); rec["cpu_verify_s"] = round(sum(ver), 1)
            rec["proof_total_mb"] = round(sum(x["proof_bytes"] for x in done.values()) / 1e6, 1)
        if st.get("sat"):
            rec["status"] = "SAT"; sat = st["sat"]; rec["sat_cube_id"] = sat["id"]; rec["sat_model_checked_by_cnc2"] = sat.get("model_checked")
            rec["colouring"] = self.colouring_cert(d, S, sat["model_pos"])
            if rec["colouring"]["ok"]:
                self.cur["stage"] = "witness"; self.save()
                w = witness_g2.analyse(self.g2, rec["colouring"]["col_file"], os.path.join(d, "witness"))
                json.dump([w], open(os.path.join(d, "witness", "witness_g2.json"), "w"), indent=1)
                rec["witness"] = {k: w[k] for k in ("blocked_min", "blocked_min_size", "order", "blocked_size_hist", "orders_tried", "verified", "edges_checked", "bad_edges", "col_u", "col_v", "out", "sha256_out")}
                rec["B_size"] = w["blocked_min_size"]
        elif st.get("status") == "certified" and os.path.exists(os.path.join(cdir, "bundle.json")):
            cb = json.load(open(os.path.join(cdir, "bundle.json")))
            rec["status"] = "certified"; rec["cover_verified"] = bool(cb.get("cover", {}).get(cb.get("cover_mode") or "", {}).get("verified"))
            rec["audit"] = cb.get("audit"); rec["max_leaf_solve_s"] = cb.get("max_leaf_solve_s"); rec["base_sha"] = cb.get("base_sha"); rec["bundle"] = os.path.join(cdir, "bundle.json")
            assert rec["cover_verified"] and rec["audit"]["all_ok"], "!! cnc2k 話 certified 但 cover/audit 唔 ok"
            assert cb.get("base_sha") == rec["cnf"]["cnf_sha256"] == st.get("base_sha"), "!! bundle base_sha %s != base.cnf sha %s (證書唔係證而今嘅 S)" % (cb.get("base_sha"), rec["cnf"]["cnf_sha256"])
            assert cb.get("leaves") == len(done) and cb.get("n_cubes0") == rec.get("n_cubes"), "!! bundle leaves/n_cubes0 同 state.json 對唔上"
            rec["keep"] = {"dir": keep_dir, "kept_leaves": cb.get("kept_leaves"), "keep_errors": cb.get("keep_errors"), "keep_error_ids": cb.get("keep_error_ids"),
                           "kept_audit": cb.get("kept_audit"), "audit_keep_errors": cb.get("audit_keep_errors"), "on_disk": True} | dir_stats(keep_dir)
        elif killed:
            rec["status"] = "hard-killed"
        elif rec.get("cnc_rc") not in (None, 0, 10):
            rec["status"] = "cnc2-error"; rec["cnc_log_tail"] = open(logp, errors="ignore").read()[-2000:] if os.path.exists(logp) else None
        elif st.get("status") == "stuck" or rec["stuck"]:
            rec["status"] = "stuck"
        else:
            rec["status"] = "budget-stop"
        rec["wall_s"] = round(time.time() - t_round + prior, 1); rec["cnc_status_json"] = st.get("status")
        if rec["status"] not in ("certified", "SAT") and solve:
            per = (sum(solve) + sum(ver) + (st.get("wasted_s") or 0)) / len(solve)
            rec["eta_remaining_h"] = round((rec["n_cubes"] - len(done)) * per / a.workers / 3600, 2)
        log("%s: %s —— cube %s, leaf 完成 %s, mean solve %s s, mean s+v %s s (G₂recon ×%s, 最長 %s s), wall %.0f s (%.2f h = %.1f CPU-h%s)%s%s%s" % (
            tag, rec["status"], rec.get("n_cubes"), rec["leaves"], rec.get("mean_solve_s"), rec.get("mean_sv_s"), rec.get("x_G2recon_sv"), rec.get("max_solve_s"),
            rec["wall_s"], rec["wall_s"] / 3600, rec["wall_s"] * a.workers / 3600, (", 含延長 %.0f s" % ext_used) if ext_used else "",
            (", 未完: 估計仲要 %s h" % rec.get("eta_remaining_h")) if rec["status"] not in ("certified", "SAT") else "",
            (", 擋路集 B (|B|=%d) = %s" % (rec["B_size"], rec["witness"]["blocked_min"])) if rec.get("witness") else "",
            (", leaf 證明保留 %s/%s (%s GB, 搬失敗 %s)" % (rec["keep"]["kept_leaves"], rec["leaves"], rec["keep"]["gb"], rec["keep"]["keep_errors"])) if rec.get("keep") else ""))
        # 4b. keep 目錄政策 (審查修正): 只有 SAT 先刪 (嗰個 S 冇證書可言, 而且下一次係另一個 S);
        #     budget-stop / hard-killed / error / stuck 一律**保留** —— 已驗嘅 leaf 證明係 cnc2k --resume 嘅本錢, 唔可以因為撞上限就掉晒 (Amber: 唔准用細規則殺死接近完成嘅 run)
        if rec["status"] == "SAT":
            ks = dir_stats(keep_dir)
            if os.path.isdir(keep_dir):
                shutil.rmtree(keep_dir, ignore_errors=True)
            rec["keep"] = {"dir": keep_dir, "on_disk": False, "deleted_sat": True} | ks
            log("%s: SAT (呢個 S 冇證書可言), 刪 keep 目錄 %s (%d 檔, %.2f GB)" % (tag, keep_dir, ks["n_files"], ks["gb"]))
        elif rec["status"] != "certified":
            ks = dir_stats(keep_dir)
            rec["keep"] = {"dir": keep_dir, "on_disk": os.path.isdir(keep_dir), "retained_resumable": True} | ks
            log("%s: %s —— keep 目錄**保留** %s (%d 檔, %.2f GB): resume 會 cnc2k --resume 由呢度續, 已完成嘅 cube 唔使重做" % (
                tag, rec["status"], keep_dir, ks["n_files"], ks["gb"]))
        else:
            cb = json.load(open(os.path.join(cdir, "bundle.json")))
            def _ndisk():
                nl = len([f for f in os.listdir(keep_dir) if f.endswith(".drat")]) if os.path.isdir(keep_dir) else 0
                na = len([f for f in os.listdir(os.path.join(keep_dir, "audit")) if f.endswith(".drat")]) if os.path.isdir(os.path.join(keep_dir, "audit")) else 0
                return nl, na
            n_disk, n_disk_aud = _ndisk(); n_aud_want = (cb.get("audit") or {}).get("n")
            rec["keep"]["n_disk_leaf"] = n_disk; rec["keep"]["n_disk_audit"] = n_disk_aud
            # 審查: 唔可以淨係信 bundle 嘅計數器 —— 用碟上真實 .drat 檔數做閘
            if (rec["keep"]["keep_errors"] or rec["keep"]["kept_leaves"] != rec["leaves"] or n_disk != rec["leaves"]
                    or cb.get("audit_keep_errors") or cb.get("kept_audit") != n_aud_want or n_disk_aud != n_aud_want):
                self.cur["stage"] = "keep-repair"; self.save()
                log("%s: keep 唔齊 (碟上 leaf %d/%d, audit %d/%s; bundle kept %s, keep_errors %s) → 重解 + 重驗 + 再搬" % (
                    tag, n_disk, rec["leaves"], n_disk_aud, n_aud_want, rec["keep"]["kept_leaves"], rec["keep"]["keep_errors"]))
                rep = repair_keep_dir(cdir, keep_dir, st, a.proof_dir, a.timeout, log)
                n_disk, n_disk_aud = _ndisk()
                rec["keep_repair"] = {"repaired": rep["repaired"], "failed": rep["failed"], "kept_after": rep["kept_after"], "kept_audit_after": rep["kept_audit_after"]}
                rec["keep"] = {**rec["keep"], **dir_stats(keep_dir), "kept_leaves": rep["kept_after"], "kept_audit": rep["kept_audit_after"], "n_disk_leaf": n_disk, "n_disk_audit": n_disk_aud}
                if rep["failed"] or n_disk != rec["leaves"] or n_disk_aud != n_aud_want:
                    rec["keep_incomplete"] = True; rec["status"] = "certified-keep-incomplete"
        return rec

    def colouring_cert(self, d, S, model_pos):
        col = decode_model(model_pos, self.g2.n, S); vc = verify_colouring(self.g2, S, col)
        p = os.path.join(d, "G2minus_%dv.col" % len(S))
        s = write_col(p, S, col, "c 4-colouring of G2 minus %s with col(-1,0) != col(1,0) (u=#%d, v=#%d): witness that this set contains a vertex necessary for the mono-pair property" % (sorted(S), self.g2.u, self.g2.v))
        rec = {"col_file": p, "sha256": s, **vc}
        json.dump(rec, open(p[:-4] + ".json", "w"), indent=1)
        log("!! SAT 染色證書: %d 點染色, 缺色 %d, 同色邊 %d/%d, col(u)=%s col(v)=%s → %s (%s)" % (
            rec["n_coloured"], rec["missing"], rec["bad_edges"], rec["edges_checked"], rec["col_u"], rec["col_v"],
            "逐邊覆核通過 ✓ (S 含必要頂點)" if rec["ok"] else "!! 覆核失敗", p))
        return rec

    # ---------------- certified 之後嘅完整認證 ----------------
    def certify_final(self, rec):
        """L2″ + L3″ + exactfield --complete + spindle 引擎 A 同 B (l3g2 --engine-b), 再加 G₃′ 5 色染色逐邊覆核 (certify4 --k 5)."""
        a = self.a; d = rec["dir"]; S = rec["S"]
        self.cur["stage"] = "l3g2 (+engine B)"; self.save()
        argv = [PY, os.path.join(PH3B, "l3g2.py"), "--remove", ",".join(map(str, S)), "--out", os.path.join(d, "l3"), "--engine-b"]
        try:
            r = subprocess.run(argv, capture_output=True, text=True, timeout=6 * 3600)
        except subprocess.TimeoutExpired as e:
            class R: pass
            r = R(); r.returncode = -999; r.stdout = (e.stdout or b"").decode(errors="ignore") if isinstance(e.stdout, bytes) else (e.stdout or ""); r.stderr = "!! l3g2 timeout 6 h"
        open(os.path.join(d, "l3g2.log"), "w").write(r.stdout + r.stderr)
        sm = json.load(open(os.path.join(d, "l3", "summary.json"))) if os.path.exists(os.path.join(d, "l3", "summary.json")) else {}
        rec["l3_ok"] = (r.returncode == 0 and sm.get("all_ok") is True); rec["G3p_n"] = sm.get("G3p", {}).get("n"); rec["G3p_m"] = sm.get("G3p", {}).get("m")
        rec["G2p_n"] = sm.get("G2p", {}).get("n"); rec["G2p_m"] = sm.get("G2p", {}).get("m")
        rec["l3_summary"] = {k: sm.get(k) for k in ("complete_G2p", "complete_G3p", "L2", "L3", "spindle_A", "spindle_B", "sha")}
        for line in r.stdout.splitlines():
            if line.startswith(("[G3″]", "[complete", "[L2″]", "[L3″]", "[spindle", "[l3g2]")):
                log("  " + line[:230])
        # 5 色染色 (certify4 --k 5 --expect sat: SAT → 逐邊覆核 → .col)
        g3p_edge = os.path.join(d, "l3", "G3p.edge")
        if rec["l3_ok"] and os.path.exists(g3p_edge):
            self.cur["stage"] = "5 色染色"; self.save()
            c5 = os.path.join(d, "col5")
            r5 = subprocess.run([PY, os.path.join(PH2, "certify4.py"), g3p_edge, "--out", c5, "--k", "5", "--tag", "G3p_5col", "--expect", "sat", "--timeout", "3600"],
                                capture_output=True, text=True, timeout=4000)
            open(os.path.join(d, "col5.log"), "w").write(r5.stdout + r5.stderr)
            j5 = os.path.join(c5, "G3p_5col.json")
            s5 = json.load(open(j5)) if os.path.exists(j5) else {}
            rec["col5"] = {k: s5.get(k) for k in ("status", "n", "m", "k", "colours_used", "edges_checked", "solve_s")}
            rec["col5"]["col_sha256"] = sha(os.path.join(c5, "G3p_5col.col")) if os.path.exists(os.path.join(c5, "G3p_5col.col")) else None
            rec["col5_ok"] = bool(r5.returncode == 0 and s5.get("status") == "SAT" and s5.get("edges_checked") == rec.get("G3p_m") and s5.get("n") == rec.get("G3p_n"))
            log("  [5 色] %s" % ([l for l in r5.stdout.splitlines() if l.startswith("[G3p_5col]")] or [r5.stdout[-200:]])[0][:230])
        else:
            rec["col5_ok"] = False
        return rec

    # ---------------- 主流程 ----------------
    def pick_S(self, S_base, excluded):
        """由候選表 (排序 key: 度數升, |Im z| 降, 索引) 順序補足到 |S| = target_removed, 排除 excluded."""
        S = set(S_base) - set(excluded)
        pool = [w for w in self.ordering if w not in S and w not in excluded]
        need = self.a.target_removed - len(S)
        added = pool[:max(0, need)]
        return sorted(S | set(added)), added

    def run(self):
        a = self.a; st = self.st; g2 = self.g2
        letters = "abcdefgh"
        while not st["stop_reason"]:
            if os.path.exists(os.path.join(self.out, "PAUSE")):                       # 審查: pause3d.sh 嘅乾淨暫停旗 (證書與證書之間停, 唔收爐, resume3d.sh 續)
                os.remove(os.path.join(self.out, "PAUSE"))
                st["paused"] = True; st["stop_reason"] = "PAUSED by operator (PAUSE 旗) —— 用 resume3d.sh 續"; break
            i = len([x for x in self.attempts if x.get("settled")])
            if i >= a.attempts:
                st["stop_reason"] = "已試 %d 張證書 (上限 %d), 無論成敗都停" % (i, a.attempts); break
            tag = "%s%s" % (a.tag_prefix, letters[i])
            proj = self.proj_wall_h(); rem_cpu_h = self.cpu_h_remaining(); rem_wall_h = self.remaining_total() / 3600
            if i > 0 and rem_cpu_h / a.workers < proj:
                st["stop_reason"] = "CPU 預算: 已用 %.1f / %.0f CPU-h, 剩 %.1f CPU-h = %.2f h wall < 預測下一張證書 %.2f h → 唔開 %s" % (
                    self.cpu_h_used(), a.cpu_cap_h, rem_cpu_h, rem_cpu_h / a.workers, proj, tag); break
            if i > 0 and rem_wall_h < proj + 0.5:
                st["stop_reason"] = "總 wall 上限 %.0f h: 已用 %.2f h, 剩 %.2f h < 預測 %.2f h + 0.5 → 唔開 %s" % (a.total_cap / 3600, self.elapsed() / 3600, rem_wall_h, proj, tag); break
            cf = free_gb("/mnt/c"); df = free_gb("/mnt/d")
            if (cf is not None and cf < 25) or (df is not None and df < 300) or not os.path.ismount("/mnt/d"):
                st["stop_reason"] = "磁碟紀律: C: 剩 %s GB (要 ≥ 25) / D: 剩 %s GB (要 ≥ 300, keep 所在, ismount %s) → 停" % (cf, df, os.path.ismount("/mnt/d")); break
            # 揀 S
            if i == 0:
                S_try, added = self.pick_S(st["S_acc"], st["excluded"])
                kind = "第一刀 (S_acc %d + 候選表下 %d 粒)" % (len(st["S_acc"]), len(added))
            else:
                prev = self.attempts[-1]
                S_try, added = self.pick_S(set(prev["S"]) - set(st["excluded"]), st["excluded"])
                kind = "排除擋路集 %d 粒後補足 %d 粒新候選" % (len(st["excluded"]), len(added))
            if len(S_try) != a.target_removed:                                          # 審查: 補唔足唔可以靜靜雞縮水 (目標係 |S| = 350 ⇒ |G₃′| = 1431)
                st["needs_operator"] = True
                st["stop_reason"] = "!! 補唔足到目標 |S| = %d (實際 %d; S_acc %d, 排除 %d 粒, 候選表共 %d) —— 停, 要人手睇" % (
                    a.target_removed, len(S_try), len(st["S_acc"]), len(st["excluded"]), len(self.ordering)); break
            cap = min(a.cap, self.remaining_total() - 600, max(600.0, rem_cpu_h * 3600 / a.workers))
            if i == 0:
                cap = min(a.cap, self.remaining_total() - 600)           # 第一張證書: 唔俾預算細規則斬 (CPU 上限用嚟開新一張, 唔係中途斬)
            log("===== 嘗試 %s (%d/%d): %s → |S| = %d, |G₂′| = %d, |G₃′| = %d %s; 輪上限 %.2f h (+延長 ≤ %.2f h); CPU 已用 %.1f / %.0f; wall 剩 %.1f h =====" % (
                tag, i + 1, a.attempts, kind, len(S_try), g2.n - len(S_try), 2 * (g2.n - len(S_try)) - 1,
                "✓ < 1441" if 2 * (g2.n - len(S_try)) - 1 < 1441 else "(未到 1441)", cap / 3600, a.extend / 3600, self.cpu_h_used(), a.cpu_cap_h, rem_wall_h))
            self.step("Phase 3d 嘗試 %s (%d/%d): 剪 %d 粒 → |G₂′| %d |G₃′| %d; buildg2 → march d=%d → cnc2k %d workers (leaf 證明保留 %s); 輪上限 %.1f h + 延長 ≤ %.1f h; CPU %.1f / %.0f CPU-h; wall %.1f / %.0f h" % (
                tag, i + 1, a.attempts, len(S_try), g2.n - len(S_try), 2 * (g2.n - len(S_try)) - 1, a.depth, a.workers, os.path.join(a.keep_root, tag),
                cap / 3600, a.extend / 3600, self.cpu_h_used(), a.cpu_cap_h, self.elapsed() / 3600, a.total_cap / 3600))
            try:
                rec = self.campaign(tag, S_try, cap)
            except Exception as e:
                rec = {"tag": tag, "removed": len(S_try), "S": sorted(S_try), "status": "error", "error": repr(e)[-600:], "wall_s": 0.0, "dir": os.path.join(self.out, tag), "settled": False}
                subprocess.run(["pkill", "-x", "kissat"], capture_output=True); subprocess.run(["pkill", "-x", "drat-trim"], capture_output=True)
                kd = os.path.join(a.keep_root, tag)
                if os.path.isdir(kd):                                                    # 審查: 例外之後唔敢刪 —— cnc2k 可能已經 certified, 證明留返俾人手 / resume
                    rec["keep"] = {"dir": kd, "on_disk": True, "retained_after_exception": True} | dir_stats(kd)
            rec["attempt"] = i + 1; rec["kind"] = kind; rec["added_candidates"] = added
            self.attempts.append(rec); self.save()
            if a.dry_run:
                rec["settled"] = True; st["stop_reason"] = "DRY RUN: %s 建咗 CNF 就停 (%s)" % (tag, rec["dir"]); self.save(); break
            if rec["status"] in ("error", "cnc2-error", "march-refuted-root", "stuck"):
                rec["settled"] = True; st["needs_operator"] = True
                st["stop_reason"] = "!! %s %s —— 停, 要人手睇 %s: %s" % (tag, rec["status"], rec["dir"], (rec.get("error") or (rec.get("cnc_log_tail") or "")[-300:]).replace("\n", " | ")); break
            if rec["status"] in ("budget-stop", "hard-killed"):
                rec["settled"] = False; st["needs_operator"] = True                      # 審查: 唔 settle + keep 保留 ⇒ 加 --ack-operator resume 會用同一個 tag cnc2k --resume 續, 已驗嘅 cube 唔白做
                st["stop_reason"] = ("%s 超上限未完 (%s: leaf %s/%s 已驗, 證明保住喺 %s, 估計仲要 %s h; 輪上限 %.2f h + 延長 %.0f s) —— 停, 等人手決定。"
                                     "續跑: `python3 probe3d.py --resume --ack-operator …` (或者 resume3d.sh 之前人手清 state.needs_operator), cnc2k --resume 會由已完成嘅 %s 個 cube 續落去") % (
                    tag, rec["status"], rec.get("leaves"), rec.get("n_cubes"), os.path.join(a.keep_root, tag), rec.get("eta_remaining_h"),
                    rec["cap_s"] / 3600, rec.get("extended_s") or 0, rec.get("leaves")); break
            if rec["status"] == "certified-keep-incomplete":
                rec["settled"] = True; st["needs_operator"] = True
                st["stop_reason"] = "!! %s L1″ certified 但 %d 個證明搬去 D: 失敗而且修唔到 (%s) —— 封存規則要求全套證明喺碟上, 停, 要人手睇 %s" % (
                    tag, len(rec["keep_repair"]["failed"]), rec["keep_repair"]["failed"][:10], os.path.join(rec["dir"], "cnc_" + tag, "keep_repair.json")); break
            if rec["status"] == "certified":
                self.certify_final(rec); rec["settled"] = True; self.save()
                if not (rec.get("l3_ok") and rec.get("col5_ok")):
                    st["needs_operator"] = True
                    st["stop_reason"] = "!! %s L1″ certified 但完整認證有步驟失敗 (l3_ok=%s, col5_ok=%s) —— 停, 要人手睇 %s" % (tag, rec.get("l3_ok"), rec.get("col5_ok"), os.path.join(rec["dir"], "l3g2.log")); break
                st["S_acc"] = sorted(rec["S"]); st["kept_certified"] = [tag]
                st["best"] = {"tag": tag, "dir": rec["dir"], "removed": rec["removed"], "G2p_n": rec["G2p_n"], "G2p_m": rec["G2p_m"], "G3p_n": rec["G3p_n"], "G3p_m": rec["G3p_m"],
                              "keep_dir": os.path.join(a.keep_root, tag), "leaves": rec["leaves"], "base_sha256": rec["cnf"]["cnf_sha256"], "when": time.strftime("%Y-%m-%d %H:%M:%S")}
                st["record_candidate"] = bool(rec["G2p_n"] <= RECORD_G2P)
                st["stop_reason"] = ("RECORD_CANDIDATE: |G₂′| = %d ≤ %d ⇒ |G₃′| = %d < 1441 (%s; L1″+L2″+L3″+完整性+spindle A/B+5 色 全部 ✓) —— 即刻停, 唔再剪; finalize3d 做獨立重驗 + 封存 + RECORD_CANDIDATE.md"
                                     if st["record_candidate"] else
                                     "有進步但未到 1441: |G₂′| = %d (> %d) ⇒ |G₃′| = %d (原本 1591) (%s; 全部認證 ✓) —— 停, 照樣封存報告") % (rec["G2p_n"], RECORD_G2P, rec["G3p_n"], tag)
                log("*** %s ***" % st["stop_reason"]); break
            if rec["status"] == "SAT":
                if not rec.get("witness"):
                    rec["settled"] = True; st["needs_operator"] = True
                    st["stop_reason"] = "!! %s SAT 但染色證書覆核失敗 (%s) —— 編碼/解碼有 bug, 停" % (tag, rec.get("colouring")); break
                B = sorted(rec["witness"]["blocked_min"]); rec["settled"] = True
                st["B_sets"].append({"tag": tag, "B": B, "size": len(B), "col_file": rec["colouring"]["col_file"], "witness_col": rec["witness"]["out"]})
                st["excluded"] = sorted(set(st["excluded"]) | set(B))
                log("%s: SAT → 擋路集 B (|B| = %d) = %s; 累計排除 %d 粒" % (tag, len(B), B, len(st["excluded"])))
                self.save(); continue
            rec["settled"] = True; st["needs_operator"] = True; st["stop_reason"] = "!! %s 未知狀態 %s" % (tag, rec["status"]); break
        if not st["stop_reason"]:
            st["stop_reason"] = "三次都試完 (attempts %d)" % len(self.attempts)
        self.cur = {}; self.save()
        if st.get("paused"):
            self.step("Phase 3d PAUSED (PAUSE 旗): 用 resume3d.sh 續跑"); log("PROBE3D PAUSED: %s" % st["stop_reason"]); return
        st["finished"] = time.strftime("%Y-%m-%d %H:%M:%S"); self.save()
        self.step("Phase 3d 縮圖完 (%s): 最佳 %s; CPU %.1f / %.0f CPU-h; 用時 %.2f h; 跟住 finalize3d (獨立重驗 + 封存 + 報告)" % (
            st["stop_reason"][:200], (st.get("best") or {}).get("tag") or "冇新證書", self.cpu_h_used(), a.cpu_cap_h, self.elapsed() / 3600))
        log("PROBE3D DONE: %s" % st["stop_reason"])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True); ap.add_argument("--batches", required=True); ap.add_argument("--out", required=True); ap.add_argument("--seed-run", default=None)
    ap.add_argument("--attempts", type=int, default=3); ap.add_argument("--target-removed", type=int, default=350); ap.add_argument("--tag-prefix", default="p3d")
    ap.add_argument("--workers", type=int, default=14); ap.add_argument("--cap", type=float, default=8 * 3600); ap.add_argument("--extend", type=float, default=3600)
    ap.add_argument("--extend-eta-h", type=float, default=0.5); ap.add_argument("--total-cap", type=float, default=24 * 3600); ap.add_argument("--cpu-cap-h", type=float, default=160.0)
    ap.add_argument("--timeout", type=float, default=900); ap.add_argument("--depth", type=int, default=14); ap.add_argument("--proof-dir", default=None)
    ap.add_argument("--keep-root", default="/mnt/d/hadwiger/phase3d/keep"); ap.add_argument("--proj-first-h", type=float, default=4.5)
    ap.add_argument("--resume", action="store_true"); ap.add_argument("--ack-operator", action="store_true"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    a.proof_dir = os.path.abspath(os.path.expanduser(a.proof_dir or os.path.join("/dev/shm", a.run_id))); os.makedirs(a.proof_dir, exist_ok=True)
    a.keep_root = os.path.abspath(os.path.expanduser(a.keep_root)); os.makedirs(a.keep_root, exist_ok=True)
    a.batches = os.path.abspath(a.batches)
    Probe(a).run()

if __name__ == "__main__":
    main()
