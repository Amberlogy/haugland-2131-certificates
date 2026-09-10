#!/bin/bash
# Phase 3b 第 4 步 (改題): beam search 搵 L 同 Moser 格仔嘅最密單位距離子圖 (背景, nice 15, 兩個 run 並行; 縮圖戰役照跑)
bash /mnt/c/Users/user/Desktop/spindle/phase3b/sync3b.sh > /dev/null
cd /home/user/hadwiger/phase3b
PY=/home/user/hadwiger/venv/bin/python
mkdir -p beam
# smoke (改咗 backward 之後再驗一次, 20 秒)
timeout 300 nice -n 15 $PY beam_udg.py --lattice L --out beam_test --alpha 20 --m 8 --nmax 30 --restarts 1 --time-cap 200 --seed 2 2>&1 | grep -E "verification done|BEAM DONE|Error|assert" | tail -3
grep -E '^\| (10|20|30) ' beam_test/beam_L.md
echo "=== launch L (alpha 200, m 16, nmax 300, restarts 4, cap 8400 s) + moser (cap 3600 s) ==="
setsid nohup nice -n 15 $PY beam_udg.py --lattice L --out /home/user/hadwiger/phase3b/beam --alpha 200 --m 16 --nmax 300 --restarts 4 --time-cap 8400 --seed 20260906 > beam/run_L.out 2>&1 &
setsid nohup nice -n 15 $PY beam_udg.py --lattice moser --out /home/user/hadwiger/phase3b/beam --alpha 200 --m 16 --nmax 300 --restarts 3 --time-cap 3600 --seed 20260906 > beam/run_moser.out 2>&1 &
sleep 45; tail -3 beam/beam_L.log | cut -c1-160; tail -3 beam/beam_moser.log | cut -c1-160; date
