# ZENODO_METADATA.md — fields of the Zenodo record (final 2026-09-06). Status: draft deposition 22435778 created through the Zenodo REST API with these fields, all files uploaded and checksummed, DOI 10.5281/zenodo.22435778 reserved; the record is published by the author by hand (see ZENODO_STEPS.md).

**Upload type / Resource type:** Dataset

**Title:** Machine-checked proof archive: Haugland's 2131-vertex Moser-spindle-free unit-distance graph is 5-chromatic (cube-and-conquer certificate for the pair property of G1)

**Creators:** Wong, King Tat — Affiliation: Independent researcher — ORCID: 0009-0003-4009-3619 (https://orcid.org/0009-0003-4009-3619)

**Description (abstract, one paragraph — same content as README.md §1 and §5):**

This record contains the complete machine-verifiable proof archive (28 GB uncompressed, 2 gzip volumes of 7.9 GB) for the theorem of J. K. Haugland (arXiv:2608.04542 v4) that his 2131-vertex Moser-spindle-free unit-distance graph G3 has chromatic number 5. The graph was reconstructed from the paper's definitions in exact cyclotomic arithmetic (ℚ(ζ₈₄) and ℚ(ζ₄₂₀); every intermediate count matches the paper), and the following statements were certified by machine: the edge list is the complete unit-distance graph on the 2131 exact points; G3 contains no Moser spindle as a subgraph (exact enumeration and a drat-trim-checked UNSAT certificate); G3 has a 5-colouring (checked edge by edge); and G3 has no 4-colouring. The last statement follows the paper's decomposition: (L1) in every 4-colouring of the 740-vertex graph G1 the points (0,0) and (0,√3) receive different colours; (L2) four isometric copies of G1 lie in G3 (exact arithmetic); (L3) the four resulting constraints plus the 4-colouring clauses of G3 are unsatisfiable (drat-trim-checked DRAT proof). Plain CDCL could not settle L1 (22 solver/encoding runs of 30 minutes all timed out), so L1 is certified by cube-and-conquer: march_cu (static depth 14) splits the CNF into 14 786 cubes; every cube is refuted by kissat 4.0.4 (mean 0.46 s, max 8.6 s) and each of the 14 786 DRAT proofs, lifted to the plain encoding, is checked by drat-trim (a 5 % sample also by the formally verified checker cake_lpr); the cover (the conjunction of the negated cubes) is itself a drat-trim-checked refutation. The archive contains the exact coordinate files, all CNFs, the cube file, the cover certificate, all 14 786 leaf proofs, the L2/L3 certificates, the spindle-freeness certificate, the 5-colouring, the scripts that produced everything, sha256 fingerprints of every file and of the tool binaries, and a one-command re-verification script (`bash rerun.sh`, about 12 minutes on 14 cores). The small companion repository (README, inputs, cubes, cover, L2/L3 certificates, scripts) is the GitHub layer of the same release and pins this archive by sha256. Computations were orchestrated with Claude Code (Anthropic); all mathematical claims are independently machine-checked by drat-trim / cake_lpr and reproducible from the included scripts.

**Keywords:** Hadwiger–Nelson problem; chromatic number of the plane; unit-distance graph; Moser spindle; 5-chromatic; SAT; cube-and-conquer; DRAT; proof certificate; drat-trim; kissat; march_cu; cake_lpr; exact cyclotomic arithmetic

**Language:** English

**License:** Creative Commons Attribution 4.0 International (CC BY 4.0) for the data; the scripts inside the archive are MIT (LICENSE file in the companion repository)

**Related works / identifiers:**
- arXiv:2608.04542 — relation: *is supplement to* — Haugland, J. K., A Moser-spindle-free 5-chromatic unit distance graph on 2131 vertices in the plane, v4, 2026 (resource type: preprint)
- https://github.com/Amberlogy/haugland-2131-certificates — relation: *is supplemented by* (GitHub layer of the same release; resource type Software)

**Subjects:** Mathematics — Combinatorics (math.CO); Computer Science — Logic in Computer Science (cs.LO)

**Version:** 1.0 (2026-09-05; metadata revised 2026-09-06)

**Publication date:** (date of publishing the record)

**Files to upload (all in release/zenodo/; verify with `sha256sum -c SHA256SUMS.volumes` before and after upload):**
- `hadwiger_G3_proof_bundle.tar.gz.part000`, `hadwiger_G3_proof_bundle.tar.gz.part001` — gzip-compressed tar of `bundle/`, split into volumes of at most 3800 MiB; sizes and sha256 in `VOLUMES.txt` / `SHA256SUMS.volumes`
- `SHA256SUMS.volumes`, `VOLUMES.txt`
- (small, so the record is self-describing) `README.md`, `CLAIM_en.md`, `SHA256SUMS.bundle`, `ZENODO_METADATA.md`

**Additional notes (for the "Additional notes"/"Method" field):**
Reassemble with `cat hadwiger_G3_proof_bundle.tar.gz.part* | tar xzf -` (GNU tar; produces `bundle/`, 28 GB, 14 830 files). Then `cd bundle && sha256sum -c SHA256SUMS && bash rerun.sh`. The scripts expect kissat, drat-trim and march_cu at the paths given in README.md §2 (or edit the constants at the top of each script). Contents of `bundle/`: `CLAIM.md`, `README.md`, `manifest.json`, `tools.json`, `SHA256SUMS`, `rerun.sh`, `aborted_runs.md`, `inputs/` (G1, G3 exact coordinates and edge lists), `L1/` (L1_a.cnf, L1_b.cnf, cubes.icnf, cover_pure.cnf/.drat, cnc_bundle.json, cnc_ledger.csv, liftall.json, lifted.jsonl, `lifted/` with 14 786 DRAT proofs — 25 GB), `L2/pairs.json`, `L3/` (L3.cnf, L3.drat, L3.json), `scripts/` (10 Python scripts), `phase2_extra/` (G3-5.col, spindle.cnf + spindle.drat 2.6 GB).

**Funding:** none. **Contributors:** none besides the creator. **Access right:** open. **DOI:** 10.5281/zenodo.22435778 (reserved on Zenodo; record not yet published at the time of writing)
