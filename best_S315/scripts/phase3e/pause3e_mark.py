#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pause3e_mark.py —— pause3e.sh --now 用: 喺 state.json 打 paused 旗 (獨立一個檔, 免得 heredoc 嵌套出事)"""
import json, os

p = "/home/user/hadwiger/phase3e/runs/p3e1_step/state.json"
s = json.load(open(p))
s["paused"] = True
s["stop_reason"] = s.get("stop_reason") or "PAUSED --now by operator"
json.dump(s, open(p + ".tmp", "w"), indent=1)
os.replace(p + ".tmp", p)
print("state.json: paused=True, round_done", s.get("round_done"), "步幅", s.get("step"),
      "S_acc", len(s["S_acc"]), "best", (s.get("best") or {}).get("tag"))
