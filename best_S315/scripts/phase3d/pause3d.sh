#!/bin/bash
# 乾淨暫停: 放 PAUSE 旗 (probe3d 喺當前證書結算之後停, 唔收爐; 之後 resume3d.sh 續)。要即刻停就加 --now:
#   先殺 run3d.sh + probe3d (等佢真係死咗), 再殺 cnc2k + solver; 當前 campaign 之後 resume 會 cnc2k --resume 續, keep 目錄同已驗證明照用
cd /home/user/hadwiger/phase3d
RUN=p3d1_final; R=runs/$RUN
touch "$R/PAUSE"; echo "PAUSE 旗已放: $R/PAUSE (當前證書結算後停)"
if [ "${1:-}" = "--now" ]; then
  pkill -f "run3d.sh" 2>/dev/null
  pkill -f "probe3d.py.*--run-id $RUN" 2>/dev/null
  for i in $(seq 1 60); do pgrep -f "probe3d.py.*--run-id $RUN" > /dev/null || break; sleep 1; done
  echo "probe3d 剩: $(pgrep -fc "probe3d.py.*--run-id $RUN") 個"
  pkill -f "cnc2k.py" 2>/dev/null; sleep 3; pkill -x kissat 2>/dev/null; pkill -x drat-trim 2>/dev/null; pkill -x march_cu 2>/dev/null; sleep 2
  echo "procs left: $(pgrep -fa 'probe3d|cnc2k|kissat|drat-trim|march_cu|run3d' | grep -v pgrep | wc -l)"
  python3 - <<'EOF'
import json, os
p = "/home/user/hadwiger/phase3d/runs/p3d1_final/state.json"
s = json.load(open(p)); s["paused"] = True; s["stop_reason"] = s.get("stop_reason") or "PAUSED --now by operator"
json.dump(s, open(p + ".tmp", "w"), indent=1); os.replace(p + ".tmp", p)
print("state.json: paused=True, S_acc", len(s["S_acc"]), "best", (s.get("best") or {}).get("tag"))
EOF
  rm -f /dev/shm/$RUN/cnc_*.drat 2>/dev/null
  echo "已即刻停; 續跑: bash resume3d.sh (當前 campaign 會 cnc2k --resume, 上次 wall 計返入預算)"
fi
