#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
finalize3c.py —— Phase 3c 收爐 (probe3c 停機之後自動跑; 幂等, 可重跑):
  1. 搵最終認證圖 (最後一張 certified + l3_ok 嘅嘗試; 可能係 Phase 3c 嘅 rNNx, 或者冇新輪時係 seed r03a)
  2. 獨立重驗 (verify_final.py: 每個 leaf 證明由碟上檔案重驗 + cover + 審計證明 + l3g2 --engine-b 重跑 + exactfield --complete) —— 只有 Phase 3c 嘗試有 leaf 證明
  3. 封存 → /mnt/d/hadwiger/release_v1_1_staging/final/ (leaf 證明由 keep 目錄 rename 過去, 同一隻碟), SHA256SUMS 逐檔, FINAL_README.md (英文), reverify.sh;
     record candidate → RECORD_CANDIDATE.md; Windows 鏡像 Desktop\\spindle\\release_v1_1_staging\\final\\ (唔抄 leaf 證明, C: 唔夠位)
  4. Phase 3c 每輪細檔 → ~/hadwiger/release_v1_1_staging/reduction/phase3c_G2_shrink/ (+PHASE3C_README.md), 重算 reduction/SHA256SUMS, 鏡像
  5. 報告 phase3c_results.md (WSL + Windows), facts.json (g2shrink3c.*), DECISION.md 路線 A 加一段, MEMORY (hadwiger-project.md / no-spindle-hardness.md / MEMORY.md 索引)
  進度寫 runs/<id>/finalize_status.json (status3c 讀). --append-s60 模式: 將 s60_full.py 結果加入報告 / facts.
用法: python3 finalize3c.py --run ~/hadwiger/phase3c/runs/p3c1_shrink [--workers 14] [--dry-run] [--append-s60 ~/hadwiger/phase3c/s60_full/s60_full.json]
"""
import sys, os, json, time, argparse, subprocess, shutil, hashlib, glob, re
from concurrent.futures import ThreadPoolExecutor
if not __debug__:
    sys.exit("!! 唔准用 python -O")
PH2 = os.path.expanduser("~/hadwiger/phase2"); PH2B = os.path.expanduser("~/hadwiger/phase2b"); PH3B = os.path.expanduser("~/hadwiger/phase3b"); PH3C = os.path.expanduser("~/hadwiger/phase3c")
FINAL_D = "/mnt/d/hadwiger/release_v1_1_staging/final"
STAGE = os.path.expanduser("~/hadwiger/release_v1_1_staging/reduction")
WIN = "/mnt/c/Users/user/Desktop/spindle"
WIN_FINAL = os.path.join(WIN, "release_v1_1_staging", "final"); WIN_STAGE = os.path.join(WIN, "release_v1_1_staging", "reduction")
MEM = "/mnt/c/Users/user/.claude/projects/C--Users-user-Desktop-spindle/memory"
PY = sys.executable
N_G2 = 1066

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)

def cp(src, dst_dir, name=None):
    if not os.path.exists(src) or not os.path.isfile(src):
        return None
    os.makedirs(dst_dir, exist_ok=True); d = os.path.join(dst_dir, name or os.path.basename(src))
    if not os.path.exists(d) or os.path.getsize(d) != os.path.getsize(src) or sha(d) != sha(src):
        shutil.copyfile(src, d)
    return d

def write(p, txt):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"; open(tmp, "w", encoding="utf-8").write(txt); os.replace(tmp, p)

def shasums(root, workers=14, exclude=("SHA256SUMS", "SHA256SUMS.small")):
    files = sorted(os.path.relpath(os.path.join(r, f), root) for r, _, fs in os.walk(root) for f in fs if f not in exclude and not f.endswith(".tmp"))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        hs = list(ex.map(lambda rel: sha(os.path.join(root, rel)), files))
    txt = "".join("%s  %s\n" % (h, rel) for h, rel in zip(hs, files))
    write(os.path.join(root, "SHA256SUMS"), txt)
    chk = subprocess.run(["sha256sum", "-c", "--quiet", "SHA256SUMS"], cwd=root, capture_output=True, text=True)
    tot = sum(os.path.getsize(os.path.join(root, r)) for r in files)
    return {"n_files": len(files), "bytes": tot, "sha256sums_sha256": hashlib.sha256(txt.encode()).hexdigest(), "check_rc": chk.returncode, "check_tail": (chk.stdout + chk.stderr).strip()[-300:]}

class Fin:
    def __init__(self, a):
        self.a = a; self.rdir = os.path.abspath(os.path.expanduser(a.run)); self.rid = os.path.basename(self.rdir)
        self.st = json.load(open(os.path.join(self.rdir, "state.json"))); self.rounds = json.load(open(os.path.join(self.rdir, "rounds.json")))
        self.rounds = [r for r in self.rounds if r["round"] <= self.st["round_done"]]
        self.fs_p = os.path.join(self.rdir, "finalize_status.json")
        self.fs = json.load(open(self.fs_p)) if os.path.exists(self.fs_p) else {"started": time.strftime("%Y-%m-%d %H:%M:%S")}
        self.fs["stage"] = "start"
        if not a.append_s60:
            self.fs["done"] = False
        self.save(); self.vok = None; self.rec_ok = False
        self.W = a.workers; self.now = time.strftime("%Y-%m-%d %H:%M:%S")
        if not self.st.get("finished") and not a.append_s60:
            tail = ""
            try:
                tail = " | ".join([l.strip() for l in open(os.path.join(self.rdir, "probe3c.log"), errors="ignore").read().splitlines() if l.strip()][-3:])[:600]
            except Exception:
                pass
            self.st["stop_reason"] = "!! probe3c 未正常結束 (state.finished 冇; 可能 crash / 被殺): %s || probe3c.log 尾: %s" % (self.st.get("stop_reason"), tail)
            self.fs["probe_unfinished"] = True; log(self.st["stop_reason"])

    def save(self, **kw):
        self.fs.update(kw); self.fs["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        json.dump(self.fs, open(self.fs_p + ".tmp", "w"), indent=1, ensure_ascii=False); os.replace(self.fs_p + ".tmp", self.fs_p)

    def step(self, msg):
        self.fs["stage"] = msg; self.save(); log(msg)
        try:
            open(os.path.join(PH3C, "STEP.txt"), "w").write("Phase 3c 收爐 (finalize3c): " + msg)
        except Exception:
            pass

    # ---------------- 1. 最終認證圖 ----------------
    def final_attempt(self):
        S_acc = sorted(self.st["S_acc"])
        allc = [(r, x) for r in self.rounds for x in r["attempts"] if x.get("status") == "certified" and x.get("l3_ok") is True]
        cert = [(r, x) for r, x in allc if sorted(x["S"]) == S_acc and not x.get("keep_incomplete")]      # 審查 #3/#13/#18: 只認 S == state.S_acc (即最後被接納嘅認證圖), keep-incomplete 唔算
        assert cert, "冇任何 S == state.S_acc 嘅 certified + l3_ok 嘗試?! (kept_certified=%s)" % self.st.get("kept_certified")
        r, x = cert[-1]
        later = [(r2["round"], x2["tag"], "keep_incomplete" if x2.get("keep_incomplete") else "S != S_acc") for r2, x2 in allc if r2["round"] > r["round"]]
        if later:
            self.fs["skipped_certified_attempts"] = later; log("!! 跳過 S != S_acc / keep-incomplete 嘅 certified 嘗試 %s, 封存上一張 %s" % (later, x["tag"]))
        d = x.get("dir") or os.path.join(self.rdir, x["tag"])
        own = not x.get("from_run")
        keep = (x.get("keep") or {}).get("dir") if own else None
        on_disk = bool((x.get("keep") or {}).get("on_disk"))
        has_keep = bool(keep and os.path.isdir(keep) and on_disk)
        if own and on_disk and not has_keep:                                                         # 審查 #1/#11/#20: keep 目錄已 rename 入 final/ → 幂等
            lp = os.path.join(FINAL_D, "L1pp", "leaf_proofs"); li = os.path.join(FINAL_D, "L1pp", "LEAF_INDEX.json")
            try:
                if os.path.isdir(lp) and os.path.exists(li):
                    ix = json.load(open(li))
                    if ix.get("tag") == x["tag"] and ix.get("base_sha256") == x["cnf"]["cnf_sha256"]:
                        keep = lp; has_keep = True; log("keep 目錄已 rename 入 final/: 用 %s" % lp)
            except Exception as e:
                log("LEAF_INDEX 讀唔到: %r" % e)
            if not has_keep:
                raise SystemExit("!! %s 記錄話 leaf 證明喺碟上 (on_disk) 但 keep 目錄 %s 同 final/L1pp/leaf_proofs 都對唔上 —— 唔敢當 seed 處理, 人手睇" % (x["tag"], keep))
        vdir = d if own else os.path.join(self.rdir, "final_verify_" + x["tag"])                        # 審查 #24: seed 分支唔寫入 Phase 3b 目錄
        if self.a.dry_run:
            vdir = os.path.join(PH3C, "selftest", "final_verify_" + x["tag"])
        os.makedirs(vdir, exist_ok=True)
        S = x["S"]
        assert sorted(S) == S_acc, "最終證書嘅 S 同 state.S_acc 對唔上"
        return {"round": r["round"], "tag": x["tag"], "dir": d, "vdir": vdir, "own": own, "from_run": x.get("from_run"), "keep_dir": keep, "has_keep": has_keep, "S": S, "rec": x, "rr": r,
                "G2p_n": x["cnf"]["n_remaining"], "G2p_m": x["cnf"]["n_edges"], "G3p_n": x.get("G3p_n"), "G3p_m": x.get("G3p_m")}

    def flag_status(self):
        """將 finalize 嘅重驗結果寫入 runs/<id>/status.json (原子), 俾 status3c 決定標題 (審查 #2/#10/#19: RECORD_CANDIDATE 只可以喺獨立重驗通過之後先叫)."""
        p = os.path.join(self.rdir, "status.json")
        try:
            st = json.load(open(p)) if os.path.exists(p) else {}
            st["finalize_verify_all_ok"] = self.vok; st["record_candidate_confirmed"] = self.rec_ok; st["finalize_verify_when"] = time.strftime("%Y-%m-%d %H:%M:%S")
            write(p, json.dumps(st, indent=1, ensure_ascii=False))
        except Exception as e:
            log("!! status.json 旗寫唔到: %r" % e)

    # ---------------- 2. 獨立重驗 ----------------
    def verify(self, fa):
        d = fa["dir"]; tag = fa["tag"]; vd = fa["vdir"]; vf = os.path.join(vd, "verify_final.json")
        res = None
        if fa["has_keep"]:
            if os.path.exists(vf) and not self.a.force_verify:
                old = json.load(open(vf))
                if old.get("all_ok") is True and old.get("leaf_reverify") and old.get("l3_final"):
                    log("verify_final.json 已有而且 all_ok (含 leaf_reverify), 唔重做"); res = old
            if res is None:
                self.step("獨立重驗 %s: %d 個 leaf 證明 (drat-trim, %d workers) + cover + 審計證明 + l3g2 --engine-b + exactfield --complete" % (tag, fa["rec"].get("leaves") or 0, self.W))
                argv = [PY, os.path.join(PH3C, "verify_final.py"), "--attempt-dir", d, "--tag", tag, "--keep-dir", fa["keep_dir"], "--workers", str(self.W), "--json-out", vf]
                with open(os.path.join(vd, "verify_final.log"), "a") as lf:
                    rc = subprocess.call(argv, stdout=lf, stderr=subprocess.STDOUT)
                res = json.load(open(vf)) if os.path.exists(vf) else {"all_ok": False, "error": "verify_final.py rc=%d 冇輸出" % rc}
                res["rc"] = rc
                if rc != 0 and res.get("all_ok") is True:
                    res["all_ok"] = False; res["error"] = "verify_final.py rc=%d 但 JSON 話 all_ok (舊檔?)" % rc
        else:
            # seed (Phase 3b) 證書: leaf 證明唔喺碟上 (舊政策), 只重跑 l3g2 --engine-b + 重驗 cover
            self.step("最終認證圖係 %s (%s, 冇 Phase 3c certified 輪): leaf 證明唔喺碟上 (Phase 3b 政策驗完即刪), 只重驗 cover + l3g2 --engine-b" % (tag, fa["from_run"]))
            res = {"tag": tag, "leaf_proofs_on_disk": False, "when": self.now}
            cdir = os.path.join(d, "cnc_" + tag); cb = json.load(open(os.path.join(cdir, "bundle.json"))); cm = cb["cover_mode"]
            dr = subprocess.run(["/home/user/hadwiger/drat-trim/drat-trim", os.path.join(cdir, "cover_%s.cnf" % cm), os.path.join(cdir, "cover_%s.drat" % cm)], capture_output=True, text=True, timeout=6 * 3600)
            res["cover_reverify"] = {"mode": cm, "verified": any(l.strip() == "s VERIFIED" for l in dr.stdout.splitlines()), "drat_sha_match": sha(os.path.join(cdir, "cover_%s.drat" % cm)) == cb["cover"][cm]["proof_sha"]}
            l3f = os.path.join(vd, "l3_final")
            rl = subprocess.run([PY, os.path.join(PH3B, "l3g2.py"), "--remove", ",".join(map(str, fa["S"])), "--out", l3f, "--engine-b"], capture_output=True, text=True, timeout=5 * 3600)
            open(os.path.join(vd, "l3_final.log"), "w").write(rl.stdout + rl.stderr)
            sm = json.load(open(os.path.join(l3f, "summary.json"))) if os.path.exists(os.path.join(l3f, "summary.json")) else {}
            res["l3_final"] = {"rc": rl.returncode, "all_ok": sm.get("all_ok"), "G2p": sm.get("G2p"), "G3p": sm.get("G3p"), "L3": {k: (sm.get("L3") or {}).get(k) for k in ("status", "verified", "sha")}, "spindle_A": sm.get("spindle_A"), "spindle_B": sm.get("spindle_B"), "dir": l3f, "sha": sm.get("sha")}
            res["all_ok"] = bool(res["cover_reverify"]["verified"] and res["cover_reverify"]["drat_sha_match"] and rl.returncode == 0 and sm.get("all_ok") is True)
            write(vf, json.dumps(res, indent=1, ensure_ascii=False))
        self.vok = (res.get("all_ok") is True); self.rec_ok = bool(self.st.get("record_candidate")) and self.vok
        self.save(verify_final={"all_ok": res.get("all_ok"), "leaf_reverify": {k: v for k, v in (res.get("leaf_reverify") or {}).items() if k != "bad"}, "cover": (res.get("cover_reverify") or {}).get("verified"), "l3_final_all_ok": (res.get("l3_final") or {}).get("all_ok"), "spindle_B_ok": ((res.get("l3_final") or {}).get("spindle_B") or {}).get("ok"), "t_s": res.get("t_s"), "error": res.get("error")},
                  verify_failed=(not self.vok), record_candidate_confirmed=self.rec_ok)
        if not self.a.dry_run:
            self.flag_status()
        log("verify_final: all_ok=%s → vok=%s, record_candidate_confirmed=%s" % (res.get("all_ok"), self.vok, self.rec_ok))
        return res

    # ---------------- 3. 封存 final/ ----------------
    def archive(self, fa, vres):
        F = FINAL_D; d = fa["dir"]; tag = fa["tag"]; cdir = os.path.join(d, "cnc_" + tag)
        self.step("封存 → %s (leaf 證明 rename 自 %s)" % (F, fa["keep_dir"]))
        if self.a.dry_run:
            log("dry-run: 唔郁 final/"); return {"dry_run": True, "final_dir": F}
        L1 = os.path.join(F, "L1pp")
        oldb = os.path.join(L1, "base.json")
        if os.path.exists(oldb):
            try:
                old_sha = json.load(open(oldb)).get("cnf_sha256")
            except Exception:
                old_sha = None
            if old_sha != fa["rec"]["cnf"]["cnf_sha256"]:
                try:
                    old_n = json.load(open(oldb)).get("n_removed")
                except Exception:
                    old_n = "unknown"
                sup = F + "_superseded_S%s_%s" % (old_n, time.strftime("%Y%m%d_%H%M%S"))
                os.rename(F, sup); log("final/ 已有另一個圖 (base sha %s…) 嘅封存, 搬去 %s (唔刪)" % ((old_sha or "")[:16], sup)); self.fs["superseded_final"] = sup
        os.makedirs(L1, exist_ok=True)
        for f in ("base.cnf", "base.json", "cubes_d14.icnf", "march.log", "cnc.log", "l3g2.log"):
            cp(os.path.join(d, f), L1)
        for f in ("l3_final.log", "verify_final.json", "verify_final.log"):
            cp(os.path.join(fa["vdir"], f), L1)
        for f in ("bundle.json", "cover_pure.cnf", "cover_pure.drat", "cover_with_base.cnf", "cover_with_base.drat", "ledger.csv", "state.json", "status.json", "keep_repair.json", "base.cnf", "cubes.icnf"):
            cp(os.path.join(cdir, f), os.path.join(L1, "cnc_" + tag))
        lp = os.path.join(L1, "leaf_proofs"); moved = None
        if fa["has_keep"]:
            kd = fa["keep_dir"]
            if os.path.isdir(lp) and (os.path.realpath(kd) == os.path.realpath(lp) or not os.path.isdir(kd)):
                moved = "already"
            else:
                assert not os.path.isdir(lp), "final/L1pp/leaf_proofs 已存在而且 keep 目錄亦存在 —— 唔敢覆寫, 人手睇"
                os.rename(kd, lp); moved = "renamed"
            for root_, _, fs_ in os.walk(lp):                                           # kill 留低嘅 .part (唔係證明) 清走, 免得入 SHA256SUMS
                for f in fs_:
                    if f.endswith(".part"):
                        os.remove(os.path.join(root_, f))
            n = sum(1 for f in os.listdir(lp) if f.endswith(".drat")); na = len([f for f in os.listdir(os.path.join(lp, "audit"))]) if os.path.isdir(os.path.join(lp, "audit")) else 0
            log("leaf 證明: %s → %s (%d leaf .drat, %d audit .drat)" % (fa["keep_dir"], lp, n, na))
            # INDEX: id → 檔名 / sha / bytes (由 bundle.json leaf_list, 加 repair 覆寫)
            cb = json.load(open(os.path.join(cdir, "bundle.json"))); stc = json.load(open(os.path.join(cdir, "state.json")))
            idx = {x["id"]: {"file": "leaf_proofs/cnc_%s_%s.drat" % (tag, x["id"]), "proof_sha256": (stc["done"].get(x["id"]) or {}).get("repaired_proof_sha") or x["proof_sha"], "proof_bytes": x["proof_bytes"], "cube": x["cube"], "cnf_sha256": x["cnf_sha"], "solve_s": x["solve_s"], "verify_s": x["verify_s"], "attempt": x["attempt"], "repaired": bool((stc["done"].get(x["id"]) or {}).get("repaired_proof_sha"))} for x in cb["leaf_list"]}
            json.dump({"tag": tag, "base_sha256": cb["base_sha"], "n_leaves": len(idx), "note": "each leaf proof refutes base.cnf + unit clauses of the cube; kissat binary DRAT, checked by drat-trim; sha256 recorded here and in SHA256SUMS", "leaves": idx}, open(os.path.join(L1, "LEAF_INDEX.json"), "w"), indent=1)
        else:
            write(os.path.join(L1, "LEAF_PROOFS_NOT_ON_DISK.txt"), "The final certified graph is %s from run %s (Phase 3b). Under the Phase 3b policy every leaf proof was deleted right after drat-trim verification; only sha256 and size are recorded in cnc_%s/bundle.json (leaf_list). Regenerating them takes ~2.3 h on 14 threads (scripts/phase2b/cnc2.py or scripts/phase3c/cnc2k.py --keep-dir).\n" % (tag, fa["from_run"], tag))
        # L2″/L3″/spindle (l3 = 戰役; l3_final = 收爐重跑, 喺 vdir)
        for sub, base_ in (("l3", d), ("l3_final", fa["vdir"])):
            for f in glob.glob(os.path.join(base_, sub, "*")):
                if os.path.isfile(f):
                    cp(f, os.path.join(F, "L2L3", sub))
            for f in glob.glob(os.path.join(base_, sub, "spindle_B", "*")):
                cp(f, os.path.join(F, "L2L3", sub, "spindle_B"))
        # run 級
        for f in ("rounds.json", "state.json", "ledger_g2.md", "gate_g2.md", "hardness_g2.json", "hardness_curve_g2.png", "probe3c.log", "status.json", "finalize_status.json"):
            cp(os.path.join(self.rdir, f), os.path.join(F, "run"))
        for f in ("batches_g2.json", "batches_g2.md"):
            cp(os.path.join(PH3B, f), os.path.join(F, "run"))
        if fa["from_run"]:
            for f in ("rounds.json", "state.json", "ledger_g2.md", "gate_g2.md", "probe3b.log"):
                cp(os.path.join(fa["rr"].get("run_dir", ""), f), os.path.join(F, "run", "seed_" + fa["from_run"]))
        # scripts
        for f in glob.glob(os.path.join(PH3C, "*.py")) + glob.glob(os.path.join(PH3C, "*.sh")) + glob.glob(os.path.join(PH3C, "*.diff")):
            cp(f, os.path.join(F, "scripts", "phase3c"))
        for f in ("buildg2.py", "g2common.py", "l3g2.py", "witness_g2.py", "hardness_g2.py", "g2batches.py", "probe3b.py"):
            cp(os.path.join(PH3B, f), os.path.join(F, "scripts", "phase3b"))
        for f in ("cnc2.py", "cubes.py"):
            cp(os.path.join(PH2B, f), os.path.join(F, "scripts", "phase2b"))
        for f in ("exactfield.py", "certify4.py", "spindlefind.py", "haugland.py", "chain.py"):
            cp(os.path.join(PH2, f), os.path.join(F, "scripts", "phase2"))
        # 入口檔 / 讀我
        self.write_reverify(F, fa)
        self.write_final_readme(F, fa, vres)
        rec_md = None
        for stale in ("RECORD_CANDIDATE.md", "RECORD_CANDIDATE_BLOCKED.md", "VERIFY_FAILED.md"):
            if os.path.exists(os.path.join(F, stale)):
                os.remove(os.path.join(F, stale))
        if not self.vok:                                                                   # 審查 #2/#10/#19: 重驗唔過 → 封存只係證據, 大聲講明
            lr_ = vres.get("leaf_reverify") or {}
            txt = "# VERIFY_FAILED.md — independent re-verification did NOT pass (%s)\n\nThis directory is EVIDENCE ONLY. Do not treat the graph as certified until `bash reverify.sh` passes.\n\nverify_final all_ok = %s; error = %s\nleaf_reverify: %s\nbad leaves (first 50): %s\ncover: %s\naudit: %s\nl3_final: %s\n" % (
                self.now, vres.get("all_ok"), vres.get("error"), json.dumps({k: v for k, v in lr_.items() if k != "bad"}, default=str), json.dumps(lr_.get("bad"), default=str)[:4000],
                json.dumps(vres.get("cover_reverify"), default=str), json.dumps(vres.get("audit_reverify"), default=str)[:2000], json.dumps(vres.get("l3_final"), default=str)[:3000])
            for p_ in (os.path.join(F, "VERIFY_FAILED.md"), os.path.join(PH3C, "VERIFY_FAILED.md"), os.path.join(WIN, "phase3c", "VERIFY_FAILED.md")):
                write(p_, txt)
        if self.rec_ok:
            rec_md = self.write_record_candidate(F, fa, vres)
        elif self.st.get("record_candidate"):
            txt = "# RECORD_CANDIDATE_BLOCKED.md (%s)\n\nprobe3c reached |G2'| <= 720 (round %d, %s) but the independent re-verification (finalize3c / verify_final) did NOT pass (all_ok = %s). NOT a record candidate until re-verified. See VERIFY_FAILED.md.\n" % (self.now, fa["round"], fa["tag"], vres.get("all_ok"))
            for p_ in (os.path.join(F, "RECORD_CANDIDATE_BLOCKED.md"), os.path.join(PH3C, "RECORD_CANDIDATE_BLOCKED.md"), os.path.join(WIN, "phase3c", "RECORD_CANDIDATE_BLOCKED.md")):
                write(p_, txt)
        self.step("SHA256SUMS (final/, 逐檔, %d threads)" % self.W)
        ss = shasums(F, self.W)
        # small list (鏡像用: 唔含 leaf_proofs)
        small = [l for l in open(os.path.join(F, "SHA256SUMS")) if "L1pp/leaf_proofs/" not in l]
        write(os.path.join(F, "SHA256SUMS.small"), "".join(small))
        log("final/: %d 檔 %.2f GB, SHA256SUMS sha %s…, sha256sum -c rc=%d %s" % (ss["n_files"], ss["bytes"] / 1e9, ss["sha256sums_sha256"][:16], ss["check_rc"], ss["check_tail"][:100]))
        # Windows 鏡像 (唔抄 leaf_proofs)
        n_m = 0
        for root, _, fs in os.walk(F):
            if "L1pp/leaf_proofs" in root.replace("\\", "/") or root.endswith("leaf_proofs"):
                continue
            for f in fs:
                rel = os.path.relpath(os.path.join(root, f), F)
                if "leaf_proofs" in rel.split(os.sep):
                    continue
                cp(os.path.join(root, f), os.path.join(WIN_FINAL, os.path.dirname(rel))); n_m += 1
        write(os.path.join(WIN_FINAL, "LEAF_PROOFS_LOCATION.txt"), "Leaf proofs (%s) are NOT mirrored here (C: has no room). They live on D: at %s/L1pp/leaf_proofs/ (Windows path D:\\hadwiger\\release_v1_1_staging\\final\\L1pp\\leaf_proofs\\). SHA256SUMS lists every file including the proofs; SHA256SUMS.small lists only the files present in this mirror.\n" % (("%d leaf .drat files, state: %s" % (n, moved)) if moved else "none on disk", F))
        arch = {"final_dir": F, "windows_mirror": WIN_FINAL, "n_files": ss["n_files"], "bytes": ss["bytes"], "sha256sums_sha256": ss["sha256sums_sha256"], "check_rc": ss["check_rc"], "leaf_proofs_moved": moved, "mirror_files": n_m, "record_candidate_md": rec_md, "when": time.strftime("%Y-%m-%d %H:%M:%S")}
        self.save(archive=arch)
        return arch

    def write_reverify(self, F, fa):
        S = ",".join(map(str, fa["S"])); tag = fa["tag"]
        txt = """#!/bin/bash
# reverify.sh — independent re-verification of the archived certificate set (needs the v1.0 tool environment: ~/hadwiger/{phase2,phase2b,phase3b,phase3c}, kissat, drat-trim, march_cu; python venv ~/hadwiger/venv)
set -u
cd "$(dirname "$0")"
PY=/home/user/hadwiger/venv/bin/python
echo "== 1. integrity"; sha256sum -c --quiet SHA256SUMS && echo "SHA256SUMS OK"
echo "== 2. rebuild base.cnf from S (must match L1pp/base.cnf)"; T=$(mktemp -d)
$PY /home/user/hadwiger/phase3b/buildg2.py --remove %s --out "$T" --tag base --protected run/batches_g2.json | cut -c1-200
sha256sum "$T/base.cnf" L1pp/base.cnf
echo "== 3. L1'' : every leaf proof (drat-trim) + cover + audit proofs (14 threads, ~1 h)"
$PY /home/user/hadwiger/phase3c/verify_final.py --attempt-dir L1pp --tag %s --keep-dir L1pp/leaf_proofs --skip-l3 --tmp "$T/vf" --json-out "$T/verify_final_reverify.json" | tail -8
cp "$T/verify_final_reverify.json" "reverify_$(date +%%Y%%m%%d_%%H%%M%%S).json"   # extra un-hashed file; the archived L1pp/verify_final.json is never overwritten
echo "== 4. L2''/L3''/completeness/spindle A+B (fresh run, seconds to minutes)"
$PY /home/user/hadwiger/phase3b/l3g2.py --remove %s --out "$T/l3" --engine-b | tail -8
sha256sum "$T/l3/G3p.edge" L2L3/l3_final/G3p.edge
rm -rf "$T"
echo "REVERIFY DONE $(date)"
""" % (S, tag, S)
        write(os.path.join(F, "reverify.sh"), txt)

    def write_final_readme(self, F, fa, vres):
        x = fa["rec"]; cb = json.load(open(os.path.join(fa["dir"], "cnc_" + fa["tag"], "bundle.json"))); sm = json.load(open(os.path.join(fa["dir"], "l3", "summary.json")))
        smf_p = os.path.join(fa["vdir"], "l3_final", "summary.json"); smf = json.load(open(smf_p)) if os.path.exists(smf_p) else {}
        lr = vres.get("leaf_reverify") or {}; ar = vres.get("audit_reverify") or {}
        G2n, G2m, G3n, G3m = sm["G2p"]["n"], sm["G2p"]["m"], sm["G3p"]["n"], sm["G3p"]["m"]
        rec = self.rec_ok; vok = self.vok
        L = ["# FINAL_README.md — Phase 3c final certified graph (staging for v1.1; **NOT released**)" if vok else "# FINAL_README.md — Phase 3c final graph — **INDEPENDENT RE-VERIFICATION FAILED, EVIDENCE ONLY** (see VERIFY_FAILED.md)", "",
             ("Archived %s by `scripts/phase3c/finalize3c.py` (run `%s`, seeded from Phase 3b run `%s`). Author of the project: King Tat Wong (Amber); all statements below are backed by machine certificates in this directory and were re-verified from the files on disk at archive time (`L1pp/verify_final.json`, all_ok = true) — nothing here is an unverified claim." if vok else
              "Archived %s by `scripts/phase3c/finalize3c.py` (run `%s`, seeded from Phase 3b run `%s`). **WARNING: the independent re-verification from the files on disk did NOT pass (`L1pp/verify_final.json`, all_ok = false; details in VERIFY_FAILED.md). The statements below describe what the campaign recorded; they must NOT be relied on until `bash reverify.sh` passes.**") % (self.now, self.rid, (self.st.get("seed") or {}).get("run_id")), "",
             "## 1. The graph", "",
             "* **G2′ = G2 − S**: the Haugland graph G2 (1066 vertices, 6264 edges; exact coordinates in ℚ(ζ₈₄)) minus the certified removable set S of **%d** vertices ⇒ **|V(G2′)| = %d, |E(G2′)| = %d**." % (len(fa["S"]), G2n, G2m),
             "* **G3′ = G2′ ∪ ρ(G2′)**, ρ(z) = (z+1)(7+i√15)/8 − 1 (exact, in ℚ(ζ₄₂₀)); G2′ ∩ ρ(G2′) = {u}. ⇒ **|V(G3′)| = %d, |E(G3′)| = %d** (a unit-distance graph, induced subgraph of Haugland's 2131-vertex G3, hence Moser-spindle-free and 5-colourable)." % (G3n, G3m),
             ("* **Certified statement: G3′ has no proper 4-colouring** (χ(G3′) = 5). %s" if vok else "* Campaign claim (NOT independently confirmed, see VERIFY_FAILED.md): G3′ has no proper 4-colouring. %s") % (
                 ("**|V(G3′)| = %d < 1441 — record candidate (see RECORD_CANDIDATE.md).**" % G3n) if rec else (("|V(G3′)| = %d < 1441 but RECORD CANDIDATE BLOCKED (re-verification failed, see RECORD_CANDIDATE_BLOCKED.md)." % G3n) if self.st.get("record_candidate") else "|V(G3′)| = %d ≥ 1441 — not a record; the campaign stopped because: %s" % (G3n, self.st.get("stop_reason")))),
             "* S (G2 vertex indices, 1-based, v1.0 numbering of `G2.cvtx`/`G2.edge` from `scripts/phase2/haugland.py`): `%s`" % fa["S"], "",
             "## 2. Proof chain and where each certificate is", "",
             "| step | statement | files | check |", "|---|---|---|---|",
             "| L1″ | every proper 4-colouring of G2′ gives col(−1,0) = col(1,0) (mono-pair property): `L1pp/base.cnf` (sha `%s`) = 4-colouring CNF of G2′ (ALO+AMO+edge clauses, triangle (u,p,q) pinned to 1,2,3) + 4 clauses ¬(col(u)=c ∧ col(v)=c) is UNSAT | `L1pp/base.{cnf,json}`, `L1pp/cubes_d14.icnf` (march_cu, %d cubes), `L1pp/cnc_%s/{bundle.json,state.json,ledger.csv}`, **`L1pp/leaf_proofs/*.drat`** (%s), `L1pp/cnc_%s/cover_pure.{cnf,drat}` (cover certificate: the negated cubes are jointly UNSAT, drat-trim VERIFIED), `L1pp/leaf_proofs/audit/` (%s), `L1pp/LEAF_INDEX.json` | each leaf: rebuild `base.cnf` + cube unit clauses (sha in state.json), `drat-trim cube.cnf leaf.drat` → `s VERIFIED`; `drat-trim cover_pure.cnf cover_pure.drat`; `scripts/phase3c/verify_final.py` does all of it (`L1pp/verify_final.json`: %s) |" % (
                 cb["base_sha"], cb["n_cubes0"], fa["tag"], ("%d files, kissat binary DRAT, re-verified from disk: %s/%s VERIFIED" % (lr.get("n", 0), lr.get("ok"), lr.get("n"))) if fa["has_keep"] else "NOT on disk — see LEAF_PROOFS_NOT_ON_DISK.txt", fa["tag"],
                 ("%s/%s of the 5 %% from-scratch audit proofs on disk%s" % (ar.get("kept_files"), ar.get("bundle_audit_n"), "" if ar.get("complete") else " — INCOMPLETE (audit record itself is in cnc_%s/bundle.json)" % fa["tag"])) if fa["has_keep"] else "audit record only (cnc_%s/bundle.json)" % fa["tag"], "all_ok=%s" % vres.get("all_ok")),
             "| L2″ | identity and ρ map V(G2′) injectively into V(G3′) and E(G2′) into E(G3′) (exact cyclotomic arithmetic, not index tables); exact coordinates + **completeness** (`exactfield.py check --complete`: the edge list is the complete unit-distance graph on the point set) for G2′ and G3′ | `L2L3/l3_final/{G2p,G3p}.{cvtx,edge}`, `maps.json`, `summary.json` (`L2`, `complete_G2p`, `complete_G3p`); `L2L3/l3/` = same files produced during the campaign (byte-identical: %s) | `scripts/phase3b/l3g2.py --remove <S> --out DIR --engine-b`; `scripts/phase2/exactfield.py check G3p.cvtx G3p.edge --complete` |" % ((vres.get("l3_final") or {}).get("same_files_as_campaign_l3")),
             "| L3″ | 4-colouring CNF of G3′ + 16 lemma clauses (col(u)=col(v) and col(u)=col(ρv), bi-implications per colour) is UNSAT — with L1″ applied to both copies this shows G3′ is not 4-colourable | `L2L3/l3_final/L3pp.{cnf,drat,json}` (kissat UNSAT, drat-trim VERIFIED, drat sha `%s`) | `drat-trim L3pp.cnf L3pp.drat` |" % (((smf.get("L3") or sm.get("L3") or {}).get("sha") or {}).get("L3pp.drat")),
             "| spindle-free | G3′ contains no Moser spindle (inherited from G3, re-certified): engine A exact rhombus enumeration copies = %s; engine B SAT subgraph-monomorphism CNF UNSAT + drat-trim VERIFIED | `L2L3/l3_final/summary.json` (`spindle_A`, `spindle_B`), `L2L3/l3_final/spindle_B/` | `scripts/phase2/spindlefind.py both G3p.edge --out DIR` |" % ((smf.get("spindle_A") or sm.get("spindle_A") or {}).get("copies")), "",
             "## 3. Independent re-verification (done at archive time, from the files on disk)", "",
             "`L1pp/verify_final.json`: %s" % json.dumps({k: v for k, v in vres.items() if k in ("all_ok", "base_sha_consistent", "leaf_count_consistent", "leaf_ids_are_all_root_cubes", "cover_reverify", "audit_reverify", "exactfield_complete_G3p_again", "t_s")} | {"leaf_reverify": {k: v for k, v in lr.items() if k != "bad"}, "l3_final": {k: v for k, v in (vres.get("l3_final") or {}).items() if k in ("rc", "all_ok", "G2p", "G3p", "L3", "spindle_A", "spindle_B", "same_files_as_campaign_l3")}}, ensure_ascii=False, default=str), "",
             "Run `bash reverify.sh` (in this directory, on the v1.0 tool environment) to repeat everything: integrity (SHA256SUMS), rebuild `base.cnf` from S, every leaf proof + cover + audit proofs, and a fresh L2″/L3″/completeness/spindle run.", "",
             "## 4. Provenance and budget", "",
             "* Seed: Phase 3b run `%s` (rounds 1–3, S_acc = 90, |G3′| = 1951; certificates in `../reduction/phase3b_G2_shrink/`). Phase 3c rounds %s; stop reason: %s." % ((self.st.get("seed") or {}).get("run_id"), [r["round"] for r in self.rounds if not r.get("from_run")], self.st.get("stop_reason")),
             "* Budget (Phase 3c, from r04): CPU-h = Σ certificate wall × 14 workers = **%.1f / 400**; wall %.2f / 40 h; per-round cap 3.5 h; batch 30 vertices, order (G2 degree ↑, |Im z| ↓, index); protected P2 = {172, 187, 646, 994}." % (self.st.get("cpu_h_used") or 0, (self.st.get("elapsed_s") or 0) / 3600),
             "* Tools: kissat / drat-trim / march_cu / cake_lpr as in v1.0 (`L1pp/cnc_%s/bundle.json` → `tools`, with sha256 of each binary); `scripts/phase3c/cnc2k.py` = v1.0 `cnc2.py` + `--keep-dir` (leaf proofs kept instead of deleted; diff in `scripts/phase3c/cnc2k.diff`)." % fa["tag"],
             "* Ledger of all rounds: `run/ledger_g2.md`; hardness/extrapolation curve: `run/hardness_curve_g2.png`.", "",
             "## 5. Integrity", "",
             "`SHA256SUMS` covers every file here (`<sha256>  <relative path>`, check with `sha256sum -c SHA256SUMS`); `SHA256SUMS.small` lists the files that are also mirrored to the Windows staging folder (which omits `L1pp/leaf_proofs/`).", "",
             "Not released: Amber (K. T. Wong) reviews first — no git push, no Zenodo version, no e-mail."]
        write(os.path.join(F, "FINAL_README.md"), "\n".join(L) + "\n")

    def write_record_candidate(self, F, fa, vres):
        assert self.rec_ok, "write_record_candidate 只可以喺獨立重驗通過之後叫"
        sm = json.load(open(os.path.join(fa["dir"], "l3", "summary.json"))); smf_p = os.path.join(fa["vdir"], "l3_final", "summary.json"); smf = json.load(open(smf_p)) if os.path.exists(smf_p) else sm
        cb = json.load(open(os.path.join(fa["dir"], "cnc_" + fa["tag"], "bundle.json")))
        G2n, G2m, G3n, G3m = smf["G2p"]["n"], smf["G2p"]["m"], smf["G3p"]["n"], smf["G3p"]["m"]
        shas = {"L1pp/base.cnf": cb["base_sha"], "L1pp/cnc_%s/cover_%s.drat" % (fa["tag"], cb["cover_mode"]): cb["cover"][cb["cover_mode"]]["proof_sha"], "L1pp/cnc_%s/bundle.json" % fa["tag"]: sha(os.path.join(fa["dir"], "cnc_" + fa["tag"], "bundle.json"))}
        for f in ("G2p.cvtx", "G2p.edge", "G3p.cvtx", "G3p.edge", "L3pp.cnf", "L3pp.drat"):
            p = os.path.join(fa["vdir"], "l3_final", f)
            if os.path.exists(p):
                shas["L2L3/l3_final/" + f] = sha(p)
        for f in glob.glob(os.path.join(fa["vdir"], "l3_final", "spindle_B", "*")):
            shas["L2L3/l3_final/spindle_B/" + os.path.basename(f)] = sha(f)
        lr = vres.get("leaf_reverify") or {}
        L = ["# RECORD_CANDIDATE.md —— |G₃′| = %d < 1441 (Phase 3c, %s)" % (G3n, self.now), "",
             "## 廣東話摘要 (Amber)", "",
             "- 圖: G₃′ = (G₂ − S) ∪ ρ(G₂ − S), **%d 點 %d 邊**, 無 Moser spindle (兩引擎), 5 色可染 (G₃ 子圖), **機器證書話唔可以 4 色** ⇒ χ = 5. 呢個係無-spindle 5-chromatic UDG 嘅紀錄候選 (Haugland 2131 → %d)." % (G3n, G3m, G3n),
             "- 剪走 S = %d 粒 G₂ 頂點 (|G₂′| = %d 點 %d 邊); 最後一張證書 %s (round %d); 全部證書 + 獨立重驗 (verify_final all_ok = %s) 封存喺 `%s` (leaf 證明 %s 個, 全部 drat-trim 重驗 %s/%s)." % (
                 len(fa["S"]), G2n, G2m, fa["tag"], fa["round"], vres.get("all_ok"), FINAL_D, lr.get("n"), lr.get("ok"), lr.get("n")),
             "- **未公開、未寄信、未 push**; 等 Amber 決定. 重驗指令: `bash %s/reverify.sh` (約 1 h, 14 threads)." % FINAL_D, "",
             "## Statement", "",
             "G3′ (%d vertices, %d edges; exact coordinates `L2L3/l3_final/G3p.cvtx`, complete unit-distance edge list `G3p.edge`) is a unit-distance graph in the plane with no proper 4-colouring, containing no Moser spindle as a subgraph. |V(G3′)| = %d < 1441." % (G3n, G3m, G3n), "",
             "S = `%s` (%d G2 vertices; protected P2 = {172, 187, 646, 994} untouched)." % (fa["S"], len(fa["S"])), "",
             "## Certificates (sha256)", "", "| file | sha256 |", "|---|---|"] + ["| `%s` | `%s` |" % (k, v) for k, v in shas.items()] + [
             "| `L1pp/leaf_proofs/*.drat` (%d files) | individually in `SHA256SUMS` and `L1pp/LEAF_INDEX.json`; sorted-concatenation sha256 `%s` |" % (lr.get("n", 0), lr.get("proof_sha_sum_sha256")),
             "| `SHA256SUMS` (all %s files) | `%s` |" % ((self.fs.get("archive") or {}).get("n_files", "?"), "(computed after this file is written — see finalize_status.json → archive.sha256sums_sha256)"), "",
             "## Independent re-verification at archive time", "",
             "```", json.dumps({k: v for k, v in vres.items() if k not in ("S",)} | {"leaf_reverify": {k: v for k, v in lr.items() if k != "bad"}}, ensure_ascii=False, indent=1, default=str)[:6000], "```", "",
             "## How to re-verify", "", "```bash", "cd %s" % FINAL_D, "sha256sum -c --quiet SHA256SUMS", "bash reverify.sh        # rebuild base.cnf from S; every leaf proof + cover + audit (drat-trim); fresh L2''/L3''/completeness/spindle A+B",
             "# single pieces:", "/home/user/hadwiger/drat-trim/drat-trim L1pp/cnc_%s/cover_%s.cnf L1pp/cnc_%s/cover_%s.drat" % (fa["tag"], cb["cover_mode"], fa["tag"], cb["cover_mode"]),
             "/home/user/hadwiger/drat-trim/drat-trim L2L3/l3_final/L3pp.cnf L2L3/l3_final/L3pp.drat",
             "/home/user/hadwiger/venv/bin/python /home/user/hadwiger/phase2/exactfield.py check L2L3/l3_final/G3p.cvtx L2L3/l3_final/G3p.edge --complete",
             "/home/user/hadwiger/venv/bin/python /home/user/hadwiger/phase2/spindlefind.py both L2L3/l3_final/G3p.edge --out /tmp/spB", "```", "",
             "Status: RECORD_CANDIDATE — waiting for Amber. Not published, not e-mailed, not pushed."]
        p = os.path.join(F, "RECORD_CANDIDATE.md"); write(p, "\n".join(L) + "\n")
        cp(p, os.path.join(PH3C)); cp(p, os.path.join(WIN, "phase3c"))
        return p

    # ---------------- 4. reduction/phase3c_G2_shrink ----------------
    def stage_rounds(self):
        self.step("封存每輪細檔 → %s/phase3c_G2_shrink (+ 重算 reduction/SHA256SUMS)" % STAGE)
        if self.a.dry_run:
            return {"dry_run": True}
        D = os.path.join(STAGE, "phase3c_G2_shrink")
        for f in ("rounds.json", "state.json", "ledger_g2.md", "gate_g2.md", "hardness_g2.json", "hardness_curve_g2.png", "probe3c.log", "finalize_status.json"):
            cp(os.path.join(self.rdir, f), D)
        rows = []
        for r in self.rounds:
            if r.get("from_run"):
                continue
            for x in r["attempts"]:
                tag = x["tag"]; sd = x.get("dir") or os.path.join(self.rdir, tag); dd = os.path.join(D, tag)
                for f in ("base.cnf", "base.json", "cubes_d14.icnf", "march.log", "cnc.log", "l3g2.log", "l3_final.log", "verify_final.json", "verify_final.log"):
                    cp(os.path.join(sd, f), dd)
                for f in glob.glob(os.path.join(sd, "G2minus_*.col")) + glob.glob(os.path.join(sd, "G2minus_*.json")):
                    cp(f, dd)
                for f in ("bundle.json", "cover_pure.cnf", "cover_pure.drat", "cover_with_base.cnf", "cover_with_base.drat", "ledger.csv", "state.json", "status.json", "keep_repair.json"):
                    cp(os.path.join(sd, "cnc_" + tag, f), os.path.join(dd, "cnc"))
                for sub in ("l3", "l3_final"):
                    for f in glob.glob(os.path.join(sd, sub, "*")):
                        if os.path.isfile(f):
                            cp(f, os.path.join(dd, sub))
                    for f in glob.glob(os.path.join(sd, sub, "spindle_B", "*")):
                        cp(f, os.path.join(dd, sub, "spindle_B"))
                for f in glob.glob(os.path.join(sd, "witness", "*")):
                    cp(f, os.path.join(dd, "witness"))
                rows.append((r, x))
        for f in glob.glob(os.path.join(PH3C, "*.py")) + glob.glob(os.path.join(PH3C, "*.sh")) + glob.glob(os.path.join(PH3C, "*.diff")):
            cp(f, os.path.join(STAGE, "scripts", "phase3c"))
        # README
        L = ["# PHASE3C_README.md — Phase 3c continuation of the G2 deletion campaign (run %s; staged %s; NOT released)" % (self.rid, self.now), "",
             "Same certificate types as section A of `../REDUCTION_README.md` (L1″ cube-and-conquer bundle, L2″/L3″ assembly, blocking colourings). Differences from Phase 3b: `cnc2k.py --keep-dir` kept every leaf proof of a certified round on D: (deleted only after the next round was certified); the final certified graph's complete set, including all leaf proofs, is in `../../final/` (D: only) — see `final/FINAL_README.md`. Budget: 400 CPU-h (Σ certificate wall × 14) from r04, 40 h wall, 3.5 h per round, stop after 3 consecutive rounds with net removal < 10.", "",
             "Seed: Phase 3b run %s, S_acc = 90 (|G2′| = 976, |G3′| = 1951), certificates in `../phase3b_G2_shrink/`." % (self.st.get("seed") or {}).get("run_id"), "",
             "| round | attempt | |S| | result | cubes | leaves | mean solve+verify / cube | wall | CPU-h (×14) | |G2−S| | |G3″| | L2″/L3″/complete/spindle | leaf proofs kept at the time | blocking set B |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r, x in rows:
            kp = x.get("keep") or {}
            L.append("| %d | %s | %d | %s | %s | %s | %s s | %.2f h | %.1f | %s | %s | %s | %s | %s |" % (
                r["round"], x["tag"], x["removed"], x["status"], x.get("n_cubes"), x.get("leaves"), x.get("mean_sv_s"), (x.get("wall_s") or 0) / 3600, (x.get("wall_s") or 0) * self.W / 3600,
                x["cnf"]["n_remaining"] if x.get("cnf") else "—", x.get("G3p_n") or "—", ("all OK" if x.get("l3_ok") else "!!") if x["status"] == "certified" else "—",
                ("%s/%s%s" % (kp.get("kept_leaves"), x.get("leaves"), " (deleted after %s certified)" % kp["deleted_after_next_certified"] if kp.get("deleted_after_next_certified") else (" (in final/)" if kp.get("on_disk") else ""))) if kp else "—",
                ("|B|=%d %s" % (x["B_size"], x["witness"]["blocked_min"])) if x.get("witness") else "—"))
        L += ["", "Certified removable set S_acc (%d vertices) = %s" % (len(self.st["S_acc"]), self.st["S_acc"]), "", "Stop reason: %s" % self.st.get("stop_reason"), "",
              "Record candidate: %s" % bool(self.st.get("record_candidate"))]
        write(os.path.join(D, "PHASE3C_README.md"), "\n".join(L) + "\n")
        ss = shasums(STAGE, self.W)
        # 鏡像 (只抄 phase3c 目錄 + SHA256SUMS + scripts/phase3c; 其他 Phase 3/3b 檔已鏡像過)
        n_m = 0
        for root, _, fs in os.walk(D):
            for f in fs:
                rel = os.path.relpath(os.path.join(root, f), STAGE); cp(os.path.join(root, f), os.path.join(WIN_STAGE, os.path.dirname(rel))); n_m += 1
        for f in glob.glob(os.path.join(STAGE, "scripts", "phase3c", "*")):
            cp(f, os.path.join(WIN_STAGE, "scripts", "phase3c")); n_m += 1
        cp(os.path.join(STAGE, "SHA256SUMS"), WIN_STAGE)
        res = {"dir": D, "n_rounds_staged": len(rows), "reduction_files": ss["n_files"], "reduction_bytes": ss["bytes"], "check_rc": ss["check_rc"], "mirrored": n_m}
        self.save(stage=res); log("reduction/: %d 檔 %.1f MB, sha256sum -c rc=%d; phase3c_G2_shrink %d 個嘗試; 鏡像 %d 檔" % (ss["n_files"], ss["bytes"] / 1e6, ss["check_rc"], len(rows), n_m))
        return res

    # ---------------- 5. 報告 / facts / DECISION / MEMORY ----------------
    def report(self, fa, vres, arch, stg):
        self.step("寫 phase3c_results.md")
        st = self.st; W = self.W; own = [r for r in self.rounds if not r.get("from_run")]
        cert_own = [(r, x) for r in own for x in r["attempts"] if x.get("status") == "certified"]
        sm_p = os.path.join(fa["vdir"], "l3_final", "summary.json"); sm = json.load(open(sm_p)) if os.path.exists(sm_p) else json.load(open(os.path.join(fa["dir"], "l3", "summary.json")))
        G2n, G2m, G3n, G3m = sm["G2p"]["n"], sm["G2p"]["m"], sm["G3p"]["n"], sm["G3p"]["m"]
        lr = vres.get("leaf_reverify") or {}
        L = ["# phase3c_results.md —— Phase 3c: G₂ 續剪 (預算放寬 400 CPU-h; run %s, 接力 %s r03a)" % (self.rid, (st.get("seed") or {}).get("run_id")), "",
             "定稿 %s (自動收爐 finalize3c.py). 開跑 %s; probe3c 停 %s; Phase 3c wall %.2f h / 40 h (resume ×%d); **CPU-h (Σ 證書 wall × %d) %.1f / 400**." % (
                 self.now, st.get("started"), st.get("finished"), (st.get("elapsed_s") or 0) / 3600, st.get("resumes", 0), W, st.get("cpu_h_used") or 0), "",
             "## 一句結果", "",
             ("**RECORD_CANDIDATE: |G₃′| = %d < 1441** (%d 點 %d 邊, 無 spindle 兩引擎, 唔可 4 色 —— 全部機器證書 + 獨立重驗 all_ok=%s); 已封存 `%s`; **未公開 / 未寄信 / 未 push, 等 Amber**. 詳見 `RECORD_CANDIDATE.md`." % (G3n, G3n, G3m, vres.get("all_ok"), FINAL_D)) if self.rec_ok else
             (("**!! 候選但獨立重驗唔過**: probe3c 到咗 |G₃′| = %d < 1441 (%d 邊), 但 finalize 由碟上檔案重驗 all_ok=%s (%s) —— **唔算紀錄候選**, 封存只係證據 (`%s`, VERIFY_FAILED.md / RECORD_CANDIDATE_BLOCKED.md); 要人手睇." % (G3n, G3m, vres.get("all_ok"), (vres.get("error") or "見 verify_final.json")[:200], FINAL_D)) if st.get("record_candidate") else
              ("**未到 1441**: 最終認證圖 |G₂′| = %d (%d 邊), |G₃′| = %d (%d 邊), S_acc = %d 粒; 停機原因: %s. 最終圖全套證書 + 獨立重驗 (all_ok=%s%s) 封存 `%s`." % (G2n, G2m, G3n, G3m, len(st["S_acc"]), st.get("stop_reason"), vres.get("all_ok"), "" if self.vok else " **!! 重驗唔過, 見 VERIFY_FAILED.md**", FINAL_D))), "",
             "## 參數 (Amber 2026-09-07 授權; 全部由 probe3c.py 執行)", "",
             "- 總成本上限 400 CPU-h (由 r04 起計; CPU-h = 每張證書 wall × 14, 同 Phase 3b 閘門定義); 總 wall 40 h (checkpoint + resume); 每輪硬上限 3.5 h; 每批 30 粒 (排序 度數升 / |Im z| 降 / 索引); SAT → witness 貪心放返跳過 (每輪 ≤ 3 張額外證書); 連續 3 輪淨剪 < 10 → 停; 14 workers; march d=14; kissat T=600 → 2T → 再拆; 5% 審計.",
             "- 開新一輪先要: 剩餘 CPU / 14 ≥ 1.15 × 上一張 certified 證書 wall, 剩餘 wall 亦然; 輪上限 = min(3.5 h, 剩餘 wall, 剩餘 CPU/14 − 15 min) ⇒ 唔會超 400.",
             "- 封存規則: cnc2k --keep-dir 每個 leaf 證明 VERIFIED 後保留喺 D: (`/mnt/d/hadwiger/phase3c/keep/<tag>/`); 唔係 certified 嘅嘗試即刪; 上一輪 certified 嘅 keep 只喺本輪 certified (L2″/L3″ 亦過) 後先刪; 搬失敗即場重解重驗再搬 (repair).",
             "- 停機規則: |G₂′| ≤ 720 (⇔ |G₃′| < 1441) 一到即停 + l3g2 --engine-b + finalize 獨立重驗 + 封存 + RECORD_CANDIDATE.md; 預算 / wall / 低淨剪 → 停 + 封存最新認證圖.", "",
             "## Ledger (全部輪; 前 3 輪係 Phase 3b seed)", "",
             "| 輪 | 來源 | 嘗試 | |S| | 結果 | cube | leaf | 每 cube solve (s) | 每 cube s+v (s) | ×G₂recon | wall | CPU-h | leaf 證明保留 | B | |G₂′| | |G₃′| | L2″/L3″/完整/spindle |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in self.rounds:
            for x in r["attempts"]:
                kp = x.get("keep") or {}
                L.append("| %d | %s | %s | %d | %s | %s | %s | %s | %s | %s | %.2f h | %.1f | %s | %s | %s | %s | %s |" % (
                    r["round"], r.get("from_run") or self.rid, x["tag"], x["removed"], x["status"], x.get("n_cubes", "—"), x.get("leaves", "—"), x.get("mean_solve_s", "—"), x.get("mean_sv_s", "—"), x.get("x_G2recon_sv", "—"),
                    (x.get("wall_s") or 0) / 3600, (x.get("wall_s") or 0) * W / 3600,
                    ("%s/%s%s" % (kp.get("kept_leaves"), x.get("leaves"), (" → 已刪 (%s 認證後)" % kp["deleted_after_next_certified"]) if kp.get("deleted_after_next_certified") else (" → final/" if kp.get("on_disk") else ""))) if kp and x["status"] == "certified" else ("驗完即刪 (3b 政策)" if r.get("from_run") and x["status"] == "certified" else "—"),
                    ("|B|=%d %s" % (x["B_size"], x["witness"]["blocked_min"])) if x.get("witness") else "—", x["cnf"]["n_remaining"] if x.get("cnf") else "—", x.get("G3p_n", "—"), ("✓" if x.get("l3_ok") else "!!") if x["status"] == "certified" else "—"))
            L.append("| %d | %s | 結算 | — | **%s** | — | — | — | — | — | %.2f h | — | — | B 集合 %s | — | — | 淨剪 %s (S_acc %d → %d) |" % (
                r["round"], r.get("from_run") or self.rid, r.get("status"), (r.get("wall_s") or 0) / 3600, r.get("B_sets"), r.get("net_removed"), len(r["S_acc_before"]), len(r.get("S_acc_after", r["S_acc_before"]))))
        L += ["", "Phase 3c 淨剪: %s; S_acc %d → %d 粒; 0 SAT: %s; 每輪三張證書 (L1″ cnc2k bundle + cover + 5%% 審計; L2″ 精確映射 + exactfield --complete; L3″ 引理 UNSAT drat-trim) 見下表." % (
            [(r["round"], r.get("status"), r.get("net_removed")) for r in own], (st.get("seed") or {}).get("S_acc_size"), len(st["S_acc"]), not any(x.get("status") == "SAT" for r in own for x in r["attempts"])), "",
              "## 每輪三張證書 (Phase 3c certified 輪)", "", "| 輪 | tag | L1″ base.cnf sha | cover drat sha | 審計 | L2″ (identity/ρ 邊映射, 完整性 G2p/G3p) | L3″ drat sha / VERIFIED | spindle A / B |", "|---|---|---|---|---|---|---|---|"]
        for r, x in cert_own:
            cdir = os.path.join(x.get("dir") or os.path.join(self.rdir, x["tag"]), "cnc_" + x["tag"]); cb = json.load(open(os.path.join(cdir, "bundle.json"))) if os.path.exists(os.path.join(cdir, "bundle.json")) else {}
            ls = x.get("l3_summary") or {}
            L.append("| %d | %s | `%s` | `%s` | %s/%s ok | 邊缺 %s/%s, 完整 rc %s/%s | `%s` / %s | %s / %s |" % (
                r["round"], x["tag"], (cb.get("base_sha") or "")[:16], ((cb.get("cover") or {}).get(cb.get("cover_mode") or "", {}).get("proof_sha") or "")[:16], (cb.get("audit") or {}).get("n"), (cb.get("audit") or {}).get("n"),
                (ls.get("L2") or {}).get("identity_edges_missing"), (ls.get("L2") or {}).get("rho_edges_missing"), (ls.get("complete_G2p") or {}).get("rc"), (ls.get("complete_G3p") or {}).get("rc"),
                (((ls.get("L3") or {}).get("sha") or {}).get("L3pp.drat") or "")[:16], (ls.get("L3") or {}).get("verified"), (ls.get("spindle_A") or {}).get("copies"), ((ls.get("spindle_B") or {}).get("ok") if ls.get("spindle_B") else "(final 先跑)")))
        L += ["", "## 停機 / 預算", "", "- 停機原因: **%s**" % st.get("stop_reason"),
              "- CPU-h: %.1f / 400 (Phase 3c 證書 wall 合計 %.2f h × %d); wall %.2f / 40 h; 連續低淨剪 %s 輪; resume %d 次." % (st.get("cpu_h_used") or 0, sum((x.get("wall_s") or 0) for r in own for x in r["attempts"]) / 3600, W, (st.get("elapsed_s") or 0) / 3600, st.get("low_net_streak"), st.get("resumes", 0)),
              "- 完場外推 (hardness_g2, 資訊): %s —— %s" % ((st.get("gate_final") or {}).get("verdict"), (st.get("gate_final") or {}).get("why")), "",
              "## 最終認證圖", "", "- 證書: round %d %s (%s); S = %d 粒 (名單喺 `final/L1pp/base.json`, `state.json`)." % (fa["round"], fa["tag"], "Phase 3c" if fa["own"] else "seed %s" % fa["from_run"], len(fa["S"])),
              "- |G₂′| = **%d** 點 **%d** 邊; |G₃′| = 2|G₂′| − 1 = **%d** 點 **%d** 邊; %s." % (G2n, G2m, G3n, G3m, ("**< 1441 ✓ RECORD_CANDIDATE (獨立重驗通過)**" if self.rec_ok else "< 1441 但重驗唔過 (BLOCKED)") if G3n < 1441 else "≥ 1441 (未到目標 720 / 1441)"),
              "- 獨立重驗 (verify_final, 由碟上檔案出發): all_ok = **%s**; leaf 證明 %s; cover %s; 審計證明 %s; l3_final (fresh, engine B) all_ok %s, spindle B ok %s, 同戰役 l3/ 檔案一致 %s; exactfield --complete G3p 再跑 rc %s." % (
                  vres.get("all_ok"), ("%s/%s drat-trim VERIFIED + sha 一致 (%.0f s, %s GB)" % (lr.get("ok"), lr.get("n"), lr.get("wall_s") or 0, lr.get("proof_total_gb"))) if lr else "唔喺碟上 (seed r03a, Phase 3b 政策)", (vres.get("cover_reverify") or {}).get("verified"),
                  ("%s/%s" % ((vres.get("audit_reverify") or {}).get("ok"), (vres.get("audit_reverify") or {}).get("kept_files"))) if vres.get("audit_reverify") else "(seed: 只有 bundle 記錄)",
                  (vres.get("l3_final") or {}).get("all_ok"), (((vres.get("l3_final") or {}).get("spindle_B") or {}).get("ok")), (all(((vres.get("l3_final") or {}).get("same_files_as_campaign_l3")).values()) if (vres.get("l3_final") or {}).get("same_files_as_campaign_l3") else "n/a"), (vres.get("exactfield_complete_G3p_again") or {}).get("rc", "n/a")), "",
              "## 封存清單", "",
              "- `%s` (D:; %s 檔, %.2f GB; SHA256SUMS sha256 `%s`; `sha256sum -c` rc=%s): `L1pp/` (base.cnf/json, cubes_d14.icnf, march.log, cnc.log, `cnc_%s/` bundle/state/ledger/cover_pure.{cnf,drat}, **`leaf_proofs/` %s 個 leaf DRAT + `audit/`**, LEAF_INDEX.json, verify_final.json), `L2L3/l3/` + `L2L3/l3_final/` (G2p/G3p .cvtx/.edge, maps.json, L3pp.{cnf,drat,json}, summary.json, spindle_B/), `run/` (ledger, rounds, state, gate, hardness, probe3c.log, batches, seed), `scripts/` (phase3c incl. cnc2k.diff, phase3b, phase2b, phase2), `FINAL_README.md` (英文), `reverify.sh`%s." % (
                  arch.get("final_dir"), arch.get("n_files"), (arch.get("bytes") or 0) / 1e9, (arch.get("sha256sums_sha256") or "")[:16], arch.get("check_rc"), fa["tag"], lr.get("n") if fa["has_keep"] else "0 (seed, 唔喺碟上)", (", `RECORD_CANDIDATE.md`" if self.rec_ok else (", `RECORD_CANDIDATE_BLOCKED.md`" if st.get("record_candidate") else "")) + ("" if self.vok else ", `VERIFY_FAILED.md`")),
              "- Windows 鏡像 `%s` (唔含 leaf_proofs, 有 LEAF_PROOFS_LOCATION.txt + SHA256SUMS.small)." % WIN_FINAL,
              "- 每輪細檔 `%s/phase3c_G2_shrink/` (%s 個嘗試, PHASE3C_README.md; reduction/ 共 %s 檔, `sha256sum -c` rc=%s), 鏡像 Windows `release_v1_1_staging/reduction/`." % (STAGE, stg.get("n_rounds_staged"), stg.get("reduction_files"), stg.get("check_rc")),
              "- 中途 keep 目錄 `/mnt/d/hadwiger/phase3c/keep/` 而今: %s" % ([d for d in os.listdir("/mnt/d/hadwiger/phase3c/keep")] if os.path.isdir("/mnt/d/hadwiger/phase3c/keep") else "(冇)"), "",
              "## 老實講明", "",
              "- Phase 3b 三輪 (r01a–r03a) 嘅 leaf 證明按當時政策驗完即刪 (只有 sha256/大細 喺 bundle.json); Phase 3c 由 r04 起全部保留. 如果 Phase 3c 冇任何 certified 輪, final/ 就冇 leaf 證明 (有 LEAF_PROOFS_NOT_ON_DISK.txt 講明).",
              "- CPU-h 用 wall × 14 計 (同 Phase 3b 閘門), 唔係 solver 實際 CPU 秒 (實際 solve+verify CPU 見 rounds.json cpu_solve_s / cpu_verify_s).",
              "- 冇公開任何嘢: 冇 git push, 冇 Zenodo new version, 冇 email.", ""]
        txt = "\n".join(L)
        if self.a.dry_run:
            write(os.path.join(PH3C, "selftest", "phase3c_results_dryrun.md"), txt); self.save(report=os.path.join(PH3C, "selftest", "phase3c_results_dryrun.md")); return txt
        write(os.path.join(PH3C, "phase3c_results.md"), txt); write(os.path.join(WIN, "phase3c", "phase3c_results.md"), txt)
        self.save(report=os.path.join(WIN, "phase3c", "phase3c_results.md"))
        return txt

    def facts(self, fa, vres, arch, stg):
        self.step("facts.json (g2shrink3c.*)")
        fp = os.path.join(WIN, "paper", "facts.json")
        if self.a.dry_run:
            fp_out = os.path.join(PH3C, "facts_dryrun.json")
        else:
            fp_out = fp
        try:
            F = json.load(open(fp, encoding="utf-8")); facts = F["facts"]; n0 = len(facts); st = self.st
            def add(key, value, unit=None, source=None, note=None, verified=True):
                facts[key] = {"value": value, "unit": unit, "source": source, "note": note, "verified": verified}
            own = [r for r in self.rounds if not r.get("from_run")]
            add("g2shrink3c.run_id", self.rid, None, "phase3c/runs/%s/state.json" % self.rid)
            add("g2shrink3c.seed", st.get("seed"), None, "phase3c/runs/%s/state.json (seed provenance: Phase 3b r03a bundle/l3 sha)" % self.rid)
            add("g2shrink3c.params", {"cpu_cap_h": 400, "cpu_h_definition": "sum of certificate wall × 14 workers", "wall_cap_h": 40, "round_cap_h": 3.5, "k": 30, "low_net": 10, "low_net_rounds": 3, "workers": 14, "depth": 14, "timeout": 600}, None, "Amber's Phase 3c mega-prompt 2026-09-07; probe3c.py argv")
            add("g2shrink3c.attempts", [{"round": r["round"], "tag": x["tag"], "removed": x["removed"], "status": x["status"], "n_cubes": x.get("n_cubes"), "leaves": x.get("leaves"), "mean_solve_s": x.get("mean_solve_s"), "mean_sv_s": x.get("mean_sv_s"), "max_solve_s": x.get("max_solve_s"),
                                          "wall_s": x.get("wall_s"), "cpu_h_wall14": round((x.get("wall_s") or 0) * 14 / 3600, 2), "cpu_solve_s": x.get("cpu_solve_s"), "cpu_verify_s": x.get("cpu_verify_s"), "proof_total_mb": x.get("proof_total_mb"), "G2p_n": (x.get("cnf") or {}).get("n_remaining"), "G2p_m": (x.get("cnf") or {}).get("n_edges"),
                                          "G3p_n": x.get("G3p_n"), "G3p_m": x.get("G3p_m"), "l3_ok": x.get("l3_ok"), "B": (x.get("witness") or {}).get("blocked_min"), "split_events": x.get("split_events"), "solver_errors": x.get("solver_errors"), "keep": {k: v for k, v in (x.get("keep") or {}).items() if k in ("kept_leaves", "keep_errors", "gb", "on_disk", "deleted_after_next_certified")}} for r in own for x in r["attempts"]],
                None, "phase3c/runs/%s/rounds.json" % self.rid)
            add("g2shrink3c.rounds", [{k: r.get(k) for k in ("round", "status", "net_removed", "G2p_n", "G3p_n", "wall_s", "B_sets", "budget_before", "budget_after")} for r in own], None, "phase3c/runs/%s/rounds.json" % self.rid)
            add("g2shrink3c.S_acc_final", st["S_acc"], None, "phase3c/runs/%s/state.json" % self.rid, "certified removable set; all certificates in release_v1_1_staging/final (D:) and reduction/phase3c_G2_shrink")
            sm_p = os.path.join(fa["vdir"], "l3_final", "summary.json"); sm = json.load(open(sm_p)) if os.path.exists(sm_p) else json.load(open(os.path.join(fa["dir"], "l3", "summary.json")))
            add("g2shrink3c.G2p_final", {"n": sm["G2p"]["n"], "m": sm["G2p"]["m"]}, None, "final/L2L3/l3_final/summary.json (exactfield --complete)")
            add("g2shrink3c.G3p_final", {"n": sm["G3p"]["n"], "m": sm["G3p"]["m"], "below_1441": sm["G3p"]["n"] < 1441}, None, "final/L2L3/l3_final/summary.json (exactfield --complete; L3'' UNSAT VERIFIED; spindle A copies=%s, engine B ok=%s)" % ((sm.get("spindle_A") or {}).get("copies"), (sm.get("spindle_B") or {}).get("ok")))
            add("g2shrink3c.final_certificate", {"round": fa["round"], "tag": fa["tag"], "from_run": fa["from_run"], "base_sha256": fa["rec"]["cnf"]["cnf_sha256"], "leaf_proofs_on_disk": fa["has_keep"]}, None, "phase3c/runs/%s/rounds.json" % self.rid)
            add("g2shrink3c.stop_reason", st.get("stop_reason"), None, "phase3c/runs/%s/state.json" % self.rid)
            add("g2shrink3c.record_candidate", self.rec_ok, None, "phase3c/runs/%s/state.json (probe3c record_candidate=%s) AND finalize independent re-verification all_ok=%s" % (self.rid, bool(st.get("record_candidate")), self.vok), "true only when |G3'| < 1441 AND verify_final passed", verified=bool(self.vok))
            add("g2shrink3c.verify_failed", not self.vok, None, "final/L1pp/verify_final.json")
            add("g2shrink3c.cpu_h_used", st.get("cpu_h_used"), "CPU-h (wall×14)", "phase3c/runs/%s/state.json" % self.rid); add("g2shrink3c.wall_h", round((st.get("elapsed_s") or 0) / 3600, 2), "h", "phase3c/runs/%s/state.json" % self.rid)
            add("g2shrink3c.verify_final", {k: v for k, v in vres.items() if k in ("all_ok", "base_sha_consistent", "leaf_count_consistent", "leaf_ids_are_all_root_cubes", "cover_reverify", "audit_reverify", "exactfield_complete_G3p_again", "t_s")} | {"leaf_reverify": {k: v for k, v in (vres.get("leaf_reverify") or {}).items() if k != "bad"}, "l3_final": {k: v for k, v in (vres.get("l3_final") or {}).items() if k in ("rc", "all_ok", "same_files_as_campaign_l3", "spindle_A", "spindle_B")}},
                None, "final/L1pp/verify_final.json (verify_final.py, independent re-verification from files on disk)")
            add("g2shrink3c.archive", arch, None, "finalize3c.py (final/SHA256SUMS)")
            add("g2shrink3c.staging", stg, None, "finalize3c.py (reduction/SHA256SUMS)")
            if st.get("gate_final"):
                add("g2shrink3c.hardness_final", st["gate_final"], None, "phase3c/runs/%s/gate_g2.md (informational extrapolation)" % self.rid)
            F["generated"] = time.strftime("%Y-%m-%d %H:%M:%S")
            if "Phase 3c additions (g2shrink3c.*)" not in (F.get("note") or ""):
                F["note"] = (F.get("note") or "") + " | Phase 3c additions (g2shrink3c.*) by phase3c/finalize3c.py."
            write(fp_out, json.dumps(F, indent=1, ensure_ascii=False))                                # 審查 #25: 先序列化再原子寫
            self.save(facts="%d → %d facts → %s" % (n0, len(facts), fp_out)); log("facts: %d → %d → %s" % (n0, len(facts), fp_out))
        except Exception as e:
            self.save(facts="!! %r" % e); log("!! facts 失敗: %r" % e)

    def decision(self, fa, vres, arch):
        self.step("DECISION.md 路線 A 加一段")
        p = os.path.join(WIN, "phase2b", "DECISION.md"); st = self.st
        try:
            s = open(p, encoding="utf-8").read()
            marker = "**Phase 3c G₂ 續剪結果"
            sm_p = os.path.join(fa["vdir"], "l3_final", "summary.json"); sm = json.load(open(sm_p)) if os.path.exists(sm_p) else json.load(open(os.path.join(fa["dir"], "l3", "summary.json")))
            own = [r for r in self.rounds if not r.get("from_run")]
            para = ("%s(%s;run %s,接力 Phase 3b r03a;Amber 放寬預算 400 CPU-h / 40 h wall / 每輪 3.5 h;只加呢一段,其他原文不動):** Phase 3c 跑咗 %d 輪 (%s),淨剪 %s,S_acc %d → %d;%s —— 最終認證圖 |G₂′| = %d 點 %d 邊,**|G₃′| = %d 點 %d 邊**(L1″+L2″+L3″ + exactfield --complete + spindle 兩引擎,獨立重驗 all_ok=%s);"
                    "CPU-h %.1f / 400,wall %.2f h;停機原因:%s。全套證書(含全部 leaf proofs)封存 `%s`(D:),每輪細檔 `release_v1_1_staging/reduction/phase3c_G2_shrink/`;報告 `phase3c/phase3c_results.md`。**未公開、未寄信、未 push。**" % (
                        marker, self.now, self.rid, len(own), [(r["round"], r.get("status")) for r in own], [r.get("net_removed") for r in own], (st.get("seed") or {}).get("S_acc_size"), len(st["S_acc"]),
                        "**RECORD_CANDIDATE(|G₃′| < 1441,獨立重驗通過)—— 等 Amber 決定**" if self.rec_ok else ("**!! 到咗 < 1441 但獨立重驗唔過(BLOCKED,要人手睇 VERIFY_FAILED.md)**" if st.get("record_candidate") else ("未到 1441" + ("" if self.vok else "(**獨立重驗唔過**,見 VERIFY_FAILED.md)"))), sm["G2p"]["n"], sm["G2p"]["m"], sm["G3p"]["n"], sm["G3p"]["m"], vres.get("all_ok"),
                        st.get("cpu_h_used") or 0, (st.get("elapsed_s") or 0) / 3600, (st.get("stop_reason") or "").replace("\n", " "), arch.get("final_dir")))
            if marker in s:
                s = re.sub(r"\*\*Phase 3c G₂ 續剪結果.*?(?=\n\n)", lambda m: para, s, count=1, flags=re.S)        # 審查 #21: lambda 免 template escape
            else:
                anchor = "\n\n---\n\n## 路線 B"
                assert anchor in s, "DECISION.md 搵唔到路線 B 錨點"
                s = s.replace(anchor, "\n\n" + para + anchor, 1)
            if not self.a.dry_run:
                write(p, s)
            else:
                write(os.path.join(PH3C, "DECISION_dryrun.md"), s)
            self.save(decision="ok: 路線 A 加一段 (%d 字)" % len(para)); log("DECISION.md: 路線 A 加一段")
        except Exception as e:
            self.save(decision="!! %r" % e); log("!! DECISION.md 失敗: %r" % e)

    def memory(self, fa, vres, arch):
        self.step("MEMORY 更新 (hadwiger-project.md / no-spindle-hardness.md / MEMORY.md)")
        st = self.st; own = [r for r in self.rounds if not r.get("from_run")]
        try:
            sm_p = os.path.join(fa["vdir"], "l3_final", "summary.json"); sm = json.load(open(sm_p)) if os.path.exists(sm_p) else json.load(open(os.path.join(fa["dir"], "l3", "summary.json")))
            G2n, G3n = sm["G2p"]["n"], sm["G3p"]["n"]; vtag = "" if self.vok else " **!! 獨立重驗唔過 (VERIFY_FAILED.md)**"
            one = "Phase 3c 完 (%s): run %s 由 r03a 接力跑 %d 輪 (certified %d), S_acc %d → %d, |G₂′| %d, |G₃′| %d%s; CPU %.1f/400 CPU-h, wall %.2f h; 停: %s; 全套證書 (含 leaf proofs) 封存 D:/hadwiger/release_v1_1_staging/final; 報告 phase3c/phase3c_results.md; 未公開" % (
                self.now[:16], self.rid, len(own), sum(1 for r in own if r.get("status") == "certified"), (st.get("seed") or {}).get("S_acc_size"), len(st["S_acc"]), G2n, G3n,
                (" **RECORD_CANDIDATE (<1441, 獨立重驗通過), 等 Amber**" if self.rec_ok else (" **<1441 但獨立重驗唔過, BLOCKED**" if st.get("record_candidate") else " (未到 1441)")) + vtag, st.get("cpu_h_used") or 0, (st.get("elapsed_s") or 0) / 3600, (st.get("stop_reason") or "")[:120].replace("\n", " "))
            out = {}
            # hadwiger-project.md
            p = os.path.join(MEM, "hadwiger-project.md"); s = open(p, encoding="utf-8").read()
            block = ("**Phase 3c(%s 起;Mega-Prompt「G₂ 續剪(預算放寬)」;源碼 `Desktop\\spindle\\phase3c\\`,WSL `~/hadwiger/phase3c/`;run `%s`;報告 `phase3c/phase3c_results.md`):** %s。"
                     "每輪 wall / 每 cube s+v:%s。獨立重驗 verify_final all_ok=%s(leaf 證明 %s/%s drat-trim 重驗)。最終圖 S 名單喺 `final/L1pp/base.json`。續跑 / 重跑收爐:`phase3c/resume3c.sh`(probe3c --resume → finalize3c 幂等)。" % (
                         st.get("started"), self.rid, one, [(x["tag"], round((x.get("wall_s") or 0) / 3600, 2), x.get("mean_sv_s")) for r in own for x in r["attempts"] if x.get("status") == "certified"], vres.get("all_ok"),
                         (vres.get("leaf_reverify") or {}).get("ok"), (vres.get("leaf_reverify") or {}).get("n")))
            if "**Phase 3c(" in s:
                s = re.sub(r"\*\*Phase 3c\(.*?(?=\n\n\*\*How to apply)", lambda m: block, s, count=1, flags=re.S)
            elif "\n\n**How to apply:**" in s:
                s = s.replace("\n\n**How to apply:**", "\n\n" + block + "\n\n**How to apply:**", 1)
            else:
                s = s.rstrip("\n") + "\n\n" + block + "\n"
            m = re.search(r'^description: "(.*)"\s*$', s, re.M)
            if m and "Phase 3c" not in m.group(1):
                s = s.replace(m.group(0), 'description: "%s; %s"' % (m.group(1), one.replace('"', "'")[:300]), 1)
            out["hadwiger-project.md"] = len(block)
            if not self.a.dry_run:
                write(p, s)
            else:
                write(os.path.join(PH3C, "mem_dryrun_hadwiger-project.md"), s)
            # no-spindle-hardness.md
            p2 = os.path.join(MEM, "no-spindle-hardness.md"); s2 = open(p2, encoding="utf-8").read()
            cert = [x for r in own for x in r["attempts"] if x.get("status") == "certified"]
            b2 = "**Phase 3c(%s,`phase3c/`)—— G₂ 續剪 r04+(預算 400 CPU-h):** %d 輪 certified / %d 輪跑;每張證書 wall %s h、每 cube s+v %s s(×G₂recon %s);SAT 嘗試 %d 個%s;結論:%s。" % (
                self.now[:10], len(cert), len(own), [round((x.get("wall_s") or 0) / 3600, 2) for x in cert], [x.get("mean_sv_s") for x in cert], [x.get("x_G2recon_sv") for x in cert],
                sum(1 for r in own for x in r["attempts"] if x.get("status") == "SAT"), (" (B 集合 %s)" % [r.get("B_sets") for r in own if r.get("B_sets")]) if any(r.get("B_sets") for r in own) else "",
                ("|G₃′| = %d < 1441 紀錄候選 (獨立重驗通過),G₂ 方向嘅 346 粒目標達成" % G3n) if self.rec_ok else (("|G₃′| = %d < 1441 但獨立重驗唔過 (BLOCKED)" % G3n) if st.get("record_candidate") else ("|G₃′| = %d,停於 %s" % (G3n, (st.get("stop_reason") or "")[:100]))))
            if "**Phase 3c(" in s2:
                s2 = re.sub(r"\*\*Phase 3c\(.*?(?=\n\n\*\*Why)", lambda m: b2, s2, count=1, flags=re.S)
            elif "\n\n**Why:**" in s2:
                s2 = s2.replace("\n\n**Why:**", "\n\n" + b2 + "\n\n**Why:**", 1)
            else:
                s2 = s2.rstrip("\n") + "\n\n" + b2 + "\n"
            if not self.a.dry_run:
                write(p2, s2)
            else:
                write(os.path.join(PH3C, "mem_dryrun_no-spindle-hardness.md"), s2)
            out["no-spindle-hardness.md"] = len(b2)
            # MEMORY.md 索引
            p3 = os.path.join(MEM, "MEMORY.md"); s3 = open(p3, encoding="utf-8").read()
            lines = s3.split("\n"); done = False
            for i, l in enumerate(lines):
                if l.startswith("- [Hadwiger project](hadwiger-project.md)"):
                    head = l.split(";**Phase 3b")[0] if ";**Phase 3b" in l else l.split("；**Phase 3b")[0] if "；**Phase 3b" in l else l
                    head = head.split(";**Phase 3c")[0]
                    lines[i] = head + ";Phase 3b 三輪 certified |G₃′| 1951(`phase3b/phase3b_results.md`);**Phase 3c 完(%s)**:%s;%s" % (self.now[:16], (("**RECORD_CANDIDATE |G₃′| = %d < 1441,獨立重驗通過,等 Amber**" % G3n) if self.rec_ok else (("**<1441 但重驗唔過 BLOCKED**" if st.get("record_candidate") else "|G₃′| %d,停 %s" % (G3n, (st.get("stop_reason") or "")[:60])) + vtag)).replace("\n", " "), "報告 `phase3c/phase3c_results.md`;冇背景任務 (S60_full 補封存見報告)")
                    done = True
            if not done:
                lines.append("- [Hadwiger project](hadwiger-project.md) — %s" % one[:300])
            s3 = "\n".join(lines)
            if not self.a.dry_run:
                write(p3, s3)
            else:
                write(os.path.join(PH3C, "mem_dryrun_MEMORY.md"), s3)
            out["MEMORY.md"] = "index line updated" if done else "appended"
            self.save(memory=out); log("MEMORY: %s" % out)
        except Exception as e:
            self.save(memory="!! %r" % e); log("!! MEMORY 失敗: %r" % e)

    # ---------------- S60 append ----------------
    def append_s60(self, s60_json):
        j = json.load(open(s60_json)); self.step("append S60_full 結果到報告 / facts")
        L = ["", "## 補封存 Proposition 2: G₁ − S₆₀ (1891 點 G₃′) L1′ 重新生成並保留 leaf proofs (`s60_full.py`, ≤ 3 h)", "",
             "- 狀態: **%s**; base.cnf sha `%s` (== Phase 3 round2 base %s); cube %s, leaf %s, mean s+v %s s, wall %.2f h; cover %s; 審計 %s; leaf 證明保留 %s/%s (搬失敗 %s); 獨立重驗 verify_final all_ok = %s." % (
                 j.get("status"), (j.get("base_sha") or "")[:16], j.get("base_sha_matches_phase3"), j.get("n_cubes"), j.get("leaves"), j.get("mean_sv_s"), (j.get("wall_s") or 0) / 3600, j.get("cover_verified"), (j.get("audit") or {}).get("all_ok"), j.get("kept_leaves"), j.get("leaves"), j.get("keep_errors"), (j.get("verify_final") or {}).get("all_ok")),
             "- 封存: `%s` (leaf 證明, D:) + `%s` (base/bundle/cover/ledger/state + Phase 3 round2 嘅 L2′/L3′ 檔 + S60_README.md); reduction/SHA256SUMS 重算 rc=%s; 鏡像 Windows." % (j.get("final_dir"), j.get("stage_dir"), j.get("stage_check_rc")),
             "- 意義: 論文 Proposition 2 (G₃′ 1891 點 5-chromatic 無 spindle) 由「可重跑」升級做「已封存」(全部 leaf proofs 喺碟上)." if j.get("status") == "certified" else "- 未完成 (%s): Proposition 2 仍係「可重跑」狀態 (round2 證書 sha 喺 reduction/phase3_G1_probe/round2/)." % j.get("status"), ""]
        for p in (os.path.join(PH3C, "phase3c_results.md"), os.path.join(WIN, "phase3c", "phase3c_results.md")):
            if os.path.exists(p):
                s = open(p, encoding="utf-8").read()
                if "## 補封存 Proposition 2" in s:
                    s = s[:s.index("\n## 補封存 Proposition 2")]
                write(p, s.rstrip("\n") + "\n" + "\n".join(L))
        try:
            fp = os.path.join(WIN, "paper", "facts.json"); F = json.load(open(fp, encoding="utf-8"))
            F["facts"]["reduction.S60_full"] = {"value": {k: v for k, v in j.items() if k not in ("leaf_ids",)}, "unit": None, "source": "phase3c/s60_full/s60_full.json (s60_full.py; cnc2k --keep-dir on Phase 3 round2 base.cnf + cubes_d14.icnf)", "note": "Proposition 2 certificate with all leaf proofs archived on D:", "verified": j.get("status") == "certified" and bool((j.get("verify_final") or {}).get("all_ok"))}
            F["generated"] = time.strftime("%Y-%m-%d %H:%M:%S")
            if not self.a.dry_run:
                write(fp, json.dumps(F, indent=1, ensure_ascii=False))
            self.save(s60_full="%s: leaf %s/%s kept, verify all_ok %s" % (j.get("status"), j.get("kept_leaves"), j.get("leaves"), (j.get("verify_final") or {}).get("all_ok")))
        except Exception as e:
            self.save(s60_full="!! facts %r" % e)
        try:
            p = os.path.join(MEM, "hadwiger-project.md"); s = open(p, encoding="utf-8").read()
            note = "S60_full 補封存: %s (leaf %s/%s 保留, verify all_ok %s, `reduction/S60_full/`)." % (j.get("status"), j.get("kept_leaves"), j.get("leaves"), (j.get("verify_final") or {}).get("all_ok"))
            if "S60_full 補封存:" in s:
                s = re.sub(r"S60_full 補封存: .*?\)\.", lambda m: note, s, count=1, flags=re.S)
            elif "\n\n**How to apply:**" in s:
                s = s.replace("\n\n**How to apply:**", " " + note + "\n\n**How to apply:**", 1)
            if not self.a.dry_run:
                write(p, s)
        except Exception as e:
            log("!! memory S60 note: %r" % e)
        self.save(all_done=True, s60_finished=time.strftime("%Y-%m-%d %H:%M:%S"))
        log("S60 append done")

    def run(self):
        a = self.a
        if a.append_s60:
            return self.append_s60(a.append_s60)
        fa = self.final_attempt()
        log("最終認證圖: round %d %s (%s) |G₂′| %d |G₃′| %s, keep %s (on disk %s)" % (fa["round"], fa["tag"], "Phase 3c" if fa["own"] else fa["from_run"], fa["G2p_n"], fa["G3p_n"], fa["keep_dir"], fa["has_keep"]))
        self.save(final={k: v for k, v in fa.items() if k not in ("rec", "rr", "S")})
        vres = self.verify(fa)
        arch = self.archive(fa, vres)
        stg = self.stage_rounds()
        self.report(fa, vres, arch, stg)
        self.facts(fa, vres, arch, stg)
        self.decision(fa, vres, arch)
        self.memory(fa, vres, arch)
        self.fs["done"] = True; self.fs["finished"] = time.strftime("%Y-%m-%d %H:%M:%S"); self.fs["all_done"] = not a.expect_s60; self.save()
        self.step("收爐完 (%s)%s" % (self.fs["finished"], "; 跟住 s60_full.py (可選, ≤ 3 h)" if a.expect_s60 else ""))
        log("FINALIZE3C DONE: verify all_ok=%s (vok=%s), archive %s, probe record_candidate=%s, confirmed=%s" % (vres.get("all_ok"), self.vok, arch.get("final_dir"), self.st.get("record_candidate"), self.rec_ok))
        if not self.vok:
            sys.exit(4)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True); ap.add_argument("--workers", type=int, default=14); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--force-verify", action="store_true")
    ap.add_argument("--append-s60", default=None); ap.add_argument("--expect-s60", action="store_true")
    a = ap.parse_args()
    Fin(a).run()

if __name__ == "__main__":
    main()
