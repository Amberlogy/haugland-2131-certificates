#!/bin/bash
# Phase 3e 重收爐 (probe3e 已經行完; finalize3e 幂等, 可以重跑):
#   2026-09-10 00:08 第一次收爐喺 write_reverify() 爆咗 (由 finalize3d.py 繼承落嚟嘅 %d/%s 格式化 bug), 獨立重驗其實全部過晒。
#   修好 make_finalize3e.py → 重新生成 finalize3e.py → 用呢個腳本重跑收爐。
#   注意: leaf 證明已經由 keep 目錄 rename 咗入封存目錄, 所以 verify_final / crosscheck 嘅快取唔啱 keep-dir, 會由頭再驗一次
#         (16382 個 leaf 證明重跑 drat-trim, 約 2.5–3 h) —— 呢次係驗**封存嗰份**, 比第一次更貼題, 唔係白做。
set -u
PY=/home/user/hadwiger/venv/bin/python
P3E=/home/user/hadwiger/phase3e; cd "$P3E"
RUN=p3e1_step; R=$P3E/runs/$RUN
# 注意: 唔可以淨係 grep -v pgrep —— 呢個腳本自己叫 refinalize3e.sh, 個名入面有 "finalize3", 會撞正自己個 pattern (同 wsl bash -lc pkill 一樣嘅陷阱)
STALEP() { pgrep -fa 'kissat|drat-trim|cnc2|march_cu|probe3|finalize3|run3e|cake_lpr|lrat-check' | grep -v pgrep | grep -v refinalize3e; }
STALE=$(STALEP | wc -l)
if [ "$STALE" != "0" ]; then STALEP; echo "!! 有舊 process, 唔重跑"; exit 2; fi
if ! mountpoint -q /mnt/d; then echo "!! /mnt/d 冇 mount"; exit 4; fi
bash /mnt/c/Users/user/Desktop/spindle/phase3e/sync3e.sh > /dev/null
echo "Phase 3e 重收爐 (finalize3e 重跑, 由封存目錄嘅 leaf 證明再驗一次; 約 3 h)" > STEP.txt
pkill -f "status3e.py --interval" 2>/dev/null
setsid nohup $PY status3e.py --interval 600 >> status3e.log 2>&1 &
setsid nohup bash /home/user/hadwiger/phase3e/refinalize3e_inner.sh > "$R/refinalize3e.nohup" 2>&1 &
sleep 45
tail -6 "$R/finalize3e.log" | cut -c1-240
echo "finalize3e procs: $(pgrep -fc 'finalize3e.py'); status3e: $(pgrep -fc 'status3e.py --interval')"; date
