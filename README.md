# Machine-checked certificate: Haugland's 2131-vertex Moser-spindle-free unit-distance graph is 5-chromatic

Independent reconstruction and full machine verification of the main theorem of

> Jan Kristian Haugland, *A Moser-spindle-free 5-chromatic unit distance graph on 2131 vertices in the plane*, arXiv:2608.04542 v4 (17 Aug 2026).

Everything claimed below is backed by a machine certificate that you can re-check with public tools
(exact cyclotomic arithmetic in Python, kissat, drat-trim, march_cu, cake_lpr). Nothing rests on our word or on the paper's word.
This repository is the small "GitHub layer" (< 100 MB). The full proof archive (28 GB, 14 786 leaf DRAT proofs) is the "Zenodo layer";
its per-file sha256 fingerprints are in `SHA256SUMS.bundle` here, so the two layers are cryptographically tied.

Release **v1.1** adds `best_S315/`: the same kind of certificate set for a **1501-vertex** Moser-spindle-free 5-chromatic unit-distance graph
obtained by deleting 315 vertices from Haugland's G2. If you arrived here from a citation of the 1501-vertex graph, that directory is what you want
(§9). The v1.0 material for the 2131-vertex graph is unchanged.

Author of the certificates: **King Tat Wong** (independent researcher, ORCID [0009-0003-4009-3619](https://orcid.org/0009-0003-4009-3619)).
Graph construction: Haugland (see citation; the author has confirmed that the reconstruction may be published with a citation of his preprint). Prepared 2026-09-05, revised 2026-09-06.

Computations were orchestrated with Claude Code (Anthropic); all mathematical claims are independently machine-checked by drat-trim / cake_lpr and reproducible from the included scripts.

---

## 1. What is certified

Let **G3** be the 2131-vertex graph whose exact vertex coordinates are in `inputs/G3.cvtx` (elements of the cyclotomic field
ℚ(ζ₄₂₀), written as integer coefficient vectors over a common denominator) and whose edge list is `inputs/G3.edge` (12 530 edges).
G3 is Haugland's graph, rebuilt from the paper's definitions by `scripts/haugland.py`; every intermediate count matches the paper
(21 / 42 / 84 / 83581 / 1042 / 12856 / 740 / 3985 / 1066 / 6264 / 2131 / 12530).

Certified statements (each with the certificate that establishes it):

| # | Statement | Certificate | Checker |
|---|---|---|---|
| C1 | Every listed edge has length exactly 1, and the edge list is the **complete** unit-distance graph on the vertex set (no missing unit pair). Same for the 740-vertex G1. | `inputs/G3.cvtx` + `inputs/G3.edge` (and G1) | `scripts/exactfield.py check --complete` (exact arithmetic, no floating-point decision) |
| C2 | **G3 has no proper 4-colouring.** | chain L1 + L2 + L3 below | drat-trim on every DRAT file; exact arithmetic for L2 |
| C3 | G3 has a proper 5-colouring. | `extra/G3-5.col` | edge-by-edge check (`scripts/certify4.py` logic; also `rerun.sh`) |
| C4 | G3 contains no Moser spindle as a subgraph (not merely as an induced subgraph). | exact rhombus-pair enumeration (0 copies) and, in the Zenodo layer, `spindle.cnf` + `spindle.drat` (subgraph-monomorphism CNF, UNSAT) | `scripts/spindlefind.py enumerate`; drat-trim |

C2 + C3 give **χ(G3) = 5**; with C4, G3 is a Moser-spindle-free 5-chromatic unit-distance graph, as the paper states.

**Not claimed** (no certificate exists for these, and we do not assert them): that G3 or G1 is vertex-critical or minimal; that any vertex can be
deleted from G3; that any graph released here is the smallest possible. See `CLAIM.md` (original, Cantonese) and `CLAIM_en.md` (English rendering).

**Smaller graphs.** Release v1.1 adds `best_S315/`, a separate certificate set for a **1501-vertex** Moser-spindle-free 5-chromatic unit-distance
graph G3′, obtained by deleting a certified set of 315 vertices from Haugland's G2. It is certified to the same standard as the 2131-vertex material
above (χ = 5, spindle-free by two independent engines). **1501 > 1441, so it is not a record**: the smallest previously known such graph has 1441
vertices (Heule, *Geombinatorics* 31(2), 2021, as cited in arXiv:2608.04542), and that graph is a bibliographic reference here — it was not
re-verified. See §9 and `best_S315/README.md`.

### The certificate chain for C2

The paper's argument is: (i) in any 4-colouring of the 740-vertex graph G1, the vertices A = (0,0) and B = (0,√3) receive different colours
("pair property"); (ii) G3 contains four isometric copies of G1; (iii) the four pair constraints plus the geometry force a contradiction.
We machine-check exactly this decomposition.

* **L1 (pair property of G1).** `L1/L1_a.cnf` encodes: a 4-colouring of G1, col(A) = col(B) (A is vertex #560, B is #181), and the standard
  colour-symmetry pin (triangle (1, 13, 87) gets colours 1, 2, 3). Claim: UNSAT.
  Direct CDCL failed for us (22 solver × encoding runs, 30 min each, all timed out; kissat 30 min, CaDiCaL 2 h, unfinished DRAT > 10 GB).
  The certificate is a **cube-and-conquer** proof:
  * `cubes/cubes.icnf`: 14 786 cubes produced by march_cu (static depth 14) on `L1/L1_b.cnf` (= L1_a + at-most-one-colour clauses for every vertex except A, B).
  * **Cover:** `cubes/cover_pure.cnf` is the conjunction of the 14 786 negated cubes (no other clauses); `cubes/cover_pure.drat` refutes it.
    drat-trim prints `s VERIFIED`. Hence every assignment falls into at least one cube.
  * **Leaves (Zenodo layer):** for each cube *c*, the file `L1/lifted/L1a_cube_<id>.drat` is a DRAT refutation of `L1_a.cnf` + the unit clauses of *c*
    (the at-most-one clauses are introduced inside the proof as RAT lemmas, then kissat's proof follows). All 14 786 pass drat-trim `s VERIFIED`;
    `L1/lifted.jsonl` lists, per leaf, the sha256 of the exact CNF and of the proof. A 5 % sample (739 leaves) was additionally checked with the
    formally verified checker cake_lpr (LRAT produced by `drat-trim -L`).
  * Cover + leaves ⇒ `L1_a.cnf` is UNSAT. Reduction to the pair property: any 4-colouring with col(A) = col(B) can be relabelled so that the pinned
    triangle gets 1, 2, 3 (colour permutation), so no such colouring exists. This colour-permutation step is the only non-machine step in the chain.
* **L2 (four copies, exact arithmetic).** `scripts/chain.py` checks, in ℚ(ζ₄₂₀), that φ₁(z) = z·e^{−iπ/3} − 1, φ₂(z) = z·e^{iπ/3} + 1,
  φ₃ = ρ∘φ₁, φ₄ = ρ∘φ₂ with ρ(w) = (w+1)(7+i√15)/8 − 1 map V(G1) injectively into V(G3) and map all 3985 edges of G1 onto edges of G3.
  The images of A and B are recorded in `L2/pairs.json`: (A₁,B₁) = (#172, #655), (A₂,B₂) = (#994, #181), (A₃,B₃) = (#172, #1720), (A₄,B₄) = (#2059, #1246).
  Therefore any 4-colouring of G3 restricted to copy *k* is a 4-colouring of G1, and by L1 col(A_k) ≠ col(B_k).
* **L3 (assembly).** `L3/L3.cnf` = 4-colouring clauses of G3 + the 16 lemma clauses (¬x_{A_k,c} ∨ ¬x_{B_k,c}), k = 1..4, c = 1..4;
  `L3/L3.drat` refutes it (kissat, 0.12 s; 4891 proof lines); drat-trim prints `s VERIFIED`.

L1 ∧ L2 ∧ L3 ⇒ G3 has no proper 4-colouring.

---

## 2. Repository layout (GitHub layer)

```
README.md, CLAIM.md, CLAIM_en.md, LICENSE, ZENODO_METADATA.md, for_author_summary.md, aborted_runs.md
fresh_test.log        transcript of `bash rerun.sh` (quick layer) from a clean copy of this repository
full_test.log         transcript of `bash rerun.sh --full` on the extracted Zenodo archive (all 14786 leaves)
SHA256SUMS            sha256 of every file in this layer
SHA256SUMS.bundle     sha256 of every file inside the Zenodo archive (14 830 entries; = the archive's own SHA256SUMS)
inputs/   G1.cvtx G1.edge G1.special.json   (740 vertices, 3985 edges; A = #560, B = #181)
          G3.cvtx G3.edge G3.special.json   (2131 vertices, 12530 edges; special points and the two "spindle" cross edges)
L1/       L1_a.cnf L1_a.json               pair-property CNF (plain encoding; UNSAT is the claim)
          L1_b.cnf L1_b.json               L1_a + at-most-one clauses (the CNF that was cubed)
          lifted.jsonl liftall.json        per-leaf sha256 of CNF and lifted proof; lifting summary
          cnc_bundle.json cnc_ledger.csv   campaign record (per-cube solve time, proof size, proof sha256)
cubes/    cubes.icnf                       14786 cubes (march_cu -d 14), "a l1 l2 ... 0" format
          cover_pure.cnf cover_pure.drat   cover certificate (drat-trim: s VERIFIED)
L2/       pairs.json chain.log             copy maps and A_k/B_k indices
L3/       L3.cnf L3.drat L3.json           assembly certificate (drat-trim: s VERIFIED)
extra/    G3-5.col G3-5.json               5-colouring; spindle.cnf (the spindle-freeness CNF; its 2.6 GB DRAT is in the Zenodo layer)
scripts/  haugland.py exactfield.py spindlefind.py chain.py certify4.py l1enc.py cnc2.py cubes.py liftall.py verify_bundle.py
          refs/appendixA_paths.json        the 231 lattice paths of the paper's Appendix A (input to haugland.py)
best_S315/                                 v1.1 layer: the 1501-vertex graph G3' (its own README, RECORD_README, certificates, scripts) -- see §9
reduction_S60/                             v1.1 layer: the Proposition 2 certificate for G1 - S60 (metadata only; its 95.2 GiB of leaf proofs are not deposited) -- see §10
rerun.sh                                   re-verification driver (quick layer / full layer)
zenodo/                                    (only in the Zenodo record) hadwiger_G3_proof_bundle.tar.gz.part000..NNN, SHA256SUMS.volumes
```

The scripts are byte-identical to the ones that produced the certificates (their sha256 values appear in `SHA256SUMS.bundle`).
They are research code: tool paths are constants near the top of each file (`~/hadwiger/kissat/build/kissat`, `~/hadwiger/drat-trim/drat-trim`,
`~/hadwiger/tools/CnC/march_cu/march_cu`); build the tools there or edit the constants. Every certificate check can also be run by hand with
drat-trim alone (commands in §4), so the scripts are a convenience, not a trust anchor.

---

## 3. Environment used to produce and re-verify the certificates

| Item | Value |
|---|---|
| CPU / RAM | Intel Core i7-12700K (8 P-cores + 4 E-cores, 20 threads), 31 GB visible to WSL |
| OS | Windows 11 Home 10.0.26200, WSL2 Ubuntu 26.04 LTS, kernel 6.18.33.1-microsoft-standard-WSL2; gcc 15.2.0 |
| Python | 3.14.4 with numpy 2.5.2 (float pre-screening only), sympy 1.14.0 (selftests only); matplotlib 3.11.1 (plots only) |
| kissat | 4.0.4, github.com/arminbiere/kissat commit `8af8e56f174b778aef3aa45af9f739b2a5f492c2` (2025-10-16); binary sha256 `d00651aec73d…a2bfa2` |
| CaDiCaL | 3.0.1, github.com/arminbiere/cadical commit `c60730422e758ef1cebe7aeddf2dda31c996bf04` (2026-07-19) — probe matrix only, no certificate depends on it |
| drat-trim / lrat-check | github.com/marijnheule/drat-trim commit `2e3b2dc0ecf938addbd779d42877b6ed69d9a985` (2024-11-25); built with `-std=gnu99` (gcc 15); drat-trim sha256 `463a21fd1b82…76cef` |
| march_cu | github.com/marijnheule/CnC commit `705b60c6491ef2b61988b3ce6ac674be1b90571d` (2025-07-14), `make CC="gcc -std=gnu99 -fcommon"`; sha256 `a8b7dfdf5af0…05092` |
| cake_lpr | github.com/tanyongkiam/cake_lpr commit `a36874a8b750b43fe4b385b8ddbf5b033e46a3fa` (2026-07-22); used for the 5 % LRAT cross-check only |

Full sha256 values of the tool binaries are in the Zenodo archive's `tools.json` / `manifest.json`.

---

## 4. How to re-verify

### 4.1 Quick layer — this repository only (seconds to a few minutes, no proofs larger than 5 MB)

```
bash rerun.sh
```
This runs, in order (expected wall times on the machine above; `fresh_test.log` is a verbatim transcript of the whole quick layer run from a
clean copy of this repository — 26 s in total, measured while an unrelated 14-worker SAT campaign was occupying the machine):

1. `sha256sum -c SHA256SUMS` — every file of this layer.
2. `scripts/haugland.py --out rebuild --paths scripts/refs/appendixA_paths.json` — rebuilds H, the 84 unit vectors, T₅/T₆, G1, G2, G3 from the paper's
   definitions in exact arithmetic and asserts every count against the paper (6 s idle, 13 s under load). The rebuilt `G1.cvtx/G1.edge/G3.cvtx/G3.edge` must be byte-identical
   to `inputs/` (rerun.sh compares sha256; the transcript shows the rebuilt sha256 `441f3121…` / `992936f8…` for G3).
3. `scripts/exactfield.py check inputs/G3.cvtx inputs/G3.edge --complete` (and G1) — C1 (G3: 12 530 edges exact, 2 269 515 pairs scanned; 4–9 s).
4. `scripts/spindlefind.py enumerate inputs/G3.edge` — C4, engine A: exact enumeration of rhombus pairs, must report `Moser spindle copies = 0` (858 rhombi, 0.03 s).
5. `scripts/l1enc.py build --variant a` — rebuilds `L1_a.cnf` from `inputs/G1.*`; sha256 must equal `6d427680d5c0afd4…` (the value in `L1/L1_a.json`).
6. `drat-trim cubes/cover_pure.cnf cubes/cover_pure.drat` — cover certificate, must print `s VERIFIED` (1 s).
7. `scripts/chain.py --haugland inputs --out rebuild/chain` — L2 (exact copy maps; must reproduce `L2/pairs.json`) and L3 (re-solves with kissat, 0.2 s, and re-checks with drat-trim).
8. `drat-trim L3/L3.cnf L3/L3.drat` — must print `s VERIFIED` (0.2 s); the 16 lemma clauses in `L3.cnf` are compared with `L2/pairs.json`.
9. 5-colouring: every edge of `inputs/G3.edge` has different colours in `extra/G3-5.col`.

What the quick layer does **not** contain: the 14 786 leaf proofs (25 GB) and the spindle-freeness DRAT (2.6 GB). Without them, L1 rests on
the recorded sha256 values only. To check L1 completely you need the Zenodo layer.

### 4.2 Full layer — Zenodo archive (≈ 12 min on 14 cores; ≈ 2 h single-threaded)

```
# 1. download every hadwiger_G3_proof_bundle.tar.gz.partNNN and SHA256SUMS.volumes from the Zenodo record
sha256sum -c SHA256SUMS.volumes
cat hadwiger_G3_proof_bundle.tar.gz.part* | tar xzf -          # creates bundle/ (28 GB)
cd bundle && sha256sum -c SHA256SUMS                            # 14 830 files; identical to SHA256SUMS.bundle in this repo
bash rerun.sh                                                   # = python scripts/verify_bundle.py --bundle . --workers 14
```
`verify_bundle.py` performs 11 checks and prints one `✓`/`FAIL` line per check: SHA256SUMS; exact+complete geometry of G1 and G3;
rebuild of L1_a.cnf with sha256 match; cover certificate; leaf-set = cover-clause-set comparison; **all 14 786 leaves** (rebuild the CNF of every leaf,
compare sha256 with `lifted.jsonl`, run drat-trim on the lifted proof, require `s VERIFIED`); L2 copy maps re-run; L2 indices vs bundle; L3 re-solved;
L3 drat-trim. Our three full runs took 729 s, 739 s and 745 s (14 workers, idle machine); `bash rerun.sh --full` as shipped here took 3221 s with 6 workers
while another 14-worker SAT campaign was running (transcript: `full_test.log`). Use `--sample N` for a random N-leaf subset.

Spindle-freeness SAT certificate: `drat-trim bundle/phase2_extra/spindle/spindle.cnf bundle/phase2_extra/spindle/spindle.drat` → `s VERIFIED` (≈ 3.5 min).

### 4.3 Regenerating the L1 certificate from scratch (optional, ≈ 20 min on 14 cores)

```
march_cu L1/L1_b.cnf -d 14 -o cubes.icnf                    # ≈ 18 s; prints "number of cubes 14786, including 847 refuted leaves"
python scripts/cnc2.py --cnf L1/L1_b.cnf --icnf cubes.icnf --out cnc --workers 14 --timeout 600 --solver kissat --binary --audit-frac 0.05
python scripts/liftall.py --bundle cnc/bundle.json --cnf-a L1/L1_a.cnf --cnf-b L1/L1_b.cnf --edge inputs/G1.edge --cvtx inputs/G1.cvtx --out lift --keep-dir lifted
```
Our campaign: 14 786 leaves, every one UNSAT and drat-trim-verified on the first attempt (mean solve 0.46 s, max 8.6 s; mean verify 0.32 s;
solver CPU 6834 s, checker CPU 4752 s, wall 948 s incl. a 5 % re-solve audit); lifting all leaves to `L1_a.cnf` took 1054 s.
kissat is deterministic, so a re-run with the same binary reproduces the same proofs bit for bit.

### 4.4 Checking by hand without any script

Every UNSAT claim is "drat-trim prints `s VERIFIED`" on a CNF/DRAT pair that is in the archive:

```
drat-trim cubes/cover_pure.cnf cubes/cover_pure.drat
drat-trim L3/L3.cnf L3/L3.drat
# for a leaf <id>: append the unit clauses of cube <id> (from cubes/cubes.icnf, one line "a l1 ... 0" → lines "l1 0", ...) to L1/L1_a.cnf,
# update the clause count in the p-line, then
drat-trim L1a_cube_<id>.cnf bundle/L1/lifted/L1a_cube_<id>.drat
```
The exact CNF that each lifted proof refutes is pinned by its sha256 in `L1/lifted.jsonl` (`cnf_a_sha`).

---

## 5. Methodological note (why cube-and-conquer)

For this graph family plain CDCL is not the right tool: on `L1_a.cnf`/`L1_b.cnf` and three other encodings, kissat 4.0.4 and CaDiCaL 3.0.1
(with and without `--unsat`, with and without symmetry breaking) produced no answer in 30 minutes in 22 of 22 runs, and 2-hour runs wrote > 10 GB of DRAT
without finishing. march_cu's look-ahead splitting turns the same CNF into 14 786 cubes each refuted in under 9 s, giving a complete, checked
certificate in 16 minutes of wall time. A direct 4-colouring refutation of G3 (2131 vertices) behaves similarly but has a hard tail: 2 h timeouts for CDCL;
a depth-15 march_cu split (32 768 cubes) refuted at a mean of 4.8 s per cube (median 3.4 s), yet 227 cubes exceeded the 600 s limit and had to be
re-split, and one sub-cube alone needed 561 s and a 480 MB proof. An 8-hour, 14-core attempt verified 32 943 leaves and stopped at the time cap with
210 sub-cubes pending, so **no direct certificate for G3 exists in this release**; the statement that G3 is not 4-colourable rests on L1 + L2 + L3 only.

---

## 6. References

* J. K. Haugland, *A Moser-spindle-free 5-chromatic unit distance graph on 2131 vertices in the plane*, arXiv:2608.04542 v4, 2026.
* M. J. H. Heule, *Odd-Distance Virtual Edges in Unit-Distance Graphs*, Geombinatorics 31(2), 2021, 68–76 (the 1441-vertex Moser-spindle-free 5-chromatic graph).
  Page numbers confirmed by the author. arXiv:2608.04542 cites this note as 77–85; that range is incorrect.
* M. J. H. Heule, *Computing small unit-distance graphs with chromatic number 5*, Geombinatorics 28(1), 2018, 32–50.
* A. D. N. J. de Grey, *The chromatic number of the plane is at least 5*, Geombinatorics 28(1), 2018, 18–31.
* V. A. Voronov, A. M. Neopryatnaya, E. A. Dergachev, *Constructing 5-chromatic unit distance graphs embedded in the Euclidean plane and two-dimensional spheres*, arXiv:2106.11824.
* M. J. H. Heule, O. Kullmann, V. W. Marek, cube-and-conquer; march_cu: github.com/marijnheule/CnC.
* N. Wetzler, M. J. H. Heule, W. A. Hunt Jr., drat-trim: github.com/marijnheule/drat-trim.
* A. Biere et al., kissat and CaDiCaL: github.com/arminbiere.
* Y. K. Tan, M. J. H. Heule, M. O. Myreen, cake_lpr (verified LRAT checker): github.com/tanyongkiam/cake_lpr.

## 7. Data availability

* GitHub layer (this repository, https://github.com/Amberlogy/haugland-2131-certificates): all inputs, CNFs, cube file, cover certificate, L2/L3 certificates, 5-colouring, scripts and fingerprints (< 100 MB).
* Zenodo layer (full proof archive, 28 GB, 14 786 leaf proofs + spindle-freeness DRAT): DOI [10.5281/zenodo.22435778](https://doi.org/10.5281/zenodo.22435778).
  The archive's per-file sha256 values are in `SHA256SUMS.bundle` here, so either layer can be checked against the other.
  That DOI is the *concept* DOI and always resolves to the latest version, so it covers the v1.1 material as well.
* v1.1 (the 1501-vertex graph G3'): `best_S315/` in this repository, and the corresponding files in the Zenodo record. The 16 382 leaf DRAT proofs
  of the v1.1 layer are **not** deposited — see §9 for why and for how to regenerate and check them.
* v1.1 (the Proposition 2 certificate for G1 − S₆₀): `reduction_S60/` in this repository. Its 16 384 leaf DRAT proofs (95.2 GiB / 102.2 GB) are **not**
  deposited in either layer; every one of them is pinned by sha256 in `reduction_S60/LEAF_INDEX.json` — see §10.

## 8. License

Code (`scripts/`, `rerun.sh`): MIT. Data and certificates (`inputs/`, `L1/`, `cubes/`, `L2/`, `L3/`, `extra/`, the Zenodo archive): CC BY 4.0.
See `LICENSE`. The graph itself is Haugland's construction; please cite the paper.

---

## 9. v1.1 layer — the 1501-vertex graph (`best_S315/`)

`best_S315/` certifies **G3' = G2' u rho(G2')**, where G2' is Haugland's G2 minus a certified removable set S of **315** vertices:

| quantity | value |
|---|---|
| G2' | 751 vertices, 4043 edges |
| **G3'** | **1501 vertices, 8088 edges** |
| deleted set S | 315 vertices (`best_S315/S315.txt`) |
| our previous certified graph | 1591 vertices |
| smallest previously known spindle-free 5-chromatic UDG (Heule 2021, bibliographic; **not** re-verified here) | 1441 vertices |

Certified, to the same standard as the v1.0 material: chi(G3') = 5 (no proper 4-colouring by cube-and-conquer over 16 382 cubes, plus an explicit
proper 5-colouring checked edge by edge), and G3' contains no Moser spindle as a subgraph, by two independent engines (exact rhombus enumeration
finding 0 copies; a SAT subgraph-monomorphism CNF that is UNSAT with a drat-trim VERIFIED proof).

**1501 > 1441: this is not a record.** `best_S315/RECORD_README.md` is the archive's own record and is the authoritative description of every
certificate and of how to check each one.

### Release notes

finalize3e ran twice: once on 2026-09-09 and again on 2026-09-10 from the
archive, after a packaging bug was fixed. Each run drew an independent
random 5% sample for the cake_lpr cross-check; both passed 819/819. The
sample released here is the second run's, recorded in crosscheck.json.
The leaf_proofs/audit/ directory in the working tree holds the first run's
DRAT artefacts and is not part of this release.

The complete set of 16382 leaf proofs (128.1 GB; ~61 GB with xz, ~79 GB
with gzip) is not uploaded: both exceed Zenodo's 50 GB per-record limit.
Every leaf proof is pinned by sha256 in L1pp/LEAF_INDEX.json, and
reverify.sh regenerates and re-checks all of them from base.cnf and the
cube file.

One further file is present here only by fingerprint, because GitHub rejects files above 100 MB: the engine-B spindle-freeness proof
`L2L3/l3_final/spindle_B/spindle.drat` (542 778 955 B, sha256 `97cf230e02827a4b18c860b5b0b6a6b046f35d432431c71533e776ed8faff4fe`; the copy under
`L2L3/l3/` is byte-identical). The CNF it refutes is present, and engine A is independent of it. See `best_S315/README.md`.

### Line endings — this also fixes v1.0

v1.0 shipped without .gitattributes. On Windows, git's autocrlf converted
the released text files to CRLF on checkout, which breaks
`sha256sum -c SHA256SUMS` -- the filenames themselves are mangled. The
blobs in the repository were always correct; only the checkout was
affected, and Linux/WSL clones were unaffected. v1.1 adds .gitattributes,
which fixes this retroactively for v1.0 as well.

If you tried to verify v1.0 on Windows and it failed, that was this, not
anything you did. Re-clone (or run `git checkout -- .` after pulling
v1.1) and the check will pass.


---

## 10. v1.1 layer — the Proposition 2 certificate (`reduction_S60/`)

`reduction_S60/` holds the cube-and-conquer certificate that **G1 − S₆₀** (680 vertices, 3580 edges) has the pair property, which together with the
L2′/L3′ assembly in `reduction_S60/l3_phase3_round2/` certifies that G3′ (1891 vertices) is not 4-colourable.

**Deposited here (41 MB):** the deleted set S₆₀ (`S60.txt`, and `base.json`), `base.cnf`, the 16 384-cube file, the cover certificate
`cnc/cover_pure.{cnf,drat}`, the campaign record, the L2′/L3′ certificate `l3_phase3_round2/L3p.{cnf,drat}` with the exact coordinate and edge files,
the run and re-verification logs, and **the sha256 of every one of the 16 384 leaf proofs** (`LEAF_INDEX.json`, `SHA256SUMS.leaf_proofs`).

**Not deposited:** the leaf proofs themselves — 16 384 leaves plus 819 audit proofs, **95.2 GiB (102.2 GB)**, which exceeds Zenodo's 50 GB per-record
limit even compressed (binary DRAT compresses about 1.6× with gzip, 2.1× with xz, measured on this project's proofs). They are regenerable in about
2.4 h on 14 threads, and each one can be checked against its recorded sha256.

**There is no driver script in that directory** — unlike `rerun.sh` at the repository root (2131-vertex layer) and `best_S315/reverify.sh`
(1501-vertex layer). `reduction_S60/README.md` gives the command line instead, and lists the checks that need no leaf proofs at all
(cover certificate, L3′ certificate, edge-list completeness, `sha256sum -c SHA256SUMS`).
