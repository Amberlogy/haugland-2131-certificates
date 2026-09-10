#!/bin/bash
# 續跑縮圖循環 (probe3b --resume), 證明目錄改去 RAM 盤 /dev/shm (防 WSL vhdx 增長食 C:); 其他參數同 launch3b.sh 一樣
bash /mnt/c/Users/user/Desktop/spindle/phase3b/sync3b.sh > /dev/null
cd /home/user/hadwiger/phase3b
PY=/home/user/hadwiger/venv/bin/python
RUN=p3br1_shrink
STALE=$(pgrep -fa 'kissat|drat-trim|cnc2|march_cu|probe3b' | grep -v pgrep | wc -l)
if [ "$STALE" != "0" ]; then pgrep -fa 'kissat|drat-trim|cnc2|march_cu|probe3b' | grep -v pgrep; echo "!! 有舊 process, 唔 resume"; exit 2; fi
PD=/dev/shm/$RUN; mkdir -p "$PD"; df -h /dev/shm | tail -1
echo "Phase 3b 第 2 步續跑 (resume, 證明目錄 → /dev/shm RAM 盤): run $RUN, 由 round $(python3 -c "import json;print(json.load(open('runs/$RUN/state.json'))['round_done']+1)") 繼續; 每輪 ≤ 3 h, 總上限 30 h, 最多 12 輪" > STEP.txt
setsid nohup $PY probe3b.py --resume --run-id $RUN --batches /home/user/hadwiger/phase3b/batches_g2.json --out /home/user/hadwiger/phase3b/runs/$RUN --rounds 12 --workers 14 --cap 10800 --total-cap 108000 --timeout 600 --depth 14 --k 30 --proof-dir "$PD" >> runs/$RUN/probe3b.log 2>&1 &
sleep 60; grep -E "resume|=====|march_cu|cnc2 開始" runs/$RUN/probe3b.log | tail -5 | cut -c1-260; echo "kissat procs: $(pgrep -xc kissat)"; ls "$PD" | head -3; date
