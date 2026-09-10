#!/bin/bash
# beam search process 控制 (STOP / CONT / status / cleanup). 用腳本檔跑, 免 pkill -f 自我匹配 (inline bash -c 命令行含 pattern 會停咗自己)
# 用法: bash beamctl.sh stop|cont|status|cleanup
set -u
case "${1:-status}" in
  cleanup)
    for p in $(pgrep -f 'pkill -STOP' ); do echo "kill -9 stuck shell $p: $(tr '\0' ' ' < /proc/$p/cmdline | cut -c1-80)"; kill -9 "$p" 2>/dev/null; done ;;
  stop)
    pkill -STOP -f 'beam_udg.py --lattice' ; sleep 1 ;;
  cont)
    pkill -CONT -f 'beam_udg.py --lattice' ; sleep 1 ;;
esac
echo "== beam procs =="; ps -o pid,stat,etime,pcpu,cmd -C python 2>/dev/null | grep 'beam_udg' | cut -c1-100
echo "== stuck shells =="; pgrep -fa 'pkill -STOP' | grep -v pgrep | cut -c1-100
uptime; date
