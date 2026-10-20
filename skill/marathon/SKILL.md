---
name: marathon
description: "Run multi-hour projects through intake, research, worker waves and gates to delivery or a decision memo. Use for marathon / 马拉松 / 大项目 / resume; not small tasks."
---

# Marathon

Run until targets, plateau, budget or a user-only blocker; never require “continue”. Global/craft rules apply.

## Must survive compaction

1. **State file protocol.** After resume/compaction read STATE.md/CHARTER.md, reconcile PROMPTS.md above ledger_through into R/Q; `marathon.py claim <dir>` and follow next. STATE keeps the latest 5 entries in each Decisions/Log section; read DECISIONS.md for older history. Never resume from memory or reclaim a completed transfer as the retired lead.
2. **Gate rule.** Fresh reviewers assess one committed SHA against CHARTER/PROMPTS/benchmark; builders cannot review it. [gate.md](gate.md) owns scoring/final review and limited stop releases. Release requires critical=0 and exact-artifact hard checks. The final gate is the independent review. Workers cannot commit/push/start reviews; only authorized ops deploy.
3. **Rotation trigger.** First quiet point past rotate_at (150k context tokens; zero/hands-on disables). Finish workers and integrate/score first. Follow [references/rotation.md](references/rotation.md): Claude transfers only after a fresh successor claims; Codex checkpoints its thread unless a fresh transfer is verified.
4. **Ask rule.** Marathon-run questions—intake, phase-end parked choices, memo—use `marathon.py ask`: ≤5, ordinary defaults preselected, one Confirm, printed HTML via show-widget or text fallback. [intake.md](intake.md) defines `ask --resolve --at-deadline` (default 10 minutes) and reply resolution. Answer-only progress uses the runtime question tool without STATE writes. Login, password, CAPTCHA, payment, public publishing, deletion and more budget/hours are must-decide: never auto-default. Reuse prior authorization; block only when nothing else can proceed.
5. **Continue within budget.** Check hours before wave/gate; stop new work at budget. Pause on request. End with `marathon.py set <dir> --status done|paused|blocked --reason "..."` under gate.md. For background-only work, `marathon.py wait <dir> "<what>"` permits ending a turn; `wait <dir> --clear` on completion. It is not a scheduler.

## Files and phases

Project = repo/slug, no agent prefix. Use your repositories folder; Codex: [references/codex.md](references/codex.md). Scratch/builds: gitignored .tmp/; large files stay out of Git.

| File | Purpose |
|---|---|
| PROMPTS.md | Verbatim user messages and lead questions |
| CHARTER.md | Goal, benchmark, G targets, rubric, intake, R/Q, parameters |
| STATE.md / DECISIONS.md | Configuration, Now/Next/Parked, recent entries / older history |
| research/ | Sources, notes, BRIEF.md ≤5,000 words, benchmark |
| audits/ / REPORTS.md | Evidence, score/worker CSVs, compromises / reports sent |

Use Python with installed scripts/ paths; examples are project-relative.

Read on phase entry: [intake](intake.md), [preflight](preflight.md), [profiles](references/profiles.md) → [research](research.md)/pack/[lessons](lessons.md) → direction sample → [build](workers.md)/hard checks → [gate](gate.md); repeat build/gate until [ship](ship.md) or stop memo. [Follow-ups](followups.md): answer or requested change.

Read [codex](mode-codex.md) (default: GPT-6.1-Sol high workers; Astra optional) or [claude](mode-claude.md). Show config at kickoff/wave/gate/changes. Modes: fast ≤10 workers/gate each wave; balanced ≤4/each integration; efficient ≤4/milestones. Same reviewers.

## Lead practice

- Default 12 running hours/balanced/no new paid tools. Standing authority: continuation, quiet-point handoff, closing lesson/asset promotion, requested follow-ups.
- Questions/opinions/“先不要动 / just discussing”: answer only. For authorized work, log all messages verbatim (including queued ones), reconcile R/Q, update ledger_through.
- Status first, at phase/wave changes and every ~30 minutes. Use the progress skill if installed; otherwise use `marathon.py status <dir> --report` for progress reports. Save sent implementation reports with --mark --save <file> --forecast "..."; answer-only requests authorize no writes.
- Update progress, targets_met, next, changed and Now. `note <dir> now "..."` replaces Now/logs old bullets; --add records concurrent work. Record measured metrics/resources at release; unknown is not zero.
- Thin lead decides/integrates/reads summaries; workers do bulk/live jobs. Reuse predecessor tooling/lessons; code, data models or art need authorization.
- Headless, no desktop input/sound. Use workers.md's browser lock and your hardware limits; explicit resource pauses hold new starts until resume; login/final Chrome opening follows authorization.

| Project | Pack / craft |
|---|---|
| Game | [game](packs/game.md) / threejs-game-director |
| Site / atlas / tool | [site](packs/site.md) / design + your deploy workflow |
| Research / strategy | [research](packs/research.md) / research + design if installed; otherwise the lead dispatches research workers per research.md |

[library.md](library.md): asset reuse. [commands](references/commands.md): CLI/tests/budgets. Historical lessons are not read by default.
