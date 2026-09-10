#!/bin/bash
# Phase 3b 第 5 步: 本機 (Windows + WSL) 都冇 pdflatex, sudo 要密碼 → 用 TinyTeX (TeX Live 精簡版) 裝落 WSL 用戶目錄 ~/.TinyTeX (唔使 sudo, 唔改系統設定, rm -rf ~/.TinyTeX 即可還原)
# 來源: https://yihui.org/tinytex/ (CTAN 鏡像下載, 約 100–150 MB). 之後用絕對路徑 ~/.TinyTeX/bin/x86_64-linux/pdflatex 編譯 paper/note_v1.tex
set -u
TT=/home/user/.TinyTeX/bin/x86_64-linux
if [ ! -x "$TT/pdflatex" ]; then
  echo "== installing TinyTeX (user space) $(date) =="
  cd /tmp && rm -rf tinytex_install && mkdir tinytex_install && cd tinytex_install
  curl -sL -m 120 -o install-bin-unix.sh https://yihui.org/tinytex/install-bin-unix.sh && echo "installer $(stat -c %s install-bin-unix.sh) bytes, sha256 $(sha256sum install-bin-unix.sh | cut -c1-16)"
  sh ./install-bin-unix.sh 2>&1 | tail -15
fi
ls -la "$TT/pdflatex" "$TT/tlmgr" 2>&1
echo "== tlmgr install packages needed by note_v1.tex (amscls geometry booktabs array url hyperref microtype amsmath amsfonts) =="
"$TT/tlmgr" install amscls geometry booktabs url hyperref microtype amsmath amsfonts tools latex-bin 2>&1 | tail -8
"$TT/pdflatex" --version | head -2
echo "TEX_SETUP DONE $(date)"
