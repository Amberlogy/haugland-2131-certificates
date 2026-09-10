#!/bin/bash
# Phase 3b 第 2 步: G₂ 縮圖循環 (背景, run ID 獨一 p3br1_shrink). 最多 12 輪, 每輪硬上限 3 h, 總上限 30 h, 14 workers, march d=14, kissat T=600
bash /mnt/c/Users/user/Desktop/spindle/phase3b/sync3b.sh > /dev/null
cd /home/user/hadwiger/phase3b
PY=/home/user/hadwiger/venv/bin/python
RUN=p3br1_shrink
STALE=$(pgrep -fa 'kissat|drat-trim|cnc2|march_cu|probe3b' | grep -v pgrep | wc -l)
echo "stale solver/probe procs: $STALE"
if [ "$STALE" != "0" ]; then pgrep -fa 'kissat|drat-trim|cnc2|march_cu|probe3b' | grep -v pgrep; echo "!! 有舊 process, 唔開 (人手睇)"; exit 2; fi
pkill -f "status3b.py --interval" 2>/dev/null
mkdir -p runs/$RUN /home/user/hadwiger/phase2b/proofs_ext4/$RUN
[ -f START.txt ] || printf "Phase 3b start\n%s\n" "$(date +%s)" > START.txt
echo "Phase 3b 第 2 步開始: run $RUN round 1 (S = batch 1, 30 粒) buildg2 → march_cu d=14 → cnc2 14 workers (每輪硬上限 3 h, 總上限 30 h, 最多 12 輪; 第 3 輪後閘門). 前台做緊第 3–5 步 (v1.1 staging / 稠密圖 / 論文核數)" > STEP.txt
setsid nohup $PY status3b.py --interval 600 > status3b.log 2>&1 &
setsid nohup $PY probe3b.py --run-id $RUN --batches /home/user/hadwiger/phase3b/batches_g2.json --out /home/user/hadwiger/phase3b/runs/$RUN --rounds 12 --workers 14 --cap 10800 --total-cap 108000 --timeout 600 --depth 14 --k 30 --proof-dir /home/user/hadwiger/phase2b/proofs_ext4/$RUN > runs/$RUN/probe3b.log 2>&1 &
sleep 75; cat runs/$RUN/probe3b.log | cut -c1-260; echo "kissat procs: $(pgrep -xc kissat)"; date
