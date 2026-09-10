#!/bin/bash
# Phase 3c 續跑 (跨晚 / 機器重啟 / PAUSE 之後): 同 launch3c.sh 一樣, 但 run3c.sh 見到 state.json 會 probe3c --resume; 已 finished 就直接收爐 (finalize3c 幂等)
bash /mnt/c/Users/user/Desktop/spindle/phase3c/sync3c.sh > /dev/null
cd /home/user/hadwiger/phase3c
PY=/home/user/hadwiger/venv/bin/python
RUN=p3c1_shrink
STALE=$(pgrep -fa 'kissat|drat-trim|cnc2|march_cu|probe3|finalize3c|s60_full|run3c' | grep -v pgrep | wc -l)
if [ "$STALE" != "0" ]; then pgrep -fa 'kissat|drat-trim|cnc2|march_cu|probe3|finalize3c|s60_full|run3c' | grep -v pgrep; echo "!! 有舊 process, 唔 resume"; exit 2; fi
if [ ! -f runs/$RUN/state.json ]; then echo "!! 冇 runs/$RUN/state.json —— 首跑用 launch3c.sh"; exit 3; fi
if ! mountpoint -q /mnt/d; then echo "!! /mnt/d 冇 mount"; exit 4; fi
mkdir -p /dev/shm/$RUN /mnt/d/hadwiger/phase3c/keep
rm -f runs/$RUN/PAUSE
echo "Phase 3c 續跑 (resume): run $RUN 由 round $(python3 -c "import json;print(json.load(open('runs/$RUN/state.json'))['round_done']+1)") 繼續 (state: $(python3 -c "import json;s=json.load(open('runs/$RUN/state.json'));print('S_acc',len(s['S_acc']),'cpu_h',s.get('cpu_h_used'),'elapsed_h',round((s.get('elapsed_s') or 0)/3600,2),'stop',s.get('stop_reason'))"))" > STEP.txt
pkill -f "status3c.py --interval" 2>/dev/null
setsid nohup $PY status3c.py --interval 600 >> status3c.log 2>&1 &
setsid nohup bash /home/user/hadwiger/phase3c/run3c.sh >> runs/$RUN/run3c.nohup 2>&1 &
sleep 60
grep -E "resume|=====|march_cu|cnc2k 開始|DONE|finalize" runs/$RUN/probe3c.log | tail -5 | cut -c1-260; echo "kissat procs: $(pgrep -xc kissat)"; date
