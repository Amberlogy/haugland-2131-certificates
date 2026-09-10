#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probe3c.py —— Phase 3c: G₂ 縮圖戰役續剪 (Haugland 方向), 由 Phase 3b run p3br1_shrink 嘅 certified S_acc (90 粒, r03a) 接力, 新 run ID p3c1_shrink.
  同 phase3b/probe3b.py 一樣嘅每輪流程 (buildg2 → march_cu d=14 → cnc2k 14 workers → certified 就 l3g2 (L2″/L3″/完整性/spindle A); SAT 就 witness 跳過, 每輪最多 3 張額外證書),
  Phase 3c 新規則 (Amber 2026-09-07 授權):
    * 預算: 總成本上限 --cpu-cap-h 400 CPU-h (由 r04 起計; CPU-h = 每張證書 wall × workers, 同 Phase 3b 閘門定義一致); 總 wall 上限 --total-cap 40 h (checkpoint + --resume 可跨幾晚); 每輪硬上限 --cap 3.5 h
      開新一輪之前: 剩餘 CPU 預算 / workers 同 剩餘 wall 都要 ≥ 1.15 × 上一張 certified 證書嘅 wall (預測), 否則停; 輪上限 = min(--cap, 剩餘 wall, 剩餘 CPU/workers − 900 s) ⇒ 唔會超 400
    * 連續 --low-net-rounds 3 輪淨剪 < --low-net 10 粒 → 停
    * 封存: cnc2k --keep-dir <keep-root>/<tag>: 每個 leaf 證明 VERIFIED 之後保留喺 D:; 唔係 certified 嘅嘗試即刪佢嘅 keep 目錄; 上一輪 certified 嘅 keep 目錄只喺本輪 certified (L2″/L3″ 亦過) 之後先刪
      ⇒ 任何時刻最新認證圖嘅全套 leaf 證明都喺碟上. 搬失敗嘅 leaf 即場重解 + 重驗 + 再搬 (repair); 修唔到 → 停 (要人手睇)
    * |G₂′| ≤ 720 (⇔ |G₃′| = 2|G₂′| − 1 < 1441) 嘅一刻: l3g2 --engine-b 三重認證, 標 record_candidate, 即刻停 (唔再剪一粒); 之後由 finalize3c.py 獨立重驗 + 封存 + RECORD_CANDIDATE.md
    * 冇第 3 輪閘門 (Amber 放寬); hardness_g2 只喺完場跑一次做曲線/外推 (資訊)
    * 磁碟紀律: D: 剩 < 300 GB 或 C: 剩 < 25 GB 唔開新輪 (繼承); 證明暫存目錄 /dev/shm (RAM 盤), 驗完即搬 D:
用法: python3 probe3c.py --run-id p3c1_shrink --seed-run ~/hadwiger/phase3b/runs/p3br1_shrink --batches ~/hadwiger/phase3b/batches_g2.json --out ~/hadwiger/phase3c/runs/p3c1_shrink
                         [--rounds 30] [--workers 14] [--cap 12600] [--total-cap 144000] [--cpu-cap-h 400] [--timeout 600] [--depth 14] [--k 30]
                         [--proof-dir /dev/shm/p3c1_shrink] [--keep-root /mnt/d/hadwiger/phase3c/keep] [--low-net 10] [--low-net-rounds 3] [--resume] [--dry-run]
"""
import sys, os, json, time, argparse, subprocess, signal, statistics, re, shutil, hashlib
if not __debug__:
    sys.exit("!! 唔准用 python -O")
PH3B = os.path.expanduser("~/hadwiger/phase3b"); PH3C = os.path.expanduser("~/hadwiger/phase3c"); PH2B = os.path.expanduser("~/hadwiger/phase2b")
sys.path.insert(0, PH3B)
from g2common import G2, decode_model, verify_colouring, write_col, sha, MARCH, KISSAT, DRATTRIM   # noqa: E402  (Phase 3b 已審核嘅共用層, 一字不改)
import witness_g2                                                                                    # noqa: E402
PY = sys.executable
CNC = os.path.join(PH3C, "cnc2k.py")
L1_MEAN_SV = 0.78                      # Phase 2b L1 (G₁ pair 性質) 每 cube solve+verify, 對照
G2RECON = {"E_floor_h": 1.43, "mean_sv_s": 4.4, "n_cubes": 16350}   # Phase 4 p4r2_g2recon (抽樣外推, 唔係證書, 只做參考錨點)
TARGET_G2P = 720                       # |G₂′| ≤ 720 ⇔ |G₃′| < 1441
PROJ_FACTOR = 1.15                     # 下一輪 wall 預測 = 1.15 × 上一張 certified 證書 wall
DEFAULT_PROJ_H = 2.6                   # 冇 certified 證書可以參考時嘅預測 (Phase 3b r03a 2.26 h × 1.15)

def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)

def free_gb(path):
    try:
        st = os.statvfs(path); return st.f_bavail * st.f_frsize / 1e9
    except Exception:
        return None

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

def repair_keep_dir(cdir, keep_dir, st, proof_dir, timeout, logf=log):
    """certified 但有 leaf / 審計證明搬唔到 D: → 由 base.cnf + cube 重建 cube CNF (sha 核對), kissat 重解 (T=4×timeout; 審計用 --no-binary 同 cnc2k 審計一致), drat-trim 重驗, 再搬 (sha 核對).
    唔改 bundle.json (原證明 sha 照留), 結果記 keep_repair.json; state.json 只改 kept / repaired_proof_sha 欄. s60_full.py 亦用 (審查 #7/#22/#23)."""
    base_p = os.path.join(cdir, "base.cnf"); base_text = "".join(l for l in open(base_p) if not l.startswith(("p", "c")))
    nvars = int(open(base_p).readline().split()[2]); nbase = sum(1 for l in open(base_p) if not l.startswith(("p", "c")))
    done = st.get("done", {}); aud = st.get("audit") or []
    missing = [("leaf", cid, d) for cid, d in done.items() if not (d.get("kept") and os.path.exists(d["kept"]))]
    missing += [("audit", ar["id"], ar) for ar in aud if ar.get("ok") and not (ar.get("kept") and os.path.exists(ar["kept"]))]
    rep = {"missing": [(k, c) for k, c, _ in missing], "repaired": [], "failed": [], "records": {}}
    logf("keep-repair: %d 個證明唔喺 keep 目錄 (leaf %d, audit %d), 重解 + 重驗 + 再搬" % (len(missing), sum(1 for k, _, _ in missing if k == "leaf"), sum(1 for k, _, _ in missing if k == "audit")))
    tmpd = os.path.join(proof_dir, "repair"); os.makedirs(tmpd, exist_ok=True); tag = os.path.basename(cdir)
    for kind, cid, rec_ in missing:
        d = done.get(cid); key = "%s:%s" % (kind, cid)
        cnf = os.path.join(tmpd, "%s_%s.cnf" % (kind, cid)); proof = os.path.join(tmpd, ("%s_%s.drat" if kind == "leaf" else "%s_audit_%s.drat") % (tag, cid))
        r = {"id": cid, "kind": kind}
        try:
            if not d:
                raise KeyError("id %s 唔喺 done" % cid)
            with open(cnf + ".tmp", "w") as f:
                f.write("p cnf %d %d\n" % (nvars, nbase + len(d["cube"]))); f.write(base_text)
                for l in d["cube"]:
                    f.write("%d 0\n" % l)
            os.replace(cnf + ".tmp", cnf)
            r["cnf_sha_match"] = sha(cnf) == d["cnf_sha"]
            tl = 4 * timeout
            argv = [KISSAT, "--time=%d" % int(tl), cnf, proof] if kind == "leaf" else [KISSAT, "-q", "--no-binary", "--time=%d" % int(tl), cnf, proof]
            rr = subprocess.run(argv, capture_output=True, text=True, timeout=tl + 300)
            r["rc"] = rr.returncode
            if rr.returncode == 20:
                dr = subprocess.run([DRATTRIM, cnf, proof], capture_output=True, text=True, timeout=6 * 3600)
                r["verified"] = any(l.strip() == "s VERIFIED" for l in dr.stdout.splitlines()); r["proof_sha"] = sha(proof); r["proof_bytes"] = os.path.getsize(proof)
                r["same_sha_as_original"] = (r["proof_sha"] == (d["proof_sha"] if kind == "leaf" else rec_.get("proof_sha")))
                if r["verified"] and r["cnf_sha_match"]:
                    kd = keep_dir if kind == "leaf" else os.path.join(keep_dir, "audit")
                    os.makedirs(kd, exist_ok=True); dst = os.path.join(kd, os.path.basename(proof)); tmp = dst + ".part"
                    shutil.copyfile(proof, tmp)
                    if sha(tmp) == r["proof_sha"]:
                        os.replace(tmp, dst); r["kept"] = dst; rep["repaired"].append(key)
                        rec_["kept"] = dst; rec_["repaired_proof_sha"] = r["proof_sha"]; rec_.pop("keep_error", None)
                        if kind == "audit":
                            rec_["proof_sha"] = r["proof_sha"]
                    else:
                        os.remove(tmp); r["error"] = "keep sha mismatch after repair"
            if key not in rep["repaired"]:
                rep["failed"].append(key)
        except Exception as e:
            r["error"] = repr(e)[-300:]; rep["failed"].append(key)
        finally:
            for p in (cnf, proof):
                if os.path.exists(p):
                    os.remove(p)
        rep["records"][key] = r
        logf("  keep-repair %s %s: rc=%s verified=%s cnf_sha_match=%s same_sha=%s → %s" % (kind, cid, r.get("rc"), r.get("verified"), r.get("cnf_sha_match"), r.get("same_sha_as_original"), "kept ✓" if r.get("kept") else "!! " + str(r.get("error", "failed"))))
    stp = os.path.join(cdir, "state.json"); st["done"] = done; st["audit"] = aud; st["keep_repair"] = {"repaired": rep["repaired"], "failed": rep["failed"], "when": time.strftime("%Y-%m-%d %H:%M:%S")}
    json.dump(st, open(stp + ".tmp", "w")); os.replace(stp + ".tmp", stp)
    json.dump(rep, open(os.path.join(cdir, "keep_repair.json"), "w"), indent=1)
    rep["kept_after"] = sum(1 for d in done.values() if d.get("kept") and os.path.exists(d["kept"]))
    rep["kept_audit_after"] = sum(1 for ar in aud if ar.get("kept") and os.path.exists(ar["kept"]))
    logf("keep-repair 完: 修好 %d, 修唔到 %d; keep 目錄而今 leaf %d/%d, audit %d/%d" % (len(rep["repaired"]), len(rep["failed"]), rep["kept_after"], len(done), rep["kept_audit_after"], len(aud)))
    return rep

class Probe:
    def __init__(self, a):
        self.a = a; self.out = os.path.abspath(a.out); os.makedirs(self.out, exist_ok=True)
        self.bj = json.load(open(a.batches)); self.ordering = self.bj["ordering"]; self.P2 = set(self.bj["P2"]); self.k = a.k or self.bj["k"]
        self.g2 = G2()
        self.state_p = os.path.join(self.out, "state.json"); self.rounds_p = os.path.join(self.out, "rounds.json"); self.status_p = os.path.join(self.out, "status.json")
        if a.resume and os.path.exists(self.state_p):
            self.st = json.load(open(self.state_p)); self.rounds = json.load(open(self.rounds_p)) if os.path.exists(self.rounds_p) else []
            self.rounds_raw = list(self.rounds); n_before = len(self.rounds)
            self.rounds = [x for x in self.rounds if x["round"] <= self.st["round_done"]]      # 掉走未結算嘅尾巴輪 (state.json round_done 先算數)
            if n_before != len(self.rounds):
                log("resume: 掉走 %d 個未結算嘅輪記錄 (round > round_done=%d); 該輪會由頭再開 (已有 cnc_<tag>/state.json 嘅嘗試會 cnc2k --resume, keep 目錄照用)" % (n_before - len(self.rounds), self.st["round_done"]))
            if self.st.get("needs_operator") and not a.ack_operator:                             # 審查 #16: 操作員停機 (error / cap-hit / l3-failed / keep-incomplete) 唔准自動 resume 重試同一批
                sys.exit("!! 上次停係要人手睇: %s —— 唔准自動 --resume; 人手睇完要續跑就加 --ack-operator" % self.st.get("stop_reason"))
            if self.st.get("target_reached"):
                sys.exit("!! 已到目標 (record candidate): %s —— 唔准再剪" % self.st.get("stop_reason"))
            self.st["needs_operator"] = False
            dropped = [x for x in self.rounds_raw if x["round"] > self.st["round_done"]]
            self.st.setdefault("prior_wall_by_tag", {})
            for rr_ in dropped:                                                                   # 審查 #5/#14: 掉走嘅輪入面已完成嘅嘗試 (例如 SAT 嘅 r06a) 嘅 wall 唔可以消失
                for x in rr_["attempts"]:
                    if x.get("wall_s"):
                        self.st["prior_wall_by_tag"][x["tag"]] = max(float(x["wall_s"]), float(self.st["prior_wall_by_tag"].get(x["tag"], 0)))
            self.st["elapsed_before_s"] = self.st.get("elapsed_s", 0)
            self.st["stop_reason"] = None; self.st.pop("paused", None); self.st.pop("finished", None); self.st.pop("gate_final", None)   # 審查 #17
            self.st["resumes"] = self.st.get("resumes", 0) + 1; self.st["config_resume"] = vars(a)
            log("resume #%d: round_done %d, S_acc %d 粒, excluded_next %d, perma %d, 之前用時 %.2f h, CPU 已用 %.1f / %.0f CPU-h, kept_certified %s" % (
                self.st["resumes"], self.st["round_done"], len(self.st["S_acc"]), len(self.st["excluded_next"]), len(self.st["perma_excluded"]), self.st["elapsed_before_s"] / 3600,
                self.cpu_h_used(), a.cpu_cap_h, self.st.get("kept_certified")))
        else:
            assert not os.path.exists(self.state_p), "out 已有 state.json (要 --resume 或者換 run-id)"
            assert a.seed_run, "首跑要 --seed-run (Phase 3b run 目錄)"
            seed = self.load_seed(a.seed_run)
            self.st = {"run_id": a.run_id, "started": time.strftime("%Y-%m-%d %H:%M:%S"), "elapsed_before_s": 0.0, "S_acc": seed["S_acc"], "excluded_next": seed["excluded_next"],
                       "perma_excluded": seed["perma_excluded"], "B_history": seed["B_history"], "round_done": seed["round_done"], "stop_reason": None, "gate": None,
                       "target_reached": False, "record_candidate": False, "config": vars(a), "seed": seed["prov"], "kept_certified": [], "resumes": 0, "low_net_streak": 0, "needs_operator": False, "prior_wall_by_tag": {}}
            self.rounds = seed["rounds"]
            log("seed: 由 %s 接力 —— round_done %d, S_acc %d 粒 (|G₂′| %d, |G₃′| %d), 最後 certified %s (bundle sha %s…, l3 all_ok %s); Phase 3c 由 round %d (r%02da) 起計預算 %.0f CPU-h / %.0f h wall" % (
                seed["prov"]["run_id"], self.st["round_done"], len(self.st["S_acc"]), self.g2.n - len(self.st["S_acc"]), 2 * (self.g2.n - len(self.st["S_acc"])) - 1,
                seed["prov"]["last_certified_tag"], seed["prov"]["bundle_sha256"][:16], seed["prov"]["l3_all_ok"], self.st["round_done"] + 1, self.st["round_done"] + 1, a.cpu_cap_h, a.total_cap / 3600))
        self.T0 = time.time(); self.cur = {}

    def load_seed(self, seed_run):
        seed_run = os.path.abspath(os.path.expanduser(seed_run))
        st0 = json.load(open(os.path.join(seed_run, "state.json"))); r0 = json.load(open(os.path.join(seed_run, "rounds.json")))
        r0 = [x for x in r0 if x["round"] <= st0["round_done"]]
        assert r0 and r0[-1]["round"] == st0["round_done"] and r0[-1].get("status") == "certified", "seed 最後一輪唔係 certified"
        last = r0[-1]["attempts"][-1]; tag = last["tag"]
        assert last["status"] == "certified" and last.get("l3_ok") is True, "seed 最後一張證書唔係 certified + l3_ok"
        assert sorted(last["S"]) == sorted(st0["S_acc"]) == sorted(r0[-1]["S_acc_after"]), "seed S_acc 同最後證書嘅 S 對唔上"
        assert last["cnf"]["n_remaining"] == self.g2.n - len(st0["S_acc"]) and last.get("G3p_n") == 2 * (self.g2.n - len(st0["S_acc"])) - 1, "seed 點數對唔上"
        assert not st0.get("target_reached"), "seed 已到目標, 唔應該再剪"
        bundle_p = os.path.join(seed_run, tag, "cnc_" + tag, "bundle.json"); l3_p = os.path.join(seed_run, tag, "l3", "summary.json")
        cb = json.load(open(bundle_p)); sm = json.load(open(l3_p))
        assert cb["base_sha"] == last["cnf"]["cnf_sha256"] and cb["leaves"] == last["leaves"] and cb["audit"]["all_ok"], "seed bundle 對唔上"
        assert sm["all_ok"] is True and sm["G3p"]["n"] == last["G3p_n"], "seed l3 summary 對唔上"
        for rr in r0:
            rr["from_run"] = st0["run_id"]; rr["run_dir"] = seed_run
            for x in rr["attempts"]:
                x["dir"] = os.path.join(seed_run, x["tag"]); x["from_run"] = st0["run_id"]
        prov = {"run_id": st0["run_id"], "run_dir": seed_run, "round_done": st0["round_done"], "S_acc_size": len(st0["S_acc"]), "last_certified_tag": tag,
                "base_sha256": last["cnf"]["cnf_sha256"], "bundle_sha256": sha(bundle_p), "l3_summary_sha256": sha(l3_p), "l3_all_ok": sm["all_ok"],
                "G2p_n": last["cnf"]["n_remaining"], "G3p_n": last["G3p_n"], "seed_stop_reason": st0.get("stop_reason"), "leaf_proofs_on_disk": False,
                "note": "Phase 3b policy deleted leaf proofs after verification (only sha256/size kept in bundle.json); Phase 3c keeps them from r04 on"}
        return {"S_acc": sorted(st0["S_acc"]), "excluded_next": sorted(st0.get("excluded_next", [])), "perma_excluded": sorted(st0.get("perma_excluded", [])),
                "B_history": sorted(st0.get("B_history", [])), "round_done": st0["round_done"], "rounds": r0, "prov": prov}

    # ---------------- 帳 ----------------
    def elapsed(self):
        return self.st["elapsed_before_s"] + time.time() - self.T0

    def remaining_total(self):
        return self.a.total_cap - self.elapsed()

    def own_rounds(self):
        return [r for r in self.rounds if not r.get("from_run")]

    def cpu_h_used(self):
        return round(sum((x.get("wall_s") or 0) for r in self.own_rounds() for x in r["attempts"]) * self.a.workers / 3600, 2)

    def cpu_h_remaining(self):
        return self.a.cpu_cap_h - self.cpu_h_used()

    def last_certified_wall_h(self):
        w = [x["wall_s"] for r in self.rounds for x in r["attempts"] if x.get("status") == "certified" and x.get("wall_s")]
        return (w[-1] / 3600) if w else None

    def proj_wall_h(self):
        w = self.last_certified_wall_h()
        return round(PROJ_FACTOR * w, 3) if w else DEFAULT_PROJ_H

    def low_net_streak(self):
        n = 0
        for r in reversed(self.own_rounds()):
            if (r.get("net_removed") or 0) < self.a.low_net:
                n += 1
            else:
                break
        return n

    def step(self, msg):
        try:
            open(os.path.join(PH3C, "STEP.txt"), "w").write(msg)
        except Exception:
            pass

    def save(self, light=False):
        st = self.st; st["elapsed_s"] = round(self.elapsed(), 1); st["updated_str"] = time.strftime("%Y-%m-%d %H:%M:%S")
        st["cpu_h_used"] = self.cpu_h_used(); st["low_net_streak"] = self.low_net_streak()
        json.dump(st, open(self.state_p + ".tmp", "w"), indent=1); os.replace(self.state_p + ".tmp", self.state_p)
        if light:                                                                                 # cnc2k 等待期間每 10 分鐘: 只寫 state.json (elapsed_s 保鮮), 唔行 D: 目錄
            return
        json.dump(self.rounds, open(self.rounds_p + ".tmp", "w"), indent=1); os.replace(self.rounds_p + ".tmp", self.rounds_p)
        summ = []
        for r in self.rounds:
            summ.append({k: r.get(k) for k in ("round", "status", "net_removed", "G2p_n", "G3p_n", "wall_s", "from_run")} | {"attempts": [{k: x.get(k) for k in ("tag", "removed", "status", "n_cubes", "leaves", "mean_solve_s", "mean_sv_s", "wall_s", "B_size", "l3_ok", "keep")} for x in r["attempts"]], "B_sets": r.get("B_sets")})
        status = {"run_id": st["run_id"], "started": st["started"], "updated_str": st["updated_str"], "elapsed_s": st["elapsed_s"], "total_cap_s": self.a.total_cap, "round_done": st["round_done"],
                  "S_acc_size": len(st["S_acc"]), "G2p_n": self.g2.n - len(st["S_acc"]), "G3p_n": 2 * (self.g2.n - len(st["S_acc"])) - 1, "excluded_next": len(st["excluded_next"]), "perma_excluded": st["perma_excluded"],
                  "current": self.cur, "stop_reason": st["stop_reason"], "gate": st.get("gate"), "target_reached": st["target_reached"], "record_candidate": st.get("record_candidate"),
                  "cpu_h_used": st["cpu_h_used"], "cpu_cap_h": self.a.cpu_cap_h, "cpu_h_remaining": round(self.cpu_h_remaining(), 2), "proj_next_round_wall_h": self.proj_wall_h(),
                  "low_net_streak": st["low_net_streak"], "low_net": self.a.low_net, "low_net_rounds": self.a.low_net_rounds, "kept_certified": st.get("kept_certified"), "keep_root": self.a.keep_root,
                  "keep_stats": {t: dir_stats(os.path.join(self.a.keep_root, t)) for t in (st.get("kept_certified") or [])}, "seed": st.get("seed"), "resumes": st.get("resumes", 0), "rounds": summ}
        json.dump(status, open(self.status_p + ".tmp", "w"), indent=1, ensure_ascii=False); os.replace(self.status_p + ".tmp", self.status_p)
        self.write_ledger()

    def write_ledger(self):
        W = self.a.workers
        L = ["# ledger_g2.md —— Phase 3c 縮圖循環帳 (run %s, 接力 %s; 更新 %s)" % (self.st["run_id"], (self.st.get("seed") or {}).get("run_id"), time.strftime("%Y-%m-%d %H:%M:%S")), "",
             "S_acc (已認證可成集剪走) = %d 粒 → |G₂′| = %d, |G₃′| = %d; 永久排除 %s; 下一輪排除 %d 粒; Phase 3c 用時 %.2f h / 上限 %.1f h; CPU-h (Σ 證書 wall × %d) %.1f / %.0f; 連續低淨剪 %d 輪; keep 目錄 (最新認證圖 leaf 證明) %s%s" % (
                 len(self.st["S_acc"]), self.g2.n - len(self.st["S_acc"]), 2 * (self.g2.n - len(self.st["S_acc"])) - 1, self.st["perma_excluded"], len(self.st["excluded_next"]),
                 self.elapsed() / 3600, self.a.total_cap / 3600, W, self.cpu_h_used(), self.a.cpu_cap_h, self.low_net_streak(), self.st.get("kept_certified"),
                 ("; **停: %s**" % self.st["stop_reason"]) if self.st["stop_reason"] else ""), "",
             "| 輪 | 來源 | 嘗試 | |S| | 結果 | cube | leaf | 每 cube solve (s) | 每 cube solve+verify (s) | ×L1 / ×G₂recon | wall | CPU-h (wall×%d) | leaf 證明保留 | B (擋住集) | |G₂′| | |G₃′| | L2″/L3″/完整/spindle |" % W,
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in self.rounds:
            for x in r["attempts"]:
                kp = x.get("keep") or {}
                L.append("| %d | %s | %s | %d | %s | %s | %s | %s | %s | %s / %s | %s s (%.2f h) | %.1f | %s | %s | %s | %s | %s |" % (
                    r["round"], r.get("from_run") or self.st["run_id"], x["tag"], x["removed"], x["status"], x.get("n_cubes", "—"), x.get("leaves", "—"), x.get("mean_solve_s", "—"), x.get("mean_sv_s", "—"),
                    x.get("x_L1_sv", "—"), x.get("x_G2recon_sv", "—"), x.get("wall_s", "—"), (x.get("wall_s") or 0) / 3600, (x.get("wall_s") or 0) * W / 3600,
                    ("%s/%s (%s GB)%s" % (kp.get("kept_leaves"), x.get("leaves"), kp.get("gb"), " 已刪(下一輪已認證)" if kp.get("deleted_after_next_certified") else ("" if kp.get("on_disk", True) else " 已刪"))) if kp else ("—" if r.get("from_run") else "—"),
                    ("|B|=%d %s" % (x["B_size"], x["witness"]["blocked_min"])) if x.get("witness") else "—",
                    x["cnf"]["n_remaining"] if x.get("cnf") else "—", x.get("G3p_n", "—"),
                    ("✓" if x.get("l3_ok") else "!!") if x["status"] == "certified" else "—"))
            L.append("| %d | %s | **輪結算** | — | **%s** | — | — | — | — | — | %.2f h | — | — | B 集合 %s | — | — | 淨剪 %s (S_acc %d → %d) |" % (
                r["round"], r.get("from_run") or self.st["run_id"], r.get("status"), (r.get("wall_s") or 0) / 3600, r.get("B_sets"), r.get("net_removed"), len(r["S_acc_before"]), len(r.get("S_acc_after", r["S_acc_before"]))))
        if self.st.get("gate_final"):
            L += ["", "## 完場外推 (hardness_g2, 資訊用; Phase 3c 冇第 3 輪閘門)", "**%s** —— %s" % (self.st["gate_final"].get("verdict"), self.st["gate_final"].get("why"))]
        open(os.path.join(self.out, "ledger_g2.md"), "w").write("\n".join(L) + "\n")

    # ---------------- 一張證書 ----------------
    def campaign(self, tag, S, cap):
        a = self.a; d = os.path.join(self.out, tag); os.makedirs(d, exist_ok=True)
        S = sorted(S)
        rec = {"tag": tag, "removed": len(S), "S": S, "cap_s": round(cap), "started": time.strftime("%Y-%m-%d %H:%M:%S"), "dir": d}
        t_round = time.time()
        cdir = os.path.join(d, "cnc_" + tag); keep_dir = os.path.join(a.keep_root, tag)
        self.cur = {"tag": tag, "stage": "build", "S_size": len(S), "cnc_status": os.path.join(cdir, "status.json"), "cap_s": round(cap), "started": rec["started"], "keep_dir": keep_dir}; self.save()
        # 1. CNF (buildg2: 拒絕 u/v/P₂)
        r = subprocess.run([PY, os.path.join(PH3B, "buildg2.py"), "--remove", ",".join(map(str, S)), "--out", d, "--tag", "base", "--protected", a.batches], capture_output=True, text=True, timeout=600)
        assert r.returncode == 0, "buildg2 失敗: " + r.stdout[-500:] + r.stderr[-500:]
        log(r.stdout.strip()); cnf = os.path.join(d, "base.cnf"); rec["cnf"] = json.load(open(os.path.join(d, "base.json")))
        if a.dry_run:
            rec["status"] = "dry-run"; rec["wall_s"] = round(time.time() - t_round, 1); log("%s: --dry-run, 唔跑 march/cnc2k" % tag); return rec
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
        # 3. cnc2k (keep-dir)
        prior = float((self.st.get("prior_wall_by_tag") or {}).get(tag, 0.0))                  # 審查 #5/#14: 上次 process 已花喺呢個 tag 嘅 wall (掉走嘅完成記錄)
        if resumed:
            try:
                prior = max(prior, float(json.load(open(os.path.join(cdir, "state.json"))).get("wall_s") or 0.0))   # cnc2k 自己記嘅累計 wall
            except Exception:
                pass
        rec["prior_wall_s"] = round(prior, 1)
        budget = max(600, cap - prior - (time.time() - t_round))
        logp = os.path.join(d, "cnc.log"); skip = False
        if resumed:
            st_old = json.load(open(os.path.join(cdir, "state.json")))
            assert st_old.get("base_sha") == rec["cnf"]["cnf_sha256"], "!! %s: 舊 cnc2k campaign base_sha %s != 而今 S 嘅 base.cnf sha %s (S 變咗?), 拒絕 resume" % (tag, st_old.get("base_sha"), rec["cnf"]["cnf_sha256"])
            assert st_old.get("keep_dir") == keep_dir, "!! %s: 舊 campaign keep_dir %s != %s" % (tag, st_old.get("keep_dir"), keep_dir)
            rec["n_cubes"] = st_old["n_cubes0"]; rec["icnf_sha"] = st_old["icnf_sha"]; rec["resumed"] = True; rec["march_s"] = None
            if (st_old.get("status") == "certified" and os.path.exists(os.path.join(cdir, "bundle.json"))) or st_old.get("sat"):
                skip = True; log("%s: 舊 campaign 已有結果 (%s), 直接讀" % (tag, "certified" if st_old.get("sat") is None else "SAT"))
            else:
                if os.path.exists(os.path.join(cdir, "lock")):
                    os.remove(os.path.join(cdir, "lock"))
                argv = [PY, CNC, "--resume", "--out", cdir, "--workers", str(a.workers), "--time-budget", str(int(st_old["wall_s"] + budget)), "--progress", "120", "--keep-dir", keep_dir]
        else:
            argv = [PY, CNC, "--cnf", cnf, "--icnf", icnf, "--out", cdir, "--workers", str(a.workers), "--timeout", str(a.timeout), "--solver", "kissat",
                    "--proof-dir", a.proof_dir, "--binary", "--time-budget", str(int(budget)), "--split-depth", "3", "--max-split", "4", "--audit-frac", "0.05", "--progress", "120", "--keep-dir", keep_dir]
        killed = False
        if not skip:
            self.cur["stage"] = "cnc2k"; self.save()
            log("%s: cnc2k 開始 (time-budget %.0f s, 硬殺 %.0f s, keep-dir %s): %s" % (tag, budget, cap + 900, keep_dir, " ".join(argv[2:])))
            t0 = time.time()
            with open(logp, "a") as lf:
                p = subprocess.Popen(argv, stdout=lf, stderr=subprocess.STDOUT, start_new_session=True)
                hard = t_round + cap + 900 - prior; last_save = time.time()
                while True:
                    try:
                        rc = p.wait(timeout=30); break
                    except subprocess.TimeoutExpired:
                        if time.time() - last_save > 600:
                            self.save(light=True); last_save = time.time()
                        if time.time() > hard:
                            killed = True; log("!! %s: 超硬上限 %.0f s, 硬殺 cnc2k process group" % (tag, cap + 900))
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
        rec["split_events"] = st.get("split_events"); rec["solver_errors"] = st.get("solver_errors"); rec["wasted_s"] = st.get("wasted_s"); rec["keep_errors"] = st.get("keep_errors", 0)
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
            assert rec["cover_verified"] and rec["audit"]["all_ok"], "!! cnc2k 話 certified 但 cover/audit 唔 ok"
            assert cb.get("base_sha") == rec["cnf"]["cnf_sha256"] == st.get("base_sha"), "!! bundle base_sha %s != base.cnf sha %s (證書唔係證而今嘅 S)" % (cb.get("base_sha"), rec["cnf"]["cnf_sha256"])
            assert cb.get("leaves") == len(done) and cb.get("n_cubes0") == rec.get("n_cubes"), "!! bundle leaves/n_cubes0 同 state.json 對唔上"
            rec["keep"] = {"dir": keep_dir, "kept_leaves": cb.get("kept_leaves"), "keep_errors": cb.get("keep_errors"), "keep_error_ids": cb.get("keep_error_ids"), "kept_audit": cb.get("kept_audit"), "on_disk": True} | dir_stats(keep_dir)
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
        log("%s: %s —— cube %s, leaf 完成 %s, mean solve %s s, mean solve+verify %s s (L1 ×%s, G₂recon ×%s), wall %.0f s (%.2f h = %.1f CPU-h)%s%s%s" % (
            tag, rec["status"], rec.get("n_cubes"), rec["leaves"], rec.get("mean_solve_s"), rec.get("mean_sv_s"), rec.get("x_L1_sv"), rec.get("x_G2recon_sv"), rec["wall_s"], rec["wall_s"] / 3600, rec["wall_s"] * a.workers / 3600,
            (", 未完: 估計仲要 %s h" % rec.get("eta_remaining_h")) if rec["status"] not in ("certified", "SAT") else "",
            (", 擋住集 B (|B|=%d) = %s" % (rec["B_size"], rec["witness"]["blocked_min"])) if rec.get("witness") else "",
            (", leaf 證明保留 %s/%s (%s GB, 搬失敗 %s)" % (rec["keep"]["kept_leaves"], rec["leaves"], rec["keep"]["gb"], rec["keep"]["keep_errors"])) if rec.get("keep") else ""))
        # 4b. keep 目錄: 唔係 certified → 即刪 (唔係證書); certified 但有搬失敗 → 即場修
        if rec["status"] != "certified":
            ks = dir_stats(keep_dir)
            if os.path.isdir(keep_dir):
                shutil.rmtree(keep_dir, ignore_errors=True)
            rec["keep"] = {"dir": keep_dir, "on_disk": False, "deleted_not_certified": True} | ks
            log("%s: 唔係 certified, 刪 keep 目錄 %s (%d 檔, %.2f GB)" % (tag, keep_dir, ks["n_files"], ks["gb"]))
        else:
            if rec["keep"]["keep_errors"] or rec["keep"]["kept_leaves"] != rec["leaves"] or cb.get("audit_keep_errors") or cb.get("kept_audit") != (cb.get("audit") or {}).get("n"):
                self.cur["stage"] = "keep-repair"; self.save()
                rec["keep_repair"] = repair_keep_dir(cdir, keep_dir, st, a.proof_dir, a.timeout)
                rec["keep"] = {**rec["keep"], **dir_stats(keep_dir), "kept_leaves": rec["keep_repair"]["kept_after"], "kept_audit": rec["keep_repair"]["kept_audit_after"], "repaired": rec["keep_repair"]["repaired"], "repair_failed": rec["keep_repair"]["failed"]}
                if rec["keep_repair"]["failed"]:
                    rec["keep_incomplete"] = True; rec["status"] = "certified-keep-incomplete"      # 審查 #3: 唔算「接納」嘅證書 (S_acc 唔郁, finalize 唔會揀佢)
        # 5. L2″ + L3″ + 完整性 + spindle
        if rec["status"] in ("certified", "certified-keep-incomplete"):
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
            rec["G2p_n"] = sm.get("G2p", {}).get("n"); rec["G2p_m"] = sm.get("G2p", {}).get("m"); rec["l3_summary"] = {k: sm.get(k) for k in ("complete_G2p", "complete_G3p", "L2", "L3", "spindle_A", "spindle_B")}
            rec["engine_b_run"] = eb
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

    # ---------------- 完場外推 (資訊) ----------------
    def gate(self, final=True):
        hj = os.path.join(self.out, "hardness_g2.json")
        if os.path.exists(hj):
            os.remove(hj)
        try:
            r = subprocess.run([PY, os.path.join(PH3B, "hardness_g2.py"), "--probe", self.out, "--batches", self.a.batches, "--out", self.out, "--workers", str(self.a.workers), "--green", str(self.a.cpu_cap_h)],
                               capture_output=True, text=True, timeout=1800)
            rc, out_txt = r.returncode, r.stdout + r.stderr
        except subprocess.TimeoutExpired:
            rc, out_txt = -999, "!! hardness_g2 timeout"
        open(os.path.join(self.out, "hardness_g2.log"), "a").write("\n===== %s =====\n" % time.strftime("%Y-%m-%d %H:%M:%S") + out_txt)
        h = json.load(open(hj)) if (rc == 0 and os.path.exists(hj)) else {"verdict": "ERROR", "why": "hardness_g2.py rc=%s: %s" % (rc, out_txt[-300:])}
        g = {"verdict": h.get("verdict"), "why": h.get("why"), "estimate": h.get("estimate"), "when": time.strftime("%Y-%m-%d %H:%M:%S"), "final": final, "informational": True}
        log("完場外推 (hardness_g2, 資訊): %s —— %s" % (g["verdict"], g["why"]))
        return g

    # ---------------- 主循環 ----------------
    def run(self):
        a = self.a; st = self.st; g2 = self.g2
        while st["round_done"] < a.rounds and not st["stop_reason"]:
            r = st["round_done"] + 1
            proj = self.proj_wall_h(); rem_cpu_h = self.cpu_h_remaining(); rem_wall_h = self.remaining_total() / 3600
            if rem_cpu_h / a.workers - 0.25 < proj:                                               # 審查 #15: 同 cap = 剩餘 CPU/14 − 900 s 一致
                st["stop_reason"] = "CPU 預算: 已用 %.1f / %.0f CPU-h, 剩 %.1f CPU-h = %.2f h wall (−0.25 h 緩衝) < 預測下一輪 %.2f h (1.15 × 上一張證書) → 唔開 round %d" % (self.cpu_h_used(), a.cpu_cap_h, rem_cpu_h, rem_cpu_h / a.workers, proj, r); break
            if rem_wall_h < proj + 0.25:
                st["stop_reason"] = "總 wall 上限 %.1f h: 已用 %.2f h, 剩 %.2f h < 預測下一輪 %.2f h + 0.25 → 唔開 round %d" % (a.total_cap / 3600, self.elapsed() / 3600, rem_wall_h, proj, r); break
            cf = free_gb("/mnt/c"); df = free_gb("/mnt/d")
            if (cf is not None and cf < 25) or (df is not None and df < 300) or not os.path.ismount("/mnt/d"):
                st["stop_reason"] = "磁碟紀律: C: 剩 %s GB (要 ≥ 25, vhdx 所在) / D: 剩 %s GB (要 ≥ 300, keep 目錄所在, ismount %s) → 停" % (cf, df, os.path.ismount("/mnt/d")); break
            S_acc = set(st["S_acc"]); excl = set(st["excluded_next"]) | set(st["perma_excluded"])
            cands = [w for w in self.ordering if w not in S_acc and w not in excl]
            batch = cands[:self.k]
            if len(batch) < self.k:
                st["stop_reason"] = "候選唔夠一批 (%d < %d)" % (len(batch), self.k); break
            t_round = time.time(); cap = min(a.cap, self.remaining_total(), rem_cpu_h * 3600 / a.workers - 900)
            rr = {"round": r, "batch": batch, "S_acc_before": sorted(S_acc), "excluded_this_round": sorted(excl), "attempts": [], "B_sets": [], "started": time.strftime("%Y-%m-%d %H:%M:%S"), "cap_s": round(cap),
                  "budget_before": {"cpu_h_used": self.cpu_h_used(), "cpu_h_remaining": round(rem_cpu_h, 2), "wall_used_h": round(self.elapsed() / 3600, 3), "wall_remaining_h": round(rem_wall_h, 3), "proj_wall_h": proj}}
            self.rounds.append(rr); self.save()
            log("===== round %d: S_acc %d 粒 + batch %d 粒 %s (排除 %d 粒); 輪上限 %.2f h (預測 %.2f h); CPU 已用 %.1f / %.0f CPU-h; wall 剩 %.1f h =====" % (
                r, len(S_acc), len(batch), batch, len(excl), cap / 3600, proj, self.cpu_h_used(), a.cpu_cap_h, rem_wall_h))
            S_target = S_acc | set(batch); S_try = set(S_target); tried = []; status = None; certified_S = None
            for ai in range(4):
                rem = cap - (time.time() - t_round)
                if rem < 900:
                    status = "cap-exhausted"; log("round %d: 輪上限剩 %.0f s < 900, 唔開第 %d 張證書" % (r, rem, ai + 1)); break
                tag = "r%02d%s" % (r, "abcd"[ai])
                self.step("Phase 3c round %d 嘗試 %s (%s): 剪 %d 粒 (S_acc %d) → buildg2 → march d=%d → cnc2k %d workers (keep-dir %s); 輪上限剩 %.1f h; Phase 3c 用時 %.1f h / %.0f h; CPU %.1f / %.0f CPU-h; S_acc %d → |G₂′| %d |G₃′| %d" % (
                    r, tag, ["第 1 張", "S∖B", "S∖(B∪B′)", "二分"][ai], len(S_try), len(S_acc), a.depth, a.workers, os.path.join(a.keep_root, tag), rem / 3600, self.elapsed() / 3600, a.total_cap / 3600,
                    self.cpu_h_used(), a.cpu_cap_h, len(S_acc), g2.n - len(S_acc), 2 * (g2.n - len(S_acc)) - 1))
                try:
                    rec = self.campaign(tag, S_try, rem)
                except Exception as e:
                    rec = {"tag": tag, "removed": len(S_try), "S": sorted(S_try), "status": "error", "error": repr(e)[-600:], "wall_s": round(time.time() - t_round, 1)}
                    subprocess.run(["pkill", "-x", "kissat"], capture_output=True); subprocess.run(["pkill", "-x", "drat-trim"], capture_output=True)
                    kd_ = os.path.join(a.keep_root, tag)
                    if os.path.isdir(kd_):
                        ks_ = dir_stats(kd_); shutil.rmtree(kd_, ignore_errors=True); rec["keep"] = {"dir": kd_, "on_disk": False, "deleted_not_certified": True} | ks_
                rec["round"] = r; rec["attempt"] = ai + 1; rec["kind"] = ["first", "S-B", "S-(B+B')", "bisect"][ai]
                rr["attempts"].append(rec); tried.append(sorted(S_try)); self.save()
                if a.dry_run:
                    status = "dry-run"; st["stop_reason"] = "DRY RUN: round %d batch 建咗 CNF 就停 (%s)" % (r, os.path.join(self.out, tag)); break
                if rec["status"] in ("error", "cnc2-error", "march-refuted-root"):
                    status = "error"; st["needs_operator"] = True; st["stop_reason"] = "!! %s %s —— 停, 要人手睇 %s: %s" % (tag, rec["status"], os.path.join(self.out, tag), (rec.get("error") or (rec.get("cnc_log_tail") or "")[-300:]).replace("\n", " | ")); break
                if rec["status"] == "certified-keep-incomplete":
                    status = "keep-incomplete"; st["needs_operator"] = True; st["stop_reason"] = "!! %s L1″ certified (l3_ok=%s) 但 %d 個證明搬去 D: 失敗而且修唔到 (%s) —— 封存規則要求全套證明喺碟上, S_acc 唔郁, 停, 要人手睇 %s" % (
                        tag, rec.get("l3_ok"), len(rec["keep_repair"]["failed"]), rec["keep_repair"]["failed"][:10], os.path.join(self.out, tag, "cnc_" + tag, "keep_repair.json")); break
                if rec["status"] == "certified":
                    if not rec.get("l3_ok"):
                        status = "l3-failed"; st["needs_operator"] = True; st["stop_reason"] = "!! %s L1″ certified 但 L2″/L3″/完整性/spindle 有步驅失敗 —— 停, 要人手睇 %s" % (tag, os.path.join(self.out, tag, "l3g2.log")); break
                    certified_S = set(S_try); status = "certified"; break
                if rec["status"] == "SAT":
                    if not rec.get("witness"):
                        st["stop_reason"] = "!! %s SAT 但染色證書覆核失敗 (%s) —— 編碼/解碼有 bug, 停" % (tag, rec.get("colouring")); status = "error"; st["needs_operator"] = True; break
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
                # cap-hit / hard-killed / budget-stop / stuck
                if ai == 0:
                    status = "cap-hit"; st["needs_operator"] = True; st["stop_reason"] = "round %d 第 1 張證書超 %.2f h 輪上限未完 (%s: leaf %s/%s, 估計仲要 %s h) —— 停, 之後只會更難" % (
                        r, cap / 3600, rec["status"], rec.get("leaves"), rec.get("n_cubes"), rec.get("eta_remaining_h")); break
                status = "cap-exhausted"; log("round %d: %s %s (第 %d 張) → 該批 blocked" % (r, tag, rec["status"], ai + 1)); break
            # 輪結算
            rr["status"] = status; rr["wall_s"] = round(time.time() - t_round, 1)
            Bs_all = set().union(*[set(b) for b in rr["B_sets"]]) if rr["B_sets"] else set()
            if status == "certified":
                st["S_acc"] = sorted(certified_S); rr["S_acc_after"] = sorted(certified_S); rr["net_removed"] = len(certified_S) - len(S_acc)
                last = rr["attempts"][-1]; rr["G2p_n"] = last["cnf"]["n_remaining"]; rr["G3p_n"] = last.get("G3p_n"); rr["certified_tag"] = last["tag"]
                st["excluded_next"] = sorted(Bs_all)
                # 封存規則: 本輪 certified (L1″+L2″+L3″ 全過) 之後, 先刪上一輪 certified 嘅 keep 目錄
                for prev in list(st.get("kept_certified") or []):
                    pdir = os.path.join(a.keep_root, prev); ks = dir_stats(pdir)
                    if os.path.isdir(pdir):
                        shutil.rmtree(pdir, ignore_errors=True)
                    for r_ in self.rounds:
                        for x in r_["attempts"]:
                            if x["tag"] == prev and x.get("keep"):
                                x["keep"]["on_disk"] = False; x["keep"]["deleted_after_next_certified"] = last["tag"]; x["keep"]["deleted_when"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    log("封存: %s 已認證 ⇒ 刪上一輪 %s 嘅 keep 目錄 %s (%d 檔, %.2f GB)" % (last["tag"], prev, pdir, ks["n_files"], ks["gb"]))
                st["kept_certified"] = [last["tag"]]
            else:
                rr["S_acc_after"] = sorted(S_acc); rr["net_removed"] = 0; rr["G2p_n"] = g2.n - len(S_acc); rr["G3p_n"] = 2 * (g2.n - len(S_acc)) - 1
                st["excluded_next"] = sorted(Bs_all | set(batch)) if status in ("blocked", "cap-exhausted") else sorted(Bs_all)
            hist = set(st["B_history"]); repeat = Bs_all & hist
            st["perma_excluded"] = sorted(set(st["perma_excluded"]) | repeat); st["B_history"] = sorted(hist | Bs_all)
            st["round_done"] = r; rr["budget_after"] = {"cpu_h_used": self.cpu_h_used(), "wall_used_h": round(self.elapsed() / 3600, 3)}; self.save()
            log("round %d 結算: %s; 淨剪 %s (S_acc %d → %d, |G₂′| %d, |G₃′| %d); B 集合 %s; 下一輪排除 %d 粒 (永久 %s); 輪 wall %.2f h; Phase 3c 用時 %.2f h; CPU %.1f / %.0f CPU-h; 連續低淨剪 %d; keep %s" % (
                r, status, rr["net_removed"], len(S_acc), len(st["S_acc"]), rr["G2p_n"], rr["G3p_n"], rr["B_sets"], len(st["excluded_next"]), st["perma_excluded"], rr["wall_s"] / 3600, self.elapsed() / 3600,
                self.cpu_h_used(), a.cpu_cap_h, self.low_net_streak(), st.get("kept_certified")))
            if status == "certified" and rr["G2p_n"] <= TARGET_G2P:
                st["target_reached"] = True; st["record_candidate"] = True
                st["stop_reason"] = "RECORD_CANDIDATE: |G₂′| = %d ≤ %d ⇒ |G₃′| = %d < 1441 (round %d, %s; l3g2 --engine-b 三重認證 %s) —— 即刻停, 唔再剪; finalize3c 做獨立重驗 + 封存 + RECORD_CANDIDATE.md" % (
                    rr["G2p_n"], TARGET_G2P, rr["G3p_n"], r, rr["certified_tag"], "✓" if rr["attempts"][-1].get("l3_ok") else "!!"); break
            if st["stop_reason"]:
                break
            if self.low_net_streak() >= a.low_net_rounds:
                st["stop_reason"] = "連續 %d 輪淨剪 < %d 粒 (%s) → 停" % (a.low_net_rounds, a.low_net, [(x["round"], x.get("status"), x.get("net_removed")) for x in self.own_rounds()[-a.low_net_rounds:]]); break
            if os.path.exists(os.path.join(self.out, "PAUSE")):          # 操作員暫停旗 (輪與輪之間乾淨停; 之後 --resume 續)
                os.remove(os.path.join(self.out, "PAUSE"))
                st["stop_reason"] = "PAUSED by operator after round %d (PAUSE flag) —— 用 resume3c.sh 續跑" % r; st["paused"] = True; break
        if not st["stop_reason"]:
            st["stop_reason"] = "%d 輪完成 (輪數上限 --rounds, 唔准自動加)" % st["round_done"]
        if st.get("paused"):                                                                      # 審查 #17: PAUSE = 乾淨暫停, 唔算完, 唔跑 gate, 等 resume3c.sh
            self.save(); self.step("Phase 3c PAUSED (PAUSE 旗, round %d 之後): 用 resume3c.sh 續跑" % st["round_done"]); log("PROBE3C PAUSED: %s" % st["stop_reason"]); return
        st["finished"] = time.strftime("%Y-%m-%d %H:%M:%S"); self.save()                         # 審查 #16: finished 喺 gate 之前先寫 (gate 可以行 30 分鐘)
        if not a.dry_run:
            try:
                g = self.gate(final=True); st["gate_final"] = g
            except Exception as e:
                st["gate_final"] = {"verdict": "ERROR", "why": repr(e)}
        self.save()
        self.step("Phase 3c 縮圖循環完 (%s): S_acc %d 粒, |G₂′| %d, |G₃′| %d; CPU %.1f / %.0f CPU-h; 用時 %.2f h; keep %s; 跟住 finalize3c.py (獨立重驗 + 封存 + 報告)" % (
            st["stop_reason"], len(st["S_acc"]), g2.n - len(st["S_acc"]), 2 * (g2.n - len(st["S_acc"])) - 1, self.cpu_h_used(), a.cpu_cap_h, self.elapsed() / 3600, st.get("kept_certified")))
        log("PROBE3C DONE: %s" % st["stop_reason"])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True); ap.add_argument("--batches", required=True); ap.add_argument("--out", required=True); ap.add_argument("--seed-run", default=None)
    ap.add_argument("--rounds", type=int, default=30); ap.add_argument("--workers", type=int, default=14); ap.add_argument("--cap", type=float, default=3.5 * 3600)
    ap.add_argument("--total-cap", type=float, default=40 * 3600); ap.add_argument("--cpu-cap-h", type=float, default=400.0); ap.add_argument("--timeout", type=float, default=600); ap.add_argument("--depth", type=int, default=14)
    ap.add_argument("--proof-dir", default=None); ap.add_argument("--keep-root", default="/mnt/d/hadwiger/phase3c/keep"); ap.add_argument("--k", type=int, default=None); ap.add_argument("--resume", action="store_true")
    ap.add_argument("--low-net", type=int, default=10); ap.add_argument("--low-net-rounds", type=int, default=3); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ack-operator", action="store_true", help="上次係操作員停機 (error/cap-hit/l3-failed/keep-incomplete) 人手睇完先可以續跑")
    a = ap.parse_args()
    a.proof_dir = os.path.abspath(os.path.expanduser(a.proof_dir or os.path.join("/dev/shm", a.run_id))); os.makedirs(a.proof_dir, exist_ok=True)
    a.keep_root = os.path.abspath(os.path.expanduser(a.keep_root)); os.makedirs(a.keep_root, exist_ok=True)
    a.batches = os.path.abspath(a.batches)
    Probe(a).run()

if __name__ == "__main__":
    main()
