#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probe3b.py —— Phase 3b 第 2 步: G₂ 縮圖循環 (Haugland 方向) —— 每輪 ≤ 3 h, 最多 12 輪, witness 跳過, 閘門 (第 3 輪後), 到達 |G₂′| ≤ 720 即停
  每輪 r 對累計批次 S = S_acc ∪ batch_r:
    a. L1″ 戰役 (buildg2 → march_cu d=14 → cnc2 kissat T=600 → 2T → 再拆, 14 workers, ext4 binary DRAT 驗完即刪, cover, 5% 審計)
       certified → L2″ + L3″ + 完整性 + spindle A (l3g2.py) → S_acc = S → 下一輪
    b. SAT (染色逐邊覆核, col(u) ≠ col(v)) → witness_g2 貪心放返 → B → 重試 S \\ B (b); 再 SAT → B′ → 重試 S \\ (B ∪ B′) (c); 再 SAT → 二分一次 (d);
       再 SAT → 該批 blocked, 下一批候選排除 B ∪ batch. 每輪最多 3 張額外證書; 每輪硬上限 --cap 秒 (含全部嘗試).
    c. 第 1 張證書超上限未完 → 停 (之後只會更難); 第 2+ 張超上限 → 該批 blocked, 繼續
  B 入面嘅頂點標「本輪必要」(下一輪候選排除, 唔係永久); 第二次再入 B 就永久排除 (防止來回撞同一個集).
  第 3 輪後: hardness_g2.py 閘門 (三模型外推 ≤ 200 CPU-h 且 3 輪內 ≥ 2 輪淨剪 ≥ 20) 唔綠 → 停
  任何時候 |G₂′| ≤ 720 (⇔ |G₃′| = 2|G₂′| − 1 < 1441): l3g2 --engine-b 三重認證 → 停, 即刻報告
用法: python3 probe3b.py --run-id ID --batches batches_g2.json --out DIR [--rounds 12] [--workers 14] [--cap 10800] [--total-cap 108000] [--timeout 600] [--depth 14]
                         [--proof-dir DIR] [--k 30] [--resume]
"""
import sys, os, json, time, argparse, subprocess, signal, statistics, re
if not __debug__:
    sys.exit("!! 唔准用 python -O")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from g2common import G2, decode_model, verify_colouring, write_col, sha, MARCH, PH2B, PH3B
import witness_g2
PY = sys.executable
L1_MEAN_SV = 0.78                      # Phase 2b L1 (G₁ pair 性質) 每 cube solve+verify, 對照
G2RECON = {"E_floor_h": 1.43, "mean_sv_s": 4.4, "n_cubes": 16350}   # Phase 4 p4r2_g2recon: x=0 抽樣外推 (唔係證書, 只做參考錨點)
TARGET_G2P = 720                       # |G₂′| ≤ 720 ⇔ |G₃′| < 1441

def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)

def free_gb(path):
    try:
        st = os.statvfs(path); return st.f_bavail * st.f_frsize / 1e9
    except Exception:
        return None

class Probe:
    def __init__(self, a):
        self.a = a; self.out = os.path.abspath(a.out); os.makedirs(self.out, exist_ok=True)
        self.bj = json.load(open(a.batches)); self.ordering = self.bj["ordering"]; self.P2 = set(self.bj["P2"]); self.k = a.k or self.bj["k"]
        self.g2 = G2()
        self.state_p = os.path.join(self.out, "state.json"); self.rounds_p = os.path.join(self.out, "rounds.json"); self.status_p = os.path.join(self.out, "status.json")
        if a.resume and os.path.exists(self.state_p):
            self.st = json.load(open(self.state_p)); self.rounds = json.load(open(self.rounds_p)) if os.path.exists(self.rounds_p) else []
            n_before = len(self.rounds)
            self.rounds = [x for x in self.rounds if x["round"] <= self.st["round_done"]]      # 審查 finding: 掉走未結算嘅尾巴輪 (state.json round_done 先算數)
            if n_before != len(self.rounds):
                log("resume: 掉走 %d 個未結算嘅輪記錄 (round > round_done=%d); 該輪會由頭再開 (已有 cnc_<tag>/state.json 嘅嘗試會 cnc2 --resume)" % (n_before - len(self.rounds), self.st["round_done"]))
            self.st["elapsed_before_s"] = self.st.get("elapsed_s", 0)
            if not self.st.get("target_reached"):
                self.st["stop_reason"] = None                                                    # 審查 finding: 已到目標就唔准再縮
            log("resume: round_done %d, S_acc %d 粒, excluded_next %d, perma %d, 之前用時 %.1f h" % (self.st["round_done"], len(self.st["S_acc"]), len(self.st["excluded_next"]), len(self.st["perma_excluded"]), self.st["elapsed_before_s"] / 3600))
        else:
            assert not os.path.exists(self.state_p), "out 已有 state.json (要 --resume 或者換 run-id)"
            self.st = {"run_id": a.run_id, "started": time.strftime("%Y-%m-%d %H:%M:%S"), "elapsed_before_s": 0.0, "S_acc": [], "excluded_next": [], "perma_excluded": [],
                       "B_history": [], "round_done": 0, "stop_reason": None, "gate": None, "target_reached": False, "config": vars(a)}
            self.rounds = []
        self.T0 = time.time(); self.cur = {}

    def elapsed(self):
        return self.st["elapsed_before_s"] + time.time() - self.T0

    def remaining_total(self):
        return self.a.total_cap - self.elapsed()

    def step(self, msg):
        try:
            open(os.path.join(PH3B, "STEP.txt"), "w").write(msg)
        except Exception:
            pass

    def save(self):
        st = self.st; st["elapsed_s"] = round(self.elapsed(), 1); st["updated_str"] = time.strftime("%Y-%m-%d %H:%M:%S")
        json.dump(st, open(self.state_p + ".tmp", "w"), indent=1); os.replace(self.state_p + ".tmp", self.state_p)
        json.dump(self.rounds, open(self.rounds_p + ".tmp", "w"), indent=1); os.replace(self.rounds_p + ".tmp", self.rounds_p)
        summ = []
        for r in self.rounds:
            summ.append({k: r.get(k) for k in ("round", "status", "net_removed", "G2p_n", "G3p_n", "wall_s")} | {"attempts": [{k: x.get(k) for k in ("tag", "removed", "status", "n_cubes", "leaves", "mean_solve_s", "mean_sv_s", "wall_s", "B_size", "l3_ok")} for x in r["attempts"]], "B_sets": r.get("B_sets")})
        status = {"run_id": st["run_id"], "started": st["started"], "updated_str": st["updated_str"], "elapsed_s": st["elapsed_s"], "total_cap_s": self.a.total_cap, "round_done": st["round_done"],
                  "S_acc_size": len(st["S_acc"]), "G2p_n": self.g2.n - len(st["S_acc"]), "G3p_n": 2 * (self.g2.n - len(st["S_acc"])) - 1, "excluded_next": len(st["excluded_next"]), "perma_excluded": st["perma_excluded"],
                  "current": self.cur, "stop_reason": st["stop_reason"], "gate": st.get("gate"), "target_reached": st["target_reached"], "rounds": summ}
        json.dump(status, open(self.status_p + ".tmp", "w"), indent=1, ensure_ascii=False); os.replace(self.status_p + ".tmp", self.status_p)
        self.write_ledger()

    def write_ledger(self):
        L = ["# ledger_g2.md —— Phase 3b 縮圖循環帳 (run %s, 更新 %s)" % (self.st["run_id"], time.strftime("%Y-%m-%d %H:%M:%S")), "",
             "S_acc (已認證可成集剪走) = %d 粒 → |G₂′| = %d, |G₃′| = %d; 永久排除 %s; 下一輪排除 %d 粒; 用時 %.2f h / 上限 %.1f h%s" % (
                 len(self.st["S_acc"]), self.g2.n - len(self.st["S_acc"]), 2 * (self.g2.n - len(self.st["S_acc"])) - 1, self.st["perma_excluded"], len(self.st["excluded_next"]),
                 self.elapsed() / 3600, self.a.total_cap / 3600, ("; **停: %s**" % self.st["stop_reason"]) if self.st["stop_reason"] else ""), "",
             "| 輪 | 嘗試 | |S| | 結果 | cube | leaf | 每 cube solve (s) | 每 cube solve+verify (s) | ×L1 / ×G₂recon | wall | B (擋住集) | |G₂′| | |G₃′| | L2″/L3″/完整/spindle |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in self.rounds:
            for x in r["attempts"]:
                L.append("| %d | %s | %d | %s | %s | %s | %s | %s | %s / %s | %s s (%.2f h) | %s | %s | %s | %s |" % (
                    r["round"], x["tag"], x["removed"], x["status"], x.get("n_cubes", "—"), x.get("leaves", "—"), x.get("mean_solve_s", "—"), x.get("mean_sv_s", "—"),
                    x.get("x_L1_sv", "—"), x.get("x_G2recon_sv", "—"), x.get("wall_s", "—"), (x.get("wall_s") or 0) / 3600,
                    ("|B|=%d %s" % (x["B_size"], x["witness"]["blocked_min"])) if x.get("witness") else "—",
                    x["cnf"]["n_remaining"] if x.get("cnf") else "—", x.get("G3p_n", "—"),
                    ("✓" if x.get("l3_ok") else "!!") if x["status"] == "certified" else "—"))
            L.append("| %d | **輪結算** | — | **%s** | — | — | — | — | — | %.2f h | B 集合 %s | — | — | 淨剪 %s (S_acc %d → %d) |" % (
                r["round"], r.get("status"), (r.get("wall_s") or 0) / 3600, r.get("B_sets"), r.get("net_removed"), len(r["S_acc_before"]), len(r.get("S_acc_after", r["S_acc_before"]))))
        if self.st.get("gate"):
            L += ["", "## 閘門 (第 3 輪後)", "**%s** —— %s" % (self.st["gate"].get("verdict"), self.st["gate"].get("why"))]
        open(os.path.join(self.out, "ledger_g2.md"), "w").write("\n".join(L) + "\n")

    # ---------------- 一張證書 ----------------
    def campaign(self, tag, S, cap):
        a = self.a; d = os.path.join(self.out, tag); os.makedirs(d, exist_ok=True)
        S = sorted(S)
        rec = {"tag": tag, "removed": len(S), "S": S, "cap_s": round(cap), "started": time.strftime("%Y-%m-%d %H:%M:%S")}
        t_round = time.time()
        cdir = os.path.join(d, "cnc_" + tag)
        self.cur = {"tag": tag, "stage": "build", "S_size": len(S), "cnc_status": os.path.join(cdir, "status.json"), "cap_s": round(cap), "started": rec["started"]}; self.save()
        # 1. CNF (buildg2: 拒絕 u/v/P₂)
        r = subprocess.run([PY, os.path.join(PH3B, "buildg2.py"), "--remove", ",".join(map(str, S)), "--out", d, "--tag", "base", "--protected", a.batches], capture_output=True, text=True, timeout=600)
        assert r.returncode == 0, "buildg2 失敗: " + r.stdout[-500:] + r.stderr[-500:]
        log(r.stdout.strip()); cnf = os.path.join(d, "base.cnf"); rec["cnf"] = json.load(open(os.path.join(d, "base.json")))
        # 2. march_cu (或 resume 舊 campaign)
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
                rec["status"] = "march-refuted-root"; rec["wall_s"] = round(time.time() - t_round, 1); return rec   # 唔信 march 單方面 refute, 當冇證書
        # 3. cnc2
        budget = max(600, cap - (time.time() - t_round))
        logp = os.path.join(d, "cnc.log"); skip = False
        if resumed:
            st_old = json.load(open(os.path.join(cdir, "state.json")))
            # 審查 finding (soundness): 舊 campaign 嘅 base.cnf 必須同而今 S 建出嚟嘅 base.cnf byte 級一致 (buildg2 deterministic), 否則 S 變咗, 拒絕重用
            assert st_old.get("base_sha") == rec["cnf"]["cnf_sha256"], "!! %s: 舊 cnc2 campaign base_sha %s != 而今 S 嘅 base.cnf sha %s (S 變咗? --k/--batches/state.json 對唔上), 拒絕 resume" % (
                tag, st_old.get("base_sha"), rec["cnf"]["cnf_sha256"])
            rec["n_cubes"] = st_old["n_cubes0"]; rec["icnf_sha"] = st_old["icnf_sha"]; rec["resumed"] = True; rec["march_s"] = None
            if (st_old.get("status") == "certified" and os.path.exists(os.path.join(cdir, "bundle.json"))) or st_old.get("sat"):
                skip = True; log("%s: 舊 campaign 已有結果 (%s), 直接讀" % (tag, "certified" if st_old.get("sat") is None else "SAT"))
            else:
                if os.path.exists(os.path.join(cdir, "lock")):
                    os.remove(os.path.join(cdir, "lock"))
                argv = [PY, os.path.join(PH2B, "cnc2.py"), "--resume", "--out", cdir, "--workers", str(a.workers), "--time-budget", str(int(st_old["wall_s"] + budget)), "--progress", "120"]
        else:
            argv = [PY, os.path.join(PH2B, "cnc2.py"), "--cnf", cnf, "--icnf", icnf, "--out", cdir, "--workers", str(a.workers), "--timeout", str(a.timeout), "--solver", "kissat",
                    "--proof-dir", a.proof_dir, "--binary", "--time-budget", str(int(budget)), "--split-depth", "3", "--max-split", "4", "--audit-frac", "0.05", "--progress", "120"]
        killed = False
        if not skip:
            self.cur["stage"] = "cnc2"; self.save()
            log("%s: cnc2 開始 (time-budget %.0f s, 硬殺 %.0f s): %s" % (tag, budget, cap + 900, " ".join(argv[2:])))
            t0 = time.time()
            with open(logp, "a") as lf:
                p = subprocess.Popen(argv, stdout=lf, stderr=subprocess.STDOUT, start_new_session=True)
                hard = t_round + cap + 900
                while True:
                    try:
                        rc = p.wait(timeout=30); break
                    except subprocess.TimeoutExpired:
                        if time.time() > hard:
                            killed = True; log("!! %s: 超硬上限 %.0f s, 硬殺 cnc2 process group" % (tag, cap + 900))
                            try:
                                os.killpg(p.pid, signal.SIGTERM); time.sleep(5); os.killpg(p.pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                            rc = p.wait(); break
            subprocess.run(["pkill", "-x", "kissat"], capture_output=True); subprocess.run(["pkill", "-x", "drat-trim"], capture_output=True)
            rec["cnc_rc"] = rc; rec["cnc_wall_s"] = round(time.time() - t0, 1)
        rec["hard_killed"] = killed
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
        rec["split_events"] = st.get("split_events"); rec["solver_errors"] = st.get("solver_errors"); rec["wasted_s"] = st.get("wasted_s")
        if solve:
            rec["mean_solve_s"] = round(statistics.mean(solve), 3); rec["median_solve_s"] = round(statistics.median(solve), 3); rec["max_solve_s"] = max(solve)
            rec["mean_verify_s"] = round(statistics.mean(ver), 3); rec["mean_sv_s"] = round(statistics.mean(solve) + statistics.mean(ver), 3)
            rec["x_L1_sv"] = round(rec["mean_sv_s"] / L1_MEAN_SV, 2); rec["x_G2recon_sv"] = round(rec["mean_sv_s"] / G2RECON["mean_sv_s"], 2)
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
            assert rec["cover_verified"] and rec["audit"]["all_ok"], "!! cnc2 話 certified 但 cover/audit 唔 ok"
            assert cb.get("base_sha") == rec["cnf"]["cnf_sha256"] == st.get("base_sha"), "!! bundle base_sha %s != base.cnf sha %s (證書唔係證而今嘅 S)" % (cb.get("base_sha"), rec["cnf"]["cnf_sha256"])
            assert cb.get("leaves") == len(done) and cb.get("n_cubes0") == rec.get("n_cubes"), "!! bundle leaves/n_cubes0 同 state.json 對唔上"
        elif killed:
            rec["status"] = "hard-killed"
        elif rec.get("cnc_rc") not in (None, 0, 10):
            rec["status"] = "cnc2-error"; rec["cnc_log_tail"] = open(logp, errors="ignore").read()[-2000:] if os.path.exists(logp) else None   # 審查 finding: 非正常退出唔係 timeout
        elif st.get("status") == "stuck" or rec["stuck"]:
            rec["status"] = "stuck"
        else:
            rec["status"] = "budget-stop"
        rec["wall_s"] = round(time.time() - t_round, 1); rec["cnc_status_json"] = st.get("status")
        if rec["status"] not in ("certified", "SAT") and solve:
            per = (sum(solve) + sum(ver) + (st.get("wasted_s") or 0)) / len(solve)
            rec["eta_remaining_h"] = round((rec["n_cubes"] - len(done)) * per / a.workers / 3600, 2)
        log("%s: %s —— cube %s, leaf 完成 %s, mean solve %s s, mean solve+verify %s s (L1 ×%s, G₂recon ×%s), wall %.0f s (%.2f h)%s%s" % (
            tag, rec["status"], rec.get("n_cubes"), rec["leaves"], rec.get("mean_solve_s"), rec.get("mean_sv_s"), rec.get("x_L1_sv"), rec.get("x_G2recon_sv"), rec["wall_s"], rec["wall_s"] / 3600,
            (", 未完: 估計仲要 %s h" % rec.get("eta_remaining_h")) if rec["status"] not in ("certified", "SAT") else "",
            (", 擋住集 B (|B|=%d) = %s" % (rec["B_size"], rec["witness"]["blocked_min"])) if rec.get("witness") else ""))
        # 5. L2″ + L3″ + 完整性 + spindle
        if rec["status"] == "certified":
            n_rem = rec["cnf"]["n_remaining"]; eb = n_rem <= TARGET_G2P
            self.cur["stage"] = "l3g2" + (" (+engine B, 目標達成三重認證)" if eb else ""); self.save()
            argv = [PY, os.path.join(PH3B, "l3g2.py"), "--remove", ",".join(map(str, S)), "--out", os.path.join(d, "l3")] + (["--engine-b"] if eb else [])
            try:
                r = subprocess.run(argv, capture_output=True, text=True, timeout=5 * 3600)
            except subprocess.TimeoutExpired as e:
                class R: pass
                r = R(); r.returncode = -999; r.stdout = (e.stdout or b"").decode(errors="ignore") if isinstance(e.stdout, bytes) else (e.stdout or ""); r.stderr = "!! l3g2 timeout 5 h"
            open(os.path.join(d, "l3g2.log"), "w").write(r.stdout + r.stderr)
            sm = json.load(open(os.path.join(d, "l3", "summary.json"))) if os.path.exists(os.path.join(d, "l3", "summary.json")) else {}
            rec["l3_ok"] = (r.returncode == 0 and sm.get("all_ok") is True); rec["G3p_n"] = sm.get("G3p", {}).get("n"); rec["G3p_m"] = sm.get("G3p", {}).get("m")
            rec["G2p_n"] = sm.get("G2p", {}).get("n"); rec["l3_summary"] = {k: sm.get(k) for k in ("complete_G2p", "complete_G3p", "L2", "L3", "spindle_A", "spindle_B")}
            for line in r.stdout.splitlines():
                if line.startswith(("[G3″]", "[complete", "[L2″]", "[L3″]", "[spindle", "[l3g2]")):
                    log("  " + line[:230])
        return rec

    def colouring_cert(self, d, S, model_pos):
        col = decode_model(model_pos, self.g2.n, S); vc = verify_colouring(self.g2, S, col)
        p = os.path.join(d, "G2minus_%dv.col" % len(S))
        s = write_col(p, S, col, "c 4-colouring of G2 minus %s with col(-1,0) != col(1,0) (u=#%d, v=#%d): witness that this set contains a vertex necessary for the mono-pair property" % (sorted(S), self.g2.u, self.g2.v))
        rec = {"col_file": p, "sha256": s, **vc}
        json.dump(rec, open(p[:-4] + ".json", "w"), indent=1)
        log("!! SAT 染色證書: %d 點染色, 缺色 %d, 同色邊 %d/%d, col(u)=%s col(v)=%s → %s (%s)" % (
            rec["n_coloured"], rec["missing"], rec["bad_edges"], rec["edges_checked"], rec["col_u"], rec["col_v"], "逐邊覆核通過 ✓ (S 含必要頂點)" if rec["ok"] else "!! 覆核失敗", p))
        return rec

    # ---------------- 閘門 ----------------
    def gate(self, final=False):
        hj = os.path.join(self.out, "hardness_g2.json")
        if os.path.exists(hj):
            os.remove(hj)                                    # 審查 finding: 唔准讀舊 hardness_g2.json
        try:
            r = subprocess.run([PY, os.path.join(PH3B, "hardness_g2.py"), "--probe", self.out, "--batches", self.a.batches, "--out", self.out, "--workers", str(self.a.workers)],
                               capture_output=True, text=True, timeout=1800)
            rc, out_txt = r.returncode, r.stdout + r.stderr
        except subprocess.TimeoutExpired:
            rc, out_txt = -999, "!! hardness_g2 timeout"
        open(os.path.join(self.out, "hardness_g2.log"), "a").write("\n===== %s =====\n" % time.strftime("%Y-%m-%d %H:%M:%S") + out_txt)
        h = json.load(open(hj)) if (rc == 0 and os.path.exists(hj)) else {"verdict": "ERROR", "why": "hardness_g2.py rc=%s: %s" % (rc, out_txt[-300:])}
        g = {"verdict": h.get("verdict"), "why": h.get("why"), "estimate": h.get("estimate"), "when": time.strftime("%Y-%m-%d %H:%M:%S"), "final": final}
        log("閘門 (%s): %s —— %s" % ("最終" if final else "第 3 輪後", g["verdict"], g["why"]))
        return g

    # ---------------- 主循環 ----------------
    def run(self):
        a = self.a; st = self.st; g2 = self.g2
        while st["round_done"] < a.rounds and not st["stop_reason"]:
            r = st["round_done"] + 1
            if self.remaining_total() < 1800:
                st["stop_reason"] = "總時間上限 %.1f h 前唔夠時間開 round %d (已用 %.2f h)" % (a.total_cap / 3600, r, self.elapsed() / 3600); break
            cf = free_gb("/mnt/c"); df = free_gb("/mnt/d")
            if (cf is not None and cf < 25) or (df is not None and df < 300):
                st["stop_reason"] = "磁碟紀律: C: 剩 %s GB (要 ≥ 25, vhdx 所在) / D: 剩 %s GB (要 ≥ 300) → 停" % (cf, df); break
            S_acc = set(st["S_acc"]); excl = set(st["excluded_next"]) | set(st["perma_excluded"])
            cands = [w for w in self.ordering if w not in S_acc and w not in excl]
            batch = cands[:self.k]
            if len(batch) < self.k:
                st["stop_reason"] = "候選唔夠一批 (%d < %d)" % (len(batch), self.k); break
            t_round = time.time(); cap = min(a.cap, self.remaining_total())
            rr = {"round": r, "batch": batch, "S_acc_before": sorted(S_acc), "excluded_this_round": sorted(excl), "attempts": [], "B_sets": [], "started": time.strftime("%Y-%m-%d %H:%M:%S"), "cap_s": round(cap)}
            self.rounds.append(rr); self.save()
            log("===== round %d: S_acc %d 粒 + batch %d 粒 %s (排除 %d 粒); 輪上限 %.2f h; 總剩 %.1f h =====" % (r, len(S_acc), len(batch), batch, len(excl), cap / 3600, self.remaining_total() / 3600))
            S_target = S_acc | set(batch); S_try = set(S_target); tried = []; status = None; certified_S = None
            for ai in range(4):
                rem = cap - (time.time() - t_round)
                if rem < 900:
                    status = "cap-exhausted"; log("round %d: 輪上限剩 %.0f s < 900, 唔開第 %d 張證書" % (r, rem, ai + 1)); break
                tag = "r%02d%s" % (r, "abcd"[ai])
                self.step("Phase 3b round %d/%d 嘗試 %s (%s): 剪 %d 粒 (S_acc %d) → buildg2 → march d=%d → cnc2 %d workers; 輪上限剩 %.1f h; 總用時 %.1f h / %.0f h; S_acc %d → |G₂′| %d |G₃′| %d" % (
                    r, a.rounds, tag, ["第 1 張", "S∖B", "S∖(B∪B′)", "二分"][ai], len(S_try), len(S_acc), a.depth, a.workers, rem / 3600, self.elapsed() / 3600, a.total_cap / 3600, len(S_acc), g2.n - len(S_acc), 2 * (g2.n - len(S_acc)) - 1))
                try:
                    rec = self.campaign(tag, S_try, rem)
                except Exception as e:                       # 審查 finding: 任何 campaign 內部錯誤 (buildg2 assert / march 錯 / 檔案錯) 記低再停, 唔好 crash 走晒 state
                    rec = {"tag": tag, "removed": len(S_try), "S": sorted(S_try), "status": "error", "error": repr(e)[-600:], "wall_s": 0.0}
                    subprocess.run(["pkill", "-x", "kissat"], capture_output=True); subprocess.run(["pkill", "-x", "drat-trim"], capture_output=True)
                rec["round"] = r; rec["attempt"] = ai + 1; rec["kind"] = ["first", "S-B", "S-(B+B')", "bisect"][ai]
                rr["attempts"].append(rec); tried.append(sorted(S_try)); self.save()
                if rec["status"] in ("error", "cnc2-error", "march-refuted-root"):
                    status = "error"; st["stop_reason"] = "!! %s %s —— 停, 要人手睇 %s: %s" % (tag, rec["status"], os.path.join(self.out, tag), (rec.get("error") or (rec.get("cnc_log_tail") or "")[-300:]).replace("\n", " | ")); break
                if rec["status"] == "certified":
                    if not rec.get("l3_ok"):
                        status = "l3-failed"; st["stop_reason"] = "!! %s L1″ certified 但 L2″/L3″/完整性/spindle 有步驟失敗 —— 停, 要人手睇 %s" % (tag, os.path.join(self.out, tag, "l3g2.log")); break
                    certified_S = set(S_try); status = "certified"; break
                if rec["status"] == "SAT":
                    if not rec.get("witness"):
                        st["stop_reason"] = "!! %s SAT 但染色證書覆核失敗 (%s) —— 編碼/解碼有 bug, 停" % (tag, rec.get("colouring")); status = "error"; break
                    B = set(rec["witness"]["blocked_min"]); rr["B_sets"].append(sorted(B))
                    Bs = set().union(*[set(b) for b in rr["B_sets"]])
                    if ai < 2:
                        S_new = S_target - Bs
                    elif ai == 2:
                        R = S_target - Bs; rest = [w for w in batch if w in R]; half = rest[:len(rest) // 2]
                        S_new = (R & S_acc) | set(half)
                    else:
                        status = "blocked"; break
                    if not (S_new - S_acc) or sorted(S_new) in tried:
                        status = "blocked"; log("round %d: B 集合食晒成批 / 重複集合 (S_new − S_acc = %d 粒), 唔再試, 該批 blocked" % (r, len(S_new - S_acc))); break
                    S_try = S_new; continue
                # cap-hit / hard-killed / budget-stop / stuck / march-refuted-root
                if ai == 0:
                    status = "cap-hit"; st["stop_reason"] = "round %d 第 1 張證書超 %.1f h 輪上限未完 (%s: leaf %s/%s, 估計仲要 %s h) —— 停, 之後只會更難" % (
                        r, cap / 3600, rec["status"], rec.get("leaves"), rec.get("n_cubes"), rec.get("eta_remaining_h")); break
                status = "cap-exhausted"; log("round %d: %s %s (第 %d 張) → 該批 blocked" % (r, tag, rec["status"], ai + 1)); break
            # 輪結算
            rr["status"] = status; rr["wall_s"] = round(time.time() - t_round, 1)
            Bs_all = set().union(*[set(b) for b in rr["B_sets"]]) if rr["B_sets"] else set()
            if status == "certified":
                st["S_acc"] = sorted(certified_S); rr["S_acc_after"] = sorted(certified_S); rr["net_removed"] = len(certified_S) - len(S_acc)
                last = rr["attempts"][-1]; rr["G2p_n"] = last["cnf"]["n_remaining"]; rr["G3p_n"] = last.get("G3p_n"); rr["certified_tag"] = last["tag"]
                st["excluded_next"] = sorted(Bs_all)
            else:
                rr["S_acc_after"] = sorted(S_acc); rr["net_removed"] = 0; rr["G2p_n"] = g2.n - len(S_acc); rr["G3p_n"] = 2 * (g2.n - len(S_acc)) - 1
                st["excluded_next"] = sorted(Bs_all | set(batch)) if status in ("blocked", "cap-exhausted") else sorted(Bs_all)
            hist = set(st["B_history"]); repeat = Bs_all & hist
            st["perma_excluded"] = sorted(set(st["perma_excluded"]) | repeat); st["B_history"] = sorted(hist | Bs_all)
            st["round_done"] = r; self.save()
            log("round %d 結算: %s; 淨剪 %s (S_acc %d → %d, |G₂′| %d, |G₃′| %d); B 集合 %s; 下一輪排除 %d 粒 (永久 %s); 輪 wall %.2f h; 總用時 %.2f h" % (
                r, status, rr["net_removed"], len(S_acc), len(st["S_acc"]), rr["G2p_n"], rr["G3p_n"], rr["B_sets"], len(st["excluded_next"]), st["perma_excluded"], rr["wall_s"] / 3600, self.elapsed() / 3600))
            if status == "certified" and rr["G2p_n"] <= TARGET_G2P:
                st["target_reached"] = True
                st["stop_reason"] = "TARGET REACHED: |G₂′| = %d ≤ %d ⇒ |G₃′| = %d < 1441 (round %d, %s; 三重認證 l3g2 --engine-b %s) —— 停, 即刻報告" % (
                    rr["G2p_n"], TARGET_G2P, rr["G3p_n"], r, rr["certified_tag"], "✓" if rr["attempts"][-1].get("l3_ok") else "!!"); break
            if st["stop_reason"]:
                break
            if os.path.exists(os.path.join(self.out, "PAUSE")):          # 操作員暫停旗 (輪與輪之間乾淨停; 之後 --resume 續)
                os.remove(os.path.join(self.out, "PAUSE"))
                st["stop_reason"] = "PAUSED by operator after round %d (PAUSE flag) —— 用 --resume 續跑" % r; st["paused"] = True; break
            if r == 3:
                g = self.gate(); st["gate"] = g; self.save()
                if g["verdict"] != "GREEN":
                    st["stop_reason"] = "閘門 (第 3 輪後) %s: %s" % (g["verdict"], g["why"]); break
        if not st["stop_reason"]:
            st["stop_reason"] = "%d 輪完成 (輪數上限, 唔准自動加)" % st["round_done"]
        self.save()
        try:
            g = self.gate(final=True); st["gate_final"] = g
        except Exception as e:
            st["gate_final"] = {"verdict": "ERROR", "why": repr(e)}
        self.save()
        self.step("Phase 3b 縮圖循環完 (%s): S_acc %d 粒, |G₂′| %d, |G₃′| %d; 睇 runs/%s/ledger_g2.md / gate_g2.md / hardness_curve_g2.png" % (
            st["stop_reason"], len(st["S_acc"]), g2.n - len(st["S_acc"]), 2 * (g2.n - len(st["S_acc"])) - 1, st["run_id"]))
        log("PROBE3B DONE: %s" % st["stop_reason"])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True); ap.add_argument("--batches", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--rounds", type=int, default=12); ap.add_argument("--workers", type=int, default=14); ap.add_argument("--cap", type=float, default=3 * 3600)
    ap.add_argument("--total-cap", type=float, default=30 * 3600); ap.add_argument("--timeout", type=float, default=600); ap.add_argument("--depth", type=int, default=14)
    ap.add_argument("--proof-dir", default=None); ap.add_argument("--k", type=int, default=None); ap.add_argument("--resume", action="store_true")
    a = ap.parse_args()
    a.proof_dir = os.path.abspath(os.path.expanduser(a.proof_dir or os.path.join(PH2B, "proofs_ext4", a.run_id))); os.makedirs(a.proof_dir, exist_ok=True)
    a.batches = os.path.abspath(a.batches)
    Probe(a).run()

if __name__ == "__main__":
    main()
