#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
status3b.py —— Phase 3b 每 10 分鐘覆寫 status.md (手機可讀)
讀: ~/hadwiger/phase3b/{START.txt, STEP.txt, items.json}, runs/*/status.json (probe3b), 當前 campaign 嘅 cnc status.json, 磁碟
寫: ~/hadwiger/phase3b/status.md + Windows phase3b/status.md (同時覆寫 phase4/phase3/phase2b 舊書籤)
用法: python3 status3b.py [--interval 600] [--once]
"""
import os, sys, json, time, argparse, glob

PH = "/home/user/hadwiger/phase3b"
WIN = ["/mnt/c/Users/user/Desktop/spindle/phase3b/status.md", "/mnt/c/Users/user/Desktop/spindle/phase4/status.md", "/mnt/c/Users/user/Desktop/spindle/phase3/status.md", "/mnt/c/Users/user/Desktop/spindle/phase2b/status.md"]
PROOFS = "/home/user/hadwiger/phase2b/proofs_ext4"

def df(path):
    try:
        st = os.statvfs(path); return st.f_bavail * st.f_frsize / 1e9
    except Exception:
        return None

def du(path):
    tot = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                tot += os.path.getsize(os.path.join(root, f))
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
    L = ["# Phase 3b status (G₂ 縮圖戰役, Haugland 方向)", "", "更新: %s (每 10 分鐘覆寫)" % time.strftime("%Y-%m-%d %H:%M:%S"),
         "Phase 3b 用時: %s (硬上限 36 h wall)" % ("%.1f h" % ((now - start) / 3600) if start else "?"), "", "## 當前步驅", step, ""]
    dD, dC, dR = df("/mnt/d"), df("/mnt/c"), df("/")
    unv = du(PROOFS) if os.path.isdir(PROOFS) else 0
    L += ["## 磁碟", "- D: 剩 %.0f GB | C: (WSL vhdx 所在) 剩 %.0f GB | WSL ext4 剩 %.0f GB | 未驗證明 (ext4) %.2f GB" % (dD or -1, dC or -1, dR or -1, unv), ""]
    warn = []
    if dD is not None and dD < 300:
        warn.append("!! D: 剩餘 < 300 GB → 要停")
    if dC is not None and dC < 25:
        warn.append("!! C: 剩餘 < 25 GB (probe3b 唔會開新輪; cnc2 < 20 GB 自動暫停)")
    if warn:
        L += ["## 警告"] + ["- " + w for w in warn] + [""]
    items = load(os.path.join(PH, "items.json")) or {}
    L += ["## 步驟進度 (items.json)"] + ["- %s: %s" % (k, v) for k, v in items.items()] + [""]
    L += ["## 縮圖循環 (每個 run ID 獨一)"]
    found = False
    for d in sorted(glob.glob(os.path.join(PH, "runs", "*"))):
        rid = os.path.basename(d); st = load(os.path.join(d, "status.json"))
        if not st:
            L.append("- %s: (冇 status.json) log 尾: %s" % (rid, " | ".join(tail(os.path.join(d, "probe3b.log"), 2))[:300])); found = True; continue
        found = True
        age = (now - os.path.getmtime(os.path.join(d, "status.json"))) / 60
        cs = (st.get("current") or {}).get("cnc_status")
        if cs and os.path.exists(cs):
            age = min(age, (now - os.path.getmtime(cs)) / 60)     # probe status 只喺每張證書完結更新; 以 cnc2 status.json 嘅新鮮度為準
        L.append("- **%s**: round 完成 %d | S_acc %d 粒 → |G₂′| %d, |G₃′| %d | 用時 %.2f h / %.1f h | 下一輪排除 %d 粒, 永久排除 %s%s%s" % (
            rid, st["round_done"], st["S_acc_size"], st["G2p_n"], st["G3p_n"], st["elapsed_s"] / 3600, st["total_cap_s"] / 3600, st["excluded_next"], st["perma_excluded"],
            (" | **停: %s**" % st["stop_reason"]) if st.get("stop_reason") else "", (" | !! STALE %.0f 分鐘" % age) if (age > 15 and not st.get("stop_reason")) else ""))
        cur = st.get("current") or {}
        if cur and not st.get("stop_reason"):
            L.append("  - 當前嘗試 %s: 階段 %s, 剪 %s 粒, 開始 %s, 輪上限 %.1f h" % (cur.get("tag"), cur.get("stage"), cur.get("S_size"), cur.get("started"), (cur.get("cap_s") or 0) / 3600))
            c = load(cur.get("cnc_status") or "")
            if c:
                cage = (now - os.path.getmtime(cur["cnc_status"])) / 60
                L.append("  - cnc2: %s | cube 完成 %s / %s, 跑緊 %s, 重排 %s, split %s, stuck %s | 平均 %s s, 最大 %s s | 已用 %.2f h | 剩餘估計 %s | 未驗證明 %s GB | 錯誤 %s%s" % (
                    c.get("status", "running"), c.get("done"), c.get("total"), c.get("running"), c.get("retry"), c.get("split_events"), c.get("stuck"), c.get("mean_cube_s"), c.get("max_cube_s"),
                    (c.get("wall_s") or 0) / 3600, c.get("eta"), c.get("unverified_proof_gb"), c.get("last_error"), (" | !! cnc status STALE %.0f 分鐘" % cage) if cage > 10 and c.get("status") in (None, "running") else ""))
        for r in st.get("rounds", []):
            att = ", ".join("%s:%s%s" % (x["tag"], x["status"], (" (%s cube, mean s+v %s s, %.2f h%s)" % (x.get("n_cubes"), x.get("mean_sv_s"), (x.get("wall_s") or 0) / 3600, (", |B|=%s" % x.get("B_size")) if x.get("B_size") else "")) if x.get("wall_s") else "") for x in r["attempts"])
            L.append("  - round %d: %s | 淨剪 %s → |G₂′| %s |G₃′| %s | %.2f h | 嘗試: %s" % (r["round"], r.get("status") or "跑緊", r.get("net_removed"), r.get("G2p_n"), r.get("G3p_n"), (r.get("wall_s") or 0) / 3600, att))
        if st.get("gate"):
            L.append("  - 閘門: **%s** — %s" % (st["gate"].get("verdict"), (st["gate"].get("why") or "")[:400]))
    if not found:
        L.append("- 無")
    L.append("")
    for p in sorted(glob.glob(os.path.join(PH, "runs_tail", "*", "status.md"))):
        t = [l for l in open(p, errors="ignore").read().split("\n") if l.strip()]
        if t:
            L += ["## 硬尾巴 (第 6 步, %s)" % os.path.basename(os.path.dirname(p))] + [x[:400] for x in t[:20]] + [""]
    for p in sorted(glob.glob(os.path.join(PH, "beam", "status_*.json")) + glob.glob(os.path.join(PH, "beam", "*", "status_*.json"))):
        st = load(p)
        if st:
            L.append("- beam %s (%s): runs %s, n 記錄 %s, max n %s, 用時 %.1f h, 更新 %s" % (st.get("lattice"), os.path.relpath(p, PH), st.get("runs_done"), st.get("n_best"), st.get("max_n"), (st.get("elapsed_s") or 0) / 3600, st.get("updated")))
    L.append("")
    return "\n".join(L)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--interval", type=float, default=600); ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    while True:
        txt = render()
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
