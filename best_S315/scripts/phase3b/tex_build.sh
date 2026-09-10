#!/bin/bash
# 第 5 步: pdflatex 編譯 paper/note_v1.tex (TinyTeX 用戶目錄), 兩 pass, 報 error/warning 原文, PDF + log 抄返 Windows paper/
set -u
PDFL=/home/user/.TinyTeX/bin/x86_64-linux/pdflatex
B=/home/user/hadwiger/phase3b/texbuild
mkdir -p "$B"; cp /mnt/c/Users/user/Desktop/spindle/paper/note_v1.tex "$B/"; cd "$B" || exit 1
sed -i 's/\r$//' note_v1.tex
echo "tex sha256: $(sha256sum note_v1.tex | cut -c1-16)  ($(wc -l < note_v1.tex) lines)"
"$PDFL" -interaction=nonstopmode -halt-on-error note_v1.tex > pass1.out 2>&1; echo "pass1 rc=$?"
"$PDFL" -interaction=nonstopmode -halt-on-error note_v1.tex > pass2.out 2>&1; echo "pass2 rc=$?"
echo "=== errors (lines starting with !) ==="; grep -n -A4 '^!' note_v1.log | head -60
echo "=== warnings ==="; grep -n -i 'LaTeX Warning\|Package .* Warning\|undefined\|Overfull\|Underfull\|Missing character' note_v1.log | head -40
echo "=== output ==="; grep -n 'Output written' note_v1.log
if [ -f note_v1.pdf ]; then ls -la note_v1.pdf; cp note_v1.pdf /mnt/c/Users/user/Desktop/spindle/paper/note_v1.pdf; cp note_v1.log /mnt/c/Users/user/Desktop/spindle/paper/note_v1.pdflatex.log; echo "copied PDF + log to Windows paper/"; else echo "!! no PDF"; tail -30 pass1.out; fi
echo "TEX_BUILD DONE $(date)"
