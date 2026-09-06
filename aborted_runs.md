# 中止嘅背景戰役記錄 (Phase 2c Step 0, 2026-09-05 15:02:48)

## cnc_minus_v1 —— 「G₁ − 頂點 1 (deg 7) + A=B 同色」4 色 UNSAT CnC 戰役 (Phase 3 範疇, 中止)
- 用途: 如果全部 cube UNSAT ⇒ 頂點 1 可剪 (G₁−1 仍有 pair 性質) 嘅機器證書; 呢個 run 冇跑完, **唔係證書**
- 設定: base = minus/G1minus_v1.cnf (sha 99c301dad27af6b5…, 2960 變量 21084 子句), march_cu -d 14 → 16384 個 cube, kissat T=600s, 14 workers, ext4 binary DRAT 驗完即刪
- 開始 13:44:33; 殺於 15:02:48; wall 4507 s
- 已完成 leaf (UNSAT + drat-trim VERIFIED): **10958 / 16384**; timeout 0; 其他 0; split 0; stuck 0; solver 錯誤 0
- 已完成 leaf 嘅 solve: mean 3.35 s, max 35.5 s (對照 L1 戰役 mean 0.46 s / max 8.6 s —— 刪咗一點之後每個 cube 難咗 ~7 倍)
- 部分結論: 頭 10958 個 cube 冇一個 SAT (所以暫時冇反例); 但未覆蓋全部 cube, 亦冇 cover 證書 → 「頂點 1 可剪」**未證**. 剩低 5426 個 cube; 如果 Phase 3 要續, `cnc2.py --resume --out cnc_minus_v1` (state.json 有 checkpoint)
- ledger: cnc_minus_v1/ledger.csv (每個已完成 cube 嘅 proof sha256/bytes); 證明檔已按紀律刪除

## cnc_minus_v6 —— 未開始 (extras.sh 排咗隊, 被殺前未輪到); 冇任何輸出

## G₃ 直接 4 色 CnC 正式戰役 —— **冇開過** (只有 Step 5.3 嘅 30 個 cube 抽樣偵察, 見 phase2b_results.md §5.3); launch_g3.sh 只係寫好未執行
