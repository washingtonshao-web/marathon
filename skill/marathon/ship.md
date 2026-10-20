# Ship and close

gate.md owns release eligibility, including the limited plateau/budget/blocked path. Publish only the exact committed artifact whose hard checks pass. Delegate the authorized live operation to ops under workers.md.

## Release

Follow your existing deploy workflow and global instructions; preserve host access and canonical URLs. Commit source before authorized publication. If needed, create a repository under your account. Keep large assets in object storage or Releases, with manifests in Git.Build outside synchronized folders. If upload fails, diagnose and retry through an authorized route without asking the user to execute commands. Acquire `marathon.py lock <dir> browser --owner <id>` before browser checks/final Chrome opening; if held, do other work. Release after closing it. Verify production, not only local:
- Desktop and phone render: layout, type, spacing, contrast, clipping and image quality.
- Main interaction/click path, load and console checks.
- Logged-out access matches CHARTER: login page for a private site, content for public; never blank/404.
- Safari-compatible HTTPS; open the final link in Chrome.

Use design's current screenshot/visual-review workflow. Record measured metrics and resources in STATE per SKILL.md.

## Delivery

Give status first, then live link, scores, ledger checklist, compromises, human-only checks, cost and anything still worth fixing. Include:
1. Verified link and deployed commit/release ID.
2. Summary in the site or SUMMARY.md: result, scores, gaps, compromises.
3. Continuation files: CHARTER, STATE, DECISIONS history when present, PROMPTS and README with build/test/publish steps.
4. Source repo and pushed commit hash.
5. Every R/Q item marked ✅ done / ❌ not done / ⚠️ changed.
6. Running hours, marathon.py usage `<dir>` totals and approved spend. Missing lead-token baseline is unknown, not zero; do not present API-equivalent estimates as subscription charges.

For a stop memo, use gate.md's memo structure.

## Close

Under the marathon standing authorization, append dated process observations to the canonical skill's lessons-archive.md (not read by default); merge reusable rules into lessons.md without exceeding 3,000 characters, and promote genuinely reusable files under 10 MB to the assets repo (pull first, update index, commit/push). library.md owns asset locations; follow shared-skill sync rules rather than editing vendor-installed copies. Keep project-only material in the project.

After successful shipping: marathon.py set `<dir>` --status done --reason "shipped `<link>`". Other stop statuses follow gate.md. This closes Marathon continuation, not an external Codex goal.
