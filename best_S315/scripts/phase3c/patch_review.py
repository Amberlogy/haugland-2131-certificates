#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_review.py —— 對抗性審查 (workflow wf_5d9ae617, 2026-09-07, 25 個確認 finding) 之後嘅修補, 全部以錨點替換施加 (錨點必須唯一), 施加後 ast.parse.
  finalize3c.py: 幂等 (keep 已 rename 入 final/ 之後再跑), 最終圖揀 S == S_acc 兼非 keep-incomplete, seed 分支唔寫入 Phase 3b 目錄 (vdir), 全部標題/RECORD_CANDIDATE/facts/DECISION/MEMORY 以獨立重驗 all_ok 為閘,
                 VERIFY_FAILED.md / RECORD_CANDIDATE_BLOCKED.md, re.sub 用 lambda, 原子寫 facts/DECISION/MEMORY, reverify.sh --json-out, .part 清走, 審計目錄字眼由 vres 決定
  verify_final.py: cover with_base 亦重建子句 (未知 mode 即唔過), header nvars, 審計證明完整性 (ids/n/sha), --json-out, l3 前先寫部分 JSON
  probe3c.py: CPU 閘同 cap 一致 (−0.25 h), resume 計返上次 cnc2k wall (prior) + 每 10 分鐘輕量 save, 操作員停機 needs_operator (唔准自動 resume, 要 --ack-operator), PAUSE 唔設 finished / 唔跑 gate,
              finished 喺 gate 前先寫, certified-keep-incomplete 狀態, 審計證明搬失敗亦 repair, campaign exception 清 keep 目錄
  s60_full.py: repair + 唔刪 keep 目錄 (除 SAT?!), rename 後幂等, 原子 JSON, resumable 旗
  status3c.py: render try/except, 標題以 finalize 重驗旗為準
"""
import io, os, re, ast, sys
HERE = os.path.dirname(os.path.abspath(__file__))

def patch(fname, reps):
    p = os.path.join(HERE, fname); s = io.open(p, encoding="utf-8").read(); n = 0
    for old, new in reps:
        c = s.count(old)
        assert c == 1, "%s: 錨點 %s (count %d): %r" % (fname, "唔存在" if c == 0 else "唔唯一", c, old[:90])
        s = s.replace(old, new, 1); n += 1
    if fname.endswith(".py"):
        ast.parse(s)
    io.open(p, "w", encoding="utf-8", newline="\n").write(s)
    print("[patch] %s: %d 個替換" % (fname, n))

# ======================= finalize3c.py =======================
F = []
F.append(('''        self.fs["stage"] = "start"; self.fs["done"] = False; self.save()
        self.W = a.workers; self.now = time.strftime("%Y-%m-%d %H:%M:%S")''',
'''        self.fs["stage"] = "start"
        if not a.append_s60:
            self.fs["done"] = False
        self.save(); self.vok = None; self.rec_ok = False
        self.W = a.workers; self.now = time.strftime("%Y-%m-%d %H:%M:%S")'''))
F.append(('''    def final_attempt(self):
        cert = [(r, x) for r in self.rounds for x in r["attempts"] if x.get("status") == "certified" and x.get("l3_ok") is True]
        assert cert, "冇任何 certified + l3_ok 嘅嘗試?!"
        r, x = cert[-1]
        d = x.get("dir") or os.path.join(self.rdir, x["tag"])
        own = not x.get("from_run")
        keep = (x.get("keep") or {}).get("dir") if own else None
        has_keep = bool(keep and os.path.isdir(keep) and (x.get("keep") or {}).get("on_disk"))
        S = x["S"]
        assert sorted(S) == sorted(self.st["S_acc"]), "最終證書嘅 S 同 state.S_acc 對唔上"
        return {"round": r["round"], "tag": x["tag"], "dir": d, "own": own, "from_run": x.get("from_run"), "keep_dir": keep, "has_keep": has_keep, "S": S, "rec": x, "rr": r,
                "G2p_n": x["cnf"]["n_remaining"], "G2p_m": x["cnf"]["n_edges"], "G3p_n": x.get("G3p_n"), "G3p_m": x.get("G3p_m") or ((x.get("l3_summary") or {}).get("L3") and None)}''',
'''    def final_attempt(self):
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
            log("!! status.json 旗寫唔到: %r" % e)'''))
F.append(('''    def verify(self, fa):
        d = fa["dir"]; tag = fa["tag"]; vf = os.path.join(d, "verify_final.json")
        if fa["has_keep"]:
            if os.path.exists(vf) and json.load(open(vf)).get("all_ok") and not self.a.force_verify:
                log("verify_final.json 已有而且 all_ok, 唔重做"); return json.load(open(vf))
            self.step("獨立重驗 %s: %d 個 leaf 證明 (drat-trim, %d workers) + cover + 審計證明 + l3g2 --engine-b + exactfield --complete" % (tag, fa["rec"].get("leaves") or 0, self.W))
            argv = [PY, os.path.join(PH3C, "verify_final.py"), "--attempt-dir", d, "--tag", tag, "--keep-dir", fa["keep_dir"], "--workers", str(self.W)]
            with open(os.path.join(d, "verify_final.log"), "a") as lf:
                rc = subprocess.call(argv, stdout=lf, stderr=subprocess.STDOUT)
            res = json.load(open(vf)) if os.path.exists(vf) else {"all_ok": False, "error": "verify_final.py rc=%d 冇輸出" % rc}
            res["rc"] = rc
        else:''',
'''    def verify(self, fa):
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
        else:'''))
F.append(('''            l3f = os.path.join(d, "l3_final")
            rl = subprocess.run([PY, os.path.join(PH3B, "l3g2.py"), "--remove", ",".join(map(str, fa["S"])), "--out", l3f, "--engine-b"], capture_output=True, text=True, timeout=5 * 3600)
            open(os.path.join(d, "l3_final.log"), "w").write(rl.stdout + rl.stderr)''',
'''            l3f = os.path.join(vd, "l3_final")
            rl = subprocess.run([PY, os.path.join(PH3B, "l3g2.py"), "--remove", ",".join(map(str, fa["S"])), "--out", l3f, "--engine-b"], capture_output=True, text=True, timeout=5 * 3600)
            open(os.path.join(vd, "l3_final.log"), "w").write(rl.stdout + rl.stderr)'''))
F.append(('''            json.dump(res, open(vf, "w"), indent=1, ensure_ascii=False)
        self.save(verify_final={"all_ok": res.get("all_ok"), "leaf_reverify": {k: v for k, v in (res.get("leaf_reverify") or {}).items() if k != "bad"}, "cover": (res.get("cover_reverify") or {}).get("verified"), "l3_final_all_ok": (res.get("l3_final") or {}).get("all_ok"), "spindle_B_ok": ((res.get("l3_final") or {}).get("spindle_B") or {}).get("ok"), "t_s": res.get("t_s")})
        log("verify_final: all_ok=%s" % res.get("all_ok"))
        return res''',
'''            write(vf, json.dumps(res, indent=1, ensure_ascii=False))
        self.vok = (res.get("all_ok") is True); self.rec_ok = bool(self.st.get("record_candidate")) and self.vok
        self.save(verify_final={"all_ok": res.get("all_ok"), "leaf_reverify": {k: v for k, v in (res.get("leaf_reverify") or {}).items() if k != "bad"}, "cover": (res.get("cover_reverify") or {}).get("verified"), "l3_final_all_ok": (res.get("l3_final") or {}).get("all_ok"), "spindle_B_ok": ((res.get("l3_final") or {}).get("spindle_B") or {}).get("ok"), "t_s": res.get("t_s"), "error": res.get("error")},
                  verify_failed=(not self.vok), record_candidate_confirmed=self.rec_ok)
        if not self.a.dry_run:
            self.flag_status()
        log("verify_final: all_ok=%s → vok=%s, record_candidate_confirmed=%s" % (res.get("all_ok"), self.vok, self.rec_ok))
        return res'''))
F.append(('''        for f in ("base.cnf", "base.json", "cubes_d14.icnf", "march.log", "cnc.log", "l3g2.log", "l3_final.log", "verify_final.json", "verify_final.log"):
            cp(os.path.join(d, f), L1)
        for f in ("bundle.json",''',
'''        for f in ("base.cnf", "base.json", "cubes_d14.icnf", "march.log", "cnc.log", "l3g2.log"):
            cp(os.path.join(d, f), L1)
        for f in ("l3_final.log", "verify_final.json", "verify_final.log"):
            cp(os.path.join(fa["vdir"], f), L1)
        for f in ("bundle.json",'''))
F.append(('''        if fa["has_keep"]:
            if os.path.isdir(lp) and not os.path.isdir(fa["keep_dir"]):
                moved = "already"
            else:
                assert not os.path.isdir(lp), "final/L1pp/leaf_proofs 已存在而且 keep 目錄亦存在 —— 唔敢覆寫, 人手睇"
                os.rename(fa["keep_dir"], lp); moved = "renamed"
            n = sum(1 for f in os.listdir(lp) if f.endswith(".drat"))''',
'''        if fa["has_keep"]:
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
            n = sum(1 for f in os.listdir(lp) if f.endswith(".drat"))'''))
F.append(('''        # L2″/L3″/spindle
        for sub in ("l3", "l3_final"):
            for f in glob.glob(os.path.join(d, sub, "*")):
                if os.path.isfile(f):
                    cp(f, os.path.join(F, "L2L3", sub))
            for f in glob.glob(os.path.join(d, sub, "spindle_B", "*")):
                cp(f, os.path.join(F, "L2L3", sub, "spindle_B"))''',
'''        # L2″/L3″/spindle (l3 = 戰役; l3_final = 收爐重跑, 喺 vdir)
        for sub, base_ in (("l3", d), ("l3_final", fa["vdir"])):
            for f in glob.glob(os.path.join(base_, sub, "*")):
                if os.path.isfile(f):
                    cp(f, os.path.join(F, "L2L3", sub))
            for f in glob.glob(os.path.join(base_, sub, "spindle_B", "*")):
                cp(f, os.path.join(F, "L2L3", sub, "spindle_B"))'''))
F.append(('''        self.write_reverify(F, fa)
        self.write_final_readme(F, fa, vres)
        rec_md = None
        if self.st.get("record_candidate"):
            rec_md = self.write_record_candidate(F, fa, vres)''',
'''        self.write_reverify(F, fa)
        self.write_final_readme(F, fa, vres)
        rec_md = None
        for stale in ("RECORD_CANDIDATE.md", "RECORD_CANDIDATE_BLOCKED.md", "VERIFY_FAILED.md"):
            if os.path.exists(os.path.join(F, stale)):
                os.remove(os.path.join(F, stale))
        if not self.vok:                                                                   # 審查 #2/#10/#19: 重驗唔過 → 封存只係證據, 大聲講明
            lr_ = vres.get("leaf_reverify") or {}
            txt = "# VERIFY_FAILED.md — independent re-verification did NOT pass (%s)\\n\\nThis directory is EVIDENCE ONLY. Do not treat the graph as certified until `bash reverify.sh` passes.\\n\\nverify_final all_ok = %s; error = %s\\nleaf_reverify: %s\\nbad leaves (first 50): %s\\ncover: %s\\naudit: %s\\nl3_final: %s\\n" % (
                self.now, vres.get("all_ok"), vres.get("error"), json.dumps({k: v for k, v in lr_.items() if k != "bad"}, default=str), json.dumps(lr_.get("bad"), default=str)[:4000],
                json.dumps(vres.get("cover_reverify"), default=str), json.dumps(vres.get("audit_reverify"), default=str)[:2000], json.dumps(vres.get("l3_final"), default=str)[:3000])
            for p_ in (os.path.join(F, "VERIFY_FAILED.md"), os.path.join(PH3C, "VERIFY_FAILED.md"), os.path.join(WIN, "phase3c", "VERIFY_FAILED.md")):
                write(p_, txt)
        if self.rec_ok:
            rec_md = self.write_record_candidate(F, fa, vres)
        elif self.st.get("record_candidate"):
            txt = "# RECORD_CANDIDATE_BLOCKED.md (%s)\\n\\nprobe3c reached |G2'| <= 720 (round %d, %s) but the independent re-verification (finalize3c / verify_final) did NOT pass (all_ok = %s). NOT a record candidate until re-verified. See VERIFY_FAILED.md.\\n" % (self.now, fa["round"], fa["tag"], vres.get("all_ok"))
            for p_ in (os.path.join(F, "RECORD_CANDIDATE_BLOCKED.md"), os.path.join(PH3C, "RECORD_CANDIDATE_BLOCKED.md"), os.path.join(WIN, "phase3c", "RECORD_CANDIDATE_BLOCKED.md")):
                write(p_, txt)'''))
F.append(('''        write(os.path.join(WIN_FINAL, "LEAF_PROOFS_LOCATION.txt"), "Leaf proofs (%s) are NOT mirrored here (C: has no room). They live on D: at %s/L1pp/leaf_proofs/ (Windows path D:\\\\hadwiger\\\\release_v1_1_staging\\\\final\\\\L1pp\\\\leaf_proofs\\\\). SHA256SUMS lists every file including the proofs; SHA256SUMS.small lists only the files present in this mirror.\\n" % (("%s files" % moved) if moved else "none", F))''',
'''        write(os.path.join(WIN_FINAL, "LEAF_PROOFS_LOCATION.txt"), "Leaf proofs (%s) are NOT mirrored here (C: has no room). They live on D: at %s/L1pp/leaf_proofs/ (Windows path D:\\\\hadwiger\\\\release_v1_1_staging\\\\final\\\\L1pp\\\\leaf_proofs\\\\). SHA256SUMS lists every file including the proofs; SHA256SUMS.small lists only the files present in this mirror.\\n" % (("%d leaf .drat files, state: %s" % (n, moved)) if moved else "none on disk", F))'''))
F.append(('''$PY /home/user/hadwiger/phase3c/verify_final.py --attempt-dir L1pp --tag %s --keep-dir L1pp/leaf_proofs --skip-l3 --tmp "$T/vf" | tail -8''',
'''$PY /home/user/hadwiger/phase3c/verify_final.py --attempt-dir L1pp --tag %s --keep-dir L1pp/leaf_proofs --skip-l3 --tmp "$T/vf" --json-out "$T/verify_final_reverify.json" | tail -8
cp "$T/verify_final_reverify.json" "reverify_$(date +%%Y%%m%%d_%%H%%M%%S).json"   # extra un-hashed file; the archived L1pp/verify_final.json is never overwritten'''))
F.append(('''        x = fa["rec"]; cb = json.load(open(os.path.join(fa["dir"], "cnc_" + fa["tag"], "bundle.json"))); sm = json.load(open(os.path.join(fa["dir"], "l3", "summary.json")))
        smf_p = os.path.join(fa["dir"], "l3_final", "summary.json"); smf = json.load(open(smf_p)) if os.path.exists(smf_p) else {}
        lr = vres.get("leaf_reverify") or {}
        G2n, G2m, G3n, G3m = sm["G2p"]["n"], sm["G2p"]["m"], sm["G3p"]["n"], sm["G3p"]["m"]
        rec = self.st.get("record_candidate")
        L = ["# FINAL_README.md — Phase 3c final certified graph (staging for v1.1; **NOT released**)", "",
             "Archived %s by `scripts/phase3c/finalize3c.py` (run `%s`, seeded from Phase 3b run `%s`). Author of the project: King Tat Wong (Amber); all statements below are backed by machine certificates in this directory — nothing here is an unverified claim." % (self.now, self.rid, (self.st.get("seed") or {}).get("run_id")), "",''',
'''        x = fa["rec"]; cb = json.load(open(os.path.join(fa["dir"], "cnc_" + fa["tag"], "bundle.json"))); sm = json.load(open(os.path.join(fa["dir"], "l3", "summary.json")))
        smf_p = os.path.join(fa["vdir"], "l3_final", "summary.json"); smf = json.load(open(smf_p)) if os.path.exists(smf_p) else {}
        lr = vres.get("leaf_reverify") or {}; ar = vres.get("audit_reverify") or {}
        G2n, G2m, G3n, G3m = sm["G2p"]["n"], sm["G2p"]["m"], sm["G3p"]["n"], sm["G3p"]["m"]
        rec = self.rec_ok; vok = self.vok
        L = ["# FINAL_README.md — Phase 3c final certified graph (staging for v1.1; **NOT released**)" if vok else "# FINAL_README.md — Phase 3c final graph — **INDEPENDENT RE-VERIFICATION FAILED, EVIDENCE ONLY** (see VERIFY_FAILED.md)", "",
             ("Archived %s by `scripts/phase3c/finalize3c.py` (run `%s`, seeded from Phase 3b run `%s`). Author of the project: King Tat Wong (Amber); all statements below are backed by machine certificates in this directory and were re-verified from the files on disk at archive time (`L1pp/verify_final.json`, all_ok = true) — nothing here is an unverified claim." if vok else
              "Archived %s by `scripts/phase3c/finalize3c.py` (run `%s`, seeded from Phase 3b run `%s`). **WARNING: the independent re-verification from the files on disk did NOT pass (`L1pp/verify_final.json`, all_ok = false; details in VERIFY_FAILED.md). The statements below describe what the campaign recorded; they must NOT be relied on until `bash reverify.sh` passes.**") % (self.now, self.rid, (self.st.get("seed") or {}).get("run_id")), "",'''))
F.append(('''             "* **Certified statement: G3′ has no proper 4-colouring** (χ(G3′) = 5). %s" % ("**|V(G3′)| = %d < 1441 — record candidate (see RECORD_CANDIDATE.md).**" % G3n if rec else "|V(G3′)| = %d ≥ 1441 — not a record; the campaign stopped because: %s" % (G3n, self.st.get("stop_reason"))),''',
'''             ("* **Certified statement: G3′ has no proper 4-colouring** (χ(G3′) = 5). %s" if vok else "* Campaign claim (NOT independently confirmed, see VERIFY_FAILED.md): G3′ has no proper 4-colouring. %s") % (
                 ("**|V(G3′)| = %d < 1441 — record candidate (see RECORD_CANDIDATE.md).**" % G3n) if rec else (("|V(G3′)| = %d < 1441 but RECORD CANDIDATE BLOCKED (re-verification failed, see RECORD_CANDIDATE_BLOCKED.md)." % G3n) if self.st.get("record_candidate") else "|V(G3′)| = %d ≥ 1441 — not a record; the campaign stopped because: %s" % (G3n, self.st.get("stop_reason")))),'''))
F.append(('''`L1pp/leaf_proofs/audit/` (5 %% of the leaves re-solved from scratch), `L1pp/LEAF_INDEX.json` | each leaf''',
'''`L1pp/leaf_proofs/audit/` (%s), `L1pp/LEAF_INDEX.json` | each leaf'''))
F.append(('''                 cb["base_sha"], cb["n_cubes0"], fa["tag"], ("%d files, kissat binary DRAT, all re-verified: %s/%s" % (lr.get("n", 0), lr.get("ok"), lr.get("n"))) if fa["has_keep"] else "NOT on disk — see LEAF_PROOFS_NOT_ON_DISK.txt", fa["tag"], "all_ok=%s" % vres.get("all_ok")),''',
'''                 cb["base_sha"], cb["n_cubes0"], fa["tag"], ("%d files, kissat binary DRAT, re-verified from disk: %s/%s VERIFIED" % (lr.get("n", 0), lr.get("ok"), lr.get("n"))) if fa["has_keep"] else "NOT on disk — see LEAF_PROOFS_NOT_ON_DISK.txt", fa["tag"],
                 ("%s/%s of the 5 %% from-scratch audit proofs on disk%s" % (ar.get("kept_files"), ar.get("bundle_audit_n"), "" if ar.get("complete") else " — INCOMPLETE (audit record itself is in cnc_%s/bundle.json)" % fa["tag"])) if fa["has_keep"] else "audit record only (cnc_%s/bundle.json)" % fa["tag"], "all_ok=%s" % vres.get("all_ok")),'''))
F.append(('''        sm = json.load(open(os.path.join(fa["dir"], "l3", "summary.json"))); smf_p = os.path.join(fa["dir"], "l3_final", "summary.json"); smf = json.load(open(smf_p)) if os.path.exists(smf_p) else sm
        cb = json.load(open(os.path.join(fa["dir"], "cnc_" + fa["tag"], "bundle.json")))
        G2n, G2m, G3n, G3m = smf["G2p"]["n"], smf["G2p"]["m"], smf["G3p"]["n"], smf["G3p"]["m"]
        shas = {"L1pp/base.cnf": cb["base_sha"], "L1pp/cnc_%s/cover_%s.drat" % (fa["tag"], cb["cover_mode"]): cb["cover"][cb["cover_mode"]]["proof_sha"], "L1pp/cnc_%s/bundle.json" % fa["tag"]: sha(os.path.join(fa["dir"], "cnc_" + fa["tag"], "bundle.json"))}
        for f in ("G2p.cvtx", "G2p.edge", "G3p.cvtx", "G3p.edge", "L3pp.cnf", "L3pp.drat"):
            p = os.path.join(fa["dir"], "l3_final", f)
            if os.path.exists(p):
                shas["L2L3/l3_final/" + f] = sha(p)
        for f in glob.glob(os.path.join(fa["dir"], "l3_final", "spindle_B", "*")):''',
'''        assert self.rec_ok, "write_record_candidate 只可以喺獨立重驗通過之後叫"
        sm = json.load(open(os.path.join(fa["dir"], "l3", "summary.json"))); smf_p = os.path.join(fa["vdir"], "l3_final", "summary.json"); smf = json.load(open(smf_p)) if os.path.exists(smf_p) else sm
        cb = json.load(open(os.path.join(fa["dir"], "cnc_" + fa["tag"], "bundle.json")))
        G2n, G2m, G3n, G3m = smf["G2p"]["n"], smf["G2p"]["m"], smf["G3p"]["n"], smf["G3p"]["m"]
        shas = {"L1pp/base.cnf": cb["base_sha"], "L1pp/cnc_%s/cover_%s.drat" % (fa["tag"], cb["cover_mode"]): cb["cover"][cb["cover_mode"]]["proof_sha"], "L1pp/cnc_%s/bundle.json" % fa["tag"]: sha(os.path.join(fa["dir"], "cnc_" + fa["tag"], "bundle.json"))}
        for f in ("G2p.cvtx", "G2p.edge", "G3p.cvtx", "G3p.edge", "L3pp.cnf", "L3pp.drat"):
            p = os.path.join(fa["vdir"], "l3_final", f)
            if os.path.exists(p):
                shas["L2L3/l3_final/" + f] = sha(p)
        for f in glob.glob(os.path.join(fa["vdir"], "l3_final", "spindle_B", "*")):'''))
F.append(('''"# single pieces:", "/home/user/hadwiger/drat-trim/drat-trim L1pp/cnc_%s/cover_pure.cnf L1pp/cnc_%s/cover_pure.drat" % (fa["tag"], fa["tag"]),''',
'''"# single pieces:", "/home/user/hadwiger/drat-trim/drat-trim L1pp/cnc_%s/cover_%s.cnf L1pp/cnc_%s/cover_%s.drat" % (fa["tag"], cb["cover_mode"], fa["tag"], cb["cover_mode"]),'''))
# report
F.append(('''        cert_own = [(r, x) for r in own for x in r["attempts"] if x.get("status") == "certified"]
        sm_p = os.path.join(fa["dir"], "l3_final", "summary.json"); sm = json.load(open(sm_p)) if os.path.exists(sm_p) else json.load(open(os.path.join(fa["dir"], "l3", "summary.json")))
        G2n, G2m, G3n, G3m = sm["G2p"]["n"], sm["G2p"]["m"], sm["G3p"]["n"], sm["G3p"]["m"]
        lr = vres.get("leaf_reverify") or {}
        L = ["# phase3c_results.md''',
'''        cert_own = [(r, x) for r in own for x in r["attempts"] if x.get("status") == "certified"]
        sm_p = os.path.join(fa["vdir"], "l3_final", "summary.json"); sm = json.load(open(sm_p)) if os.path.exists(sm_p) else json.load(open(os.path.join(fa["dir"], "l3", "summary.json")))
        G2n, G2m, G3n, G3m = sm["G2p"]["n"], sm["G2p"]["m"], sm["G3p"]["n"], sm["G3p"]["m"]
        lr = vres.get("leaf_reverify") or {}
        L = ["# phase3c_results.md'''))
F.append(('''             ("**RECORD_CANDIDATE: |G₃′| = %d < 1441** (%d 點 %d 邊, 無 spindle 兩引擎, 唔可 4 色 —— 全部機器證書 + 獨立重驗 all_ok=%s); 已封存 `%s`; **未公開 / 未寄信 / 未 push, 等 Amber**. 詳見 `RECORD_CANDIDATE.md`." % (G3n, G3n, G3m, vres.get("all_ok"), FINAL_D)) if st.get("record_candidate") else
             ("**未到 1441**: 最終認證圖 |G₂′| = %d (%d 邊), |G₃′| = %d (%d 邊), S_acc = %d 粒; 停機原因: %s. 最終圖全套證書 + 獨立重驗 (all_ok=%s) 封存 `%s`." % (G2n, G2m, G3n, G3m, len(st["S_acc"]), st.get("stop_reason"), vres.get("all_ok"), FINAL_D)), "",''',
'''             ("**RECORD_CANDIDATE: |G₃′| = %d < 1441** (%d 點 %d 邊, 無 spindle 兩引擎, 唔可 4 色 —— 全部機器證書 + 獨立重驗 all_ok=%s); 已封存 `%s`; **未公開 / 未寄信 / 未 push, 等 Amber**. 詳見 `RECORD_CANDIDATE.md`." % (G3n, G3n, G3m, vres.get("all_ok"), FINAL_D)) if self.rec_ok else
             (("**!! 候選但獨立重驗唔過**: probe3c 到咗 |G₃′| = %d < 1441 (%d 邊), 但 finalize 由碟上檔案重驗 all_ok=%s (%s) —— **唔算紀錄候選**, 封存只係證據 (`%s`, VERIFY_FAILED.md / RECORD_CANDIDATE_BLOCKED.md); 要人手睇." % (G3n, G3m, vres.get("all_ok"), (vres.get("error") or "見 verify_final.json")[:200], FINAL_D)) if st.get("record_candidate") else
              ("**未到 1441**: 最終認證圖 |G₂′| = %d (%d 邊), |G₃′| = %d (%d 邊), S_acc = %d 粒; 停機原因: %s. 最終圖全套證書 + 獨立重驗 (all_ok=%s%s) 封存 `%s`." % (G2n, G2m, G3n, G3m, len(st["S_acc"]), st.get("stop_reason"), vres.get("all_ok"), "" if self.vok else " **!! 重驗唔過, 見 VERIFY_FAILED.md**", FINAL_D))), "",'''))
F.append(('''              "- |G₂′| = **%d** 點 **%d** 邊; |G₃′| = 2|G₂′| − 1 = **%d** 點 **%d** 邊; %s." % (G2n, G2m, G3n, G3m, "**< 1441 ✓ RECORD_CANDIDATE**" if G3n < 1441 else "≥ 1441 (未到目標 720 / 1441)"),''',
'''              "- |G₂′| = **%d** 點 **%d** 邊; |G₃′| = 2|G₂′| − 1 = **%d** 點 **%d** 邊; %s." % (G2n, G2m, G3n, G3m, ("**< 1441 ✓ RECORD_CANDIDATE (獨立重驗通過)**" if self.rec_ok else "< 1441 但重驗唔過 (BLOCKED)") if G3n < 1441 else "≥ 1441 (未到目標 720 / 1441)"),'''))
F.append(('''                  arch.get("final_dir"), arch.get("n_files"), (arch.get("bytes") or 0) / 1e9, (arch.get("sha256sums_sha256") or "")[:16], arch.get("check_rc"), fa["tag"], lr.get("n") if fa["has_keep"] else "0 (seed, 唔喺碟上)", ", `RECORD_CANDIDATE.md`" if st.get("record_candidate") else ""),''',
'''                  arch.get("final_dir"), arch.get("n_files"), (arch.get("bytes") or 0) / 1e9, (arch.get("sha256sums_sha256") or "")[:16], arch.get("check_rc"), fa["tag"], lr.get("n") if fa["has_keep"] else "0 (seed, 唔喺碟上)", (", `RECORD_CANDIDATE.md`" if self.rec_ok else (", `RECORD_CANDIDATE_BLOCKED.md`" if st.get("record_candidate") else "")) + ("" if self.vok else ", `VERIFY_FAILED.md`")),'''))
# facts
F.append(('''            sm_p = os.path.join(fa["dir"], "l3_final", "summary.json"); sm = json.load(open(sm_p)) if os.path.exists(sm_p) else json.load(open(os.path.join(fa["dir"], "l3", "summary.json")))
            add("g2shrink3c.G2p_final",''',
'''            sm_p = os.path.join(fa["vdir"], "l3_final", "summary.json"); sm = json.load(open(sm_p)) if os.path.exists(sm_p) else json.load(open(os.path.join(fa["dir"], "l3", "summary.json")))
            add("g2shrink3c.G2p_final",'''))
F.append(('''            add("g2shrink3c.record_candidate", bool(st.get("record_candidate")), None, "phase3c/runs/%s/state.json" % self.rid)''',
'''            add("g2shrink3c.record_candidate", self.rec_ok, None, "phase3c/runs/%s/state.json (probe3c record_candidate=%s) AND finalize independent re-verification all_ok=%s" % (self.rid, bool(st.get("record_candidate")), self.vok), "true only when |G3'| < 1441 AND verify_final passed", verified=bool(self.vok))
            add("g2shrink3c.verify_failed", not self.vok, None, "final/L1pp/verify_final.json")'''))
F.append(('''            F["generated"] = time.strftime("%Y-%m-%d %H:%M:%S"); F["note"] = (F.get("note") or "") + " | Phase 3c additions (g2shrink3c.*) by phase3c/finalize3c.py."
            json.dump(F, open(fp_out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)''',
'''            F["generated"] = time.strftime("%Y-%m-%d %H:%M:%S")
            if "Phase 3c additions (g2shrink3c.*)" not in (F.get("note") or ""):
                F["note"] = (F.get("note") or "") + " | Phase 3c additions (g2shrink3c.*) by phase3c/finalize3c.py."
            write(fp_out, json.dumps(F, indent=1, ensure_ascii=False))                                # 審查 #25: 先序列化再原子寫'''))
# decision
F.append(('''            sm_p = os.path.join(fa["dir"], "l3_final", "summary.json"); sm = json.load(open(sm_p)) if os.path.exists(sm_p) else json.load(open(os.path.join(fa["dir"], "l3", "summary.json")))
            own = [r for r in self.rounds if not r.get("from_run")]
            para = (''',
'''            sm_p = os.path.join(fa["vdir"], "l3_final", "summary.json"); sm = json.load(open(sm_p)) if os.path.exists(sm_p) else json.load(open(os.path.join(fa["dir"], "l3", "summary.json")))
            own = [r for r in self.rounds if not r.get("from_run")]
            para = ('''))
F.append(('''                        "**RECORD_CANDIDATE(|G₃′| < 1441)—— 等 Amber 決定**" if st.get("record_candidate") else "未到 1441", sm["G2p"]["n"], sm["G2p"]["m"], sm["G3p"]["n"], sm["G3p"]["m"], vres.get("all_ok"),
                        st.get("cpu_h_used") or 0, (st.get("elapsed_s") or 0) / 3600, st.get("stop_reason"), arch.get("final_dir")))
            if marker in s:
                s = re.sub(r"\\*\\*Phase 3c G₂ 續剪結果.*?(?=\\n\\n)", para, s, count=1, flags=re.S)''',
'''                        "**RECORD_CANDIDATE(|G₃′| < 1441,獨立重驗通過)—— 等 Amber 決定**" if self.rec_ok else ("**!! 到咗 < 1441 但獨立重驗唔過(BLOCKED,要人手睇 VERIFY_FAILED.md)**" if st.get("record_candidate") else ("未到 1441" + ("" if self.vok else "(**獨立重驗唔過**,見 VERIFY_FAILED.md)"))), sm["G2p"]["n"], sm["G2p"]["m"], sm["G3p"]["n"], sm["G3p"]["m"], vres.get("all_ok"),
                        st.get("cpu_h_used") or 0, (st.get("elapsed_s") or 0) / 3600, (st.get("stop_reason") or "").replace("\\n", " "), arch.get("final_dir")))
            if marker in s:
                s = re.sub(r"\\*\\*Phase 3c G₂ 續剪結果.*?(?=\\n\\n)", lambda m: para, s, count=1, flags=re.S)        # 審查 #21: lambda 免 template escape'''))
F.append(('''            if not self.a.dry_run:
                open(p, "w", encoding="utf-8", newline="\\n").write(s)
            else:
                write(os.path.join(PH3C, "DECISION_dryrun.md"), s)''',
'''            if not self.a.dry_run:
                write(p, s)
            else:
                write(os.path.join(PH3C, "DECISION_dryrun.md"), s)'''))
# memory
F.append(('''            sm_p = os.path.join(fa["dir"], "l3_final", "summary.json"); sm = json.load(open(sm_p)) if os.path.exists(sm_p) else json.load(open(os.path.join(fa["dir"], "l3", "summary.json")))
            G2n, G3n = sm["G2p"]["n"], sm["G3p"]["n"]''',
'''            sm_p = os.path.join(fa["vdir"], "l3_final", "summary.json"); sm = json.load(open(sm_p)) if os.path.exists(sm_p) else json.load(open(os.path.join(fa["dir"], "l3", "summary.json")))
            G2n, G3n = sm["G2p"]["n"], sm["G3p"]["n"]; vtag = "" if self.vok else " **!! 獨立重驗唔過 (VERIFY_FAILED.md)**"'''))
F.append(('''                " **RECORD_CANDIDATE (<1441), 等 Amber**" if st.get("record_candidate") else " (未到 1441)", st.get("cpu_h_used") or 0, (st.get("elapsed_s") or 0) / 3600, (st.get("stop_reason") or "")[:120].replace("\\n", " "))''',
'''                (" **RECORD_CANDIDATE (<1441, 獨立重驗通過), 等 Amber**" if self.rec_ok else (" **<1441 但獨立重驗唔過, BLOCKED**" if st.get("record_candidate") else " (未到 1441)")) + vtag, st.get("cpu_h_used") or 0, (st.get("elapsed_s") or 0) / 3600, (st.get("stop_reason") or "")[:120].replace("\\n", " "))'''))
F.append(('''            if "**Phase 3c(" in s:
                s = re.sub(r"\\*\\*Phase 3c\\(.*?(?=\\n\\n\\*\\*How to apply)", block, s, count=1, flags=re.S)''',
'''            if "**Phase 3c(" in s:
                s = re.sub(r"\\*\\*Phase 3c\\(.*?(?=\\n\\n\\*\\*How to apply)", lambda m: block, s, count=1, flags=re.S)'''))
F.append(('''            if not self.a.dry_run:
                open(p, "w", encoding="utf-8", newline="\\n").write(s)
            else:
                write(os.path.join(PH3C, "mem_dryrun_hadwiger-project.md"), s)''',
'''            if not self.a.dry_run:
                write(p, s)
            else:
                write(os.path.join(PH3C, "mem_dryrun_hadwiger-project.md"), s)'''))
F.append(('''                ("|G₃′| = %d < 1441 紀錄候選,G₂ 方向嘅 346 粒目標達成" % G3n) if st.get("record_candidate") else ("|G₃′| = %d,停於 %s" % (G3n, (st.get("stop_reason") or "")[:100])))
            if "**Phase 3c(" in s2:
                s2 = re.sub(r"\\*\\*Phase 3c\\(.*?(?=\\n\\n\\*\\*Why)", b2, s2, count=1, flags=re.S)''',
'''                ("|G₃′| = %d < 1441 紀錄候選 (獨立重驗通過),G₂ 方向嘅 346 粒目標達成" % G3n) if self.rec_ok else (("|G₃′| = %d < 1441 但獨立重驗唔過 (BLOCKED)" % G3n) if st.get("record_candidate") else ("|G₃′| = %d,停於 %s" % (G3n, (st.get("stop_reason") or "")[:100]))))
            if "**Phase 3c(" in s2:
                s2 = re.sub(r"\\*\\*Phase 3c\\(.*?(?=\\n\\n\\*\\*Why)", lambda m: b2, s2, count=1, flags=re.S)'''))
F.append(('''            if not self.a.dry_run:
                open(p2, "w", encoding="utf-8", newline="\\n").write(s2)
            else:
                write(os.path.join(PH3C, "mem_dryrun_no-spindle-hardness.md"), s2)''',
'''            if not self.a.dry_run:
                write(p2, s2)
            else:
                write(os.path.join(PH3C, "mem_dryrun_no-spindle-hardness.md"), s2)'''))
F.append(('''                    lines[i] = head + ";Phase 3b 三輪 certified |G₃′| 1951(`phase3b/phase3b_results.md`);**Phase 3c 完(%s)**:%s;%s" % (self.now[:16], ("**RECORD_CANDIDATE |G₃′| = %d < 1441,等 Amber**" % G3n) if st.get("record_candidate") else "|G₃′| %d,停 %s" % (G3n, (st.get("stop_reason") or "")[:60]), "報告 `phase3c/phase3c_results.md`;冇背景任務 (S60_full 補封存見報告)")''',
'''                    lines[i] = head + ";Phase 3b 三輪 certified |G₃′| 1951(`phase3b/phase3b_results.md`);**Phase 3c 完(%s)**:%s;%s" % (self.now[:16], (("**RECORD_CANDIDATE |G₃′| = %d < 1441,獨立重驗通過,等 Amber**" % G3n) if self.rec_ok else (("**<1441 但重驗唔過 BLOCKED**" if st.get("record_candidate") else "|G₃′| %d,停 %s" % (G3n, (st.get("stop_reason") or "")[:60])) + vtag)).replace("\\n", " "), "報告 `phase3c/phase3c_results.md`;冇背景任務 (S60_full 補封存見報告)")'''))
F.append(('''            if not self.a.dry_run:
                open(p3, "w", encoding="utf-8", newline="\\n").write(s3)
            else:
                write(os.path.join(PH3C, "mem_dryrun_MEMORY.md"), s3)''',
'''            if not self.a.dry_run:
                write(p3, s3)
            else:
                write(os.path.join(PH3C, "mem_dryrun_MEMORY.md"), s3)'''))
# append_s60
F.append(('''            if not self.a.dry_run:
                json.dump(F, open(fp, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
            self.save(s60_full=''',
'''            if not self.a.dry_run:
                write(fp, json.dumps(F, indent=1, ensure_ascii=False))
            self.save(s60_full='''))
F.append(('''            if "S60_full 補封存:" in s:
                s = re.sub(r"S60_full 補封存: .*?\\)\\.", note, s, count=1, flags=re.S)
            elif "\\n\\n**How to apply:**" in s:
                s = s.replace("\\n\\n**How to apply:**", " " + note + "\\n\\n**How to apply:**", 1)
            if not self.a.dry_run:
                open(p, "w", encoding="utf-8", newline="\\n").write(s)''',
'''            if "S60_full 補封存:" in s:
                s = re.sub(r"S60_full 補封存: .*?\\)\\.", lambda m: note, s, count=1, flags=re.S)
            elif "\\n\\n**How to apply:**" in s:
                s = s.replace("\\n\\n**How to apply:**", " " + note + "\\n\\n**How to apply:**", 1)
            if not self.a.dry_run:
                write(p, s)'''))
F.append(('''        self.save(all_done=True, finished=time.strftime("%Y-%m-%d %H:%M:%S"))
        log("S60 append done")''',
'''        self.save(all_done=True, s60_finished=time.strftime("%Y-%m-%d %H:%M:%S"))
        log("S60 append done")'''))
F.append(('''        log("FINALIZE3C DONE: verify all_ok=%s, archive %s, record_candidate=%s" % (vres.get("all_ok"), arch.get("final_dir"), self.st.get("record_candidate")))''',
'''        log("FINALIZE3C DONE: verify all_ok=%s (vok=%s), archive %s, probe record_candidate=%s, confirmed=%s" % (vres.get("all_ok"), self.vok, arch.get("final_dir"), self.st.get("record_candidate"), self.rec_ok))
        if not self.vok:
            sys.exit(4)'''))
patch("finalize3c.py", F)

# ======================= verify_final.py =======================
V = []
V.append(('''    ap.add_argument("--workers", type=int, default=14); ap.add_argument("--skip-l3", action="store_true"); ap.add_argument("--tmp", default=None)
    a = ap.parse_args()
    d = os.path.abspath(os.path.expanduser(a.attempt_dir)); tag = a.tag; cdir = os.path.join(d, "cnc_" + tag); keep = os.path.abspath(os.path.expanduser(a.keep_dir))''',
'''    ap.add_argument("--workers", type=int, default=14); ap.add_argument("--skip-l3", action="store_true"); ap.add_argument("--tmp", default=None)
    ap.add_argument("--json-out", default=None, help="結果 JSON 路徑 (預設 <attempt-dir>/verify_final.json); reverify.sh 用嚟避免覆寫已封存嘅檔")
    a = ap.parse_args()
    d = os.path.abspath(os.path.expanduser(a.attempt_dir)); tag = a.tag; cdir = os.path.join(d, "cnc_" + tag); keep = os.path.abspath(os.path.expanduser(a.keep_dir))
    out_json = os.path.abspath(os.path.expanduser(a.json_out)) if a.json_out else os.path.join(d, "verify_final.json")
    def dump(res_):
        tmp_ = out_json + ".tmp"; json.dump(res_, open(tmp_, "w"), indent=1, ensure_ascii=False); os.replace(tmp_, out_json)'''))
V.append(('''    r = {"mode": cm, "cnf": ccnf, "drat": cdrat, "cnf_sha_match": sha(ccnf) == cov["cnf_sha"], "drat_sha_match": sha(cdrat) == cov["proof_sha"]}
    # cover cnf 要係 leaf cube 嘅否定 (純模式) —— 重建對數
    if cm == "pure":
        neg = sorted(tuple(-l for l in done[i]["cube"]) for i in ids)
        got = sorted(tuple(int(x) for x in l.split()[:-1]) for l in open(ccnf) if not l.startswith(("p", "c")))
        r["cover_clauses_match_negated_leaves"] = (neg == got)
    t0 = time.time(); dr = subprocess.run([DRATTRIM, ccnf, cdrat], capture_output=True, text=True, timeout=6 * 3600)
    r["verified"] = any(l.strip() == "s VERIFIED" for l in dr.stdout.splitlines()); r["verify_s"] = round(time.time() - t0, 1)
    r["ok"] = bool(r["cnf_sha_match"] and r["drat_sha_match"] and r["verified"] and (r.get("cover_clauses_match_negated_leaves", True)))''',
'''    r = {"mode": cm, "cnf": ccnf, "drat": cdrat, "cnf_sha_match": sha(ccnf) == cov["cnf_sha"], "drat_sha_match": sha(cdrat) == cov["proof_sha"]}
    # cover cnf 要係 leaf cube 嘅否定 (pure) 或 base 子句 + 否定 (with_base) —— 由 state.json done 重建對數; 未知 mode 即唔過 (審查 #4)
    neg = [tuple(-l for l in done[i]["cube"]) for i in ids]
    got = sorted(tuple(int(x) for x in l.split()[:-1]) for l in open(ccnf) if not l.startswith(("p", "c")))
    if cm == "pure":
        want = sorted(neg)
    elif cm == "with_base":
        want = sorted([tuple(int(x) for x in l.split()[:-1]) for l in lines] + neg)
    else:
        want = None
    r["cover_clauses_match_negated_leaves"] = (want is not None and want == got)
    try:
        r["cover_header_nvars_ok"] = (int(open(ccnf).readline().split()[2]) == nvars)
    except Exception:
        r["cover_header_nvars_ok"] = False
    t0 = time.time(); dr = subprocess.run([DRATTRIM, ccnf, cdrat], capture_output=True, text=True, timeout=6 * 3600)
    r["verified"] = any(l.strip() == "s VERIFIED" for l in dr.stdout.splitlines()); r["verify_s"] = round(time.time() - t0, 1)
    r["ok"] = bool(r["cnf_sha_match"] and r["drat_sha_match"] and r["verified"] and r["cover_clauses_match_negated_leaves"] and r["cover_header_nvars_ok"])'''))
V.append(('''    log("cover (%s) 重驗: drat-trim %s, cnf sha %s, drat sha %s, 子句 == ¬leaf %s" % (cm, "VERIFIED ✓" if r["verified"] else "!! NOT", r["cnf_sha_match"], r["drat_sha_match"], r.get("cover_clauses_match_negated_leaves")))''',
'''    log("cover (%s) 重驗: drat-trim %s, cnf sha %s, drat sha %s, 子句 == (base+)¬leaf %s, header nvars %s" % (cm, "VERIFIED ✓" if r["verified"] else "!! NOT", r["cnf_sha_match"], r["drat_sha_match"], r.get("cover_clauses_match_negated_leaves"), r.get("cover_header_nvars_ok")))'''))
V.append(('''    aud = cb.get("audit", {}); akeep = os.path.join(keep, "audit"); arecs = []
    if os.path.isdir(akeep):
        afiles = sorted(f for f in os.listdir(akeep) if f.endswith(".drat"))
        def one_a(f):
            cid = f[len("cnc_%s_audit_" % tag):-5]; dd = done.get(cid); rr = {"id": cid, "file": f}
            cnf = os.path.join(tmp, "audit_%s.cnf" % cid)
            try:
                if not dd:
                    rr["ok"] = False; rr["error"] = "id 唔喺 done"; return rr
                with open(cnf, "w") as fh:
                    fh.write("p cnf %d %d\\n" % (nvars, nbase + len(dd["cube"]))); fh.write(base_text)
                    for l in dd["cube"]:
                        fh.write("%d 0\\n" % l)
                dr = subprocess.run([DRATTRIM, cnf, os.path.join(akeep, f)], capture_output=True, text=True, timeout=6 * 3600)
                rr["verified"] = any(l.strip() == "s VERIFIED" for l in dr.stdout.splitlines()); rr["ok"] = rr["verified"]
            except Exception as e:
                rr["ok"] = False; rr["error"] = repr(e)[-200:]
            finally:
                if os.path.exists(cnf):
                    os.remove(cnf)
            return rr
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            arecs = list(ex.map(one_a, afiles))
    res["audit_reverify"] = {"bundle_audit_n": aud.get("n"), "bundle_all_ok": aud.get("all_ok"), "kept_files": len(arecs), "ok": sum(1 for x in arecs if x["ok"]), "bad": [x for x in arecs if not x["ok"]][:20]}
    log("審計證明重驗: bundle 5%% 審計 %s/%s ok; keep/audit %d 檔, %d VERIFIED" % (aud.get("n"), aud.get("n"), len(arecs), res["audit_reverify"]["ok"]))''',
'''    aud = cb.get("audit", {}); akeep = os.path.join(keep, "audit"); arecs = []
    arec_by_id = {x["id"]: x for x in (st.get("audit") or [])}                      # cnc2k 審計記錄 (有 kept 就有 proof_sha)
    if os.path.isdir(akeep):
        afiles = sorted(f for f in os.listdir(akeep) if f.endswith(".drat"))
        def one_a(f):
            cid = f[len("cnc_%s_audit_" % tag):-5]; dd = done.get(cid); rr = {"id": cid, "file": f}
            cnf = os.path.join(tmp, "audit_%s.cnf" % cid)
            try:
                if not dd:
                    rr["ok"] = False; rr["error"] = "id 唔喺 done"; return rr
                with open(cnf, "w") as fh:
                    fh.write("p cnf %d %d\\n" % (nvars, nbase + len(dd["cube"]))); fh.write(base_text)
                    for l in dd["cube"]:
                        fh.write("%d 0\\n" % l)
                want = (arec_by_id.get(cid) or {}).get("proof_sha")
                rr["sha_match"] = (sha(os.path.join(akeep, f)) == want) if want else None
                dr = subprocess.run([DRATTRIM, cnf, os.path.join(akeep, f)], capture_output=True, text=True, timeout=6 * 3600)
                rr["verified"] = any(l.strip() == "s VERIFIED" for l in dr.stdout.splitlines()); rr["ok"] = bool(rr["verified"] and rr["sha_match"] is not False)
            except Exception as e:
                rr["ok"] = False; rr["error"] = repr(e)[-200:]
            finally:
                if os.path.exists(cnf):
                    os.remove(cnf)
            return rr
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            arecs = list(ex.map(one_a, afiles))
    a_ids = sorted(x["id"] for x in arecs); want_ids = sorted(aud.get("ids") or [])
    res["audit_reverify"] = {"bundle_audit_n": aud.get("n"), "bundle_all_ok": aud.get("all_ok"), "kept_files": len(arecs), "ok": sum(1 for x in arecs if x["ok"]), "bad": [x for x in arecs if not x["ok"]][:20],
                             "complete": (a_ids == want_ids and len(a_ids) == (aud.get("n") or 0) and len(a_ids) > 0), "n_missing": len(set(want_ids) - set(a_ids)), "missing_ids": sorted(set(want_ids) - set(a_ids))[:50]}   # 審查 #8/#23
    log("審計證明重驗: bundle 5%% 審計 %s/%s ok; keep/audit %d 檔, %d VERIFIED; 完整 %s (缺 %d)" % (aud.get("n"), aud.get("n"), len(arecs), res["audit_reverify"]["ok"], res["audit_reverify"]["complete"], res["audit_reverify"]["n_missing"]))
    res["partial"] = True; dump(res)                                                  # l3 之前先落地 (免 l3g2 crash 失去 1 h leaf 重驗結果)'''))
V.append(('''    ok = bool(res["base_sha_consistent"] and res["leaf_count_consistent"] and res.get("leaf_ids_are_all_root_cubes", True) and not bad and res["cover_reverify"]["ok"]
              and res["audit_reverify"]["bad"] == [] and (a.skip_l3 or (res["l3_final"]["rc"] == 0 and res["l3_final"]["all_ok"] is True and all(res["l3_final"]["same_files_as_campaign_l3"].values()) and res["exactfield_complete_G3p_again"]["rc"] == 0)))
    res["all_ok"] = ok; res["t_s"] = round(time.time() - T0, 1)
    json.dump(res, open(os.path.join(d, "verify_final.json"), "w"), indent=1, ensure_ascii=False)
    log("verify_final %s: %s (%.0f s) → %s" % (tag, "全部通過 ✓" if ok else "!! 有步驟唔過", res["t_s"], os.path.join(d, "verify_final.json")))''',
'''    ok = bool(res["base_sha_consistent"] and res["leaf_count_consistent"] and res.get("leaf_ids_are_all_root_cubes", True) and not bad and res["cover_reverify"]["ok"]
              and res["audit_reverify"]["bad"] == [] and res["audit_reverify"]["complete"]
              and (a.skip_l3 or (res["l3_final"]["rc"] == 0 and res["l3_final"]["all_ok"] is True and all(res["l3_final"]["same_files_as_campaign_l3"].values()) and res["exactfield_complete_G3p_again"]["rc"] == 0)))
    res["all_ok"] = ok; res["t_s"] = round(time.time() - T0, 1); res["partial"] = False
    dump(res)
    log("verify_final %s: %s (%.0f s) → %s" % (tag, "全部通過 ✓" if ok else "!! 有步驟唔過", res["t_s"], out_json))'''))
V.append(('''        l3f = os.path.join(d, "l3_final"); t0 = time.time()
        rl = subprocess.run([PY, os.path.join(PH3B, "l3g2.py"), "--remove", ",".join(map(str, bj["removed"])), "--out", l3f, "--engine-b"], capture_output=True, text=True, timeout=5 * 3600)
        open(os.path.join(d, "l3_final.log"), "w").write(rl.stdout + rl.stderr)
        sm = json.load(open(os.path.join(l3f, "summary.json"))) if os.path.exists(os.path.join(l3f, "summary.json")) else {}
        old = os.path.join(d, "l3")
        same = {f: (os.path.exists(os.path.join(old, f)) and sha(os.path.join(old, f)) == sha(os.path.join(l3f, f))) for f in ("G2p.cvtx", "G2p.edge", "G3p.cvtx", "G3p.edge", "L3pp.cnf")}''',
'''        l3f = os.path.join(d, "l3_final"); t0 = time.time()
        rl = subprocess.run([PY, os.path.join(PH3B, "l3g2.py"), "--remove", ",".join(map(str, bj["removed"])), "--out", l3f, "--engine-b"], capture_output=True, text=True, timeout=5 * 3600)
        open(os.path.join(d, "l3_final.log"), "w").write(rl.stdout + rl.stderr)
        sm = json.load(open(os.path.join(l3f, "summary.json"))) if os.path.exists(os.path.join(l3f, "summary.json")) else {}
        old = os.path.join(d, "l3")
        same = {f: (os.path.exists(os.path.join(old, f)) and os.path.exists(os.path.join(l3f, f)) and sha(os.path.join(old, f)) == sha(os.path.join(l3f, f))) for f in ("G2p.cvtx", "G2p.edge", "G3p.cvtx", "G3p.edge", "L3pp.cnf")}'''))
V.append(('''        t0 = time.time(); re_ = subprocess.run([PY, os.path.join(PH2, "exactfield.py"), "check", os.path.join(l3f, "G3p.cvtx"), os.path.join(l3f, "G3p.edge"), "--complete"], capture_output=True, text=True, timeout=3600)
        res["exactfield_complete_G3p_again"] = {"rc": re_.returncode, "last": (re_.stdout.strip().split("\\n")[-1] if re_.stdout.strip() else "")[:300], "s": round(time.time() - t0, 1)}''',
'''        t0 = time.time()
        if os.path.exists(os.path.join(l3f, "G3p.cvtx")) and os.path.exists(os.path.join(l3f, "G3p.edge")):
            re_ = subprocess.run([PY, os.path.join(PH2, "exactfield.py"), "check", os.path.join(l3f, "G3p.cvtx"), os.path.join(l3f, "G3p.edge"), "--complete"], capture_output=True, text=True, timeout=3600)
            res["exactfield_complete_G3p_again"] = {"rc": re_.returncode, "last": (re_.stdout.strip().split("\\n")[-1] if re_.stdout.strip() else "")[:300], "s": round(time.time() - t0, 1)}
        else:
            res["exactfield_complete_G3p_again"] = {"rc": -1, "last": "l3_final/G3p.* 唔存在 (l3g2 失敗)", "s": 0}'''))
patch("verify_final.py", V)

# ======================= probe3c.py =======================
P = []
P.append(('''            self.st["elapsed_before_s"] = self.st.get("elapsed_s", 0)
            if not self.st.get("target_reached"):
                self.st["stop_reason"] = None                                                    # 已到目標就唔准再縐
            self.st["resumes"] = self.st.get("resumes", 0) + 1; self.st["config_resume"] = vars(a)''',
'''            if self.st.get("needs_operator") and not a.ack_operator:                             # 審查 #16: 操作員停機 (error / cap-hit / l3-failed / keep-incomplete) 唔准自動 resume 重試同一批
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
            self.st["resumes"] = self.st.get("resumes", 0) + 1; self.st["config_resume"] = vars(a)'''))
P.append(('''            self.st = json.load(open(self.state_p)); self.rounds = json.load(open(self.rounds_p)) if os.path.exists(self.rounds_p) else []
            n_before = len(self.rounds)''',
'''            self.st = json.load(open(self.state_p)); self.rounds = json.load(open(self.rounds_p)) if os.path.exists(self.rounds_p) else []
            self.rounds_raw = list(self.rounds); n_before = len(self.rounds)'''))
P.append(('''                       "target_reached": False, "record_candidate": False, "config": vars(a), "seed": seed["prov"], "kept_certified": [], "resumes": 0, "low_net_streak": 0}''',
'''                       "target_reached": False, "record_candidate": False, "config": vars(a), "seed": seed["prov"], "kept_certified": [], "resumes": 0, "low_net_streak": 0, "needs_operator": False, "prior_wall_by_tag": {}}'''))
P.append(('''    def save(self):
        st = self.st; st["elapsed_s"] = round(self.elapsed(), 1); st["updated_str"] = time.strftime("%Y-%m-%d %H:%M:%S")
        st["cpu_h_used"] = self.cpu_h_used(); st["low_net_streak"] = self.low_net_streak()
        json.dump(st, open(self.state_p + ".tmp", "w"), indent=1); os.replace(self.state_p + ".tmp", self.state_p)
        json.dump(self.rounds, open(self.rounds_p + ".tmp", "w"), indent=1); os.replace(self.rounds_p + ".tmp", self.rounds_p)''',
'''    def save(self, light=False):
        st = self.st; st["elapsed_s"] = round(self.elapsed(), 1); st["updated_str"] = time.strftime("%Y-%m-%d %H:%M:%S")
        st["cpu_h_used"] = self.cpu_h_used(); st["low_net_streak"] = self.low_net_streak()
        json.dump(st, open(self.state_p + ".tmp", "w"), indent=1); os.replace(self.state_p + ".tmp", self.state_p)
        if light:                                                                                 # cnc2k 等待期間每 10 分鐘: 只寫 state.json (elapsed_s 保鮮), 唔行 D: 目錄
            return
        json.dump(self.rounds, open(self.rounds_p + ".tmp", "w"), indent=1); os.replace(self.rounds_p + ".tmp", self.rounds_p)'''))
P.append(('''        budget = max(600, cap - (time.time() - t_round))
        logp = os.path.join(d, "cnc.log"); skip = False
        if resumed:
            st_old = json.load(open(os.path.join(cdir, "state.json")))''',
'''        prior = float((self.st.get("prior_wall_by_tag") or {}).get(tag, 0.0))                  # 審查 #5/#14: 上次 process 已花喺呢個 tag 嘅 wall (掉走嘅完成記錄)
        if resumed:
            try:
                prior = max(prior, float(json.load(open(os.path.join(cdir, "state.json"))).get("wall_s") or 0.0))   # cnc2k 自己記嘅累計 wall
            except Exception:
                pass
        rec["prior_wall_s"] = round(prior, 1)
        budget = max(600, cap - prior - (time.time() - t_round))
        logp = os.path.join(d, "cnc.log"); skip = False
        if resumed:
            st_old = json.load(open(os.path.join(cdir, "state.json")))'''))
P.append(('''                p = subprocess.Popen(argv, stdout=lf, stderr=subprocess.STDOUT, start_new_session=True)
                hard = t_round + cap + 900
                while True:
                    try:
                        rc = p.wait(timeout=30); break
                    except subprocess.TimeoutExpired:
                        if time.time() > hard:''',
'''                p = subprocess.Popen(argv, stdout=lf, stderr=subprocess.STDOUT, start_new_session=True)
                hard = t_round + cap + 900 - prior; last_save = time.time()
                while True:
                    try:
                        rc = p.wait(timeout=30); break
                    except subprocess.TimeoutExpired:
                        if time.time() - last_save > 600:
                            self.save(light=True); last_save = time.time()
                        if time.time() > hard:'''))
P.append(('''        rec["wall_s"] = round(time.time() - t_round, 1); rec["cnc_status_json"] = st.get("status")''',
'''        rec["wall_s"] = round(time.time() - t_round + prior, 1); rec["cnc_status_json"] = st.get("status")'''))
P.append(('''            if rec["keep"]["keep_errors"] or rec["keep"]["kept_leaves"] != rec["leaves"]:
                self.cur["stage"] = "keep-repair"; self.save()
                rec["keep_repair"] = self.repair_keep(cdir, keep_dir, st)
                rec["keep"] = {**rec["keep"], **dir_stats(keep_dir), "kept_leaves": rec["keep_repair"]["kept_after"], "repaired": rec["keep_repair"]["repaired"], "repair_failed": rec["keep_repair"]["failed"]}
                if rec["keep_repair"]["failed"]:
                    rec["keep_incomplete"] = True''',
'''            if rec["keep"]["keep_errors"] or rec["keep"]["kept_leaves"] != rec["leaves"] or cb.get("audit_keep_errors") or cb.get("kept_audit") != (cb.get("audit") or {}).get("n"):
                self.cur["stage"] = "keep-repair"; self.save()
                rec["keep_repair"] = repair_keep_dir(cdir, keep_dir, st, a.proof_dir, a.timeout)
                rec["keep"] = {**rec["keep"], **dir_stats(keep_dir), "kept_leaves": rec["keep_repair"]["kept_after"], "kept_audit": rec["keep_repair"]["kept_audit_after"], "repaired": rec["keep_repair"]["repaired"], "repair_failed": rec["keep_repair"]["failed"]}
                if rec["keep_repair"]["failed"]:
                    rec["keep_incomplete"] = True; rec["status"] = "certified-keep-incomplete"      # 審查 #3: 唔算「接納」嘅證書 (S_acc 唔郁, finalize 唔會揀佢)'''))
P.append(('''        # 5. L2″ + L3″ + 完整性 + spindle
        if rec["status"] == "certified":''',
'''        # 5. L2″ + L3″ + 完整性 + spindle
        if rec["status"] in ("certified", "certified-keep-incomplete"):'''))
P.append(('''    def repair_keep(self, cdir, keep_dir, st):
        """certified 但有 leaf 證明搬唔到 D: → 由 base.cnf + cube 重建 cube CNF (sha 核對), kissat 重解 (T=4×timeout), drat-trim 重驗, 再搬 (sha 核對). 唔改 bundle.json (原證明 sha 照留), 結果記 keep_repair.json."""
        base_p = os.path.join(cdir, "base.cnf"); base_text = "".join(l for l in open(base_p) if not l.startswith(("p", "c")))
        nvars = int(open(base_p).readline().split()[2]); nbase = sum(1 for l in open(base_p) if not l.startswith(("p", "c")))
        done = st.get("done", {}); missing = [cid for cid, d in done.items() if not (d.get("kept") and os.path.exists(d["kept"]))]
        rep = {"missing": missing, "repaired": [], "failed": [], "records": {}}
        log("keep-repair: %d 個 leaf 證明唔喺 keep 目錄, 重解 + 重驗 + 再搬" % len(missing))
        tmpd = os.path.join(self.a.proof_dir, "repair"); os.makedirs(tmpd, exist_ok=True)
        for cid in missing:
            d = done[cid]; cnf = os.path.join(tmpd, "cube_%s.cnf" % cid); proof = os.path.join(tmpd, "%s_%s.drat" % (os.path.basename(cdir), cid))
            r = {"id": cid}
            try:
                with open(cnf + ".tmp", "w") as f:
                    f.write("p cnf %d %d\\n" % (nvars, nbase + len(d["cube"]))); f.write(base_text)
                    for l in d["cube"]:
                        f.write("%d 0\\n" % l)
                os.replace(cnf + ".tmp", cnf)
                r["cnf_sha_match"] = sha(cnf) == d["cnf_sha"]
                tl = 4 * self.a.timeout
                rr = subprocess.run([KISSAT, "--time=%d" % int(tl), cnf, proof], capture_output=True, text=True, timeout=tl + 300)
                r["rc"] = rr.returncode
                if rr.returncode == 20:
                    dr = subprocess.run([DRATTRIM, cnf, proof], capture_output=True, text=True, timeout=6 * 3600)
                    r["verified"] = any(l.strip() == "s VERIFIED" for l in dr.stdout.splitlines()); r["proof_sha"] = sha(proof); r["proof_bytes"] = os.path.getsize(proof)
                    r["same_sha_as_original"] = (r["proof_sha"] == d["proof_sha"])
                    if r["verified"] and r["cnf_sha_match"]:
                        os.makedirs(keep_dir, exist_ok=True); dst = os.path.join(keep_dir, os.path.basename(proof)); tmp = dst + ".part"
                        shutil.copyfile(proof, tmp)
                        if sha(tmp) == r["proof_sha"]:
                            os.replace(tmp, dst); r["kept"] = dst; rep["repaired"].append(cid)
                            done[cid]["kept"] = dst; done[cid]["repaired_proof_sha"] = r["proof_sha"]; done[cid].pop("keep_error", None)
                        else:
                            os.remove(tmp); r["error"] = "keep sha mismatch after repair"
                if cid not in rep["repaired"]:
                    rep["failed"].append(cid)
            except Exception as e:
                r["error"] = repr(e)[-300:]; rep["failed"].append(cid)
            finally:
                for p in (cnf, proof):
                    if os.path.exists(p):
                        os.remove(p)
            rep["records"][cid] = r
            log("  keep-repair leaf %s: rc=%s verified=%s cnf_sha_match=%s same_sha=%s → %s" % (cid, r.get("rc"), r.get("verified"), r.get("cnf_sha_match"), r.get("same_sha_as_original"), "kept ✓" if r.get("kept") else "!! " + str(r.get("error", "failed"))))
        # 寫返 state.json (只改 kept 欄) 同 keep_repair.json
        stp = os.path.join(cdir, "state.json"); st["done"] = done; st["keep_repair"] = {"repaired": rep["repaired"], "failed": rep["failed"], "when": time.strftime("%Y-%m-%d %H:%M:%S")}
        json.dump(st, open(stp + ".tmp", "w")); os.replace(stp + ".tmp", stp)
        json.dump(rep, open(os.path.join(cdir, "keep_repair.json"), "w"), indent=1)
        rep["kept_after"] = sum(1 for d in done.values() if d.get("kept") and os.path.exists(d["kept"]))
        log("keep-repair 完: 修好 %d, 修唔到 %d; keep 目錄而今 %d/%d leaf 證明" % (len(rep["repaired"]), len(rep["failed"]), rep["kept_after"], len(done)))
        return rep
''',
''''''))
P.append(('''class Probe:
    def __init__(self, a):''',
'''def repair_keep_dir(cdir, keep_dir, st, proof_dir, timeout, logf=log):
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
                f.write("p cnf %d %d\\n" % (nvars, nbase + len(d["cube"]))); f.write(base_text)
                for l in d["cube"]:
                    f.write("%d 0\\n" % l)
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
    def __init__(self, a):'''))
P.append(('''            proj = self.proj_wall_h(); rem_cpu_h = self.cpu_h_remaining(); rem_wall_h = self.remaining_total() / 3600
            if rem_cpu_h / a.workers < proj:
                st["stop_reason"] = "CPU 預算: 已用 %.1f / %.0f CPU-h, 剩 %.1f CPU-h = %.2f h wall < 預測下一輪 %.2f h (1.15 × 上一張證書) → 唔開 round %d" % (self.cpu_h_used(), a.cpu_cap_h, rem_cpu_h, rem_cpu_h / a.workers, proj, r); break''',
'''            proj = self.proj_wall_h(); rem_cpu_h = self.cpu_h_remaining(); rem_wall_h = self.remaining_total() / 3600
            if rem_cpu_h / a.workers - 0.25 < proj:                                               # 審查 #15: 同 cap = 剩餘 CPU/14 − 900 s 一致
                st["stop_reason"] = "CPU 預算: 已用 %.1f / %.0f CPU-h, 剩 %.1f CPU-h = %.2f h wall (−0.25 h 緩衝) < 預測下一輪 %.2f h (1.15 × 上一張證書) → 唔開 round %d" % (self.cpu_h_used(), a.cpu_cap_h, rem_cpu_h, rem_cpu_h / a.workers, proj, r); break'''))
P.append(('''                except Exception as e:
                    rec = {"tag": tag, "removed": len(S_try), "S": sorted(S_try), "status": "error", "error": repr(e)[-600:], "wall_s": round(time.time() - t_round, 1)}
                    subprocess.run(["pkill", "-x", "kissat"], capture_output=True); subprocess.run(["pkill", "-x", "drat-trim"], capture_output=True)''',
'''                except Exception as e:
                    rec = {"tag": tag, "removed": len(S_try), "S": sorted(S_try), "status": "error", "error": repr(e)[-600:], "wall_s": round(time.time() - t_round, 1)}
                    subprocess.run(["pkill", "-x", "kissat"], capture_output=True); subprocess.run(["pkill", "-x", "drat-trim"], capture_output=True)
                    kd_ = os.path.join(a.keep_root, tag)
                    if os.path.isdir(kd_):
                        ks_ = dir_stats(kd_); shutil.rmtree(kd_, ignore_errors=True); rec["keep"] = {"dir": kd_, "on_disk": False, "deleted_not_certified": True} | ks_'''))
P.append(('''                if rec["status"] in ("error", "cnc2-error", "march-refuted-root"):
                    status = "error"; st["stop_reason"] = "!! %s %s —— 停, 要人手睇 %s: %s" % (tag, rec["status"], os.path.join(self.out, tag), (rec.get("error") or (rec.get("cnc_log_tail") or "")[-300:]).replace("\\n", " | ")); break
                if rec["status"] == "certified":
                    if not rec.get("l3_ok"):
                        status = "l3-failed"; st["stop_reason"] = "!! %s L1″ certified 但 L2″/L3″/完整性/spindle 有步驅失敗 —— 停, 要人手睇 %s" % (tag, os.path.join(self.out, tag, "l3g2.log")); break
                    if rec.get("keep_incomplete"):
                        status = "keep-incomplete"; st["stop_reason"] = "!! %s certified + l3 ✓ 但 %d 個 leaf 證明搬去 D: 失敗而且修唔到 (%s) —— 封存規則要求全套證明喺碟上, 停, 要人手睇 %s" % (
                            tag, len(rec["keep_repair"]["failed"]), rec["keep_repair"]["failed"][:10], os.path.join(self.out, tag, "cnc_" + tag, "keep_repair.json")); break
                    certified_S = set(S_try); status = "certified"; break''',
'''                if rec["status"] in ("error", "cnc2-error", "march-refuted-root"):
                    status = "error"; st["needs_operator"] = True; st["stop_reason"] = "!! %s %s —— 停, 要人手睇 %s: %s" % (tag, rec["status"], os.path.join(self.out, tag), (rec.get("error") or (rec.get("cnc_log_tail") or "")[-300:]).replace("\\n", " | ")); break
                if rec["status"] == "certified-keep-incomplete":
                    status = "keep-incomplete"; st["needs_operator"] = True; st["stop_reason"] = "!! %s L1″ certified (l3_ok=%s) 但 %d 個證明搬去 D: 失敗而且修唔到 (%s) —— 封存規則要求全套證明喺碟上, S_acc 唔郁, 停, 要人手睇 %s" % (
                        tag, rec.get("l3_ok"), len(rec["keep_repair"]["failed"]), rec["keep_repair"]["failed"][:10], os.path.join(self.out, tag, "cnc_" + tag, "keep_repair.json")); break
                if rec["status"] == "certified":
                    if not rec.get("l3_ok"):
                        status = "l3-failed"; st["needs_operator"] = True; st["stop_reason"] = "!! %s L1″ certified 但 L2″/L3″/完整性/spindle 有步驅失敗 —— 停, 要人手睇 %s" % (tag, os.path.join(self.out, tag, "l3g2.log")); break
                    certified_S = set(S_try); status = "certified"; break'''))
P.append(('''                    if not rec.get("witness"):
                        st["stop_reason"] = "!! %s SAT 但染色證書覆核失敗 (%s) —— 編碼/解碼有 bug, 停" % (tag, rec.get("colouring")); status = "error"; break''',
'''                    if not rec.get("witness"):
                        st["stop_reason"] = "!! %s SAT 但染色證書覆核失敗 (%s) —— 編碼/解碼有 bug, 停" % (tag, rec.get("colouring")); status = "error"; st["needs_operator"] = True; break'''))
P.append(('''                if ai == 0:
                    status = "cap-hit"; st["stop_reason"] = "round %d 第 1 張證書超 %.2f h 輪上限未完 (%s: leaf %s/%s, 估計仲要 %s h) —— 停, 之後只會更難" % (
                        r, cap / 3600, rec["status"], rec.get("leaves"), rec.get("n_cubes"), rec.get("eta_remaining_h")); break''',
'''                if ai == 0:
                    status = "cap-hit"; st["needs_operator"] = True; st["stop_reason"] = "round %d 第 1 張證書超 %.2f h 輪上限未完 (%s: leaf %s/%s, 估計仲要 %s h) —— 停, 之後只會更難" % (
                        r, cap / 3600, rec["status"], rec.get("leaves"), rec.get("n_cubes"), rec.get("eta_remaining_h")); break'''))
P.append(('''        if not st["stop_reason"]:
            st["stop_reason"] = "%d 輪完成 (輪數上限 --rounds, 唔准自動加)" % st["round_done"]
        self.save()
        if not a.dry_run:
            try:
                g = self.gate(final=True); st["gate_final"] = g
            except Exception as e:
                st["gate_final"] = {"verdict": "ERROR", "why": repr(e)}
        st["finished"] = time.strftime("%Y-%m-%d %H:%M:%S"); self.save()''',
'''        if not st["stop_reason"]:
            st["stop_reason"] = "%d 輪完成 (輪數上限 --rounds, 唔准自動加)" % st["round_done"]
        if st.get("paused"):                                                                      # 審查 #17: PAUSE = 乾淨暫停, 唔算完, 唔跑 gate, 等 resume3c.sh
            self.save(); self.step("Phase 3c PAUSED (PAUSE 旗, round %d 之後): 用 resume3c.sh 續跑" % st["round_done"]); log("PROBE3C PAUSED: %s" % st["stop_reason"]); return
        st["finished"] = time.strftime("%Y-%m-%d %H:%M:%S"); self.save()                         # 審查 #16: finished 喺 gate 之前先寫 (gate 可以行 30 分鐘)
        if not a.dry_run:
            try:
                g = self.gate(final=True); st["gate_final"] = g
            except Exception as e:
                st["gate_final"] = {"verdict": "ERROR", "why": repr(e)}
        self.save()'''))
P.append(('''    ap.add_argument("--low-net", type=int, default=10); ap.add_argument("--low-net-rounds", type=int, default=3); ap.add_argument("--dry-run", action="store_true")''',
'''    ap.add_argument("--low-net", type=int, default=10); ap.add_argument("--low-net-rounds", type=int, default=3); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ack-operator", action="store_true", help="上次係操作員停機 (error/cap-hit/l3-failed/keep-incomplete) 人手睇完先可以續跑")'''))
patch("probe3c.py", P)

# ======================= s60_full.py =======================
S = []
S.append(('''import sys, os, json, time, argparse, subprocess, shutil, hashlib, glob, signal
if not __debug__:
    sys.exit("!! 唔准用 python -O")
PH3 = os.path.expanduser("~/hadwiger/phase3"); PH3C = os.path.expanduser("~/hadwiger/phase3c"); PH2B = os.path.expanduser("~/hadwiger/phase2b")''',
'''import sys, os, json, time, argparse, subprocess, shutil, hashlib, glob, signal
if not __debug__:
    sys.exit("!! 唔准用 python -O")
PH3 = os.path.expanduser("~/hadwiger/phase3"); PH3C = os.path.expanduser("~/hadwiger/phase3c"); PH2B = os.path.expanduser("~/hadwiger/phase2b")
sys.path.insert(0, PH3C)
from probe3c import repair_keep_dir      # 同 probe3c 一樣嘅搬失敗修補 (leaf + audit)

def write_json(p, obj):
    tmp = p + ".tmp"; open(tmp, "w", encoding="utf-8").write(json.dumps(obj, indent=1, ensure_ascii=False)); os.replace(tmp, p)'''))
S.append(('''    tag = "S60_full"; cdir = os.path.join(out, "cnc_" + tag); T0 = time.time()
    res = {"tag": tag, "started": time.strftime("%Y-%m-%d %H:%M:%S"), "cap_s": a.cap, "source": ROUND2}''',
'''    tag = "S60_full"; cdir = os.path.join(out, "cnc_" + tag); T0 = time.time()
    lp0 = os.path.join(STAGE_D, "leaf_proofs")
    if not os.path.isdir(a.keep_dir) and os.path.isdir(lp0):                       # 審查 #7: rename 之後再跑 → 用封存位置 (幂等)
        a.keep_dir = lp0; log("keep 目錄已 rename 入 %s, 用返佢" % lp0)
    res = {"tag": tag, "started": time.strftime("%Y-%m-%d %H:%M:%S"), "cap_s": a.cap, "source": ROUND2, "keep_dir": a.keep_dir}'''))
S.append(('''        assert cb["base_sha"] == BASE_SHA and cb["leaves"] == len(done)
        if res["kept_leaves"] != len(done):
            res["status"] = "certified-keep-incomplete"; log("!! %d/%d leaf 證明未保留 (keep_errors %d) —— 唔封存做「全套」, 人手睇" % (res["kept_leaves"], len(done), res["keep_errors"]))''',
'''        assert cb["base_sha"] == BASE_SHA and cb["leaves"] == len(done)
        res["kept_leaves"] = sum(1 for d in done.values() if d.get("kept") and os.path.exists(d["kept"]))
        if res["kept_leaves"] != len(done) or cb.get("audit_keep_errors") or cb.get("kept_audit") != cb["audit"]["n"]:
            step("keep-repair (leaf %d/%d, audit %s/%s)" % (res["kept_leaves"], len(done), cb.get("kept_audit"), cb["audit"]["n"]))
            rep = repair_keep_dir(cdir, a.keep_dir, st, a.proof_dir, 600, log)
            res["keep_repair"] = {"repaired": len(rep["repaired"]), "failed": rep["failed"][:20], "kept_after": rep["kept_after"], "kept_audit_after": rep["kept_audit_after"]}
            res["kept_leaves"] = rep["kept_after"]
            if rep["failed"]:
                res["status"] = "certified-keep-incomplete"; log("!! %d 個證明修唔到 —— 唔封存做「全套」, keep 目錄保留, 人手睇" % len(rep["failed"]))'''))
S.append(('''            json.dump({"tag": tag, "base_sha256": BASE_SHA, "n_leaves": len(idx), "leaf_proofs_dir": lp, "leaves": idx}, open(os.path.join(SD, "LEAF_INDEX.json"), "w"), indent=1)''',
'''            write_json(os.path.join(SD, "LEAF_INDEX.json"), {"tag": tag, "base_sha256": BASE_SHA, "n_leaves": len(idx), "leaf_proofs_dir": lp, "leaves": idx})'''))
S.append(('''    if res["status"] != "certified" and os.path.isdir(a.keep_dir):
        ks = sum(1 for f in os.listdir(a.keep_dir) if f.endswith(".drat"))
        shutil.rmtree(a.keep_dir, ignore_errors=True); res["keep_deleted"] = ks; log("唔係 certified/封存, 刪 keep 目錄 (%d 檔)" % ks)
    res["finished"] = time.strftime("%Y-%m-%d %H:%M:%S"); res["t_s"] = round(time.time() - T0, 1)
    json.dump(res, open(os.path.join(out, "s60_full.json"), "w"), indent=1, ensure_ascii=False)''',
'''    if res["status"] == "SAT?!" and os.path.isdir(a.keep_dir):                       # 審查 #7/#22: 只有 SAT?! (證明無意義) 先刪; budget-stop / verify-failed / keep-incomplete 全部保留 (可續跑 / 證據)
        ks = sum(1 for f in os.listdir(a.keep_dir) if f.endswith(".drat"))
        shutil.rmtree(a.keep_dir, ignore_errors=True); res["keep_deleted"] = ks; log("SAT?!, 刪 keep 目錄 (%d 檔)" % ks)
    res["keep_dir_retained"] = a.keep_dir if os.path.isdir(a.keep_dir) else None
    res["resumable"] = res["status"] in ("budget-stop", "hard-killed")
    if res["resumable"]:
        log("未完 (%s): cnc 狀態 + keep 目錄保留; 人手決定先續跑 (python3 s60_full.py 會 cnc2k --resume; Amber 上限 3 h 已用)" % res["status"])
    res["finished"] = time.strftime("%Y-%m-%d %H:%M:%S"); res["t_s"] = round(time.time() - T0, 1)
    write_json(os.path.join(out, "s60_full.json"), res)'''))
patch("s60_full.py", S)

# ======================= status3c.py =======================
T = []
T.append(('''    rec = any((st or {}).get("record_candidate") for _, st, _ in sts)
    fin = [load(os.path.join(d, "finalize_status.json")) for d in runs]; fin = [f for f in fin if f]
    title = "# Phase 3c status (G₂ 續剪, Haugland 方向, run p3c1_shrink)"
    if rec:
        title = "# **RECORD_CANDIDATE** —— Phase 3c status: |G₃′| < 1441 已認證, 唔再剪; 等 Amber (唔公開 / 唔寄信 / 唔 push)"
    elif fin and fin[-1].get("done"):
        title = "# Phase 3c status —— 完成 (%s); 報告 phase3c/phase3c_results.md; %s" % (fin[-1].get("finished"), "冇背景任務" if fin[-1].get("all_done") else "S60_full 補封存跑緊")''',
'''    rec = any((st or {}).get("record_candidate") for _, st, _ in sts)
    confirmed = any((st or {}).get("record_candidate_confirmed") for _, st, _ in sts)
    vfail = any((st or {}).get("finalize_verify_all_ok") is False for _, st, _ in sts)
    fin = [load(os.path.join(d, "finalize_status.json")) for d in runs]; fin = [f for f in fin if f]
    title = "# Phase 3c status (G₂ 續剪, Haugland 方向, run p3c1_shrink)"
    if rec and confirmed:
        title = "# **RECORD_CANDIDATE** —— Phase 3c status: |G₃′| < 1441 已認證 + 獨立重驗通過, 唔再剪; 等 Amber (唔公開 / 唔寄信 / 唔 push)"
    elif rec and vfail:
        title = "# **!! RECORD CANDIDATE BLOCKED** —— probe3c 到咗 |G₃′| < 1441 但 finalize 獨立重驗唔過 (VERIFY_FAILED.md), 唔算紀錄候選, 要人手睇"
    elif rec:
        title = "# **RECORD_CANDIDATE (候選, finalize 獨立重驗中)** —— probe3c 到咗 |G₃′| < 1441, 唔再剪; 等重驗 + 封存"
    elif vfail:
        title = "# **!! 獨立重驗唔過** —— Phase 3c 停咗, finalize verify_final all_ok=False (VERIFY_FAILED.md), 要人手睇"
    elif fin and fin[-1].get("done"):
        title = "# Phase 3c status —— 完成 (%s); 報告 phase3c/phase3c_results.md; %s" % (fin[-1].get("finished"), "冇背景任務" if fin[-1].get("all_done") else "S60_full 補封存跑緊 (或者 finalize 失敗, 睇下面)")'''))
T.append(('''    while True:
        txt = render()
        for dst in [os.path.join(PH, "status.md")] + WIN:''',
'''    while True:
        try:
            txt = render()
        except Exception as e:                                                             # 審查 (cosmetic): render 出錯唔可以令 10 分鐘循環死
            import traceback
            txt = "# Phase 3c status —— status3c render 出錯 (%s)\\n\\n```\\n%s\\n```\\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), traceback.format_exc()[-3000:])
        for dst in [os.path.join(PH, "status.md")] + WIN:'''))
patch("status3c.py", T)

# ======================= make_cnc2k.py (cnc2k disk_ok: /dev/shm 剩餘) =======================
M = []
M.append(('''    rep(\'\'\'    ap.add_argument("--max-errors", type=int, default=3); ap.add_argument("--requeue-stuck", action="store_true")
    a = ap.parse_args()\'\'\',''',
'''    rep(\'\'\'def disk_ok(run, st):
    pd = st["proof_dir"]
    if du_prefix_gb(pd, run.tag + "_") > DISK_UNVERIFIED_GB_MAX:
        return False
\'\'\',
        \'\'\'DISK_PD_MIN_GB = 4.0     # Phase 3c: 證明暫存目錄 (/dev/shm 16 GB RAM 盤) 剩餘 < 4 GB 就唔派新 cube (審查 #9; 磁碟紀律, 唔郁 cube/驗證邏輯)

def disk_ok(run, st):
    pd = st["proof_dir"]
    if du_prefix_gb(pd, run.tag + "_") > DISK_UNVERIFIED_GB_MAX:
        return False
    try:
        if free_gb(pd) < DISK_PD_MIN_GB:
            return False
    except OSError:
        return False
\'\'\')
    rep(\'\'\'    ap.add_argument("--max-errors", type=int, default=3); ap.add_argument("--requeue-stuck", action="store_true")
    a = ap.parse_args()\'\'\','''))
patch("make_cnc2k.py", M)
print("[patch_review] 全部施加完; 記得重跑 make_cnc2k.py 生成 cnc2k.py")
