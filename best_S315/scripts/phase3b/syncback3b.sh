#!/bin/bash
# WSL ~/hadwiger/phase3b 結果 (md / json / png / log 細檔) → Windows Desktop\spindle\phase3b (唔抄 cnf / drat / icnf / cubes)
SRC=/home/user/hadwiger/phase3b; DST=/mnt/c/Users/user/Desktop/spindle/phase3b
mkdir -p "$DST"
for f in "$SRC"/*.md "$SRC"/*.json "$SRC"/*.png "$SRC"/*.txt; do
  case "$(basename "$f")" in items.json|extra_facts.json) continue ;; esac     # 源頭喺 Windows, 唔抄返 (之前抄返覆寫咗新版)
  cp "$f" "$DST"/ 2>/dev/null
done
cd "$SRC" && find runs runs_tail -type f \( -name "*.md" -o -name "*.json" -o -name "*.png" -o -name "*.log" -o -name "*.col" -o -name "*.csv" -o -name "*.txt" \) -size -20M 2>/dev/null | grep -v '/cubes/' | while read -r f; do
  mkdir -p "$DST/$(dirname "$f")"; cp "$f" "$DST/$f"
done
echo "syncback done $(date)"
