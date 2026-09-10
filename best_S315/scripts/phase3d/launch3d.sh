#!/bin/bash
# Phase 3d 開跑 (單次啟動): sync → 冇舊 process → START/STEP → status3d 每 10 分鐘 → setsid nohup run3d.sh (probe3d → finalize3d → park)
bash /mnt/c/Users/user/Desktop/spindle/phase3d/sync3d.sh > /dev/null
cd /home/user/hadwiger/phase3d
PY=/home/user/hadwiger/venv/bin/python
RUN=p3d1_final
STALE=$(pgrep -fa 'kissat|drat-trim|cnc2|march_cu|probe3|finalize3|s60_full|cake_lpr|lrat-check' | grep -v pgrep | wc -l)
echo "stale solver/probe procs: $STALE"
if [ "$STALE" != "0" ]; then pgrep -fa 'kissat|drat-trim|cnc2|march_cu|probe3|finalize3|s60_full|cake_lpr|lrat-check' | grep -v pgrep; echo "!! 有舊 process, 唔開 (人手睇)"; exit 2; fi
if [ -f runs/$RUN/state.json ]; then echo "!! runs/$RUN/state.json 已存在 —— 要續跑用 resume3d.sh"; exit 3; fi
if ! mountpoint -q /mnt/d; then echo "!! /mnt/d 冇 mount"; exit 4; fi
mkdir -p runs/$RUN /mnt/d/hadwiger/phase3d/keep /dev/shm/$RUN
df -h /mnt/d /mnt/c /dev/shm | tail -3
printf "Phase 3d start\n%s\n" "$(date +%s)" > START.txt
echo "Phase 3d 開跑: run $RUN 由 Phase 3c r09a (S_acc 270, |G₂′| 796, |G₃′| 1591) 接力, 一刀剪 80 粒 → |S| 350, |G₂′| 716, |G₃′| 1431 < 1441; buildg2 → march_cu d=14 → cnc2k 14 workers (leaf 證明保留 D:); 每張證書上限 8 h + 自動延長 ≤ 1 h; 最多 3 張 (a/b/c); 預算 160 CPU-h / 24 h wall" > STEP.txt
pkill -f "status3d.py --interval" 2>/dev/null; pkill -f "status3c.py --interval" 2>/dev/null
setsid nohup $PY status3d.py --interval 600 > status3d.log 2>&1 &
setsid nohup bash /home/user/hadwiger/phase3d/run3d.sh > runs/$RUN/run3d.nohup 2>&1 &
sleep 90
echo "== probe3d.log =="; cut -c1-300 runs/$RUN/probe3d.log | tail -12
echo "kissat procs: $(pgrep -xc kissat); status3d: $(pgrep -fc 'status3d.py --interval'); run3d: $(pgrep -fc run3d.sh)"; date
