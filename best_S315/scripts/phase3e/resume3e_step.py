#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""resume3e_step.py —— resume3e.sh 用: 印一行 STEP.txt 內容 (現況摘要)"""
import json

s = json.load(open("/home/user/hadwiger/phase3e/runs/p3e1_step/state.json"))
print("Phase 3e 續跑 (resume): round_done %s / 步幅 %s / S_acc %d 粒 (|G2'| %d) | CPU %s CPU-h | best %s | 上次停: %s" % (
    s.get("round_done"), s.get("step"), len(s["S_acc"]), 1066 - len(s["S_acc"]), s.get("cpu_h_used"),
    (s.get("best") or {}).get("tag"), (s.get("stop_reason") or "")[:160]))
