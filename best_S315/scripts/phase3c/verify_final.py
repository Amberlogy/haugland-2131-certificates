#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_final.py —— Phase 3c 獨立重驗 (由碟上檔案出發, 唔信戰役入面嘅 in-memory 結果):
  (1) L1″: 對 certified 嘗試目錄 <dir>/cnc_<tag>/ 嘅每個 leaf: 由 base.cnf + cube 重建 cube CNF (sha 要同 state.json 記錄一致), 讀 keep 目錄嘅證明檔 (sha 要同記錶一致),
      drat-trim 逐個重驗 (要 "s VERIFIED"); cover_pure.cnf/.drat 重驗; 5% 審計證明 (keep/audit/) 有幾多重驗幾多; 要 leaf 數 == bundle.leaves == march cube 數 (含 split 後嘅 leaf, 由 state.json done 定義)
  (2) L2″/L3″/完整性/spindle A+B: 重跑 l3g2.py --remove S --engine-b 去新目錄 <dir>/l3_final/ (同戰役嘅 l3/ 獨立), 再對數 G2p/G3p edge sha 要同戰役 l3/ 一致
  (3) 精確坐標完整性: exactfield check --complete 由 l3g2 內部做; 呢度再獨立跑一次 G3p (l3_final) 記 rc
  全部結果 → <dir>/verify_final.json; 任何一步唔過 → all_ok false, rc 4. 14 workers.
用法: python3 verify_final.py --attempt-dir ~/hadwiger/phase3c/runs/p3c1_shrink/r05a --tag r05a --keep-dir /mnt/d/hadwiger/phase3c/keep/r05a [--workers 14] [--skip-l3]
"""
import sys, os, json, time, argparse, subprocess, hashlib, statistics
from concurrent.futures import ThreadPoolExecutor
if not __debug__:
    sys.exit("!! 唔准用 python -O")
PH3B = os.path.expanduser("~/hadwiger/phase3b"); PH2 = os.path.expanduser("~/hadwiger/phase2")
KISSAT = "/home/user/hadwiger/kissat/build/kissat"; DRATTRIM = "/home/user/hadwiger/drat-trim/drat-trim"
PY = sys.executable

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--attempt-dir", required=True); ap.add_argument("--tag", required=True); ap.add_argument("--keep-dir", required=True)
    ap.add_argument("--workers", type=int, default=14); ap.add_argument("--skip-l3", action="store_true"); ap.add_argument("--tmp", default=None)
    ap.add_argument("--json-out", default=None, help="結果 JSON 路徑 (預設 <attempt-dir>/verify_final.json); reverify.sh 用嚟避免覆寫已封存嘅檔")
    a = ap.parse_args()
    d = os.path.abspath(os.path.expanduser(a.attempt_dir)); tag = a.tag; cdir = os.path.join(d, "cnc_" + tag); keep = os.path.abspath(os.path.expanduser(a.keep_dir))
    out_json = os.path.abspath(os.path.expanduser(a.json_out)) if a.json_out else os.path.join(d, "verify_final.json")
    def dump(res_):
        tmp_ = out_json + ".tmp"; json.dump(res_, open(tmp_, "w"), indent=1, ensure_ascii=False); os.replace(tmp_, out_json)
    tmp = a.tmp or os.path.join("/dev/shm", "verify_final_" + tag); os.makedirs(tmp, exist_ok=True)
    T0 = time.time(); res = {"attempt_dir": d, "tag": tag, "keep_dir": keep, "when": time.strftime("%Y-%m-%d %H:%M:%S"), "workers": a.workers}
    st = json.load(open(os.path.join(cdir, "state.json"))); cb = json.load(open(os.path.join(cdir, "bundle.json"))); bj = json.load(open(os.path.join(d, "base.json")))
    base_p = os.path.join(cdir, "base.cnf"); base_sha = sha(base_p)
    res["base_sha256"] = base_sha
    res["base_sha_consistent"] = (base_sha == st["base_sha"] == cb["base_sha"] == bj["cnf_sha256"] == sha(os.path.join(d, "base.cnf")))
    res["S"] = bj["removed"]; res["n_removed"] = bj["n_removed"]; res["G2p_n_from_base"] = bj["n_remaining"]; res["G2p_m_from_base"] = bj["n_edges"]
    lines = [l for l in open(base_p) if not l.startswith(("p", "c"))]; nvars = int(open(base_p).readline().split()[2]); base_text = "".join(lines); nbase = len(lines)
    done = st["done"]; ids = sorted(done)
    res["leaves"] = len(ids); res["bundle_leaves"] = cb["leaves"]; res["n_cubes0"] = st["n_cubes0"]; res["split_events"] = st.get("split_events")
    res["leaf_count_consistent"] = (len(ids) == cb["leaves"] == len(cb["leaf_list"]))
    # cube 覆蓋: 冇 split 就 leaf id 集合 == {0..n_cubes0-1}; 有 split 就 cover 證書負責 (照樣要求 cover 重驗過)
    if not st.get("split_events"):
        res["leaf_ids_are_all_root_cubes"] = (set(ids) == {str(i) for i in range(st["n_cubes0"])})
    kept_files = set(os.listdir(keep)) if os.path.isdir(keep) else set()
    res["keep_dir_files"] = len([f for f in kept_files if f.endswith(".drat")])
    log("verify_final %s: base sha 一致 %s; leaves %d (bundle %d, root cubes %d, split %s); keep 目錄 %d 個 .drat" % (tag, res["base_sha_consistent"], len(ids), cb["leaves"], st["n_cubes0"], st.get("split_events"), res["keep_dir_files"]))

    def one(cid):
        dd = done[cid]; r = {"id": cid}
        cnf = os.path.join(tmp, "cube_%s.cnf" % cid)
        try:
            with open(cnf, "w") as f:
                f.write("p cnf %d %d\n" % (nvars, nbase + len(dd["cube"]))); f.write(base_text)
                for l in dd["cube"]:
                    f.write("%d 0\n" % l)
            r["cnf_sha_match"] = (sha(cnf) == dd["cnf_sha"])
            proof = dd.get("kept") or os.path.join(keep, "cnc_%s_%s.drat" % (tag, cid))
            if not os.path.exists(proof):
                proof2 = os.path.join(keep, os.path.basename(proof))
                proof = proof2 if os.path.exists(proof2) else proof
            r["proof"] = proof; r["proof_exists"] = os.path.exists(proof)
            if r["proof_exists"]:
                ps = sha(proof); r["proof_sha"] = ps
                want = dd.get("repaired_proof_sha") or dd["proof_sha"]
                r["proof_sha_match"] = (ps == want); r["proof_bytes"] = os.path.getsize(proof); r["proof_bytes_match"] = (r["proof_bytes"] == dd["proof_bytes"]) if not dd.get("repaired_proof_sha") else None
                t0 = time.time()
                dr = subprocess.run([DRATTRIM, cnf, proof, "-t", "20000"], capture_output=True, text=True, timeout=6 * 3600)
                r["verify_s"] = round(time.time() - t0, 2); r["verified"] = any(l.strip() == "s VERIFIED" for l in dr.stdout.splitlines())
                if not r["verified"]:
                    r["tail"] = (dr.stdout + dr.stderr)[-300:]
            r["ok"] = bool(r["cnf_sha_match"] and r["proof_exists"] and r["proof_sha_match"] and r["verified"])
        except Exception as e:
            r["ok"] = False; r["error"] = repr(e)[-300:]
        finally:
            if os.path.exists(cnf):
                os.remove(cnf)
        return r
    t0 = time.time(); recs = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for i, r in enumerate(ex.map(one, ids), 1):
            recs.append(r)
            if i % 2000 == 0 or i == len(ids):
                log("  leaf 重驗 %d/%d, ok %d, %.0f s" % (i, len(ids), sum(1 for x in recs if x["ok"]), time.time() - t0))
    bad = [r for r in recs if not r["ok"]]
    res["leaf_reverify"] = {"n": len(recs), "ok": len(recs) - len(bad), "bad": bad[:50], "n_bad": len(bad), "wall_s": round(time.time() - t0, 1),
                            "verify_cpu_s": round(sum(r.get("verify_s") or 0 for r in recs), 1), "mean_verify_s": round(statistics.mean([r.get("verify_s") or 0 for r in recs]), 3) if recs else None,
                            "proof_total_gb": round(sum(r.get("proof_bytes") or 0 for r in recs) / 1e9, 3), "proof_sha_sum_sha256": hashlib.sha256("".join(sorted(r.get("proof_sha") or "" for r in recs)).encode()).hexdigest()}
    log("L1″ leaf 重驗: %d/%d VERIFIED + sha 一致 (%.0f s, 證明共 %.2f GB)%s" % (len(recs) - len(bad), len(recs), time.time() - t0, res["leaf_reverify"]["proof_total_gb"], (" !! %d 個唔過: %s" % (len(bad), [b["id"] for b in bad[:10]])) if bad else ""))
    # cover
    cm = cb.get("cover_mode"); cov = cb["cover"][cm]
    ccnf = os.path.join(cdir, "cover_%s.cnf" % cm); cdrat = os.path.join(cdir, "cover_%s.drat" % cm)
    r = {"mode": cm, "cnf": ccnf, "drat": cdrat, "cnf_sha_match": sha(ccnf) == cov["cnf_sha"], "drat_sha_match": sha(cdrat) == cov["proof_sha"]}
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
    r["ok"] = bool(r["cnf_sha_match"] and r["drat_sha_match"] and r["verified"] and r["cover_clauses_match_negated_leaves"] and r["cover_header_nvars_ok"])
    res["cover_reverify"] = r
    log("cover (%s) 重驗: drat-trim %s, cnf sha %s, drat sha %s, 子句 == (base+)¬leaf %s, header nvars %s" % (cm, "VERIFIED ✓" if r["verified"] else "!! NOT", r["cnf_sha_match"], r["drat_sha_match"], r.get("cover_clauses_match_negated_leaves"), r.get("cover_header_nvars_ok")))
    # audit proofs (kept)
    aud = cb.get("audit", {}); akeep = os.path.join(keep, "audit"); arecs = []
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
                    fh.write("p cnf %d %d\n" % (nvars, nbase + len(dd["cube"]))); fh.write(base_text)
                    for l in dd["cube"]:
                        fh.write("%d 0\n" % l)
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
    res["partial"] = True; dump(res)                                                  # l3 之前先落地 (免 l3g2 crash 失去 1 h leaf 重驗結果)
    # l3 (fresh, engine B)
    if not a.skip_l3:
        l3f = os.path.join(d, "l3_final"); t0 = time.time()
        rl = subprocess.run([PY, os.path.join(PH3B, "l3g2.py"), "--remove", ",".join(map(str, bj["removed"])), "--out", l3f, "--engine-b"], capture_output=True, text=True, timeout=5 * 3600)
        open(os.path.join(d, "l3_final.log"), "w").write(rl.stdout + rl.stderr)
        sm = json.load(open(os.path.join(l3f, "summary.json"))) if os.path.exists(os.path.join(l3f, "summary.json")) else {}
        old = os.path.join(d, "l3")
        same = {f: (os.path.exists(os.path.join(old, f)) and os.path.exists(os.path.join(l3f, f)) and sha(os.path.join(old, f)) == sha(os.path.join(l3f, f))) for f in ("G2p.cvtx", "G2p.edge", "G3p.cvtx", "G3p.edge", "L3pp.cnf")}
        res["l3_final"] = {"rc": rl.returncode, "all_ok": sm.get("all_ok"), "wall_s": round(time.time() - t0, 1), "G2p": sm.get("G2p"), "G3p": sm.get("G3p"), "complete_G2p_rc": (sm.get("complete_G2p") or {}).get("rc"), "complete_G3p_rc": (sm.get("complete_G3p") or {}).get("rc"),
                           "L2": sm.get("L2"), "L3": {k: (sm.get("L3") or {}).get(k) for k in ("status", "verified", "drat_lines", "sha", "solve_s")}, "spindle_A": sm.get("spindle_A"), "spindle_B": sm.get("spindle_B"),
                           "same_files_as_campaign_l3": same, "dir": l3f, "sha": sm.get("sha")}
        # 獨立再跑一次 exactfield --complete (G3p)
        t0 = time.time()
        if os.path.exists(os.path.join(l3f, "G3p.cvtx")) and os.path.exists(os.path.join(l3f, "G3p.edge")):
            re_ = subprocess.run([PY, os.path.join(PH2, "exactfield.py"), "check", os.path.join(l3f, "G3p.cvtx"), os.path.join(l3f, "G3p.edge"), "--complete"], capture_output=True, text=True, timeout=3600)
            res["exactfield_complete_G3p_again"] = {"rc": re_.returncode, "last": (re_.stdout.strip().split("\n")[-1] if re_.stdout.strip() else "")[:300], "s": round(time.time() - t0, 1)}
        else:
            res["exactfield_complete_G3p_again"] = {"rc": -1, "last": "l3_final/G3p.* 唔存在 (l3g2 失敗)", "s": 0}
        log("l3_final (engine B): rc=%d all_ok=%s, G₃′ %s, L3″ %s, spindle A %s, spindle B ok=%s; 同戰役 l3/ 檔案一致 %s; exactfield --complete G3p 再跑 rc=%d" % (
            rl.returncode, sm.get("all_ok"), sm.get("G3p"), (sm.get("L3") or {}).get("status"), (sm.get("spindle_A") or {}).get("copies"), (sm.get("spindle_B") or {}).get("ok"), all(same.values()), re_.returncode))
    ok = bool(res["base_sha_consistent"] and res["leaf_count_consistent"] and res.get("leaf_ids_are_all_root_cubes", True) and not bad and res["cover_reverify"]["ok"]
              and res["audit_reverify"]["bad"] == [] and res["audit_reverify"]["complete"]
              and (a.skip_l3 or (res["l3_final"]["rc"] == 0 and res["l3_final"]["all_ok"] is True and all(res["l3_final"]["same_files_as_campaign_l3"].values()) and res["exactfield_complete_G3p_again"]["rc"] == 0)))
    res["all_ok"] = ok; res["t_s"] = round(time.time() - T0, 1); res["partial"] = False
    dump(res)
    log("verify_final %s: %s (%.0f s) → %s" % (tag, "全部通過 ✓" if ok else "!! 有步驟唔過", res["t_s"], out_json))
    try:
        os.rmdir(tmp)
    except OSError:
        pass
    sys.exit(0 if ok else 4)

if __name__ == "__main__":
    main()
