#!/bin/bash
# Phase 3b 第 6 步 (可選, 過夜 ≤ 8 h): 13 個硬尾巴 root cube 換招 (march d=12 由零重拆, 葉 kissat T=900, --max-split 0). run ID 獨一 p3bt6_tail.
# 只可以喺縮圖循環 (probe3b) 完全停低之後開 (兩邊都會 pkill kissat, 而且爭 CPU)
bash /mnt/c/Users/user/Desktop/spindle/phase3b/sync3b.sh > /dev/null
cd /home/user/hadwiger/phase3b
PY=/home/user/hadwiger/venv/bin/python
RUN=p3bt6_tail
STALE=$(pgrep -fa 'kissat|drat-trim|cnc2\.py|march_cu|probe3b\.py --run|tail6\.py --run' | grep -v -E 'pgrep|tail -n0|launch_tail6' | wc -l)
if [ "$STALE" != "0" ]; then pgrep -fa 'kissat|drat-trim|cnc2\.py|march_cu|probe3b\.py --run|tail6\.py --run' | grep -v -E 'pgrep|tail -n0|launch_tail6'; echo "!! 有舊 process (縮圖循環未停?), 唔開"; exit 2; fi
mkdir -p runs_tail/$RUN /home/user/hadwiger/phase2b/proofs_ext4/$RUN
echo "Phase 3b 第 6 步開始: run $RUN — 13 個 root cube 各自 march_cu d=12 重拆 → cnc2 kissat T=900 (14 workers, 8 h 硬上限, 唔延長)" > STEP.txt
setsid nohup $PY tail6.py --run-id $RUN --out /home/user/hadwiger/phase3b/runs_tail/$RUN --depth 12 --timeout 900 --workers 14 --total-cap 28800 --proof-dir /home/user/hadwiger/phase2b/proofs_ext4/$RUN > runs_tail/$RUN/tail6.log 2>&1 &
sleep 60; cut -c1-240 runs_tail/$RUN/tail6.log; echo "kissat procs: $(pgrep -xc kissat)"; date
