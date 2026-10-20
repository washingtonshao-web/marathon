# Project worker rules template

Generate docs/WORKER-RULES.md before wave 1 and link it from briefs. Copy workers.md's permissions/report rules, with project values:

- Project, stack, benchmark, STATE/audit paths and exact owned files; contracts, formatter/linter and numeric acceptance/performance/payload budgets.
- Scratch only .tmp/<id>/; Codex harness deletes it after non-gate attempts, workers do not. Keep deliverables/full reports outside that directory. Gate scratch/report permissions follow gate.md; configured Claude reviewer writes its one authorized audit.
- Leave unrelated integrations unused in all workers. No commit/push, no self-initiated review; ops needs an explicit named live operation. Repeat paid cap and report protocol.
- Before opening a browser: `marathon.py lock <dir> browser --owner <id>`. If held, do other work. Close it, then release with --release. Renew before the 30-minute default TTL expires or set --ttl MIN; never steal a live lock. Separate server ports; stop own servers.
- Headless only. For 3D use hardware-accelerated headless Chrome and the platform-appropriate graphics backend; record it. Respect hardware limits and measure on quiet hardware. The marathon lease permits only one browser across projects.
- One contact sheet with scripts/contact_sheet.py; inspect individual shots for specific defects. Save generated images in-project; follow the user's asset policy.

Reuse relevant rules from your assets folder's process templates; current brief/marathon permissions win.
