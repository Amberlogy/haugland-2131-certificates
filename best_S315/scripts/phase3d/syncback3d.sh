#!/bin/bash
# WSL ~/hadwiger/phase3d 結果 (md / json / log / txt 細檔) → Windows Desktop\spindle\phase3d (唔抄 cnf / drat / icnf / cubes / 證明)
SRC=/home/user/hadwiger/phase3d; DST=/mnt/c/Users/user/Desktop/spindle/phase3d
mkdir -p "$DST"
for f in "$SRC"/*.md "$SRC"/*.json "$SRC"/*.txt; do
  [ -f "$f" ] && cp "$f" "$DST"/ 2>/dev/null
done
cd "$SRC" && find runs selftest -type f \( -name "*.md" -o -name "*.json" -o -name "*.log" -o -name "*.col" -o -name "*.csv" -o -name "*.txt" \) -size -20M 2>/dev/null | grep -v '/cubes/' | while read -r f; do
  mkdir -p "$DST/$(dirname "$f")"; cp "$f" "$DST/$f"
done
echo "syncback3d done $(date)"
