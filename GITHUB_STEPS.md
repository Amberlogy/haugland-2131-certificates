# GITHUB_STEPS.md — publishing the GitHub layer (the author presses the buttons; nothing here is done by Claude Code)

The local repository is `~/hadwiger/release/` inside WSL (Ubuntu). It already contains one commit on branch `main`
("Machine-checked certificates for Haugland's 2131-vertex Moser-spindle-free 5-chromatic graph (v1.0)", author King Tat Wong).
`zenodo/` (the 28 GB archive volumes) and all large proof files are excluded by `.gitignore`; the tracked content is about 34 MB.

## 1. Create the empty repository on GitHub (web browser)
1. Log in to GitHub → **New repository**.
2. Repository name: `haugland-2131-certificates`.
3. Visibility: **Public**.
4. **Do not** tick "Add a README file", **do not** add a `.gitignore` template, **do not** choose a licence — the local repository already has README.md, .gitignore and LICENSE; adding them on the web would create a conflicting first commit.
5. Click **Create repository**. GitHub shows a page "…or push an existing repository from the command line"; note the repository URL, e.g. `https://github.com/Amberlogy/haugland-2131-certificates.git`.

## 2. Push from WSL (Ubuntu terminal)
```
cd ~/hadwiger/release
git remote add origin https://github.com/Amberlogy/haugland-2131-certificates.git
git push -u origin main
```
Authentication: with HTTPS, GitHub asks for a username and a **personal access token** (not the account password): GitHub → Settings → Developer settings →
Personal access tokens → Fine-grained token with "Contents: read and write" on this repository, or a classic token with scope `repo`.
Alternatively use SSH: `git remote set-url origin git@github.com:<USER>/haugland-2131-certificates.git` after adding your SSH key to GitHub.

If the push is rejected with "remote contains work that you do not have locally", the repository was created with a README/licence on the web;
delete it on GitHub and recreate it empty (step 1.4), then push again.

## 3. Check the result in the browser
* The repository page renders `README.md` (title, §1 table of certified statements, §4 re-verification).
* `SHA256SUMS`, `SHA256SUMS.bundle`, `inputs/`, `cubes/`, `L1/`, `L2/`, `L3/`, `extra/`, `scripts/` are present; `zenodo/` is absent (correct).
* Optional: GitHub → Releases → "Draft a new release", tag `v1.0`, title "v1.0 — certificates as verified 2026-09-05", attach nothing (the archive goes to Zenodo).

## 4. Tell Claude Code the repository URL
The URL is needed in `ZENODO_METADATA.md` (related identifier) and, after Zenodo assigns a DOI, README.md §7 will get the DOI and a second commit
("Add Zenodo DOI") will be prepared for you to push.

## 5. Later: second push after the DOI is added
```
cd ~/hadwiger/release
git log --oneline          # expect two commits: v1.0 and "Add Zenodo DOI"
git push
```
