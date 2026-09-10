#!/bin/bash
# Phase 3e 開跑 (單次啟動): sync → 冇舊 process → START/STEP → status3e 每 10 分鐘 → setsid nohup run3e.sh (probe3e → finalize3e → park)
bash /mnt/c/Users/user/Desktop/spindle/phase3e/sync3e.sh > /dev/null
cd /home/user/hadwiger/phase3e
PY=/home/user/hadwiger/venv/bin/python
RUN=p3e1_step
STALE=$(pgrep -fa 'kissat|drat-trim|cnc2|march_cu|probe3|finalize3|s60_full|cake_lpr|lrat-check' | grep -v pgrep | wc -l)
echo "stale solver/probe procs: $STALE"
if [ "$STALE" != "0" ]; then pgrep -fa 'kissat|drat-trim|cnc2|march_cu|probe3|finalize3|s60_full|cake_lpr|lrat-check' | grep -v pgrep; echo "!! 有舊 process, 唔開 (人手睇)"; exit 2; fi
if [ -f runs/$RUN/state.json ]; then echo "!! runs/$RUN/state.json 已存在 —— 要續跑用 resume3e.sh"; exit 3; fi
if ! mountpoint -q /mnt/d; then echo "!! /mnt/d 冇 mount"; exit 4; fi
if [ ! -f finalize3e.py ]; then echo "!! 冇 finalize3e.py (要先跑 make_finalize3e.py)"; exit 5; fi
mkdir -p runs/$RUN /mnt/d/hadwiger/phase3e/keep /dev/shm/$RUN
df -h /mnt/d /mnt/c /dev/shm | tail -3
printf "Phase 3e start\n%s\n" "$(date +%s)" > START.txt
echo "Phase 3e 開跑: run $RUN 由 Phase 3c r09a (S_acc 270, |G2'| 796, |G3'| 1591) 接力; 每輪剪 20 粒 (796 → 776 → 756 → 736 → 716), 最多 6 輪, 每輪最多 2 張證書 (a/b); 兩張都 SAT ⇒ 步幅減半 20→10→5; 排除集逐輪重置; buildg2 → march_cu d=14 → cnc2k 14 workers (leaf 證明保留 D:); 每輪上限 6 h + 自動延長 ≤ 1 h; 預算 500 CPU-h / 60 h wall (Amber 2026-09-08 放寬, 原本 160 / 24)" > STEP.txt
pkill -f "status3e.py --interval" 2>/dev/null; pkill -f "status3d.py --interval" 2>/dev/null; pkill -f "status3c.py --interval" 2>/dev/null
setsid nohup $PY status3e.py --interval 600 > status3e.log 2>&1 &
setsid nohup bash /home/user/hadwiger/phase3e/run3e.sh > runs/$RUN/run3e.nohup 2>&1 &
sleep 90
echo "== probe3e.log =="; cut -c1-300 runs/$RUN/probe3e.log | tail -12
echo "kissat procs: $(pgrep -xc kissat); status3e: $(pgrep -fc 'status3e.py --interval'); run3e: $(pgrep -fc run3e.sh)"; date
