#!/bin/bash
# Phase 3c 開跑 (單次啟動): sync → 冇舊 process → START/STEP → status3c 每 10 分鐘 → setsid nohup run3c.sh (probe3c → finalize3c → s60_full → park)
bash /mnt/c/Users/user/Desktop/spindle/phase3c/sync3c.sh > /dev/null
cd /home/user/hadwiger/phase3c
PY=/home/user/hadwiger/venv/bin/python
RUN=p3c1_shrink
STALE=$(pgrep -fa 'kissat|drat-trim|cnc2|march_cu|probe3|finalize3c|s60_full|tail6|beam_udg' | grep -v pgrep | wc -l)
echo "stale solver/probe procs: $STALE"
if [ "$STALE" != "0" ]; then pgrep -fa 'kissat|drat-trim|cnc2|march_cu|probe3|finalize3c|s60_full|tail6|beam_udg' | grep -v pgrep; echo "!! 有舊 process, 唔開 (人手睇)"; exit 2; fi
if [ -f runs/$RUN/state.json ]; then echo "!! runs/$RUN/state.json 已存在 —— 要續跑用 resume3c.sh"; exit 3; fi
if ! mountpoint -q /mnt/d; then echo "!! /mnt/d 冇 mount"; exit 4; fi
mkdir -p runs/$RUN /mnt/d/hadwiger/phase3c/keep /dev/shm/$RUN
df -h /mnt/d /mnt/c /dev/shm | tail -3
printf "Phase 3c start\n%s\n" "$(date +%s)" > START.txt
echo "Phase 3c 開跑: run $RUN 由 Phase 3b r03a (S_acc 90, |G₃′| 1951) 接力, round 4 (r04a, S=120) → buildg2 → march_cu d=14 → cnc2k 14 workers (leaf 證明保留 D:); 每輪 ≤ 3.5 h, 總 400 CPU-h / 40 h wall; 停機: |G₂′| ≤ 720 / 預算 / 連續 3 輪淨剪 < 10" > STEP.txt
pkill -f "status3c.py --interval" 2>/dev/null; pkill -f "status3b.py --interval" 2>/dev/null
setsid nohup $PY status3c.py --interval 600 > status3c.log 2>&1 &
setsid nohup bash /home/user/hadwiger/phase3c/run3c.sh > runs/$RUN/run3c.nohup 2>&1 &
sleep 90
echo "== probe3c.log =="; cut -c1-300 runs/$RUN/probe3c.log | tail -12
echo "kissat procs: $(pgrep -xc kissat); status3c: $(pgrep -fc 'status3c.py --interval'); run3c: $(pgrep -fc run3c.sh)"; date
