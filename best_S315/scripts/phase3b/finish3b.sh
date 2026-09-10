#!/bin/bash
# Phase 3b 縮圖循環完場收尾: 確認冇 process 跑緊, 清殘留證明檔 (記大細), 最終閘門/曲線, stage_v11 加入 Phase 3b 證書, 抄結果返 Windows
set -u
PY=/home/user/hadwiger/venv/bin/python
cd /home/user/hadwiger/phase3b
RUN=p3br1_shrink
echo "== procs =="; pgrep -fa "kissat|cnc2|drat-trim|march_cu|probe3b" | grep -v pgrep | wc -l
echo "== probe3b.log 尾 =="; grep -E "結算|PROBE3B DONE|閘門|TARGET|!!" runs/$RUN/probe3b.log | tail -8 | cut -c1-300
echo "== 殘留證明檔 =="; PD=/home/user/hadwiger/phase2b/proofs_ext4/$RUN; ls "$PD" | wc -l; du -sh "$PD" 2>/dev/null; rm -f "$PD"/*.drat; echo "已刪, 剩 $(ls "$PD" | wc -l)"
echo "== 最終閘門 / 曲線 =="; $PY hardness_g2.py --probe runs/$RUN --batches batches_g2.json --out runs/$RUN --workers 14 > runs/$RUN/hardness_final.log 2>&1; tail -6 runs/$RUN/gate_g2.md
echo "== stage_v11 (加 Phase 3b 證書) =="; $PY stage_v11.py --phase3b-run /home/user/hadwiger/phase3b/runs/$RUN 2>&1 | tail -3
echo "== syncback =="; bash /mnt/c/Users/user/Desktop/spindle/phase3b/syncback3b.sh | tail -1
cp status.md /mnt/c/Users/user/Desktop/spindle/phase3b/status.md 2>/dev/null
echo "== 磁碟 =="; df -h /mnt/d /mnt/c / | tail -3
echo "FINISH3B DONE $(date)"
