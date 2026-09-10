#!/bin/bash
# 喺輪與輪之間 (新一輪 cnc2 啱啱開) 暫停縮圖循環: 殺 probe3b + 該輪 cnc2 + solver, 刪該輪 cnc 目錄 (只損失幾分鐘), 清殘留證明檔.
# 用法: bash pause3b.sh <tag>   例如 r04a   (該 tag 嘅 campaign 會由頭再嚟, 之後 resume3b.sh 用新 proof-dir)
set -u
TAG=${1:?tag}
RUN=p3br1_shrink; R=/home/user/hadwiger/phase3b/runs/$RUN
echo "== before =="; pgrep -fa 'probe3b|cnc2|kissat|drat-trim|march_cu' | grep -v pgrep | cut -c1-120
pkill -f "probe3b.py --run-id $RUN" 2>/dev/null; sleep 2
pkill -f "cnc2.py --cnf $R/$TAG/base.cnf" 2>/dev/null; sleep 3
pkill -x kissat 2>/dev/null; pkill -x drat-trim 2>/dev/null; pkill -x march_cu 2>/dev/null; sleep 2
echo "== after kill =="; pgrep -fa 'probe3b|cnc2|kissat|drat-trim|march_cu' | grep -v pgrep | wc -l
if [ -d "$R/$TAG/cnc_$TAG" ]; then
  echo "cnc_$TAG state: $(python3 -c "import json;s=json.load(open('$R/$TAG/cnc_$TAG/state.json'));print('done',len(s['done']),'pending',len(s['pending']),'status',s.get('status'))" 2>/dev/null)"
  rm -rf "$R/$TAG/cnc_$TAG"; echo "removed $R/$TAG/cnc_$TAG (campaign restarts from scratch on resume)"
fi
PD=/home/user/hadwiger/phase2b/proofs_ext4/$RUN; N=$(ls "$PD" 2>/dev/null | wc -l); rm -f "$PD"/*.drat; echo "leftover proofs in $PD: $N → $(ls "$PD" | wc -l)"
python3 -c "import json;s=json.load(open('$R/state.json'));print('probe state: round_done',s['round_done'],'S_acc',len(s['S_acc']),'elapsed_s',s.get('elapsed_s'),'stop',s.get('stop_reason'))"
python3 -c "import json;r=json.load(open('$R/rounds.json'));print('rounds.json:',[(x['round'],x.get('status')) for x in r])"
echo "PAUSE3B DONE $(date)"
