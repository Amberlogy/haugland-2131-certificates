# ZENODO_STEPS.md — uploading the proof archive to Zenodo (the author presses the buttons)

**Status 2026-09-06:** steps A and B below are done — draft deposition https://zenodo.org/deposit/22435778 was created through the REST API
(with a deposit-only token, never calling the publish endpoint); the two volumes, `SHA256SUMS.volumes`, `VOLUMES.txt`, `README.md`, `CLAIM_en.md`,
`SHA256SUMS.bundle` and `ZENODO_METADATA.md` are uploaded and their MD5 checksums returned by the API match the local files
(Zenodo reports MD5; the sha256 values are in `SHA256SUMS.volumes` / `SHA256SUMS`); the DOI **10.5281/zenodo.22435778** is reserved and already written
into README.md §7, CLAIM_en.md and ZENODO_METADATA.md (commit "Add Zenodo DOI"). Remaining: step C (publish) and step D (e-mail), both by the author.

Files to upload are in `D:\hadwiger\release\zenodo\` (WSL path `/mnt/d/hadwiger/release/zenodo/`, same as `~/hadwiger/release/zenodo/`):

```
hadwiger_G3_proof_bundle.tar.gz.part000   (≈ 3.98 GB)
hadwiger_G3_proof_bundle.tar.gz.part001   (≈ 3.9 GB)
SHA256SUMS.volumes                        (sha256 of the two volumes)
VOLUMES.txt                               (sizes + sha256, reassembly command)
README.md  CLAIM_en.md  SHA256SUMS.bundle  ZENODO_METADATA.md   (small, make the record self-describing)
```
Before uploading, in WSL: `cd /mnt/d/hadwiger/release/zenodo && sha256sum -c SHA256SUMS.volumes` → both lines `OK`.

## A. Reserve the DOI first (do NOT publish yet)
1. Log in to https://zenodo.org → **New upload** (the "+" / "Upload" button).
2. Drag in the files listed above (the two volumes take a while; Zenodo accepts up to 50 GB per record).
3. Fill in the metadata exactly as in `ZENODO_METADATA.md`:
   * Resource type: **Dataset**
   * Title: *Machine-checked proof archive: Haugland's 2131-vertex Moser-spindle-free unit-distance graph is 5-chromatic (cube-and-conquer certificate for the pair property of G1)*
   * Creators: **Wong, King Tat** — affiliation *Independent researcher* — ORCID `0009-0003-4009-3619`
   * Description: the one-paragraph abstract from `ZENODO_METADATA.md` (it ends with the AI-tool disclosure sentence)
   * Licence: **Creative Commons Attribution 4.0 International**; Access: Open
   * Keywords: copy the keyword list
   * Related works: `arXiv:2608.04542` — relation "Is supplement to" — resource type Preprint; the GitHub URL — relation "Is supplemented by" — resource type Software
   * Subjects: Mathematics – Combinatorics; Computer Science – Logic in Computer Science
   * Version: `1.0`; Language: English; Publication date: leave as today
   * Additional notes: the "Additional notes" paragraph from `ZENODO_METADATA.md` (reassembly command and archive contents)
4. In the "Digital Object Identifier" box choose **Get a DOI now** (Zenodo reserves a DOI of the form `10.5281/zenodo.NNNNNNN` without publishing).
5. Click **Save** (draft). **Do not click Publish yet.**
6. Send the reserved DOI to Claude Code.

## B. After the DOI is written into the repository
Claude Code puts the DOI into `README.md` §7 (Data availability), `CLAIM_en.md` and `ZENODO_METADATA.md`, regenerates `SHA256SUMS`, and prepares
the commit "Add Zenodo DOI". You then:
```
cd ~/hadwiger/release && git push
```
and replace the small files `README.md`, `CLAIM_en.md`, `ZENODO_METADATA.md` in the Zenodo draft with the updated ones (the two volumes and
`SHA256SUMS.bundle` do not change).

## C. Publish
1. Re-check the draft (files, metadata, licence, ORCID).
2. Click **Publish**. The DOI becomes resolvable within minutes.
3. Optional: on GitHub, add the DOI badge line to the repository description.

## D. Then the e-mail to the author
Send the GitHub URL + DOI with `for_author_summary.md` as the attachment (the letter text is written by you).
