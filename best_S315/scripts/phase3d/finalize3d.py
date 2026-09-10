#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
finalize3d.py —— Phase 3d 收爐 / RECORD 程序 (probe3d 停機之後自動跑; 幂等, 可重跑):
  1. 搵最終認證圖 (state.best: certified + l3_ok + col5_ok 嘅嘗試)
  2. 獨立重驗 (由碟上檔案出發, 唔信戰役結果):
     (a) verify_final.py —— **全部** leaf 證明重跑 drat-trim (唔抽樣) + cnf/proof sha 對數 + cover 子句重建 + 審計證明 + l3g2 --engine-b 重跑 + exactfield --complete
     (b) crosscheck3d.py —— 5% leaf 用 cake_lpr (形式化驗證過) + lrat-check 交叉覆核 (drat-trim -L 出 LRAT)
     (c) 5 色染色: 重新解一次 (certify4 --k 5) + 對封存嘅 .col 逐邊覆核 (純 Python, 唔用 solver)
  3. 封存 → /mnt/d/hadwiger/release_v1_1_staging/record/ (|G₃′| < 1441) 或者 best_S<n>/ (有進步但未到);
     leaf 證明由 keep 目錄 rename 過去 (同一隻碟), SHA256SUMS 逐檔, RECORD_README.md (英文), reverify.sh; Windows 鏡像唔含 leaf 證明
  4. RECORD_CANDIDATE.md + status RECORD_CANDIDATE —— **只有喺 (a)(b)(c) 全部通過而且 |G₃′| < 1441 先寫**; 否則寫 VERIFY_FAILED.md / RECORD_CANDIDATE_BLOCKED.md
  5. 每輪細檔 → ~/hadwiger/release_v1_1_staging/reduction/phase3d_G2_final/ + 報告 phase3d_results.md + facts.json (g2shrink3d.*) + DECISION.md 路線 A + MEMORY
  唔准公開: 冇 git push, 冇 Zenodo, 冇 email.
用法: python3 finalize3d.py --run ~/hadwiger/phase3d/runs/p3d1_final [--workers 14] [--dry-run] [--force-verify] [--frac 0.05]
"""
import sys, os, json, time, argparse, subprocess, shutil, hashlib, glob, re
from concurrent.futures import ThreadPoolExecutor
if not __debug__:
    sys.exit("!! 唔准用 python -O")
PH2 = os.path.expanduser("~/hadwiger/phase2"); PH2B = os.path.expanduser("~/hadwiger/phase2b")
PH3B = os.path.expanduser("~/hadwiger/phase3b"); PH3C = os.path.expanduser("~/hadwiger/phase3c"); PH3D = os.path.expanduser("~/hadwiger/phase3d")
ARCH_ROOT = "/mnt/d/hadwiger/release_v1_1_staging"
STAGE = os.path.expanduser("~/hadwiger/release_v1_1_staging/reduction")
WIN = "/mnt/c/Users/user/Desktop/spindle"
WIN_STAGE = os.path.join(WIN, "release_v1_1_staging", "reduction")
MEM = "/mnt/c/Users/user/.claude/projects/C--Users-user-Desktop-spindle/memory"
PY = sys.executable
RECORD_G3P = 1441            # 文獻值 (Amber 提供: Heule 2021 無-spindle 5-chromatic UDG 最細已知點數); 我哋冇獨立重驗過呢個數
PREV_G3P = 1591              # Phase 3c r09a (我哋自己上一個已認證圖)

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

def read_edges(p):
    n = None; E = []
    for line in open(p):
        t = line.split()
        if not t:
            continue
        if t[0] == "p":
            n = int(t[2]); continue
        if t[0] == "e":
            E.append((int(t[1]), int(t[2])))
    return n, E

class Fin:
    def __init__(self, a):
        self.a = a; self.rdir = os.path.abspath(os.path.expanduser(a.run)); self.rid = os.path.basename(self.rdir)
        self.st = json.load(open(os.path.join(self.rdir, "state.json")))
        self.attempts = json.load(open(os.path.join(self.rdir, "attempts.json"))) if os.path.exists(os.path.join(self.rdir, "attempts.json")) else []
        self.fs_p = os.path.join(self.rdir, "finalize_status.json")
        self.fs = json.load(open(self.fs_p)) if os.path.exists(self.fs_p) else {"started": time.strftime("%Y-%m-%d %H:%M:%S")}
        self.fs["stage"] = "start"; self.fs["done"] = False; self.save()
        self.W = a.workers; self.now = time.strftime("%Y-%m-%d %H:%M:%S")
        self.vok = None; self.rec_ok = False; self.improved = False; self.rb = {}
        if not self.st.get("finished"):
            tail = ""
            try:
                tail = " | ".join([l.strip() for l in open(os.path.join(self.rdir, "probe3d.log"), errors="ignore").read().splitlines() if l.strip()][-3:])[:600]
            except Exception:
                pass
            self.st["stop_reason"] = "!! probe3d 未正常結束 (state.finished 冇): %s || probe3d.log 尾: %s" % (self.st.get("stop_reason"), tail)
            self.fs["probe_unfinished"] = True; log(self.st["stop_reason"])

    def save(self, **kw):
        self.fs.update(kw); self.fs["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        json.dump(self.fs, open(self.fs_p + ".tmp", "w"), indent=1, ensure_ascii=False); os.replace(self.fs_p + ".tmp", self.fs_p)

    def step(self, msg):
        self.fs["stage"] = msg; self.save(); log(msg)
        try:
            open(os.path.join(PH3D, "STEP.txt"), "w").write("Phase 3d 收爐 (finalize3d): " + msg)
        except Exception:
            pass

    def flag_status(self):
        p = os.path.join(self.rdir, "status.json")
        try:
            st = json.load(open(p)) if os.path.exists(p) else {}
            st["finalize_verify_all_ok"] = self.vok; st["record_candidate_confirmed"] = self.rec_ok
            st["finalize_verify_when"] = time.strftime("%Y-%m-%d %H:%M:%S"); st["archive_dir"] = self.fs.get("archive", {}).get("dir")
            write(p, json.dumps(st, indent=1, ensure_ascii=False))
        except Exception as e:
            log("!! status.json 旗寫唔到: %r" % e)

    # ---------------- 1. 最終認證圖 ----------------
    def final_attempt(self):
        best = self.st.get("best")
        assert best, "!! state.best 冇 —— probe3d 冇拎到新證書 (stop: %s); 冇嘢好封存" % self.st.get("stop_reason")
        cand = [x for x in self.attempts if x["tag"] == best["tag"] and x.get("status") == "certified" and x.get("l3_ok") is True and x.get("col5_ok") is True]
        assert cand, "!! attempts.json 搵唔到 %s 嘅 certified + l3_ok + col5_ok 記錄" % best["tag"]
        x = cand[-1]; d = x.get("dir") or os.path.join(self.rdir, x["tag"])
        assert sorted(x["S"]) == sorted(self.st["S_acc"]), "最終證書嘅 S 同 state.S_acc 對唔上"
        keep = best.get("keep_dir"); has_keep = bool(keep and os.path.isdir(keep))
        arch = self.arch_dir(x)
        if not has_keep:                                                     # 幂等: keep 目錄可能已經 rename 咗入封存目錄
            lp = os.path.join(arch, "L1pp", "leaf_proofs"); li = os.path.join(arch, "L1pp", "LEAF_INDEX.json")
            try:
                if os.path.isdir(lp) and os.path.exists(li):
                    ix = json.load(open(li))
                    if ix.get("tag") == x["tag"] and ix.get("base_sha256") == x["cnf"]["cnf_sha256"]:
                        keep = lp; has_keep = True; log("keep 目錄已 rename 入封存: 用 %s" % lp)
            except Exception as e:
                log("LEAF_INDEX 讀唔到: %r" % e)
        assert has_keep, "!! %s 嘅 leaf 證明搵唔到 (keep %s, 封存 %s) —— 封存規則要求全套證明喺碟上, 人手睇" % (x["tag"], best.get("keep_dir"), arch)
        # 審查: 由碟上檔案再對數一次 —— base.json 嘅 S / sha / 點數, 同 keep 目錄真實 .drat 檔數
        bj = json.load(open(os.path.join(d, "base.json")))
        assert sorted(bj["removed"]) == sorted(x["S"]), "!! base.json removed 同 attempts.json 嘅 S 對唔上"
        assert bj["cnf_sha256"] == x["cnf"]["cnf_sha256"] and bj["n_remaining"] == x["G2p_n"] and bj["n_edges"] == x["G2p_m"], "!! base.json sha / 點數 / 邊數 對唔上"
        n_disk = len([f for f in os.listdir(keep) if f.endswith(".drat")])
        n_aud = len([f for f in os.listdir(os.path.join(keep, "audit")) if f.endswith(".drat")]) if os.path.isdir(os.path.join(keep, "audit")) else 0
        assert n_disk == x["leaves"], "!! keep 目錄 %s 得 %d 個 .drat, 但 leaves = %d —— 封存唔完整, 人手睇" % (keep, n_disk, x["leaves"])
        log("最終圖對數: base.json ✓ (S %d 粒, sha %s…), keep 目錄 %d 個 leaf .drat + %d 個審計 .drat" % (len(x["S"]), bj["cnf_sha256"][:16], n_disk, n_aud))
        return {"tag": x["tag"], "dir": d, "vdir": d, "keep_dir": keep, "has_keep": True, "S": x["S"], "rec": x, "arch": arch, "n_disk_leaf": n_disk, "n_disk_audit": n_aud,
                "G2p_n": x["G2p_n"], "G2p_m": x["G2p_m"], "G3p_n": x["G3p_n"], "G3p_m": x["G3p_m"], "leaves": x["leaves"]}

    def rebuild_base(self, fa):
        """審查: 由 S 重新起一次 base.cnf (buildg2.py), sha 要同封存嘅 base.cnf 一模一樣 —— 閂返「CNF 真係呢幅圖」呢個環."""
        self.step("獨立重驗 (0) 由 S 重新生成 base.cnf, sha 對數")
        tmp = os.path.join(fa["vdir"], "rebuild"); os.makedirs(tmp, exist_ok=True)
        r = subprocess.run([PY, os.path.join(PH3B, "buildg2.py"), "--remove", ",".join(map(str, fa["S"])), "--out", tmp, "--tag", "base",
                            "--protected", os.path.join(PH3B, "batches_g2.json")], capture_output=True, text=True, timeout=900)
        res = {"rc": r.returncode, "tail": (r.stdout + r.stderr)[-300:]}
        p = os.path.join(tmp, "base.cnf")
        if r.returncode == 0 and os.path.exists(p):
            res["rebuilt_sha256"] = sha(p); res["archived_sha256"] = sha(os.path.join(fa["dir"], "base.cnf"))
            res["match"] = res["rebuilt_sha256"] == res["archived_sha256"] == fa["rec"]["cnf"]["cnf_sha256"]
            meta = json.load(open(os.path.join(tmp, "base.json")))
            res["n_remaining"] = meta["n_remaining"]; res["n_edges"] = meta["n_edges"]
            res["graph_match"] = (meta["n_remaining"] == fa["G2p_n"] and meta["n_edges"] == fa["G2p_m"])
        res["ok"] = bool(res.get("match") and res.get("graph_match"))
        shutil.rmtree(tmp, ignore_errors=True)
        self.save(rebuild_base=res); log("由 S 重建 base.cnf: sha %s (%s)" % (res.get("rebuilt_sha256", "?")[:16], "同封存一致 ✓" if res["ok"] else "!! 唔一致"))
        return res

    def arch_dir(self, x):
        return os.path.join(ARCH_ROOT, "record" if (x.get("G3p_n") or 10 ** 9) < RECORD_G3P else "best_S%d" % x["removed"])

    # ---------------- 2. 獨立重驗 ----------------
    def verify(self, fa):
        d = fa["dir"]; tag = fa["tag"]; vf = os.path.join(d, "verify_final.json")
        res = None
        if os.path.exists(vf) and not self.a.force_verify:
            old = json.load(open(vf))
            bound = (old.get("base_sha256") == fa["rec"]["cnf"]["cnf_sha256"] and (old.get("leaf_reverify") or {}).get("n") == fa["leaves"]
                     and os.path.realpath(old.get("keep_dir") or "/x") == os.path.realpath(fa["keep_dir"]) and old.get("tag") == tag)   # 審查: cache 要綁死呢張證書
            if old.get("all_ok") is True and old.get("leaf_reverify") and old.get("l3_final") and bound:
                log("verify_final.json 已有而且 all_ok + 綁得返呢張證書 (base sha / leaves / keep-dir), 唔重做"); res = old
            elif old.get("all_ok") is True:
                log("verify_final.json 有 all_ok 但綁唔返呢張證書 (base sha/leaves/keep-dir 唔啱) → 重做")
        if res is None:
            self.step("獨立重驗 (a) %s: **全部** %d 個 leaf 證明 drat-trim + cover + 審計證明 + l3g2 --engine-b + exactfield --complete (%d workers, 估計 2–3 h)" % (tag, fa["leaves"], self.W))
            argv = [PY, os.path.join(PH3C, "verify_final.py"), "--attempt-dir", d, "--tag", tag, "--keep-dir", fa["keep_dir"], "--workers", str(self.W), "--json-out", vf]
            with open(os.path.join(d, "verify_final.log"), "a") as lf:
                rc = subprocess.call(argv, stdout=lf, stderr=subprocess.STDOUT)
            res = json.load(open(vf)) if os.path.exists(vf) else {"all_ok": False, "error": "verify_final.py rc=%d 冇輸出" % rc}
            res["rc"] = rc
            if rc != 0 and res.get("all_ok") is True:
                res["all_ok"] = False; res["error"] = "verify_final.py rc=%d 但 JSON 話 all_ok" % rc
        lr = res.get("leaf_reverify") or {}
        self.save(verify_final={"all_ok": res.get("all_ok"), "leaf_reverify": {k: v for k, v in lr.items() if k != "bad"}, "cover": (res.get("cover_reverify") or {}).get("verified"),
                                "audit": (res.get("audit_reverify") or {}).get("complete"), "l3_final_all_ok": (res.get("l3_final") or {}).get("all_ok"),
                                "spindle_B_ok": ((res.get("l3_final") or {}).get("spindle_B") or {}).get("ok"), "t_s": res.get("t_s"), "error": res.get("error")})
        log("verify_final: all_ok=%s (leaf %s/%s, cover %s, audit complete %s, l3_final %s)" % (
            res.get("all_ok"), lr.get("ok"), lr.get("n"), (res.get("cover_reverify") or {}).get("verified"), (res.get("audit_reverify") or {}).get("complete"), (res.get("l3_final") or {}).get("all_ok")))
        return res

    def crosscheck(self, fa):
        d = fa["dir"]; xf = os.path.join(d, "crosscheck.json")
        if os.path.exists(xf) and not self.a.force_verify:
            old = json.load(open(xf))
            bound = (old.get("base_sha256") == fa["rec"]["cnf"]["cnf_sha256"] and old.get("n_leaves") == fa["leaves"] and old.get("tag") == fa["tag"]
                     and os.path.realpath(old.get("keep_dir") or "/x") == os.path.realpath(fa["keep_dir"]) and (old.get("n_sampled") or 0) >= int(self.a.frac * fa["leaves"] * 0.9))
            if old.get("all_ok") is True and bound:
                log("crosscheck.json 已有而且 all_ok + 綁得返呢張證書, 唔重做"); self.save(crosscheck={k: old.get(k) for k in ("n_sampled", "ok", "n_bad", "all_ok", "wall_s")}); return old
            if old.get("all_ok") is True:
                log("crosscheck.json 有 all_ok 但綁唔返呢張證書 → 重做")
        self.step("獨立重驗 (b) %s: %.0f%% leaf 用 cake_lpr (形式化驗證過) + lrat-check 交叉覆核" % (fa["tag"], self.a.frac * 100))
        argv = [PY, os.path.join(PH3D, "crosscheck3d.py"), "--attempt-dir", d, "--tag", fa["tag"], "--keep-dir", fa["keep_dir"], "--out", d,
                "--frac", str(self.a.frac), "--workers", str(self.W)]
        with open(os.path.join(d, "crosscheck.log"), "a") as lf:
            rc = subprocess.call(argv, stdout=lf, stderr=subprocess.STDOUT)
        res = json.load(open(xf)) if os.path.exists(xf) else {"all_ok": False, "error": "crosscheck3d.py rc=%d 冇輸出" % rc}
        res["rc"] = rc
        if rc != 0 and res.get("all_ok") is True:
            res["all_ok"] = False
        self.save(crosscheck={k: res.get(k) for k in ("n_sampled", "ok", "n_bad", "all_ok", "wall_s", "lrat_total_gb", "error")})
        log("crosscheck (cake_lpr): all_ok=%s (%s/%s)" % (res.get("all_ok"), res.get("ok"), res.get("n_sampled")))
        return res

    def col5(self, fa, vres):
        """(c) 5 色: 對封存嘅 .col 逐邊覆核 (純 Python) + 用收爐重跑嘅 l3_final/G3p.edge 再解一次 (certify4 --k 5)."""
        self.step("獨立重驗 (c) %s: G₃′ 5 色染色逐邊覆核 + 重新解一次" % fa["tag"])
        d = fa["dir"]; res = {"when": time.strftime("%Y-%m-%d %H:%M:%S")}
        colp = os.path.join(d, "col5", "G3p_5col.col"); e_camp = os.path.join(d, "l3", "G3p.edge"); e_fresh = os.path.join(d, "l3_final", "G3p.edge")
        try:
            n, E = read_edges(e_camp)
            col = {}
            for line in open(colp):
                t = line.split()
                if len(t) == 2:
                    col[int(t[0])] = int(t[1])
            # 審查: 兩端都要有色先算, 而且頂點集要啱啱好係 1..n (缺一個頂點唔可以扮通過)
            bad = [(u, v) for u, v in E if col.get(u) is None or col.get(v) is None or col.get(u) == col.get(v)]
            used = sorted(set(col.values()))
            vertex_set_ok = (set(col) == set(range(1, (n or 0) + 1)))
            res["archived_col"] = {"file": colp, "sha256": sha(colp), "n": n, "n_coloured": len(col), "edges_checked": len(E), "bad_edges": len(bad), "vertex_set_ok": vertex_set_ok,
                                   "colours_used": used, "ok": (not bad and vertex_set_ok and len(col) == n and len(used) <= 5 and all(isinstance(c, int) and 1 <= c <= 5 for c in col.values()))}
            log("  封存嘅 5 色染色: %d 點, %d/%d 條邊逐條覆核異色 %s, 用色 %s" % (len(col), len(E) - len(bad), len(E), "✓" if not bad else "!! %d 條同色" % len(bad), used))
        except Exception as e:
            res["archived_col"] = {"ok": False, "error": repr(e)[-300:]}
        # 用收爐重跑嘅圖再解一次 (獨立於戰役)
        try:
            if os.path.exists(e_fresh):
                out5 = os.path.join(d, "col5_final")
                r5 = subprocess.run([PY, os.path.join(PH2, "certify4.py"), e_fresh, "--out", out5, "--k", "5", "--tag", "G3p_5col_final", "--expect", "sat", "--timeout", "3600"],
                                    capture_output=True, text=True, timeout=4000)
                open(os.path.join(d, "col5_final.log"), "w").write(r5.stdout + r5.stderr)
                j5 = os.path.join(out5, "G3p_5col_final.json"); s5 = json.load(open(j5)) if os.path.exists(j5) else {}
                res["fresh_col"] = {"rc": r5.returncode, "status": s5.get("status"), "n": s5.get("n"), "m": s5.get("m"), "colours_used": s5.get("colours_used"),
                                    "edges_checked": s5.get("edges_checked"), "solve_s": s5.get("solve_s"),
                                    "col_sha256": sha(os.path.join(out5, "G3p_5col_final.col")) if os.path.exists(os.path.join(out5, "G3p_5col_final.col")) else None,
                                    "ok": bool(r5.returncode == 0 and s5.get("status") == "SAT" and s5.get("edges_checked") == fa["G3p_m"] and s5.get("n") == fa["G3p_n"])}
                log("  重新解 5 色 (l3_final/G3p.edge): %s" % ([l for l in r5.stdout.splitlines() if l.startswith("[G3p_5col_final]")] or ["rc=%d" % r5.returncode])[0][:200])
            else:
                res["fresh_col"] = {"ok": False, "error": "l3_final/G3p.edge 唔存在 (verify_final 冇跑完?)"}
        except Exception as e:
            res["fresh_col"] = {"ok": False, "error": repr(e)[-300:]}
        # 兩個圖要一致 (戰役 l3/G3p.edge == 收爐 l3_final/G3p.edge)
        try:
            res["G3p_edge_same"] = (os.path.exists(e_fresh) and sha(e_camp) == sha(e_fresh))
        except Exception:
            res["G3p_edge_same"] = False
        res["all_ok"] = bool(res.get("archived_col", {}).get("ok") and res.get("fresh_col", {}).get("ok") and res["G3p_edge_same"])
        write(os.path.join(d, "col5_check.json"), json.dumps(res, indent=1, ensure_ascii=False))
        self.save(col5={"all_ok": res["all_ok"], "archived_ok": res.get("archived_col", {}).get("ok"), "fresh_ok": res.get("fresh_col", {}).get("ok"), "edge_same": res["G3p_edge_same"]})
        log("5 色覆核: all_ok=%s" % res["all_ok"])
        return res

    # ---------------- 3. 封存 ----------------
    def archive(self, fa, vres, xres, c5):
        F = fa["arch"]; d = fa["dir"]; tag = fa["tag"]; cdir = os.path.join(d, "cnc_" + tag)
        self.step("封存 → %s (leaf 證明 rename 自 %s)" % (F, fa["keep_dir"]))
        if self.a.dry_run:
            log("dry-run: 唔郁封存目錄"); return {"dry_run": True, "dir": F}
        L1 = os.path.join(F, "L1pp")
        oldb = os.path.join(L1, "base.json")
        if os.path.exists(oldb):
            try:
                old_sha = json.load(open(oldb)).get("cnf_sha256")
            except Exception:
                old_sha = None
            if old_sha != fa["rec"]["cnf"]["cnf_sha256"]:
                sup = F + "_superseded_%s" % time.strftime("%Y%m%d_%H%M%S")
                os.rename(F, sup); log("封存目錄已有另一個圖 (base sha %s…), 搬去 %s (唔刪)" % ((old_sha or "")[:16], sup)); self.fs["superseded"] = sup
        os.makedirs(L1, exist_ok=True)
        for f in ("base.cnf", "base.json", "cubes_d14.icnf", "march.log", "cnc.log", "l3g2.log", "col5.log", "col5_final.log",
                  "verify_final.json", "verify_final.log", "crosscheck.json", "crosscheck.log", "col5_check.json"):
            cp(os.path.join(d, f), L1)
        for f in ("bundle.json", "cover_pure.cnf", "cover_pure.drat", "cover_with_base.cnf", "cover_with_base.drat", "ledger.csv", "state.json", "status.json", "keep_repair.json", "base.cnf", "cubes.icnf"):
            cp(os.path.join(cdir, f), os.path.join(L1, "cnc_" + tag))
        lp = os.path.join(L1, "leaf_proofs"); kd = fa["keep_dir"]; moved = None
        if os.path.isdir(lp) and (os.path.realpath(kd) == os.path.realpath(lp) or not os.path.isdir(kd)):
            moved = "already"
        else:
            assert not os.path.isdir(lp), "封存目錄已有 leaf_proofs 而且 keep 目錄亦存在 —— 唔敢覆寫, 人手睇"
            os.rename(kd, lp); moved = "renamed"
        for root_, _, fs_ in os.walk(lp):
            for f in fs_:
                if f.endswith(".part"):
                    os.remove(os.path.join(root_, f))
        n_leaf = sum(1 for f in os.listdir(lp) if f.endswith(".drat"))
        n_aud = len([f for f in os.listdir(os.path.join(lp, "audit"))]) if os.path.isdir(os.path.join(lp, "audit")) else 0
        log("leaf 證明: %s → %s (%d leaf .drat + %d 審計 .drat)" % (kd, lp, n_leaf, n_aud))
        cb = json.load(open(os.path.join(cdir, "bundle.json"))); stc = json.load(open(os.path.join(cdir, "state.json")))
        def _bytes(x):                                                                    # 審查: 修過嘅 leaf 要記返新檔嘅大細, 唔可以留舊數
            if (stc["done"].get(x["id"]) or {}).get("repaired_proof_sha"):
                p_ = os.path.join(lp, "cnc_%s_%s.drat" % (tag, x["id"]))
                if os.path.exists(p_):
                    return os.path.getsize(p_)
            return x["proof_bytes"]
        idx = {x["id"]: {"file": "leaf_proofs/cnc_%s_%s.drat" % (tag, x["id"]), "proof_sha256": (stc["done"].get(x["id"]) or {}).get("repaired_proof_sha") or x["proof_sha"],
                         "proof_bytes": _bytes(x), "cube": x["cube"], "cnf_sha256": x["cnf_sha"], "solve_s": x["solve_s"], "verify_s": x["verify_s"],
                         "attempt": x["attempt"], "repaired": bool((stc["done"].get(x["id"]) or {}).get("repaired_proof_sha"))} for x in cb["leaf_list"]}
        write(os.path.join(L1, "LEAF_INDEX.json"), json.dumps({"tag": tag, "base_sha256": cb["base_sha"], "n_leaves": len(idx),
              "note": "each leaf proof refutes base.cnf + the unit clauses of its cube; kissat binary DRAT, checked by drat-trim (all of them, again at archive time) and by cake_lpr on a 5% sample", "leaves": idx}, indent=1))
        for sub in ("l3", "l3_final"):
            for f in glob.glob(os.path.join(d, sub, "*")):
                if os.path.isfile(f):
                    cp(f, os.path.join(F, "L2L3", sub))
            for f in glob.glob(os.path.join(d, sub, "spindle_B", "*")):
                cp(f, os.path.join(F, "L2L3", sub, "spindle_B"))
        for sub in ("col5", "col5_final"):
            for f in glob.glob(os.path.join(d, sub, "*")):
                if os.path.isfile(f):
                    cp(f, os.path.join(F, "COL5", sub))
        for f in ("state.json", "attempts.json", "ledger_g2.md", "status.json", "probe3d.log", "finalize_status.json"):
            cp(os.path.join(self.rdir, f), os.path.join(F, "run"))
        for f in ("batches_g2.json", "batches_g2.md"):
            cp(os.path.join(PH3B, f), os.path.join(F, "run"))
        seed = self.st.get("seed") or {}
        if seed.get("run_dir"):
            for f in ("state.json", "rounds.json", "ledger_g2.md", "probe3c.log"):
                cp(os.path.join(seed["run_dir"], f), os.path.join(F, "run", "seed_" + seed.get("run_id", "phase3c")))
        for sub, src in (("phase3d", PH3D), ("phase3c", PH3C), ("phase3b", PH3B)):
            for f in glob.glob(os.path.join(src, "*.py")) + glob.glob(os.path.join(src, "*.sh")) + glob.glob(os.path.join(src, "*.diff")):
                cp(f, os.path.join(F, "scripts", sub))
        for f in ("cnc2.py", "cubes.py", "crosscheck_cakelpr.py"):
            cp(os.path.join(PH2B, f), os.path.join(F, "scripts", "phase2b"))
        for f in ("exactfield.py", "certify4.py", "spindlefind.py", "haugland.py", "chain.py"):
            cp(os.path.join(PH2, f), os.path.join(F, "scripts", "phase2"))
        self.write_reverify(F, fa)
        self.write_readme(F, fa, vres, xres, c5, n_leaf, n_aud)
        for stale in ("RECORD_CANDIDATE.md", "RECORD_CANDIDATE_BLOCKED.md", "VERIFY_FAILED.md"):    # 審查: 封存目錄以外嘅副本都要清, 免得舊判斷留低誤導
            for base_ in (F, PH3D, os.path.join(WIN, "phase3d")):
                p_ = os.path.join(base_, stale)
                if os.path.exists(p_):
                    os.remove(p_)
        rec_md = None
        if not self.vok:
            lr_ = vres.get("leaf_reverify") or {}
            txt = ("# VERIFY_FAILED.md — independent re-verification did NOT pass (%s)\n\nThis directory is EVIDENCE ONLY. Do not treat the graph as certified until `bash reverify.sh` passes.\n\n"
                   "verify_final all_ok = %s (error %s)\nleaf_reverify: %s\nbad leaves (first 50): %s\ncover: %s\naudit: %s\nl3_final: %s\ncake_lpr crosscheck: %s\n5-colouring: %s\n") % (
                self.now, vres.get("all_ok"), vres.get("error"), json.dumps({k: v for k, v in lr_.items() if k != "bad"}, default=str), json.dumps(lr_.get("bad"), default=str)[:3000],
                json.dumps(vres.get("cover_reverify"), default=str), json.dumps(vres.get("audit_reverify"), default=str)[:1500],
                json.dumps(vres.get("l3_final"), default=str)[:2000], json.dumps({k: v for k, v in (xres or {}).items() if k != "records"}, default=str)[:2000], json.dumps(c5, default=str)[:2000])
            for p_ in (os.path.join(F, "VERIFY_FAILED.md"), os.path.join(PH3D, "VERIFY_FAILED.md"), os.path.join(WIN, "phase3d", "VERIFY_FAILED.md")):
                write(p_, txt)
        if self.rec_ok:
            rec_md = self.write_record_candidate(F, fa, vres, xres, c5)
        elif fa["G3p_n"] < RECORD_G3P:
            txt = ("# RECORD_CANDIDATE_BLOCKED.md (%s)\n\nprobe3d reached |G3'| = %d < %d, but the independent re-verification did NOT pass "
                   "(verify_final all_ok = %s, cake_lpr crosscheck all_ok = %s, 5-colouring all_ok = %s). NOT a record candidate until re-verified. See VERIFY_FAILED.md.\n") % (
                self.now, fa["G3p_n"], RECORD_G3P, vres.get("all_ok"), (xres or {}).get("all_ok"), (c5 or {}).get("all_ok"))
            for p_ in (os.path.join(F, "RECORD_CANDIDATE_BLOCKED.md"), os.path.join(PH3D, "RECORD_CANDIDATE_BLOCKED.md"), os.path.join(WIN, "phase3d", "RECORD_CANDIDATE_BLOCKED.md")):
                write(p_, txt)
        self.step("SHA256SUMS (%s, 逐檔, %d threads; 約 %d 個檔)" % (F, self.W, n_leaf + 200))
        ss = shasums(F, self.W)
        small = [l for l in open(os.path.join(F, "SHA256SUMS")) if "L1pp/leaf_proofs/" not in l]
        write(os.path.join(F, "SHA256SUMS.small"), "".join(small))
        log("封存: %d 檔 %.2f GB, SHA256SUMS sha %s…, sha256sum -c rc=%d %s" % (ss["n_files"], ss["bytes"] / 1e9, ss["sha256sums_sha256"][:16], ss["check_rc"], ss["check_tail"][:100]))
        win_dir = os.path.join(WIN, "release_v1_1_staging", os.path.basename(F)); n_m = 0
        c_free = None
        try:
            stv = os.statvfs("/mnt/c"); c_free = stv.f_bavail * stv.f_frsize / 1e9
        except Exception:
            pass
        if c_free is not None and c_free < 10:                                            # 審查: C: 得 44 GB, 唔好因為鏡像塞爆佢 (vhdx 都喺 C:)
            log("!! C: 只剩 %.0f GB (< 10), 唔做 Windows 鏡像 (封存喺 D: 照樣完整)" % c_free)
            write(os.path.join(F, "WINDOWS_MIRROR_SKIPPED.txt"), "C: had only %.1f GB free at %s, so the Windows mirror was skipped. The complete archive is on D: at %s.\n" % (c_free, self.now, F))
            arch_mirror_skipped = True
        else:
            arch_mirror_skipped = False
        for root, _, fs in os.walk(F if not arch_mirror_skipped else os.path.join(F, "__none__")):
            rel_root = os.path.relpath(root, F)
            if "leaf_proofs" in rel_root.split(os.sep):
                continue
            for f in fs:
                rel = os.path.relpath(os.path.join(root, f), F)
                cp(os.path.join(root, f), os.path.join(win_dir, os.path.dirname(rel))); n_m += 1
        try:
            write(os.path.join(win_dir, "LEAF_PROOFS_LOCATION.txt"),
                  "The %d leaf proofs (+ %d audit proofs) are NOT mirrored here (C: has no room). They live on D: at %s/L1pp/leaf_proofs/ "
                  "(Windows path %s). SHA256SUMS lists every file including the proofs; SHA256SUMS.small lists only the files present in this mirror.%s\n" % (
                      n_leaf, n_aud, F, F.replace("/mnt/d/", "D:\\").replace("/", "\\") + "\\L1pp\\leaf_proofs\\",
                      " NOTE: the whole Windows mirror was skipped this run (C: nearly full) — see WINDOWS_MIRROR_SKIPPED.txt in the D: archive." if arch_mirror_skipped else ""))
        except Exception as e:
            log("!! Windows 鏡像說明檔寫唔到 (%r) —— D: 封存唔受影響" % e)
        arch = {"dir": F, "windows_mirror": (None if arch_mirror_skipped else win_dir), "mirror_skipped": arch_mirror_skipped, "c_free_gb": (round(c_free, 1) if c_free is not None else None),
                "n_files": ss["n_files"], "bytes": ss["bytes"], "sha256sums_sha256": ss["sha256sums_sha256"], "check_rc": ss["check_rc"],
                "leaf_proofs_moved": moved, "n_leaf_proofs": n_leaf, "n_audit_proofs": n_aud, "mirror_files": n_m, "record_candidate_md": rec_md, "when": time.strftime("%Y-%m-%d %H:%M:%S")}
        self.save(archive=arch)
        return arch

    def write_reverify(self, F, fa):
        S = ",".join(map(str, fa["S"])); tag = fa["tag"]
        txt = """#!/bin/bash
# reverify.sh — independent re-verification of this archived certificate set.
# Needs the v1.0 tool environment: ~/hadwiger/{phase2,phase2b,phase3b,phase3c,phase3d}, kissat, drat-trim, march_cu, cake_lpr; python venv ~/hadwiger/venv.
# Wall-clock on 14 threads: ~3 h (step 3 dominates: every one of the %d leaf proofs is re-checked).
set -u
cd "$(dirname "$0")"
PY=/home/user/hadwiger/venv/bin/python
T=$(mktemp -d)
RC=0
step () { if [ "$2" = "0" ]; then echo "   [PASS] $1"; else echo "   [FAIL] $1 (rc=$2)"; RC=1; fi }
echo "== 1. integrity (every file, including the leaf proofs)"
sha256sum -c --quiet SHA256SUMS; step "SHA256SUMS" $?
echo "== 2. rebuild base.cnf from S (must match L1pp/base.cnf byte for byte)"
$PY /home/user/hadwiger/phase3b/buildg2.py --remove %s --out "$T" --tag base --protected run/batches_g2.json | cut -c1-200
A=$(sha256sum "$T/base.cnf" | cut -d' ' -f1); B=$(sha256sum L1pp/base.cnf | cut -d' ' -f1)
echo "   rebuilt $A"; echo "   archived $B"
[ "$A" = "$B" ]; step "base.cnf rebuilt from S matches the archived one" $?
echo "== 3. L1'' : ALL %d leaf proofs (drat-trim) + cover certificate + audit proofs"
$PY /home/user/hadwiger/phase3c/verify_final.py --attempt-dir L1pp --tag %s --keep-dir L1pp/leaf_proofs --skip-l3 --tmp "$T/vf" --json-out "$T/verify_final_reverify.json" | tail -8
step "every leaf proof + cover + audit re-verified" $?
echo "== 4. cake_lpr cross-check on a 5%% sample (formally verified checker) + lrat-check"
$PY /home/user/hadwiger/phase3d/crosscheck3d.py --attempt-dir L1pp --tag %s --keep-dir L1pp/leaf_proofs --out "$T" --frac 0.05 | tail -4
step "cake_lpr + lrat-check sample" $?
echo "== 5. L2''/L3''/completeness/spindle A+B (fresh run from S)"
$PY /home/user/hadwiger/phase3b/l3g2.py --remove %s --out "$T/l3" --engine-b | tail -8
step "L2''/L3''/exactfield --complete/spindle A+B" $?
C=$(sha256sum "$T/l3/G3p.edge" | cut -d' ' -f1); D=$(sha256sum L2L3/l3_final/G3p.edge | cut -d' ' -f1)
[ "$C" = "$D" ]; step "G3p.edge from a fresh run matches the archived one" $?
echo "== 6. 5-colouring (fresh solve + edge-by-edge check of the archived colouring)"
$PY /home/user/hadwiger/phase2/certify4.py "$T/l3/G3p.edge" --out "$T/col5" --k 5 --tag c5 --expect sat --timeout 3600 | tail -3
step "fresh 5-colouring" $?
$PY - <<'EOF'
import sys
E=[tuple(map(int,l.split()[1:3])) for l in open("L2L3/l3_final/G3p.edge") if l.startswith("e")]
n=max(max(u,v) for u,v in E)
col={int(a):int(b) for a,b in (l.split() for l in open("COL5/col5/G3p_5col.col") if len(l.split())==2)}
bad=[(u,v) for u,v in E if col.get(u) is None or col.get(v) is None or col.get(u)==col.get(v)]
ok = (not bad) and set(col)==set(range(1,n+1)) and all(1<=c<=5 for c in col.values())
print("archived 5-colouring: %%d vertices, %%d/%%d edges bichromatic, colours %%s -> %%s" %% (len(col), len(E)-len(bad), len(E), sorted(set(col.values())), "OK" if ok else "FAILED"))
sys.exit(0 if ok else 1)
EOF
step "archived 5-colouring edge-by-edge" $?
rm -rf "$T"
if [ "$RC" = "0" ]; then echo "REVERIFY DONE: ALL CHECKS PASSED $(date)"; else echo "REVERIFY DONE: !! SOME CHECKS FAILED $(date)"; fi
exit $RC
""" % (S, fa["leaves"], tag, tag, S)
        write(os.path.join(F, "reverify.sh"), txt)

    def write_readme(self, F, fa, vres, xres, c5, n_leaf, n_aud):
        cb = json.load(open(os.path.join(fa["dir"], "cnc_" + fa["tag"], "bundle.json")))
        smf_p = os.path.join(fa["dir"], "l3_final", "summary.json"); sm_p = os.path.join(fa["dir"], "l3", "summary.json")
        sm = json.load(open(smf_p)) if os.path.exists(smf_p) else json.load(open(sm_p))
        lr = vres.get("leaf_reverify") or {}; ar = vres.get("audit_reverify") or {}
        G2n, G2m, G3n, G3m = fa["G2p_n"], fa["G2p_m"], fa["G3p_n"], fa["G3p_m"]
        rec = self.rec_ok; vok = self.vok
        title = ("# RECORD_README.md — a Moser-spindle-free 5-chromatic unit-distance graph on %d vertices (staging for v1.1; **NOT released**)" % G3n) if rec else (
                ("# RECORD_README.md — %d-vertex graph, independent re-verification FAILED (EVIDENCE ONLY, see VERIFY_FAILED.md)" % G3n) if not vok else
                ("# RECORD_README.md — improved Moser-spindle-free 5-chromatic unit-distance graph on %d vertices (not a record; **NOT released**)" % G3n))
        L = [title, "",
             ("Archived %s by `scripts/phase3d/finalize3d.py` (run `%s`, certificate `%s`, seeded from Phase 3c `%s` %s). Author of the project: King Tat Wong (Amber). "
              "Every statement below is backed by a machine certificate in this directory and was re-verified from those files at archive time%s." % (
                 self.now, self.rid, fa["tag"], (self.st.get("seed") or {}).get("run_id"), (self.st.get("seed") or {}).get("last_certified_tag"),
                 " (`L1pp/verify_final.json`, `L1pp/crosscheck.json`, `L1pp/col5_check.json`: all_ok = true)" if vok else
                 " — **EXCEPT that the re-verification did not pass; see VERIFY_FAILED.md. Do not rely on this archive until `bash reverify.sh` passes.**")), "",
             "## 1. The graph", "",
             "* **G2′ = G2 − S**: Haugland's graph G2 (1066 vertices, 6264 edges; exact coordinates in ℚ(ζ₈₄)) minus a certified removable set S of **%d** vertices ⇒ **|V(G2′)| = %d, |E(G2′)| = %d**." % (len(fa["S"]), G2n, G2m),
             "* **G3′ = G2′ ∪ ρ(G2′)**, ρ(z) = (z+1)(7+i√15)/8 − 1 (exact, in ℚ(ζ₄₂₀)); G2′ ∩ ρ(G2′) = {u = (−1,0)} ⇒ **|V(G3′)| = %d, |E(G3′)| = %d**." % (G3n, G3m),
             "* G3′ is an induced subgraph of Haugland's 2131-vertex graph G3 (arXiv:2608.04542), so it is a unit-distance graph in the plane, it contains **no Moser spindle**, and it is 5-colourable — all three re-certified here from scratch (§2).",
             "* **Certified statement: G3′ has no proper 4-colouring, i.e. χ(G3′) = 5.**", "",
             "| quantity | value |", "|---|---|", "| vertices of G3′ | **%d** |" % G3n, "| edges of G3′ | **%d** |" % G3m,
             "| vertices of G2′ (the half we shrink) | %d |" % G2n, "| edges of G2′ | %d |" % G2m, "| deleted G2 vertices (S) | %d |" % len(fa["S"]),
             "| our previous certified graph (Phase 3c) | %d vertices |" % PREV_G3P,
             "| smallest previously known spindle-free 5-chromatic UDG — Heule, *Geombinatorics* 31(2), 2021, as cited in Haugland arXiv:2608.04542 (**bibliographic value; that graph was NOT re-verified here**) | %d vertices |" % RECORD_G3P, "",
             "S (G2 vertex indices, 1-based, in the v1.0 numbering of `G2.cvtx`/`G2.edge` produced by `scripts/phase2/haugland.py`):", "", "```", str(fa["S"]), "```", "",
             "## 2. The proof chain and where every certificate is", "",
             "| step | statement | files | how to check |", "|---|---|---|---|",
             ("| L1″ | every proper 4-colouring of G2′ gives col(−1,0) = col(1,0) (the *mono-pair property*). `L1pp/base.cnf` (sha `%s`) is the 4-colouring CNF of G2′ (ALO + AMO + edge clauses, one triangle through u pinned to colours 1,2,3) plus 4 clauses ¬(col(u)=c ∧ col(v)=c); it is UNSAT. | `L1pp/base.{cnf,json}`, `L1pp/cubes_d14.icnf` (march_cu, %d cubes), `L1pp/cnc_%s/{bundle.json,state.json,ledger.csv}`, **`L1pp/leaf_proofs/*.drat` (%d binary DRAT files)**, `L1pp/cnc_%s/cover_pure.{cnf,drat}`, `L1pp/leaf_proofs/audit/` (%d proofs), `L1pp/LEAF_INDEX.json` | every leaf: rebuild `base.cnf` + the cube's unit clauses (sha in `state.json`), then `drat-trim cube.cnf leaf.drat` → `s VERIFIED`. The cover certificate shows the negated cubes are jointly unsatisfiable, i.e. the cubes cover the whole search space. `scripts/phase3c/verify_final.py` does all of it; result: `L1pp/verify_final.json` (leaf %s/%s re-verified, cover %s, audit complete %s). |" % (
                 cb["base_sha"], cb["n_cubes0"], fa["tag"], n_leaf, fa["tag"], n_aud, lr.get("ok"), lr.get("n"), (vres.get("cover_reverify") or {}).get("verified"), ar.get("complete"))),
             ("| cake_lpr cross-check | a %.0f%% sample of the leaf proofs also passes the **formally verified** checker cake_lpr (CakeML) and the independent `lrat-check`, via `drat-trim -L` LRAT. | `L1pp/crosscheck.json` (%s/%s sampled leaves, all three checkers) | `scripts/phase3d/crosscheck3d.py --attempt-dir L1pp --tag %s --keep-dir L1pp/leaf_proofs --out DIR --frac 0.05` |" % (
                 self.a.frac * 100, (xres or {}).get("ok"), (xres or {}).get("n_sampled"), fa["tag"])),
             ("| L2″ | identity and ρ map V(G2′) injectively into V(G3′), and every edge of G2′ into E(G3′) — computed with exact cyclotomic arithmetic, not index tables; plus **completeness**: `exactfield.py check --complete` certifies that each edge list is the complete unit-distance graph on its exact point set. | `L2L3/l3_final/{G2p,G3p}.{cvtx,edge}`, `maps.json`, `summary.json` (`L2`, `complete_G2p`, `complete_G3p`); `L2L3/l3/` is the same computation done during the campaign (byte-identical: %s) | `scripts/phase3b/l3g2.py --remove <S> --out DIR --engine-b`; `scripts/phase2/exactfield.py check G3p.cvtx G3p.edge --complete` |" % (
                 (vres.get("l3_final") or {}).get("same_files_as_campaign_l3"))),
             ("| L3″ | the 4-colouring CNF of G3′ plus 16 lemma clauses (col(u)=col(v) and col(u)=col(ρv), as bi-implications per colour) is UNSAT. Together with L1″ applied to both copies, this proves G3′ has no proper 4-colouring. | `L2L3/l3_final/L3pp.{cnf,drat,json}` (kissat UNSAT, drat-trim VERIFIED; drat sha `%s`) | `drat-trim L3pp.cnf L3pp.drat` |" % (
                 ((sm.get("L3") or {}).get("sha") or {}).get("L3pp.drat"))),
             ("| spindle-free | G3′ contains no Moser spindle as a subgraph. Engine A: exact enumeration of all rhombi → %s copies. Engine B: SAT subgraph-monomorphism CNF is UNSAT with a drat-trim VERIFIED proof. Both engines agree. | `L2L3/l3_final/summary.json` (`spindle_A`, `spindle_B`), `L2L3/l3_final/spindle_B/{spindle.cnf,spindle.drat}` | `scripts/phase2/spindlefind.py both G3p.edge --out DIR` |" % (
                 (sm.get("spindle_A") or {}).get("copies"))),
             ("| 5-colourable | an explicit proper 5-colouring of G3′, every one of the %d edges checked bichromatic (twice: the archived colouring re-checked in plain Python, and a fresh solve of the 5-colouring CNF). | `COL5/col5/G3p_5col.col` (+`.json`), `COL5/col5_final/`, `L1pp/col5_check.json` | `scripts/phase2/certify4.py G3p.edge --out DIR --k 5 --expect sat` |" % G3m), "",
             "Chain: **L1″ (mono-pair for G2′) + L2″ (exact embeddings) + L3″ (lemma CNF UNSAT) ⇒ G3′ is not 4-colourable**; with the explicit 5-colouring, χ(G3′) = 5; with the spindle-free certificate, G3′ is a Moser-spindle-free 5-chromatic unit-distance graph on %d vertices." % G3n, "",
             "## 3. Independent re-verification performed at archive time (from the files in this directory)", "", "```",
             json.dumps({"rebuild_base_cnf_from_S": self.rb,
                         "verify_final": {k: v for k, v in vres.items() if k in ("all_ok", "base_sha_consistent", "leaf_count_consistent", "leaf_ids_are_all_root_cubes", "cover_reverify", "audit_reverify", "exactfield_complete_G3p_again", "t_s")}
                         | {"leaf_reverify": {k: v for k, v in lr.items() if k != "bad"}, "l3_final": {k: v for k, v in (vres.get("l3_final") or {}).items() if k in ("rc", "all_ok", "G2p", "G3p", "L3", "spindle_A", "spindle_B", "same_files_as_campaign_l3")}},
                         "cake_lpr_crosscheck": {k: v for k, v in (xres or {}).items() if k not in ("records", "sampled_ids", "bad")},
                         "five_colouring": c5}, ensure_ascii=False, indent=1, default=str)[:9000], "```", "",
             "Re-run everything with `bash reverify.sh` (about 3 h on 14 threads).", "",
             "## 4. Provenance and cost", "",
             "* Seed: Phase 3c run `%s`, certificate `%s` (S_acc = %s vertices, |G2′| = %s, |G3′| = %s; its own full archive with all leaf proofs is in `../final/`)." % (
                 (self.st.get("seed") or {}).get("run_id"), (self.st.get("seed") or {}).get("last_certified_tag"),
                 (1066 - ((self.st.get("seed") or {}).get("G2p_n") or 0)) or "?", (self.st.get("seed") or {}).get("G2p_n"), (self.st.get("seed") or {}).get("G3p_n")),
             "* Phase 3d cut %d further G2 vertices in one shot (candidate order: G2 degree ascending, |Im z| descending, index ascending; protected set P2 = {172, 187, 646, 994} never touched)." % (len(fa["S"]) - 270),
             "* Attempts: %s. Budget: %.1f / %.0f CPU-h (Σ certificate wall-clock × %d workers), %.2f / %.0f h wall-clock; per-certificate cap 8 h + up to 1 h automatic extension when the run was nearly finished." % (
                 [(x["tag"], x["status"], round((x.get("wall_s") or 0) / 3600, 2)) for x in self.attempts], self.st.get("cpu_h_used") or 0, (self.st.get("config") or {}).get("cpu_cap_h", 160), self.W, (self.st.get("elapsed_s") or 0) / 3600, (self.st.get("config") or {}).get("total_cap", 86400) / 3600),
             "* Solver / checkers (same binaries as v1.0; sha256 in `L1pp/cnc_%s/bundle.json` → `tools`): kissat (proofs), drat-trim (checking), march_cu (cube-and-conquer split), cake_lpr + lrat-check (cross-check). `scripts/phase3c/cnc2k.py` = the audited v1.0 `cnc2.py` plus `--keep-dir` (leaf proofs are kept instead of deleted); the diff is `scripts/phase3c/cnc2k.diff`." % fa["tag"],
             "* Ledger of all attempts: `run/ledger_g2.md`; blocking sets from SAT attempts (if any): `run/state.json` → `B_sets`.", "",
             "## 5. Integrity", "",
             "`SHA256SUMS` covers every file here (`<sha256>  <relative path>`; check with `sha256sum -c SHA256SUMS`). `SHA256SUMS.small` lists the subset mirrored to the Windows staging folder, which omits `L1pp/leaf_proofs/`.", "",
             "Not released: Amber (K. T. Wong) reviews first — no git push, no Zenodo version, no e-mail."]
        write(os.path.join(F, "RECORD_README.md"), "\n".join(L) + "\n")

    def write_record_candidate(self, F, fa, vres, xres, c5):
        assert self.rec_ok, "write_record_candidate 只可以喺獨立重驗通過而且 < %d 之後叫" % RECORD_G3P
        G2n, G2m, G3n, G3m = fa["G2p_n"], fa["G2p_m"], fa["G3p_n"], fa["G3p_m"]
        cb = json.load(open(os.path.join(fa["dir"], "cnc_" + fa["tag"], "bundle.json")))
        lr = vres.get("leaf_reverify") or {}
        shas = {"L1pp/base.cnf": cb["base_sha"],
                "L1pp/cnc_%s/cover_%s.drat" % (fa["tag"], cb["cover_mode"]): cb["cover"][cb["cover_mode"]]["proof_sha"],
                "L1pp/cnc_%s/bundle.json" % fa["tag"]: sha(os.path.join(fa["dir"], "cnc_" + fa["tag"], "bundle.json"))}
        for sub, files in (("l3_final", ("G2p.cvtx", "G2p.edge", "G3p.cvtx", "G3p.edge", "L3pp.cnf", "L3pp.drat", "maps.json", "summary.json")),):
            for f in files:
                p = os.path.join(fa["dir"], sub, f)
                if os.path.exists(p):
                    shas["L2L3/%s/%s" % (sub, f)] = sha(p)
        for f in glob.glob(os.path.join(fa["dir"], "l3_final", "spindle_B", "*")):
            shas["L2L3/l3_final/spindle_B/" + os.path.basename(f)] = sha(f)
        for f in ("G3p_5col.col", "G3p_5col.json"):
            p = os.path.join(fa["dir"], "col5", f)
            if os.path.exists(p):
                shas["COL5/col5/" + f] = sha(p)
        L = ["# RECORD_CANDIDATE.md —— |G₃′| = %d < %d (Phase 3d, %s)" % (G3n, RECORD_G3P, self.now), "",
             "## 廣東話摘要 (俾 Amber)", "",
             "- **圖**: G₃′ = (G₂ − S) ∪ ρ(G₂ − S), **%d 點 %d 邊**, 平面單位距離圖, **冇 Moser spindle**(兩個引擎), **5 色可染**(逐邊覆核), **機器證書話唔可以 4 色** ⇒ χ(G₃′) = 5." % (G3n, G3m),
             "- **紀錄**: 我哋上一個已認證圖係 %d 點 (Phase 3c); 文獻已知最細嘅無-spindle 5-chromatic UDG 係 %d 點 (Amber 提供嘅數, 我哋冇獨立重驗過)。而今 **%d < %d**." % (PREV_G3P, RECORD_G3P, G3n, RECORD_G3P),
             "- **剪咗**: S = %d 粒 G₂ 頂點 (|G₂′| = %d 點 %d 邊); 最後一張證書 %s; 保護集 P₂ = {172, 187, 646, 994} 冇郁過." % (len(fa["S"]), G2n, G2m, fa["tag"]),
             "- **獨立重驗全部通過**: 全部 %s/%s 個 leaf 證明由碟上檔案重跑 drat-trim ✓; cover 證書重建 + 重驗 ✓; 審計證明 ✓; %s/%s 個 leaf 再經形式化驗證過嘅 cake_lpr + lrat-check ✓; L2″/L3″/exactfield --complete/spindle 兩引擎由零重跑 ✓; 5 色染色逐邊覆核 ✓." % (
                 lr.get("ok"), lr.get("n"), (xres or {}).get("ok"), (xres or {}).get("n_sampled")),
             "- **封存**: `%s` (%s 個檔; leaf 證明喺 `L1pp/leaf_proofs/`); 重驗一句: `bash %s/reverify.sh` (約 3 h, 14 threads)." % (F, (self.fs.get("archive") or {}).get("n_files", "?"), F),
             "- **未公開、未寄信、未 push、未上 Zenodo** —— 等你決定.", "",
             "## Statement (English)", "",
             "G3′ is a unit-distance graph in the plane with **%d vertices and %d edges** (exact coordinates: `L2L3/l3_final/G3p.cvtx`; complete unit-distance edge list certified by `exactfield.py check --complete`: `G3p.edge`). "
             "It contains **no Moser spindle** as a subgraph (exact rhombus enumeration: 0 copies; SAT subgraph-monomorphism CNF: UNSAT with a drat-trim VERIFIED proof), it is **5-colourable** (explicit colouring, all %d edges checked bichromatic), "
             "and it has **no proper 4-colouring** (cube-and-conquer: %s leaf DRAT proofs, all drat-trim VERIFIED, plus a verified cover certificate; assembled through the exact embeddings L2″ and the lemma CNF L3″). Hence **χ(G3′) = 5**." % (G3n, G3m, G3m, lr.get("n")), "",
             "S = `%s` (%d G2 vertices)." % (fa["S"], len(fa["S"])), "",
             "## Key certificate hashes (sha256)", "", "| file | sha256 |", "|---|---|"] + ["| `%s` | `%s` |" % (k, v) for k, v in shas.items()] + [
             "| `L1pp/leaf_proofs/*.drat` (%s files) | listed individually in `SHA256SUMS` and `L1pp/LEAF_INDEX.json`; sha256 of the sorted concatenation of all leaf-proof hashes: `%s` |" % (lr.get("n"), lr.get("proof_sha_sum_sha256")), "",
             "## How to re-verify (one command)", "", "```bash", "cd %s" % F, "bash reverify.sh", "```", "",
             "Or piece by piece: `sha256sum -c SHA256SUMS`; `drat-trim L1pp/cnc_%s/cover_%s.cnf L1pp/cnc_%s/cover_%s.drat`; `drat-trim L2L3/l3_final/L3pp.cnf L2L3/l3_final/L3pp.drat`; "
             "`python3 scripts/phase2/exactfield.py check L2L3/l3_final/G3p.cvtx L2L3/l3_final/G3p.edge --complete`; `python3 scripts/phase2/spindlefind.py both L2L3/l3_final/G3p.edge --out /tmp/spB`." % (
                 fa["tag"], cb["cover_mode"], fa["tag"], cb["cover_mode"]), "",
             "Status: **RECORD_CANDIDATE — waiting for Amber (K. T. Wong).** Not published, not e-mailed, not pushed, no Zenodo version."]
        p = os.path.join(F, "RECORD_CANDIDATE.md"); write(p, "\n".join(L) + "\n")
        cp(p, PH3D); cp(p, os.path.join(WIN, "phase3d"))
        return p

    # ---------------- 4. reduction/phase3d_G2_final ----------------
    def stage_small(self):
        self.step("封存細檔 → %s/phase3d_G2_final (+ 重算 reduction/SHA256SUMS)" % STAGE)
        if self.a.dry_run:
            return {"dry_run": True}
        D = os.path.join(STAGE, "phase3d_G2_final")
        for f in ("state.json", "attempts.json", "ledger_g2.md", "status.json", "probe3d.log", "finalize_status.json"):
            cp(os.path.join(self.rdir, f), D)
        for x in self.attempts:
            tag = x["tag"]; sd = x.get("dir") or os.path.join(self.rdir, tag); dd = os.path.join(D, tag)
            for f in ("base.cnf", "base.json", "cubes_d14.icnf", "march.log", "cnc.log", "l3g2.log", "col5.log", "col5_final.log",
                      "verify_final.json", "verify_final.log", "crosscheck.json", "crosscheck.log", "col5_check.json"):
                cp(os.path.join(sd, f), dd)
            for f in glob.glob(os.path.join(sd, "G2minus_*.col")) + glob.glob(os.path.join(sd, "G2minus_*.json")):
                cp(f, dd)
            for f in ("bundle.json", "cover_pure.cnf", "cover_pure.drat", "ledger.csv", "state.json", "status.json", "keep_repair.json"):
                cp(os.path.join(sd, "cnc_" + tag, f), os.path.join(dd, "cnc"))
            for sub in ("l3", "l3_final", "col5", "col5_final"):
                for f in glob.glob(os.path.join(sd, sub, "*")):
                    if os.path.isfile(f):
                        cp(f, os.path.join(dd, sub))
                for f in glob.glob(os.path.join(sd, sub, "spindle_B", "*")):
                    cp(f, os.path.join(dd, sub, "spindle_B"))
            for f in glob.glob(os.path.join(sd, "witness", "*")):
                cp(f, os.path.join(dd, "witness"))
        for f in glob.glob(os.path.join(PH3D, "*.py")) + glob.glob(os.path.join(PH3D, "*.sh")):
            cp(f, os.path.join(STAGE, "scripts", "phase3d"))
        best = self.st.get("best") or {}
        L = ["# PHASE3D_README.md — Phase 3d: the last cut (run %s; staged %s; NOT released)" % (self.rid, self.now), "",
             "Same certificate types as `../REDUCTION_README.md` §A (L1″ cube-and-conquer bundle, L2″/L3″ assembly, blocking colourings), continuing Phase 3c. "
             "Difference: **one cut of %d vertices instead of several rounds of 30** (a certificate costs the same whether we delete 30 or 80 — march_cu always splits into ~16 384 cubes), "
             "per-certificate cap 8 h + up to 1 h automatic extension when a run is nearly finished, at most 3 certificates (a/b/c). "
             "The complete certificate set of the final graph, including every leaf proof, is in `%s`." % (
                 (best.get("removed") or 0) - 270, (self.fs.get("archive") or {}).get("dir", ARCH_ROOT)), "",
             "Seed: Phase 3c `%s` %s — S_acc = 270, |G2′| = 796, |G3′| = %d." % ((self.st.get("seed") or {}).get("run_id"), (self.st.get("seed") or {}).get("last_certified_tag"), PREV_G3P), "",
             "| attempt | \\|S\\| | result | cubes | leaves | mean solve+verify / cube | max cube | wall (extension) | CPU-h (×%d) | \\|G2′\\| | \\|G3′\\| | L2″/L3″/complete/spindle A+B | 5-colouring | blocking set B |" % self.W,
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for x in self.attempts:
            L.append("| %s | %d | %s | %s | %s | %s s | %s s | %.2f h%s | %.1f | %s | %s | %s | %s | %s |" % (
                x["tag"], x["removed"], x["status"], x.get("n_cubes"), x.get("leaves"), x.get("mean_sv_s"), x.get("max_solve_s"),
                (x.get("wall_s") or 0) / 3600, (" (+%.2f h)" % ((x.get("extended_s") or 0) / 3600)) if x.get("extended_s") else "", (x.get("wall_s") or 0) * self.W / 3600,
                x.get("G2p_n") or (x["cnf"]["n_remaining"] if x.get("cnf") else "—"), x.get("G3p_n") or "—",
                ("all OK" if x.get("l3_ok") else "!!") if x["status"] == "certified" else "—",
                ("OK (%s edges)" % (x.get("col5") or {}).get("edges_checked")) if x.get("col5_ok") else "—",
                ("|B|=%d %s" % (x["B_size"], x["witness"]["blocked_min"])) if x.get("witness") else "—"))
        L += ["", "Final certified removable set S (%d vertices) = %s" % (len(self.st["S_acc"]), self.st["S_acc"]), "",
              "Stop reason: %s" % self.st.get("stop_reason"), "",
              "Record candidate (|G3′| < %d **and** independent re-verification passed): %s" % (RECORD_G3P, self.rec_ok)]
        if self.st.get("B_sets"):
            L += ["", "Blocking sets from SAT attempts (each has a machine-checkable 4-colouring of G2 − B with col(u) ≠ col(v), i.e. B cannot be deleted as a whole):"]
            L += ["- %s: |B| = %d, B = %s" % (b["tag"], b["size"], b["B"]) for b in self.st["B_sets"]]
        write(os.path.join(D, "PHASE3D_README.md"), "\n".join(L) + "\n")
        ss = shasums(STAGE, self.W)
        n_m = 0
        for root, _, fs in os.walk(D):
            for f in fs:
                rel = os.path.relpath(os.path.join(root, f), STAGE); cp(os.path.join(root, f), os.path.join(WIN_STAGE, os.path.dirname(rel))); n_m += 1
        for f in glob.glob(os.path.join(STAGE, "scripts", "phase3d", "*")):
            cp(f, os.path.join(WIN_STAGE, "scripts", "phase3d")); n_m += 1
        cp(os.path.join(STAGE, "SHA256SUMS"), WIN_STAGE)
        res = {"dir": D, "reduction_files": ss["n_files"], "reduction_bytes": ss["bytes"], "check_rc": ss["check_rc"], "mirrored": n_m}
        self.save(stage=res); log("reduction/: %d 檔 %.1f MB, sha256sum -c rc=%d; 鏡像 %d 檔" % (ss["n_files"], ss["bytes"] / 1e6, ss["check_rc"], n_m))
        return res

    # ---------------- 5. 報告 / facts / DECISION / MEMORY ----------------
    def report(self, fa, vres, xres, c5, arch, stg):
        self.step("寫 phase3d_results.md")
        st = self.st; W = self.W; lr = vres.get("leaf_reverify") or {}
        G2n, G2m, G3n, G3m = (fa or {}).get("G2p_n"), (fa or {}).get("G2p_m"), (fa or {}).get("G3p_n"), (fa or {}).get("G3p_m")
        L = ["# phase3d_results.md —— Phase 3d: 最後一刀 (一刀剪 %s 粒; run %s, 接力 Phase 3c %s)" % (
                (len(fa["S"]) - 270) if fa else "?", self.rid, (st.get("seed") or {}).get("last_certified_tag")), "",
             "定稿 %s (自動收爐 finalize3d.py). 開跑 %s; probe3d 停 %s; Phase 3d wall %.2f h / %.0f h; **CPU-h (Σ 證書 wall × %d) %.1f / %.0f**." % (
                 self.now, st.get("started"), st.get("finished"), (st.get("elapsed_s") or 0) / 3600, (st.get("config") or {}).get("total_cap", 86400) / 3600, W,
                 st.get("cpu_h_used") or 0, (st.get("config") or {}).get("cpu_cap_h", 160)), "",
             "## 一句結果", ""]
        if fa and self.rec_ok:
            L += ["**RECORD_CANDIDATE:|G₃′| = %d 點 %d 邊 < %d** —— 無 Moser spindle(兩引擎)、5 色可染(逐邊覆核)、唔可以 4 色(全部機器證書);"
                  "獨立重驗全部通過(%s/%s 個 leaf 證明重跑 drat-trim、%s/%s 個再經 cake_lpr + lrat-check、cover、審計、L2″/L3″/完整性/spindle 由零重跑、5 色重解)。"
                  "封存 `%s`;**未公開 / 未寄信 / 未 push / 未上 Zenodo,等 Amber**。詳見 `RECORD_CANDIDATE.md`。" % (
                      G3n, G3m, RECORD_G3P, lr.get("ok"), lr.get("n"), (xres or {}).get("ok"), (xres or {}).get("n_sampled"), arch.get("dir"))]
        elif fa and self.vok:
            L += ["**有進步但未到 %d**:最終認證圖 |G₂′| = %d(%d 邊),**|G₃′| = %d(%d 邊)**,由 Phase 3c 嘅 %d 點再細 %d 點;獨立重驗全部通過;封存 `%s`。" % (
                RECORD_G3P, G2n, G2m, G3n, G3m, PREV_G3P, PREV_G3P - G3n, arch.get("dir"))]
        elif fa:
            L += ["**!! 有 certified 證書但獨立重驗唔過**:|G₃′| = %d,verify_final all_ok=%s、cake_lpr all_ok=%s、5 色 all_ok=%s —— **唔算數**,封存只係證據(`%s`,VERIFY_FAILED.md);要人手睇。" % (
                G3n, vres.get("all_ok"), (xres or {}).get("all_ok"), (c5 or {}).get("all_ok"), arch.get("dir"))]
        else:
            L += ["**冇新證書**:%d 次嘗試全部冇拎到 certified;最新認證圖仍然係 Phase 3c 嘅 |G₃′| = %d(封存喺 `../final/`)。停機原因:%s" % (
                len(self.attempts), PREV_G3P, st.get("stop_reason"))]
        L += ["", "## 設計修正 (Amber 2026-09-08) 同今次點做", "",
              "- **成本按證書計,唔係按粒數計**:march_cu d=14 每次都切約 16 384 個 cube,剪 30 同剪 80 一樣貴 ⇒ 今次**一刀剪 80 粒**(Phase 3c 用咗 6 輪 × 30 粒 = 271.9 CPU-h 先剪到 180 粒)。",
              "- **唔用細規則殺死接近完成嘅 run**:每張證書輪上限 8 h,cnc2k budget-stop 之後如果剩餘估計 ≤ 0.5 h 就自動 `--resume` 延長(累計 ≤ 1 h)。Phase 3c round 10 就係喺 15 698/16 384(差 ~9 分鐘)撞 3.5 h 上限而報廢。",
              "- 預算:%.0f CPU-h、%.0f h wall、最多 3 張證書(a/b/c);SAT 就 witness 分析出擋路集 B,排除之後由候選表補足返到 |S| = %d 再證。" % (
                  (st.get("config") or {}).get("cpu_cap_h", 160), (st.get("config") or {}).get("total_cap", 86400) / 3600, (st.get("config") or {}).get("target_removed", 350)), "",
              "## 帳 (每張證書)", "",
              "| 嘗試 | |S| | 結果 | cube | leaf | 每 cube s+v (s) | 最長 cube (s) | wall (延長) | CPU-h | |G₂′| | |G₃′| | 認證 | 擋路集 B |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for x in self.attempts:
            L.append("| %s | %d | %s | %s | %s | %s | %s | %.2f h%s | %.1f | %s | %s | %s | %s |" % (
                x["tag"], x["removed"], x["status"], x.get("n_cubes", "—"), x.get("leaves", "—"), x.get("mean_sv_s", "—"), x.get("max_solve_s", "—"),
                (x.get("wall_s") or 0) / 3600, (" (+%.2f)" % ((x.get("extended_s") or 0) / 3600)) if x.get("extended_s") else "", (x.get("wall_s") or 0) * W / 3600,
                x.get("G2p_n") or (x["cnf"]["n_remaining"] if x.get("cnf") else "—"), x.get("G3p_n", "—"),
                ("L2″/L3″/完整/spindle A+B %s, 5 色 %s" % ("✓" if x.get("l3_ok") else "!!", "✓" if x.get("col5_ok") else "!!")) if x["status"] == "certified" else "—",
                ("|B|=%d %s" % (x["B_size"], x["witness"]["blocked_min"])) if x.get("witness") else "—"))
        L += ["", "停機原因:**%s**" % st.get("stop_reason"), ""]
        if st.get("B_sets"):
            L += ["## 擋路集 (SAT 嘅收穫: 下一步嘅地圖)", "",
                  "每個 B 都有一張逐邊覆核嘅 4 色染色證書 —— G₂ − B 有一個 col(u) ≠ col(v) 嘅 4 色染色 ⇒ **B 唔可以成集剪走**(入面至少一粒係 mono-pair 性質嘅必要頂點)。", ""]
            L += ["- **%s**: |B| = %d, B = `%s`(染色證書 `%s`)" % (b["tag"], b["size"], b["B"], os.path.basename(b.get("witness_col") or "")) for b in st["B_sets"]]
            L += [""]
        if fa:
            L += ["## 最終認證圖", "",
                  "- 證書 %s;S = %d 粒 G₂ 頂點(名單喺 `L1pp/base.json` / `run/state.json`);|G₂′| = **%d** 點 **%d** 邊;|G₃′| = 2|G₂′| − 1 = **%d** 點 **%d** 邊。" % (fa["tag"], len(fa["S"]), G2n, G2m, G3n, G3m),
                  "- 證明鏈:L1″(%s 個 leaf DRAT + cover + 5%% 審計,全部 drat-trim VERIFIED)+ L2″(精確映射 + exactfield --complete)+ L3″(引理 CNF UNSAT)⇒ G₃′ 冇 4 色染色;加 5 色染色(逐邊覆核)⇒ χ(G₃′) = 5;spindle 兩引擎 copies = 0。" % lr.get("n"),
                  "- **獨立重驗(由碟上檔案出發)**:由 S 重建 base.cnf sha 一致 = **%s**;verify_final all_ok = **%s**(leaf %s/%s drat-trim + sha 一致,%.0f s,%s GB;cover %s;審計完整 %s;l3_final 由零重跑 all_ok %s,同戰役檔案 byte 一致 %s;exactfield --complete 再跑 rc %s);"
                  "cake_lpr 交叉覆核 all_ok = **%s**(%s/%s 個 leaf,三個檢查器);5 色覆核 all_ok = **%s**。" % (
                      self.rb.get("ok"), vres.get("all_ok"), lr.get("ok"), lr.get("n"), lr.get("wall_s") or 0, lr.get("proof_total_gb"), (vres.get("cover_reverify") or {}).get("verified"),
                      (vres.get("audit_reverify") or {}).get("complete"), (vres.get("l3_final") or {}).get("all_ok"),
                      all(((vres.get("l3_final") or {}).get("same_files_as_campaign_l3") or {"x": None}).values()) if (vres.get("l3_final") or {}).get("same_files_as_campaign_l3") else "n/a",
                      (vres.get("exactfield_complete_G3p_again") or {}).get("rc"), (xres or {}).get("all_ok"), (xres or {}).get("ok"), (xres or {}).get("n_sampled"), (c5 or {}).get("all_ok")), "",
                  "## 封存清單", "",
                  "- `%s`(D:;%s 檔 %.2f GB;SHA256SUMS sha256 `%s`;`sha256sum -c` rc=%s):`L1pp/`(base.cnf/json、cubes_d14.icnf、cnc_%s/{bundle,state,ledger,cover_pure.*}、**`leaf_proofs/` %s 個 leaf DRAT + `audit/` %s 個**、LEAF_INDEX.json、verify_final.json、crosscheck.json、col5_check.json)、`L2L3/l3/` + `L2L3/l3_final/`(含 spindle_B/)、`COL5/`(5 色染色)、`run/`、`scripts/`、`RECORD_README.md`(英文)、`reverify.sh`%s。" % (
                      arch.get("dir"), arch.get("n_files"), (arch.get("bytes") or 0) / 1e9, (arch.get("sha256sums_sha256") or "")[:16], arch.get("check_rc"), fa["tag"],
                      arch.get("n_leaf_proofs"), arch.get("n_audit_proofs"), "、`RECORD_CANDIDATE.md`" if self.rec_ok else ("、`RECORD_CANDIDATE_BLOCKED.md`" if G3n < RECORD_G3P else "")),
                  "- Windows 鏡像 `%s`(唔含 leaf 證明,有 LEAF_PROOFS_LOCATION.txt + SHA256SUMS.small)。" % arch.get("windows_mirror"),
                  "- 細檔 `%s/phase3d_G2_final/`(PHASE3D_README.md;reduction/ 共 %s 檔,`sha256sum -c` rc=%s),鏡像 Windows。" % (STAGE, stg.get("reduction_files"), stg.get("check_rc")), ""]
        L += ["## 老實講明", "",
              "- 「%d 點」呢個文獻紀錄數字係 Amber 提供,我哋**冇**獨立重驗過;我哋自己認證嘅只係上面呢幅圖嘅點數、邊數、無 spindle、5 色可染、唔可 4 色。" % RECORD_G3P,
              "- CPU-h 一律用 wall × %d 計(同 Phase 3b/3c 一致),唔係 solver 實際 CPU 秒(實際數字喺 attempts.json 嘅 cpu_solve_s / cpu_verify_s)。" % W,
              "- 冇公開任何嘢:冇 git push、冇 Zenodo new version、冇 email。", ""]
        txt = "\n".join(L)
        if self.a.dry_run:
            write(os.path.join(PH3D, "selftest", "phase3d_results_dryrun.md"), txt); self.save(report="dry-run"); return txt
        write(os.path.join(PH3D, "phase3d_results.md"), txt); write(os.path.join(WIN, "phase3d", "phase3d_results.md"), txt)
        self.save(report=os.path.join(WIN, "phase3d", "phase3d_results.md"))
        return txt

    def facts(self, fa, vres, xres, c5, arch, stg):
        self.step("facts.json (g2shrink3d.*)")
        fp = os.path.join(WIN, "paper", "facts.json")
        fp_out = os.path.join(PH3D, "facts_dryrun.json") if self.a.dry_run else fp
        try:
            F = json.load(open(fp, encoding="utf-8")); facts = F["facts"]; n0 = len(facts); st = self.st
            def add(key, value, unit=None, source=None, note=None, verified=True):
                facts[key] = {"value": value, "unit": unit, "source": source, "note": note, "verified": verified}
            add("g2shrink3d.run_id", self.rid, None, "phase3d/runs/%s/state.json" % self.rid)
            add("g2shrink3d.seed", st.get("seed"), None, "phase3d/runs/%s/state.json (Phase 3c r09a provenance: bundle/l3 sha)" % self.rid)
            add("g2shrink3d.params", {"one_cut_removed": (st.get("config") or {}).get("target_removed"), "attempts_max": (st.get("config") or {}).get("attempts"),
                                      "cpu_cap_h": (st.get("config") or {}).get("cpu_cap_h"), "wall_cap_h": ((st.get("config") or {}).get("total_cap") or 0) / 3600,
                                      "round_cap_h": ((st.get("config") or {}).get("cap") or 0) / 3600, "auto_extend_h": ((st.get("config") or {}).get("extend") or 0) / 3600,
                                      "extend_eta_h": (st.get("config") or {}).get("extend_eta_h"), "workers": (st.get("config") or {}).get("workers"),
                                      "depth": (st.get("config") or {}).get("depth"), "kissat_timeout_s": (st.get("config") or {}).get("timeout")},
                None, "Amber's Phase 3d mega-prompt 2026-09-08; probe3d.py argv")
            add("g2shrink3d.attempts", [{k: x.get(k) for k in ("tag", "removed", "status", "n_cubes", "leaves", "mean_solve_s", "median_solve_s", "mean_sv_s", "max_solve_s", "wall_s",
                                                               "extended_s", "cnc_launches", "cpu_solve_s", "cpu_verify_s", "proof_total_mb", "split_events", "solver_errors", "wasted_s",
                                                               "G2p_n", "G2p_m", "G3p_n", "G3p_m", "l3_ok", "col5_ok", "B_size")} | {"cpu_h_wall_x_workers": round((x.get("wall_s") or 0) * self.W / 3600, 2),
                                                                                                                                     "B": (x.get("witness") or {}).get("blocked_min")} for x in self.attempts],
                None, "phase3d/runs/%s/attempts.json" % self.rid)
            add("g2shrink3d.B_sets", st.get("B_sets"), None, "phase3d/runs/%s/state.json (each B has an edge-checked 4-colouring of G2 − B with col(u) != col(v))" % self.rid)
            add("g2shrink3d.stop_reason", st.get("stop_reason"), None, "phase3d/runs/%s/state.json" % self.rid)
            add("g2shrink3d.cpu_h_used", st.get("cpu_h_used"), "CPU-h (wall×%d)" % self.W, "phase3d/runs/%s/state.json" % self.rid)
            add("g2shrink3d.wall_h", round((st.get("elapsed_s") or 0) / 3600, 2), "h", "phase3d/runs/%s/state.json" % self.rid)
            if fa:
                add("g2shrink3d.S_final", fa["S"], None, "phase3d/runs/%s/state.json (S_acc)" % self.rid, "certified removable set of G2 vertices")
                add("g2shrink3d.G2p_final", {"n": fa["G2p_n"], "m": fa["G2p_m"]}, None, "%s/L2L3/l3_final/summary.json (exactfield --complete)" % arch.get("dir"))
                add("g2shrink3d.G3p_final", {"n": fa["G3p_n"], "m": fa["G3p_m"], "below_%d" % RECORD_G3P: fa["G3p_n"] < RECORD_G3P, "previous_ours": PREV_G3P},
                    None, "%s/L2L3/l3_final/summary.json + RECORD_README.md" % arch.get("dir"),
                    "Moser-spindle-free (engines A+B), 5-colourable (edge-checked), no proper 4-colouring (L1''+L2''+L3'')", verified=bool(self.vok))
                add("g2shrink3d.final_certificate", {"tag": fa["tag"], "base_sha256": fa["rec"]["cnf"]["cnf_sha256"], "leaves": fa["leaves"],
                                                     "leaf_proofs_dir": os.path.join(arch.get("dir", ""), "L1pp", "leaf_proofs"), "cover_mode": json.load(open(os.path.join(fa["dir"], "cnc_" + fa["tag"], "bundle.json")))["cover_mode"]},
                    None, "phase3d/runs/%s/attempts.json" % self.rid)
                add("g2shrink3d.verify_final", {k: v for k, v in vres.items() if k in ("all_ok", "base_sha_consistent", "leaf_count_consistent", "leaf_ids_are_all_root_cubes", "cover_reverify", "audit_reverify", "exactfield_complete_G3p_again", "t_s")}
                    | {"leaf_reverify": {k: v for k, v in (vres.get("leaf_reverify") or {}).items() if k != "bad"},
                       "l3_final": {k: v for k, v in (vres.get("l3_final") or {}).items() if k in ("rc", "all_ok", "same_files_as_campaign_l3", "spindle_A", "spindle_B")}},
                    None, "%s/L1pp/verify_final.json (every leaf proof re-checked from disk)" % arch.get("dir"))
                add("g2shrink3d.rebuild_base_from_S", self.rb, None, "finalize3d.py: buildg2.py --remove <S> 重跑, sha 對封存嘅 base.cnf", "closes the loop 'the CNF really is G2 minus S'", verified=bool(self.rb.get("ok")))
                add("g2shrink3d.crosscheck_cake_lpr", {k: v for k, v in (xres or {}).items() if k not in ("records", "sampled_ids", "bad")}, None, "%s/L1pp/crosscheck.json" % arch.get("dir"))
                add("g2shrink3d.five_colouring", c5, None, "%s/L1pp/col5_check.json + COL5/" % arch.get("dir"))
                add("g2shrink3d.record_candidate", self.rec_ok, None, "phase3d/runs/%s/state.json (probe3d record_candidate=%s) AND finalize independent re-verification (verify_final %s, cake_lpr %s, 5-col %s)" % (
                    self.rid, st.get("record_candidate"), vres.get("all_ok"), (xres or {}).get("all_ok"), (c5 or {}).get("all_ok")),
                    "true only when |G3'| < %d AND all three independent re-verifications passed" % RECORD_G3P, verified=bool(self.vok))
                add("g2shrink3d.archive", arch, None, "finalize3d.py (SHA256SUMS)")
                add("g2shrink3d.staging", stg, None, "finalize3d.py (reduction/SHA256SUMS)")
            if fa:
                add("g2shrink3d.vs_heule_1441", {"ours_G3p_n": fa["G3p_n"], "heule_1441": RECORD_G3P, "below": fa["G3p_n"] < RECORD_G3P, "our_previous": PREV_G3P,
                                                 "note_on_1441": "existing fact record.heule_1441 (Heule, Geombinatorics 31(2) 2021, as cited in Haugland arXiv:2608.04542); we did NOT re-verify that graph — only our own is machine-certified here"},
                    None, "derived from g2shrink3d.G3p_final and record.heule_1441", verified=bool(self.vok))
            F["generated"] = time.strftime("%Y-%m-%d %H:%M:%S")
            if "Phase 3d additions (g2shrink3d.*)" not in (F.get("note") or ""):
                F["note"] = (F.get("note") or "") + " | Phase 3d additions (g2shrink3d.*) by phase3d/finalize3d.py."
            write(fp_out, json.dumps(F, indent=1, ensure_ascii=False))
            self.save(facts="%d → %d facts → %s" % (n0, len(facts), fp_out)); log("facts: %d → %d → %s" % (n0, len(facts), fp_out))
        except Exception as e:
            self.save(facts="!! %r" % e); log("!! facts 失敗: %r" % e)

    def decision(self, fa, vres, xres, arch):
        self.step("DECISION.md 路線 A 加一段")
        p = os.path.join(WIN, "phase2b", "DECISION.md"); st = self.st
        try:
            s = open(p, encoding="utf-8").read()
            marker = "**Phase 3d 最後一刀"
            if fa:
                head = ("**RECORD_CANDIDATE:|G₃′| = %d < %d(獨立重驗全部通過)—— 等 Amber**" % (fa["G3p_n"], RECORD_G3P)) if self.rec_ok else (
                    ("**!! |G₃′| = %d < %d 但獨立重驗唔過(BLOCKED)**" % (fa["G3p_n"], RECORD_G3P)) if fa["G3p_n"] < RECORD_G3P else
                    ("有進步:|G₃′| = %d(未到 %d)" % (fa["G3p_n"], RECORD_G3P)))
                body = "最終認證圖 |G₂′| = %d 點 %d 邊,**|G₃′| = %d 點 %d 邊**(L1″+L2″+L3″ + exactfield --complete + spindle 兩引擎 + 5 色逐邊覆核);獨立重驗:全部 %s 個 leaf 證明重跑 drat-trim %s、%s 個 leaf 經 cake_lpr %s。" % (
                    fa["G2p_n"], fa["G2p_m"], fa["G3p_n"], fa["G3p_m"], (vres.get("leaf_reverify") or {}).get("n"), "✓" if vres.get("all_ok") else "!!", (xres or {}).get("n_sampled"), "✓" if (xres or {}).get("all_ok") else "!!")
            else:
                head = "冇新證書(%d 次嘗試)" % len(self.attempts); body = "最新認證圖仍然係 Phase 3c 嘅 |G₃′| = %d。" % PREV_G3P
            para = ("%s(%s;run %s,接力 Phase 3c r09a;Amber 設計修正:成本按證書計 ⇒ 一刀剪 80 粒,唔再分輪;輪上限 8 h + 自動延長 1 h;最多 3 張證書;預算 %.0f CPU-h / %.0f h wall;只加呢一段,其他原文不動):** %s。%s "
                    "嘗試 %s;CPU-h %.1f / %.0f,wall %.2f h;停機原因:%s。%s報告 `phase3d/phase3d_results.md`。**未公開、未寄信、未 push、未上 Zenodo。**" % (
                        marker, self.now, self.rid, (st.get("config") or {}).get("cpu_cap_h", 160), ((st.get("config") or {}).get("total_cap") or 86400) / 3600,
                        head, body, [(x["tag"], x["status"], round((x.get("wall_s") or 0) / 3600, 2)) for x in self.attempts],
                        st.get("cpu_h_used") or 0, (st.get("config") or {}).get("cpu_cap_h", 160), (st.get("elapsed_s") or 0) / 3600,
                        (st.get("stop_reason") or "").replace("\n", " "),
                        ("全套證書(含全部 leaf proofs)封存 `%s`(D:),細檔 `release_v1_1_staging/reduction/phase3d_G2_final/`;" % arch.get("dir")) if fa else ""))
            if marker in s:
                s = re.sub(r"\*\*Phase 3d 最後一刀.*?(?=\n\n)", lambda m: para, s, count=1, flags=re.S)
            else:
                anchor = "\n\n---\n\n## 路線 B"
                assert anchor in s, "DECISION.md 搵唔到路線 B 錨點"
                s = s.replace(anchor, "\n\n" + para + anchor, 1)
            if not self.a.dry_run:
                write(p, s)
            else:
                write(os.path.join(PH3D, "DECISION_dryrun.md"), s)
            self.save(decision="ok (%d 字)" % len(para)); log("DECISION.md: 路線 A 加一段")
        except Exception as e:
            self.save(decision="!! %r" % e); log("!! DECISION.md 失敗: %r" % e)

    def memory(self, fa, vres, xres, arch):
        self.step("MEMORY 更新 (hadwiger-project.md / no-spindle-hardness.md / MEMORY.md)")
        st = self.st
        try:
            if fa:
                one = ("Phase 3d 完 (%s): run %s 一刀剪 %d 粒 (%s), **|G₂′| %d, |G₃′| %d**%s; 獨立重驗 %s (全部 %s 個 leaf drat-trim + %s 個 cake_lpr + cover + 審計 + L2″/L3″/完整性/spindle 兩引擎 + 5 色逐邊); "
                       "CPU %.1f/%.0f CPU-h, wall %.2f h; 全套證書封存 %s; 報告 phase3d/phase3d_results.md; 未公開") % (
                    self.now[:16], self.rid, len(fa["S"]) - 270, ", ".join("%s:%s" % (x["tag"], x["status"]) for x in self.attempts), fa["G2p_n"], fa["G3p_n"],
                    (" **< %d 紀錄候選, 等 Amber**" % RECORD_G3P) if self.rec_ok else ((" (< %d 但重驗唔過, BLOCKED)" % RECORD_G3P) if fa["G3p_n"] < RECORD_G3P else " (未到 %d)" % RECORD_G3P),
                    "all_ok ✓" if self.vok else "!! 唔過", (vres.get("leaf_reverify") or {}).get("n"), (xres or {}).get("n_sampled"),
                    st.get("cpu_h_used") or 0, (st.get("config") or {}).get("cpu_cap_h", 160), (st.get("elapsed_s") or 0) / 3600, arch.get("dir"))
            else:
                one = "Phase 3d 完 (%s): run %s %d 次嘗試冇新證書 (%s); 最新認證圖仍然係 Phase 3c |G₃′| %d; 停: %s; 報告 phase3d/phase3d_results.md" % (
                    self.now[:16], self.rid, len(self.attempts), ", ".join("%s:%s" % (x["tag"], x["status"]) for x in self.attempts), PREV_G3P, (st.get("stop_reason") or "")[:120])
            out = {}
            p = os.path.join(MEM, "hadwiger-project.md"); s = open(p, encoding="utf-8").read()
            block = ("**Phase 3d(%s;Mega-Prompt「最後一刀」;源碼 `Desktop\\spindle\\phase3d\\`,WSL `~/hadwiger/phase3d/`;run `%s`):** %s。"
                     "設計修正:成本按證書計(march d=14 每次都係 ~16 384 cube)⇒ 一刀剪 80 粒;輪上限 8 h + 剩餘 ≤ 0.5 h 自動延長 ≤ 1 h(Phase 3c round 10 就係差 9 分鐘被 3.5 h 上限殺死);最多 3 張證書 a/b/c,SAT 就 witness 出擋路集 B 再補足重試。"
                     "%s重跑收爐:`phase3d/resume3d.sh`(probe3d --resume → finalize3d 幂等)。") % (
                         st.get("started"), self.rid, one,
                         ("擋路集 %s。" % [(b["tag"], b["size"]) for b in st.get("B_sets") or []]) if st.get("B_sets") else "")
            if "**Phase 3d(" in s:
                s = re.sub(r"\*\*Phase 3d\(.*?(?=\n\n\*\*How to apply)", lambda m: block, s, count=1, flags=re.S)
            elif "\n\n**How to apply:**" in s:
                s = s.replace("\n\n**How to apply:**", "\n\n" + block + "\n\n**How to apply:**", 1)
            else:
                s = s.rstrip("\n") + "\n\n" + block + "\n"
            m = re.search(r'^description: "(.*)"\s*$', s, re.M)
            if m and "Phase 3d" not in m.group(1):
                s = s.replace(m.group(0), 'description: "%s; %s"' % (m.group(1), one.replace('"', "'")[:260]), 1)
            out["hadwiger-project.md"] = len(block)
            if not self.a.dry_run:
                write(p, s)
            else:
                write(os.path.join(PH3D, "mem_dryrun_hadwiger-project.md"), s)
            p2 = os.path.join(MEM, "no-spindle-hardness.md"); s2 = open(p2, encoding="utf-8").read()
            cert = [x for x in self.attempts if x.get("status") == "certified"]
            b2 = ("**Phase 3d(%s,`phase3d/`)—— 一刀剪 80 粒:** %d/%d 張證書 certified;每張 wall %s h、每 cube s+v %s s、最長 cube %s s;%s。"
                  "教訓:剪 30 同剪 80 一樣貴(cube 數一樣),所以應該一刀剪到目標;cnc2k budget-stop 之後 `--resume` 可以無損續(cnc2k 會 drain 住嘅 cube 先停)。") % (
                self.now[:10], len(cert), len(self.attempts), [round((x.get("wall_s") or 0) / 3600, 2) for x in cert], [x.get("mean_sv_s") for x in cert], [x.get("max_solve_s") for x in cert],
                ("|G₃′| = %d%s" % (fa["G3p_n"], " < %d 紀錄候選" % RECORD_G3P if self.rec_ok else "")) if fa else "三次都 SAT / 冇證書, 擋路集 %s" % [(b["tag"], b["size"]) for b in st.get("B_sets") or []])
            if "**Phase 3d(" in s2:
                s2 = re.sub(r"\*\*Phase 3d\(.*?(?=\n\n\*\*Why)", lambda m: b2, s2, count=1, flags=re.S)
            elif "\n\n**Why:**" in s2:
                s2 = s2.replace("\n\n**Why:**", "\n\n" + b2 + "\n\n**Why:**", 1)
            else:
                s2 = s2.rstrip("\n") + "\n\n" + b2 + "\n"
            out["no-spindle-hardness.md"] = len(b2)
            if not self.a.dry_run:
                write(p2, s2)
            else:
                write(os.path.join(PH3D, "mem_dryrun_no-spindle-hardness.md"), s2)
            p3 = os.path.join(MEM, "MEMORY.md"); s3 = open(p3, encoding="utf-8").read(); lines = s3.split("\n"); done = False
            for i, l in enumerate(lines):
                if l.startswith("- [Hadwiger project](hadwiger-project.md)"):
                    head = l.split(";Phase 3b 三輪")[0].split(";**Phase 3c")[0].split(";Phase 3c")[0].split(";**Phase 3d")[0].split(";Phase 3b/3c")[0]
                    tail_txt = (("**RECORD_CANDIDATE |G₃′| = %d < %d,獨立重驗通過,等 Amber**" % (fa["G3p_n"], RECORD_G3P)) if self.rec_ok else
                                (("|G₃′| = %d(%s)" % (fa["G3p_n"], "重驗唔過 BLOCKED" if not self.vok else "未到 %d" % RECORD_G3P)) if fa else "冇新證書")).replace("\n", " ")
                    lines[i] = head + ";Phase 3b/3c 已收爐(|G₃′| 1591,`phase3c/phase3c_results.md`);**Phase 3d 完(%s)**:%s;報告 `phase3d/phase3d_results.md`;冇背景任務" % (self.now[:16], tail_txt)
                    done = True
            if not done:
                lines.append("- [Hadwiger project](hadwiger-project.md) — %s" % one[:300])
            out["MEMORY.md"] = "index line updated" if done else "appended"
            if not self.a.dry_run:
                write(p3, "\n".join(lines))
            else:
                write(os.path.join(PH3D, "mem_dryrun_MEMORY.md"), "\n".join(lines))
            self.save(memory=out); log("MEMORY: %s" % out)
        except Exception as e:
            self.save(memory="!! %r" % e); log("!! MEMORY 失敗: %r" % e)

    # ---------------- run ----------------
    def run(self):
        if not self.st.get("best"):
            log("冇新證書 (state.best 冇): 只寫報告 / facts / DECISION / MEMORY")
            self.vok = None; self.rec_ok = False
            self.report(None, {}, {}, {}, {}, {}); self.facts(None, {}, {}, {}, {}, {}); self.decision(None, {}, {}, {}); self.memory(None, {}, {}, {})
            self.fs["done"] = True; self.fs["finished"] = time.strftime("%Y-%m-%d %H:%M:%S"); self.fs["all_done"] = True; self.save(); self.flag_status()
            self.step("收爐完 (冇新證書, %s)" % self.fs["finished"]); log("FINALIZE3D DONE: 冇新證書"); return
        fa = self.final_attempt()
        log("最終認證圖: %s |G₂′| %d 點 %d 邊, |G₃′| %d 點 %d 邊 (%s); leaf 證明 %s" % (fa["tag"], fa["G2p_n"], fa["G2p_m"], fa["G3p_n"], fa["G3p_m"],
            "< %d ⇒ 紀錄候選 (未重驗)" % RECORD_G3P if fa["G3p_n"] < RECORD_G3P else "≥ %d" % RECORD_G3P, fa["keep_dir"]))
        self.save(final={k: v for k, v in fa.items() if k not in ("rec", "S")})
        self.rb = self.rebuild_base(fa)
        vres = self.verify(fa)
        xres = self.crosscheck(fa)
        c5 = self.col5(fa, vres)
        self.vok = bool(self.rb.get("ok") is True and vres.get("all_ok") is True and xres.get("all_ok") is True and c5.get("all_ok") is True)
        self.rec_ok = bool(self.vok and fa["G3p_n"] < RECORD_G3P)
        self.improved = bool(fa["G3p_n"] < PREV_G3P)
        self.save(verify_all_ok=self.vok, record_candidate_confirmed=self.rec_ok, improved=self.improved)
        if not self.a.dry_run:
            self.flag_status()
        log("獨立重驗總結: verify_final %s + cake_lpr %s + 5 色 %s ⇒ vok=%s, record_candidate=%s" % (vres.get("all_ok"), xres.get("all_ok"), c5.get("all_ok"), self.vok, self.rec_ok))
        arch = self.archive(fa, vres, xres, c5)
        stg = self.stage_small()
        self.report(fa, vres, xres, c5, arch, stg)
        self.facts(fa, vres, xres, c5, arch, stg)
        self.decision(fa, vres, xres, arch)
        self.memory(fa, vres, xres, arch)
        self.fs["done"] = True; self.fs["finished"] = time.strftime("%Y-%m-%d %H:%M:%S"); self.fs["all_done"] = True; self.save()
        if not self.a.dry_run:
            self.flag_status()
        self.step("收爐完 (%s): %s" % (self.fs["finished"], "RECORD_CANDIDATE (等 Amber)" if self.rec_ok else ("重驗唔過, 要人手睇" if not self.vok else "有進步, 已封存")))
        log("FINALIZE3D DONE: vok=%s, record_candidate=%s, archive %s" % (self.vok, self.rec_ok, arch.get("dir")))
        if not self.vok:
            sys.exit(4)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True); ap.add_argument("--workers", type=int, default=14); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force-verify", action="store_true"); ap.add_argument("--frac", type=float, default=0.05)
    a = ap.parse_args()
    Fin(a).run()

if __name__ == "__main__":
    main()
