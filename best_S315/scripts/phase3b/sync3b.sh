#!/bin/bash
# Windows phase3b 源碼 → WSL ~/hadwiger/phase3b (源頭喺 Windows); 只同步 .py / .sh (json 結果由 WSL 生成, 用 syncback3b.sh 抄返)
mkdir -p /home/user/hadwiger/phase3b/runs
cp /mnt/c/Users/user/Desktop/spindle/phase3b/*.py /home/user/hadwiger/phase3b/ 2>/dev/null
cp /mnt/c/Users/user/Desktop/spindle/phase3b/*.sh /home/user/hadwiger/phase3b/ 2>/dev/null
cp /mnt/c/Users/user/Desktop/spindle/phase3b/items.json /home/user/hadwiger/phase3b/items.json 2>/dev/null
cp /mnt/c/Users/user/Desktop/spindle/phase3b/extra_facts.json /home/user/hadwiger/phase3b/extra_facts.json 2>/dev/null
sed -i 's/\r$//' /home/user/hadwiger/phase3b/*.py /home/user/hadwiger/phase3b/*.sh 2>/dev/null
chmod +x /home/user/hadwiger/phase3b/*.py /home/user/hadwiger/phase3b/*.sh 2>/dev/null
ls /home/user/hadwiger/phase3b/
