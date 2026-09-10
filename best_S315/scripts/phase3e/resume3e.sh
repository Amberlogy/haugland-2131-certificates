#!/bin/bash
# Phase 3e 續跑 (跨晚 / 機器重啟 / PAUSE 之後): run3e.sh 見到 state.json 就 probe3e --resume; 已 finished 就直接收爐 (finalize3e 幂等)
# 上次係操作員停機 (needs_operator) 就要人手加 --ack-operator 跑 probe3e, 呢個腳本淨係會收爐
bash /mnt/c/Users/user/Desktop/spindle/phase3e/sync3e.sh > /dev/null
cd /home/user/hadwiger/phase3e
PY=/home/user/hadwiger/venv/bin/python
RUN=p3e1_step
STALE=$(pgrep -fa 'kissat|drat-trim|cnc2|march_cu|probe3|finalize3|run3e|cake_lpr' | grep -v pgrep | wc -l)
if [ "$STALE" != "0" ]; then pgrep -fa 'kissat|drat-trim|cnc2|march_cu|probe3|finalize3|run3e|cake_lpr' | grep -v pgrep; echo "!! 有舊 process, 唔 resume"; exit 2; fi
if [ ! -f runs/$RUN/state.json ]; then echo "!! 冇 runs/$RUN/state.json —— 首跑用 launch3e.sh"; exit 3; fi
if ! mountpoint -q /mnt/d; then echo "!! /mnt/d 冇 mount"; exit 4; fi
mkdir -p /dev/shm/$RUN /mnt/d/hadwiger/phase3e/keep
rm -f runs/$RUN/PAUSE
$PY resume3e_step.py > STEP.txt
cat STEP.txt
pkill -f "status3e.py --interval" 2>/dev/null
setsid nohup $PY status3e.py --interval 600 >> status3e.log 2>&1 &
setsid nohup bash /home/user/hadwiger/phase3e/run3e.sh >> runs/$RUN/run3e.nohup 2>&1 &
sleep 60
grep -E "resume|=====|march_cu|cnc2k 第|DONE|finalize|RECORD|round" runs/$RUN/probe3e.log | tail -6 | cut -c1-260; echo "kissat procs: $(pgrep -xc kissat)"; date
