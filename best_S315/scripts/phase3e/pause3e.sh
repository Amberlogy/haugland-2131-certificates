#!/bin/bash
# 乾淨暫停: 放 PAUSE 旗 (probe3e 喺當前輪結算之後停, 唔收爐; 之後 resume3e.sh 續)。要即刻停就加 --now:
#   先殺 run3e.sh + probe3e (等佢真係死咗), 再殺 cnc2k + solver; 當前 campaign 之後 resume 會 cnc2k --resume 續, keep 目錄同已驗證明照用
cd /home/user/hadwiger/phase3e
RUN=p3e1_step; R=runs/$RUN
touch "$R/PAUSE"; echo "PAUSE 旗已放: $R/PAUSE (當前輪結算後停)"
if [ "${1:-}" = "--now" ]; then
  pkill -f "run3e.sh" 2>/dev/null
  pkill -f "probe3e.py.*--run-id $RUN" 2>/dev/null
  for i in $(seq 1 60); do pgrep -f "probe3e.py.*--run-id $RUN" > /dev/null || break; sleep 1; done
  echo "probe3e 剩: $(pgrep -fc "probe3e.py.*--run-id $RUN") 個"
  pkill -f "cnc2k.py" 2>/dev/null; sleep 3; pkill -x kissat 2>/dev/null; pkill -x drat-trim 2>/dev/null; pkill -x march_cu 2>/dev/null; sleep 2
  echo "procs left: $(pgrep -fa 'probe3e|cnc2k|kissat|drat-trim|march_cu|run3e' | grep -v pgrep | wc -l)"
  python3 /home/user/hadwiger/phase3e/pause3e_mark.py
  rm -f /dev/shm/$RUN/cnc_*.drat 2>/dev/null
  echo "已即刻停; 續跑: bash resume3e.sh (當前 campaign 會 cnc2k --resume, 上次 wall 計返入預算)"
fi
