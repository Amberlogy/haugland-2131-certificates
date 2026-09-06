# CLAIM.md —— 呢個 bundle 精確證明咗乜嘢(只寫實際跑到、有機器證書嘅部分)

**命題(機器證明):** 設 G₃ 係 Haugland(arXiv:2608.04542 v4)嘅 2131 點單位距離圖,頂點精確坐標喺 `inputs/G3.cvtx`(ℚ(ζ₄₂₀) 分圓整數),邊表 `inputs/G3.edge`(12530 條邊)。
**G₃ 冇合法 4 色染色。** 連同 Phase 2 認證嘅 5 色染色(`phase2_extra/G3-5.col`,12530/12530 條邊逐條覆核異色),**χ(G₃) = 5**。

**證明鏈(每一步都係機器證書,重驗命令 `bash rerun.sh`):**

1. **inputs 認證(`scripts/exactfield.py check --complete`):** G₁(740 點)同 G₃ 嘅邊表 == 點集嘅完整單位距離圖(精確代數,無浮點判定):G₁ 3985/3985 條邊、G₃ 12530/12530 條邊,冇漏邊、冇非單位邊。
2. **L1 —— G₁ 嘅 pair 性質:** `L1/L1_a.cnf` 編碼「G₁ 嘅 4 色染色 + 頂點 A=(0,0)(#560)同 B=(0,√3)(#181)同色 + 第一個三角形 (1,13,87) 釘色 1,2,3」。
   證書:march_cu 將 `L1/L1_b.cnf`(= L1_a + 「每點至多一色」子句,A、B 除外)拆成 14786 個 cube(`L1/cubes.icnf`);
   (a) `L1/cover_pure.cnf`(14786 條 ¬cube 子句)俾 `L1/cover_pure.drat` 反駁,drat-trim `s VERIFIED` ⇒ 任何賦值都落喺某個 cube;
   (b) 對每個 cube c:`L1_a.cnf + c 嘅 unit 子句` 俾 `L1/lifted/L1a_cube_<id>.drat` 反駁,drat-trim `s VERIFIED`,14786/14786(`L1/lifted.jsonl` 記每個 CNF 同證明嘅 sha256;
   5% = 739 個另經 cake_lpr(形式化驗證檢查器)LRAT 覆核通過,見 `phase2b_results.md`)。
   (a)+(b) ⇒ L1_a.cnf UNSAT ⇒ **G₁ 嘅任何合法 4 色染色都必須 col(A) ≠ col(B)**(三角形釘色只係換色對稱,任何染色都可以換色做到 (1,13,87)=(1,2,3);呢個係唯一非機器步驟,同 Phase 0–2 一致)。
3. **L2 —— 四個等距 copy(`L2/pairs.json`,`scripts/chain.py`):** φ₁(z)=z·e^{−iπ/3}−1、φ₂(z)=z·e^{iπ/3}+1、φ₃=ρ∘φ₁、φ₄=ρ∘φ₂(ρ(w)=(w+1)(7+i√15)/8−1)
   精確計算:φ_k(V(G₁)) ⊂ V(G₃)(740 點 injective)而且 E(G₁) 3985/3985 條映落 E(G₃),k=1..4。⇒ G₃ 嘅任何 4 色染色限制喺 copy k 係 G₁ 嘅 4 色染色 ⇒ 由 L1,col(A_k) ≠ col(B_k)。
4. **L3 —— 拼合(`L3/L3.cnf`, `L3/L3.drat`):** G₃ 嘅 4 色 CNF + 16 條引理子句 (¬x_{A_k,c} ∨ ¬x_{B_k,c})(k=1..4,c=1..4)俾 L3.drat 反駁,drat-trim `s VERIFIED`(4891 行)。
   ⇒ G₃ 冇 4 色染色。

**附件(Phase 2 證書,唔屬於 rerun.sh,重驗命令喺括號):**
- Moser-spindle-free(subgraph 意義):`phase2_extra/spindle/spindle.cnf` + `spindle.drat`(subgraph monomorphism CNF,kissat UNSAT,drat-trim VERIFIED;重驗:`drat-trim spindle.cnf spindle.drat`,約 3.5 分鐘);引擎 A 精確枚舉菱形對 0 隻(Phase 2 報告)。
- 5 色染色:`phase2_extra/G3-5.col`(重驗:逐邊對照 `inputs/G3.edge`)。

**呢個 bundle 冇證明嘅嘢(唔好誤讀):**
- 冇證明 G₁ 或 G₃ 係 vertex-critical / 最細;冇證明任何頂點可剪(critscan 738/738 timeout,v=1 CnC 戰役中止,見 `aborted_runs.md`)。
- 冇「G₃ 直接 4 色 UNSAT」嘅單一 CnC 證書(只有 30 個 cube 嘅抽樣偵察);G₃ 唔可 4 色嘅結論係經 L1+L2+L3 得出。
- 冇任何關於 1441 或者破紀錄嘅主張。

**工具(`tools.json` 有 sha256):** kissat 4.0.4、drat-trim(GitHub marijnheule/drat-trim)、march_cu(marijnheule/CnC 705b60c)、cake_lpr(tanyongkiam/cake_lpr a36874a,只用於抽樣覆核)、Python 3.14 + `scripts/exactfield.py`(精確分圓代數,selftest 29 粒毒藥)。
