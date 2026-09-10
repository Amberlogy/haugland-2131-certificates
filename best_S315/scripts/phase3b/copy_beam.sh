#!/bin/bash
# beam 結果 (json / md / log) → Windows phase3b/beam/ (含子目錄 runB / moserB / runC)
SRC=/home/user/hadwiger/phase3b/beam; DST=/mnt/c/Users/user/Desktop/spindle/phase3b/beam
for d in . runB moserB runC; do
  mkdir -p "$DST/$d"
  cp "$SRC/$d"/*.json "$SRC/$d"/*.md "$SRC/$d"/*.log "$DST/$d/" 2>/dev/null
done
cp /home/user/hadwiger/phase3b/dense_udg_L.md /mnt/c/Users/user/Desktop/spindle/phase3b/dense_udg_L.md
du -sh "$DST"; find "$DST" -name "beam_*.json" | sort
