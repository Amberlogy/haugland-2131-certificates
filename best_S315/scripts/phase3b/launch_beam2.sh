#!/bin/bash
# 第 4 步加強: L run B (alpha 400, seed 7, cap 2.4 h) + Moser run B (alpha 1000, seed 7, cap 50 min), 各自獨立目錄 (結果由 make_dense_md.py 合併取每 n 最大)
cd /home/user/hadwiger/phase3b
PY=/home/user/hadwiger/venv/bin/python
mkdir -p beam/runB beam/moserB
setsid nohup nice -n 15 $PY beam_udg.py --lattice L --out /home/user/hadwiger/phase3b/beam/runB --alpha 400 --m 20 --nmax 300 --restarts 3 --time-cap 8600 --seed 7 > beam/runB/run_L.out 2>&1 &
setsid nohup nice -n 15 $PY beam_udg.py --lattice moser --out /home/user/hadwiger/phase3b/beam/moserB --alpha 1000 --m 24 --nmax 300 --restarts 2 --time-cap 3000 --seed 7 > beam/moserB/run_moser.out 2>&1 &
sleep 30; tail -2 beam/runB/beam_L.log | cut -c1-140; tail -2 beam/moserB/beam_moser.log | cut -c1-140; uptime
