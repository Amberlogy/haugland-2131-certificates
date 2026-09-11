# RECORD_README.md — improved Moser-spindle-free 5-chromatic unit-distance graph on 1501 vertices (1501 > 1441: not a record)

Archived 2026-09-10 01:20:15 by `scripts/phase3e/finalize3e.py` (run `p3e1_step`, certificate `r05a`, seeded from Phase 3c `p3c1_shrink` r09a). Author of the project: King Tat Wong (Amber). Every statement below is backed by a machine certificate in this directory and was re-verified from those files at archive time (`L1pp/verify_final.json`, `L1pp/crosscheck.json`, `L1pp/col5_check.json`: all_ok = true).

## 1. The graph

* **G2′ = G2 − S**: Haugland's graph G2 (1066 vertices, 6264 edges; exact coordinates in ℚ(ζ₈₄)) minus a certified removable set S of **315** vertices ⇒ **|V(G2′)| = 751, |E(G2′)| = 4043**.
* **G3′ = G2′ ∪ ρ(G2′)**, ρ(z) = (z+1)(7+i√15)/8 − 1 (exact, in ℚ(ζ₄₂₀)); G2′ ∩ ρ(G2′) = {u = (−1,0)} ⇒ **|V(G3′)| = 1501, |E(G3′)| = 8088**.
* G3′ is an induced subgraph of Haugland's 2131-vertex graph G3 (arXiv:2608.04542), so it is a unit-distance graph in the plane, it contains **no Moser spindle**, and it is 5-colourable — all three re-certified here from scratch (§2).
* **Certified statement: G3′ has no proper 4-colouring, i.e. χ(G3′) = 5.**

| quantity | value |
|---|---|
| vertices of G3′ | **1501** |
| edges of G3′ | **8088** |
| vertices of G2′ (the half we shrink) | 751 |
| edges of G2′ | 4043 |
| deleted G2 vertices (S) | 315 |
| our previous certified graph (Phase 3c) | 1591 vertices |
| smallest previously known spindle-free 5-chromatic UDG — Heule, *Geombinatorics* 31(2), 2021, as cited in Haugland arXiv:2608.04542 (**bibliographic value; that graph was NOT re-verified here**) | 1441 vertices |

S (G2 vertex indices, 1-based, in the v1.0 numbering of `G2.cvtx`/`G2.edge` produced by `scripts/phase2/haugland.py`):

```
[1, 2, 3, 4, 5, 8, 10, 13, 15, 16, 20, 21, 24, 26, 27, 30, 32, 33, 34, 37, 38, 44, 50, 51, 61, 66, 67, 68, 69, 71, 72, 73, 76, 78, 79, 81, 83, 84, 85, 90, 92, 101, 105, 106, 109, 115, 116, 118, 130, 131, 133, 134, 135, 137, 148, 152, 156, 157, 161, 164, 168, 169, 171, 173, 176, 185, 188, 190, 196, 197, 201, 203, 205, 207, 209, 213, 214, 218, 224, 226, 230, 231, 235, 239, 245, 246, 253, 256, 258, 262, 270, 271, 273, 276, 278, 282, 286, 287, 295, 296, 298, 300, 303, 304, 305, 312, 317, 333, 334, 335, 337, 340, 344, 345, 347, 353, 365, 369, 372, 374, 382, 384, 385, 387, 394, 395, 396, 397, 405, 407, 412, 413, 415, 416, 421, 422, 427, 428, 431, 439, 453, 455, 457, 463, 466, 468, 469, 477, 478, 484, 487, 492, 499, 500, 509, 511, 516, 519, 526, 531, 536, 543, 547, 549, 554, 563, 564, 566, 572, 573, 577, 581, 582, 583, 588, 590, 601, 603, 605, 606, 611, 612, 614, 615, 619, 621, 625, 626, 631, 642, 672, 677, 683, 688, 689, 695, 701, 702, 704, 708, 709, 710, 713, 716, 721, 722, 723, 724, 737, 744, 749, 753, 758, 759, 771, 773, 776, 778, 784, 791, 792, 793, 794, 797, 799, 802, 804, 807, 809, 817, 819, 822, 824, 832, 834, 835, 837, 838, 839, 840, 846, 851, 853, 859, 862, 864, 865, 868, 869, 871, 878, 890, 897, 898, 901, 903, 912, 914, 920, 921, 925, 928, 929, 932, 934, 936, 940, 941, 942, 946, 947, 948, 952, 953, 956, 964, 967, 968, 974, 979, 982, 985, 987, 992, 993, 996, 998, 999, 1003, 1004, 1006, 1007, 1011, 1014, 1017, 1020, 1022, 1026, 1029, 1033, 1037, 1041, 1043, 1047, 1050, 1054, 1055, 1057, 1059, 1060, 1061, 1062, 1063, 1064, 1066]
```

## 2. The proof chain and where every certificate is

| step | statement | files | how to check |
|---|---|---|---|
| L1″ | every proper 4-colouring of G2′ gives col(−1,0) = col(1,0) (the *mono-pair property*). `L1pp/base.cnf` (sha `1516417ea9ba4ceee78c6579b90827d7c026d77cd4cd6b3befc2c766f2ad3d2c`) is the 4-colouring CNF of G2′ (ALO + AMO + edge clauses, one triangle through u pinned to colours 1,2,3) plus 4 clauses ¬(col(u)=c ∧ col(v)=c); it is UNSAT. | `L1pp/base.{cnf,json}`, `L1pp/cubes_d14.icnf` (march_cu, 16382 cubes), `L1pp/cnc_r05a/{bundle.json,state.json,ledger.csv}`, **`L1pp/leaf_proofs/*.drat` (16382 binary DRAT files)**, `L1pp/cnc_r05a/cover_pure.{cnf,drat}`, `L1pp/leaf_proofs/audit/` (819 proofs), `L1pp/LEAF_INDEX.json` | every leaf: rebuild `base.cnf` + the cube's unit clauses (sha in `state.json`), then `drat-trim cube.cnf leaf.drat` → `s VERIFIED`. The cover certificate shows the negated cubes are jointly unsatisfiable, i.e. the cubes cover the whole search space. `scripts/phase3c/verify_final.py` does all of it; result: `L1pp/verify_final.json` (leaf 16382/16382 re-verified, cover True, audit complete True). |
| cake_lpr cross-check | a 5% sample of the leaf proofs also passes the **formally verified** checker cake_lpr (CakeML) and the independent `lrat-check`, via `drat-trim -L` LRAT. | `L1pp/crosscheck.json` (819/819 sampled leaves, all three checkers) | `scripts/phase3d/crosscheck3d.py --attempt-dir L1pp --tag r05a --keep-dir L1pp/leaf_proofs --out DIR --frac 0.05` |
| L2″ | identity and ρ map V(G2′) injectively into V(G3′), and every edge of G2′ into E(G3′) — computed with exact cyclotomic arithmetic, not index tables; plus **completeness**: `exactfield.py check --complete` certifies that each edge list is the complete unit-distance graph on its exact point set. | `L2L3/l3_final/{G2p,G3p}.{cvtx,edge}`, `maps.json`, `summary.json` (`L2`, `complete_G2p`, `complete_G3p`); `L2L3/l3/` is the same computation done during the campaign (byte-identical: {'G2p.cvtx': True, 'G2p.edge': True, 'G3p.cvtx': True, 'G3p.edge': True, 'L3pp.cnf': True}) | `scripts/phase3b/l3g2.py --remove <S> --out DIR --engine-b`; `scripts/phase2/exactfield.py check G3p.cvtx G3p.edge --complete` |
| L3″ | the 4-colouring CNF of G3′ plus 16 lemma clauses (col(u)=col(v) and col(u)=col(ρv), as bi-implications per colour) is UNSAT. Together with L1″ applied to both copies, this proves G3′ has no proper 4-colouring. | `L2L3/l3_final/L3pp.{cnf,drat,json}` (kissat UNSAT, drat-trim VERIFIED; drat sha `e9376129cbf656722623d8f09fd09650be0c2f0b8edbf9196c299793f7aebf93`) | `drat-trim L3pp.cnf L3pp.drat` |
| spindle-free | G3′ contains no Moser spindle as a subgraph. Engine A: exact enumeration of all rhombi → 0 copies. Engine B: SAT subgraph-monomorphism CNF is UNSAT with a drat-trim VERIFIED proof. Both engines agree. | `L2L3/l3_final/summary.json` (`spindle_A`, `spindle_B`), `L2L3/l3_final/spindle_B/{spindle.cnf,spindle.drat}` | `scripts/phase2/spindlefind.py both G3p.edge --out DIR` |
| 5-colourable | an explicit proper 5-colouring of G3′, every one of the 8088 edges checked bichromatic (twice: the archived colouring re-checked in plain Python, and a fresh solve of the 5-colouring CNF). | `COL5/col5/G3p_5col.col` (+`.json`), `COL5/col5_final/`, `L1pp/col5_check.json` | `scripts/phase2/certify4.py G3p.edge --out DIR --k 5 --expect sat` |

Chain: **L1″ (mono-pair for G2′) + L2″ (exact embeddings) + L3″ (lemma CNF UNSAT) ⇒ G3′ is not 4-colourable**; with the explicit 5-colouring, χ(G3′) = 5; with the spindle-free certificate, G3′ is a Moser-spindle-free 5-chromatic unit-distance graph on 1501 vertices.

## 3. Independent re-verification performed at archive time (from the files in this directory)

```
{
 "rebuild_base_cnf_from_S": {
  "rc": 0,
  "tail": "[buildg2] S=315 粒 [1, 2, 3, 4, 5, 8, …]: G₂′ 751 點 4043 邊 (刪 2221 邊), 21436 子句, 釘 (172,11,166)=(1,2,3), 反 pair 4 條, sha 1516417ea9ba4cee → /home/user/hadwiger/phase3e/runs/p3e1_step/r05a/rebuild/base.cnf\n",
  "rebuilt_sha256": "1516417ea9ba4ceee78c6579b90827d7c026d77cd4cd6b3befc2c766f2ad3d2c",
  "archived_sha256": "1516417ea9ba4ceee78c6579b90827d7c026d77cd4cd6b3befc2c766f2ad3d2c",
  "match": true,
  "n_remaining": 751,
  "n_edges": 4043,
  "graph_match": true,
  "ok": true
 },
 "verify_final": {
  "base_sha_consistent": true,
  "leaf_count_consistent": true,
  "leaf_ids_are_all_root_cubes": true,
  "cover_reverify": {
   "mode": "pure",
   "cnf": "/home/user/hadwiger/phase3e/runs/p3e1_step/r05a/cnc_r05a/cover_pure.cnf",
   "drat": "/home/user/hadwiger/phase3e/runs/p3e1_step/r05a/cnc_r05a/cover_pure.drat",
   "cnf_sha_match": true,
   "drat_sha_match": true,
   "cover_clauses_match_negated_leaves": true,
   "cover_header_nvars_ok": true,
   "verified": true,
   "verify_s": 0.3,
   "ok": true
  },
  "audit_reverify": {
   "bundle_audit_n": 819,
   "bundle_all_ok": true,
   "kept_files": 819,
   "ok": 819,
   "bad": [],
   "complete": true,
   "n_missing": 0,
   "missing_ids": []
  },
  "exactfield_complete_G3p_again": {
   "rc": 0,
   "last": "[G3p.cvtx] 邊表 == 點集嘅完整單位距離圖 ✓ (8088 條)",
   "s": 3.0
  },
  "all_ok": true,
  "t_s": 10013.2,
  "leaf_reverify": {
   "n": 16382,
   "ok": 16382,
   "n_bad": 0,
   "wall_s": 9275.8,
   "verify_cpu_s": 126391.7,
   "mean_verify_s": 7.715,
   "proof_total_gb": 128.119,
   "proof_sha_sum_sha256": "63fe311ba124f41a1efab7fef74da87b6417b6cab73cd74f6e35fd59099b789b"
  },
  "l3_final": {
   "rc": 0,
   "all_ok": true,
   "G2p": {
    "n": 751,
    "m": 4043
   },
   "G3p": {
    "n": 1501,
    "m": 8088
   },
   "L3": {
    "status": "UNSAT",
    "verified": true,
    "drat_lines": 1121,
    "sha": {
     "L3pp.cnf": "b3b2582404c1280c32ca5b669aec75d055303d8a9947219f17f8b5ffc57abc35",
     "L3pp.drat": "e9376129cbf656722623d8f09fd09650be0c2f0b8edbf9196c299793f7aebf93"
    },
    "solve_s": 0.01
   },
   "spindle_A": {
    "copies": 0,
    "rhombi": 510,
    "t_s": 0.01
   },
   "spindle_B": {
    "rc": 0,
    "ok": true,
    "t_s": 48.9,
    "lines": [
     "[B SAT] CNF 21007 變量 / 100546 子句 (symbreak=True)",
     "[B SAT] kissat UNSAT 18.75s; DRAT 340498 行; drat-trim s VERIFIED ✓ (30.0s)",
     "[B SAT] 證書: /home/user/hadwiger/phase3e/runs/p3e1_step/r05a/l3_final/spindle_B/spindle.cnf + /home/user/hadwiger/phase3e/runs/p3e1_step/r05a/l3_final/spindle_B/spindle.drat",
     "[對數] 引擎 A (0 隻) 同引擎 B (UNSAT) 一致 ✓"
    ]
   },
   "same_files_as_campaign_l3": {
    "G2p.cvtx": true,
    "G2p.edge": true,
    "G3p.cvtx": true,
    "G3p.edge": true,
    "L3pp.cnf": true
   }
  }
 },
 "cake_lpr_crosscheck": {
  "attempt_dir": "/home/user/hadwiger/phase3e/runs/p3e1_step/r05a",
  "tag": "r05a",
  "keep_dir": "/mnt/d/hadwiger/release_v1_1_staging/best_S315/L1pp/leaf_proofs",
  "when": "2026-09-10 04:22:17",
  "frac": 0.05,
  "seed": 20260908,
  "n_leaves": 16382,
  "n_sampled": 819,
  "ok": 819,
  "n_bad": 0,
  "base_sha256": "1516417ea9ba4ceee78c6579b90827d7c026d77cd4cd6b3befc2c766f2ad3d2c",
  "bundle_base_sha": "1516417ea9ba4ceee78c6579b90827d7c026d77cd4cd6b3befc2c766f2ad3d2c",
  "lrat_total_gb": 25.033,
  "mean_drattrim_s": 5.74,
  "mean_cake_lpr_s": 2.23,
  "checkers": {
   "drat-trim": "/home/user/hadwiger/drat-trim/drat-trim",
   "cake_lpr": "/home/user/hadwiger/tools/cake_lpr/cake_lpr",
   "lrat-check": "/home/user/hadwiger/drat-trim/lrat-check",
   "sha256": {
    "drat-trim": "463a21fd1b8214280c55dfc32c4faf845c765cf98d54334e5d01c8c09bd76cef",
    "cake_lpr": "567c0dfe400239149df1ea7382365840746cdae284d8a321661a813fef884fa6",
    "lrat-check": "e9a774c0a87e01c072a507366adf5a95a02a2fca277822f0a2c6ade653787a14"
   }
  },
  "wall_s": 908.3,
  "all_ok": true,
  "rc": 0
 },
 "five_colouring": {
  "when": "2026-09-10 04:22:17",
  "archived_col": {
   "file": "/home/user/hadwiger/phase3e/runs/p3e1_step/r05a/col5/G3p_5col.col",
   "sha256": "a0d4bbf15b7dfaa5f5bd2c3d772dc1f737d0f42907f1c686df81f2daa5ae0ce1",
   "n": 1501,
   "n_coloured": 1501,
   "edges_checked": 8088,
   "bad_edges": 0,
   "vertex_set_ok": true,
   "colours_used": [
    1,
    2,
    3,
    4,
    5
   ],
   "ok": true
  },
  "fresh_col": {
   "rc": 0,
   "status": "SAT",
   "n": 1501,
   "m": 8088,
   "colours_used": [
    1,
    2,
    3,
    4,
    5
   ],
   "edges_checked": 8088,
   "solve_s": 0.05,
   "col_sha256": "a0d4bbf15b7dfaa5f5bd2c3d772dc1f737d0f42907f1c686df81f2daa5ae0ce1",
   "ok": true
  },
  "G3p_edge_same": true,
  "all_ok": true
 }
}
```

Re-run everything with `bash reverify.sh` (about 3 h on 14 threads).

## 4. Provenance and cost

* Seed: Phase 3c run `p3c1_shrink`, certificate `r09a` (S_acc = 270 vertices, |G2′| = 796, |G3′| = 1591; its own full archive with all leaf proofs is in `../final/`).
* Phase 3e cut 45 further G2 vertices in 3 certified rounds of 20/20/5 (candidate order: G2 degree ascending, |Im z| descending, index ascending; protected set P2 = {172, 187, 646, 994} never touched).
* Attempts: [('r01a', 'certified', 4.32), ('r02a', 'certified', 3.99), ('r03a', 'SAT', 0.28), ('r03b', 'SAT', 0.34), ('r04a', 'SAT', 3.88), ('r04b', 'SAT', 0.14), ('r05a', 'certified', 4.16), ('r06a', 'SAT', 3.78), ('r06b', 'SAT', 0.2)]. Budget: 295.3 / 500 CPU-h (Σ certificate wall-clock × 14 workers), 21.43 / 60 h wall-clock; per-certificate cap 8 h + up to 1 h automatic extension when the run was nearly finished.
* Solver / checkers (same binaries as v1.0; sha256 in `L1pp/cnc_r05a/bundle.json` → `tools`): kissat (proofs), drat-trim (checking), march_cu (cube-and-conquer split), cake_lpr + lrat-check (cross-check). `scripts/phase3c/cnc2k.py` = the audited v1.0 `cnc2.py` plus `--keep-dir` (leaf proofs are kept instead of deleted); the diff is `scripts/phase3c/cnc2k.diff`.
* Ledger of all attempts: `run/ledger_g2.md`; blocking sets from SAT attempts (if any): `run/state.json` → `B_sets`.

## 5. Integrity

`SHA256SUMS` covers every file here (`<sha256>  <relative path>`; check with `sha256sum -c SHA256SUMS`). The 17201 entries under `L1pp/leaf_proofs/` name proofs that are deliberately not packaged, so a plain
`sha256sum -c SHA256SUMS` reports them as `FAILED open or read`; that is absence, not corruption. To check what is
present: `grep -v 'L1pp/leaf_proofs/' SHA256SUMS | sha256sum -c --quiet`.

Released as v1.1: GitHub tag `v1.1` of github.com/Amberlogy/haugland-2131-certificates, and the Zenodo record
under concept DOI 10.5281/zenodo.22435777.
