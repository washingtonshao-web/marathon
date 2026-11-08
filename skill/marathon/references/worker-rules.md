# Project worker rules template

Generate docs/WORKER-RULES.md before wave 1 and link it from briefs. Copy workers.md's permissions/report rules, with project values:

- Project, stack, benchmark, STATE/audit paths and exact owned files; contracts, formatter/linter and numeric acceptance/performance/payload budgets.
- Scratch only .tmp/<id>/; Codex harness deletes it after non-gate attempts, workers do not. Keep deliverables/full reports outside that directory. Gate scratch/report permissions follow gate.md; configured Claude reviewer writes its one authorized audit.
- Leave unrelated integrations unused in all workers. No commit/push, no self-initiated review; ops needs an explicit named live operation. Repeat paid cap and report protocol.
- Before opening a browser: `marathon.py lock <dir> browser --owner <id>`. If held, do other work. Close it, then release with --release. Renew before the 30-minute default TTL expires or set --ttl MIN; never steal a live lock. Separate server ports; stop own servers.
- Headless only. For 3D use hardware-accelerated headless Chrome and the platform-appropriate graphics backend; record it. Respect hardware limits and measure on quiet hardware. The marathon lease permits only one browser across projects.
- Copy CHARTER's "What the user will do with it" section unchanged into every brief, so every builder knows who will use the work and how it could miss.
- Copy CHARTER's Scoring card (when there is one) into every brief: builders work to the same scoring the gate uses.
- A fix brief names the files to change and the problems to fix, quoting the reviewer or the user. Read only those files and what they directly reference; do not read the whole project.
- Output that may run past 40 lines (tests, builds, logs, scraping) goes to a file; report only the result and the failing lines. The project's digest scripts, when it has them, do this for tests and walks.
- Check scripts (ai_tells.py and the like) are hints, not targets: never rewrite text just to move a script's number. Reading it aloud like a colleague is the test.
- Reader-facing text (pages, captions, slides, narration) follows the design skill's writing.md when it is installed; run de-ai scripts/ai_tells.py (--spoken for narration) and report the summary line with the work, so voice problems surface in the build, not at the gate. To fix flagged text, follow the de-ai skill (read only the patterns.md sections it flags).
- One contact sheet with scripts/contact_sheet.py; inspect individual shots for specific defects. Save generated images in-project; follow the user's asset policy.

Reuse relevant rules from your assets folder's process templates; current brief/marathon permissions win.
