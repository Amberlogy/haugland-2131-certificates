#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
status3c.py —— Phase 3c 每 10 分鐘覆寫 status.md (手機可讀)
讀: ~/hadwiger/phase3c/{START.txt, STEP.txt}, runs/*/status.json (probe3c), 當前 campaign 嘅 cnc status.json, keep 目錄, 磁碟, finalize 狀態 (runs/*/finalize_status.json)
寫: ~/hadwiger/phase3c/status.md + Windows Desktop\\spindle\\phase3c\\status.md (同時覆寫 phase3b/status.md 舊書籤)
用法: python3 status3c.py [--interval 600] [--once]
"""
import os, sys, json, time, argparse, glob

PH = "/home/user/hadwiger/phase3c"
WIN = ["/mnt/c/Users/user/Desktop/spindle/phase3c/status.md", "/mnt/c/Users/user/Desktop/spindle/phase3b/status.md"]
SHM = "/dev/shm"

def df(path):
    try:
        st = os.statvfs(path); return st.f_bavail * st.f_frsize / 1e9
    except Exception:
        return None

def du(path, prefix=None):
    tot = 0
    try:
        for f in os.listdir(path):
            if prefix and not f.startswith(prefix):
                continue
            try:
                tot += os.path.getsize(os.path.join(path, f))
            except OSError:
                pass
    except OSError:
        pass
    return tot / 1e9

def load(p):
    try:
        return json.load(open(p))
    except Exception:
        return None

def tail(p, n=3):
    try:
        return [l.rstrip() for l in open(p, errors="ignore").read().split("\n") if l.strip()][-n:]
    except Exception:
        return []

def render():
    now = time.time(); start = None
    try:
        start = float(open(os.path.join(PH, "START.txt")).read().split("\n")[1])
    except Exception:
        pass
    step = "?"
    try:
        step = open(os.path.join(PH, "STEP.txt")).read().strip()
    except Exception:
        pass
    runs = sorted(glob.glob(os.path.join(PH, "runs", "*")))
    sts = [(os.path.basename(d), load(os.path.join(d, "status.json")), d) for d in runs]
    rec = any((st or {}).get("record_candidate") for _, st, _ in sts)
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
        title = "# Phase 3c status —— 完成 (%s); 報告 phase3c/phase3c_results.md; %s" % (fin[-1].get("finished"), "冇背景任務" if fin[-1].get("all_done") else "S60_full 補封存跑緊 (或者 finalize 失敗, 睇下面)")
    L = [title, "", "更新: %s (每 10 分鐘覆寫)" % time.strftime("%Y-%m-%d %H:%M:%S"),
         "Phase 3c 用時 (由 launch 起): %s" % ("%.1f h" % ((now - start) / 3600) if start else "?"), "", "## 當前步驟", step, ""]
    dD, dC, dR, dS = df("/mnt/d"), df("/mnt/c"), df("/"), df(SHM)
    L += ["## 磁碟", "- D: 剩 %.0f GB (keep 目錄所在, 要 ≥ 300) | C: (WSL vhdx 所在) 剩 %.0f GB (要 ≥ 25) | WSL ext4 剩 %.0f GB | /dev/shm (證明暫存) 剩 %.1f GB, 暫存中 %.2f GB" % (
        dD or -1, dC or -1, dR or -1, dS or -1, du(os.path.join(SHM, "p3c1_shrink"))), ""]
    warn = []
    if dD is not None and dD < 300:
        warn.append("!! D: 剩餘 < 300 GB → probe3c 唔會開新輪")
    if dC is not None and dC < 25:
        warn.append("!! C: 剩餘 < 25 GB (probe3c 唔會開新輪; cnc2k < 20 GB 自動暫停)")
    if dS is not None and dS < 2:
        warn.append("!! /dev/shm 剩 < 2 GB (證明暫存盤)")
    if warn:
        L += ["## 警告"] + ["- " + w for w in warn] + [""]
    L.append("## 縮圖循環 (run ID 獨一)")
    found = False
    for rid, st, d in sts:
        if not st:
            L.append("- %s: (冇 status.json) log 尾: %s" % (rid, " | ".join(tail(os.path.join(d, "probe3c.log"), 2))[:300])); found = True; continue
        found = True
        age = (now - os.path.getmtime(os.path.join(d, "status.json"))) / 60
        cs = (st.get("current") or {}).get("cnc_status")
        if cs and os.path.exists(cs):
            age = min(age, (now - os.path.getmtime(cs)) / 60)
        seed = st.get("seed") or {}
        L.append("- **%s** (接力 %s r%02d, S_acc %s 粒): round 完成 %d | S_acc %d 粒 → |G₂′| %d, |G₃′| %d (目標 ≤ 720 / < 1441) | 用時 %.2f h / %.1f h | **CPU %.1f / %.0f CPU-h** (剩 %.1f; 預測下一輪 %.2f h wall) | 連續低淨剪 %d/%d 輪 | 下一輪排除 %d 粒, 永久排除 %s%s%s%s" % (
            rid, seed.get("run_id"), seed.get("round_done") or 0, seed.get("S_acc_size"), st["round_done"], st["S_acc_size"], st["G2p_n"], st["G3p_n"], st["elapsed_s"] / 3600, st["total_cap_s"] / 3600,
            st.get("cpu_h_used") or 0, st.get("cpu_cap_h") or 0, st.get("cpu_h_remaining") or 0, st.get("proj_next_round_wall_h") or 0, st.get("low_net_streak") or 0, st.get("low_net_rounds") or 3,
            st["excluded_next"], st["perma_excluded"],
            (" | **停: %s**" % st["stop_reason"]) if st.get("stop_reason") else "", (" | !! STALE %.0f 分鐘" % age) if (age > 15 and not st.get("stop_reason")) else "",
            (" | resume ×%d" % st["resumes"]) if st.get("resumes") else ""))
        ks = st.get("keep_stats") or {}
        L.append("  - 封存 (最新認證圖 leaf 證明喺 D: %s): %s" % (st.get("keep_root"), ", ".join("%s: %d 檔 %.1f GB" % (t, v.get("n_files", 0), v.get("gb", 0)) for t, v in ks.items()) or "(未有 Phase 3c certified 輪; Phase 3b r03a 嘅 leaf 證明按舊政策已刪, 只有 sha)"))
        cur = st.get("current") or {}
        if cur and not st.get("stop_reason"):
            L.append("  - 當前嘗試 %s: 階段 %s, 剪 %s 粒, 開始 %s, 輪上限 %.2f h, keep-dir %s (暫存 %.2f GB, 已搬 %.1f GB)" % (
                cur.get("tag"), cur.get("stage"), cur.get("S_size"), cur.get("started"), (cur.get("cap_s") or 0) / 3600, cur.get("keep_dir"), du(os.path.join(SHM, "p3c1_shrink"), "cnc_%s_" % cur.get("tag")), du(cur.get("keep_dir") or "/nonexistent")))
            c = load(cur.get("cnc_status") or "")
            if c:
                cage = (now - os.path.getmtime(cur["cnc_status"])) / 60
                L.append("  - cnc2k: %s | cube 完成 %s / %s, 跑緊 %s, 重排 %s, split %s, stuck %s | 平均 %s s, 最大 %s s | 已用 %.2f h | 剩餘估計 %s | 未驗證明 %s GB | 錯誤 %s%s" % (
                    c.get("status", "running"), c.get("done"), c.get("total"), c.get("running"), c.get("retry"), c.get("split_events"), c.get("stuck"), c.get("mean_cube_s"), c.get("max_cube_s"),
                    (c.get("wall_s") or 0) / 3600, c.get("eta"), c.get("unverified_proof_gb"), c.get("last_error"), (" | !! cnc status STALE %.0f 分鐘" % cage) if cage > 10 and c.get("status") in (None, "running") else ""))
        for r in st.get("rounds", []):
            att = ", ".join("%s:%s%s" % (x["tag"], x["status"], (" (%s cube, mean s+v %s s, %.2f h%s%s)" % (x.get("n_cubes"), x.get("mean_sv_s"), (x.get("wall_s") or 0) / 3600, (", |B|=%s" % x.get("B_size")) if x.get("B_size") else "",
                                                                                                          (", keep %s/%s" % ((x.get("keep") or {}).get("kept_leaves"), x.get("leaves"))) if (x.get("keep") or {}).get("on_disk") else "")) if x.get("wall_s") else "") for x in r["attempts"])
            L.append("  - round %d%s: %s | 淨剪 %s → |G₂′| %s |G₃′| %s | %.2f h | 嘗試: %s" % (r["round"], (" (%s)" % r["from_run"]) if r.get("from_run") else "", r.get("status") or "跑緊", r.get("net_removed"), r.get("G2p_n"), r.get("G3p_n"), (r.get("wall_s") or 0) / 3600, att))
        if st.get("gate"):
            L.append("  - 完場外推 (資訊): **%s** — %s" % (st["gate"].get("verdict"), (st["gate"].get("why") or "")[:300]))
    if not found:
        L.append("- 無")
    L.append("")
    for f in fin:
        L += ["## 收爐 (finalize3c)", "- %s" % f.get("stage"), "- 開始 %s%s" % (f.get("started"), (", 完 %s" % f["finished"]) if f.get("finished") else "")]
        for k in ("verify_final", "archive", "record_candidate", "report", "facts", "decision", "memory", "s60_full"):
            if f.get(k):
                L.append("  - %s: %s" % (k, str(f[k])[:300]))
        L.append("")
    return "\n".join(L)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--interval", type=float, default=600); ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    while True:
        try:
            txt = render()
        except Exception as e:                                                             # 審查 (cosmetic): render 出錯唔可以令 10 分鐘循環死
            import traceback
            txt = "# Phase 3c status —— status3c render 出錯 (%s)\n\n```\n%s\n```\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), traceback.format_exc()[-3000:])
        for dst in [os.path.join(PH, "status.md")] + WIN:
            try:
                tmp = dst + ".tmp"; open(tmp, "w").write(txt); os.replace(tmp, dst)
            except Exception as e:
                sys.stderr.write("write %s: %s\n" % (dst, e))
        if a.once:
            print(txt); break
        time.sleep(a.interval)

if __name__ == "__main__":
    main()
