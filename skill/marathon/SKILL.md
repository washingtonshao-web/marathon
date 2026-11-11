---
name: marathon
description: "Run multi-hour projects through intake, research, worker waves and gates to delivery or a decision memo. Use for marathon / 马拉松 / 大项目 / resume; not small tasks."
---

# Marathon

A marathon runs until the targets are met, scores plateau, the budget is used up or only the user can remove the obstacle; the user never has to say "continue". The global and craft rules apply.

## Must survive compaction

1. **State files.** After a resume or compaction read STATE.md and CHARTER.md, reconcile PROMPTS.md entries above ledger_through into R/Q, run `marathon.py claim <dir>` and follow next. STATE keeps the latest 5 Decisions and Log entries; older history is in DECISIONS.md. Never resume from memory, and a retired lead never reclaims a completed transfer.
2. **Gates.** Fresh reviewers assess one committed SHA against CHARTER, PROMPTS and the benchmark; builders never review their own work. [gate.md](gate.md) owns scoring, the final review and limited stop releases. Done means no critical or major problem left and both reviewers ending with `USE: yes` (they would use it as is); the score is only the floor. A release also needs the exact-artifact hard checks. Workers never commit, push or start reviews; only an authorized ops worker deploys.
3. **Rotation.** Hand off at the first quiet point past rotate_at (300k context tokens; 0 or a hands-on lead disables it). The stop hook measures the context and reminds the lead, at most three times per project, when it passes the threshold with no worker running. Integrate running workers and score any gate first, then follow [references/rotation.md](references/rotation.md): a Claude lead transfers only after a fresh successor claims; a Codex lead checkpoints its thread unless a fresh transfer is verified.
4. **Questions.** Questions the run asks the user (intake, parked choices at a phase end, the memo) go through `marathon.py ask`: at most five, ordinary defaults preselected, one Confirm, the printed HTML shown with show-widget or its text fallback. [intake.md](intake.md) covers the one-line form, `ask --resolve --at-deadline` (default 10 minutes) and replies. Answer-only progress uses the runtime question tool without STATE writes. Login, password, CAPTCHA, payment, public publishing, deletion and more budget or hours are must-decide and never default. Reuse earlier authorization; block only when nothing else can proceed.
5. **Budget and stops.** Check the hours before every wave and gate; at the budget no new work starts. Pause when the user asks. End with `marathon.py set <dir> --status done|paused|blocked --reason "..."` under gate.md's rules. While only background work runs, `marathon.py wait <dir> "<what>"` lets a turn end; `wait <dir> --clear` ends it.

## Files and phases

A project is a repo named by its slug, with no agent prefix: Use your repositories folder; Codex follows [references/codex.md](references/codex.md). Scratch and builds go to the gitignored .tmp/; large files stay out of Git.

| File | Purpose |
|---|---|
| PROMPTS.md | Verbatim user messages and lead questions |
| CHARTER.md | Goal and use, the user's problems, benchmark, G targets, rubric, intake, R/Q, parameters |
| STATE.md / DECISIONS.md | Configuration, Now/Next/Parked, recent entries / older history |
| research/ | Sources, notes, BRIEF.md ≤5,000 words, benchmark |
| audits/ / REPORTS.md | Evidence, score/worker CSVs, compromises / reports sent |

Run the installed scripts/ with Python; examples use project-relative paths. Read each phase's file on entry: [intake](intake.md), [preflight](preflight.md), [profiles](references/profiles.md) → [research](research.md), the pack, [lessons](lessons.md) → direction check → [build](workers.md) and hard checks → [gate](gate.md); repeat build and gate until [ship](ship.md) or a stop memo. [Follow-ups](followups.md) cover later answers and requested changes.

The direction check: at 15–20% of the budget, or as soon as the user can open a first version, send a preview with `marathon.py ask` and three sentences (what was done, what comes next, is this the right direction). The default is to keep going, so the run never waits for it. Record it with `set <dir> direction="sent <date> <link>"`, and later the reply.

Read the mode card, [codex](mode-codex.md) (default: GPT-6.1-Sol high workers, Astra optional) or [claude](mode-claude.md). Show the configuration at kickoff, every wave and gate, and after changes. fast runs up to 10 workers with a gate after each wave, balanced up to 4 with a gate after each integration, efficient up to 4 with gates at milestones; the reviewers are the same.

## Lead practice

- Defaults: 12 running hours, balanced, no new paid tools. Standing authority: continuing, quiet-point handoff, promoting closing lessons and assets, requested follow-ups.
- Questions, opinions and "先不要动 / just discussing" get an answer only. For authorized work, log every user message verbatim, reconcile R/Q and update ledger_through.
- When the user writes during a run, answer in a sentence or two first, then continue. Keep foreground commands under two minutes and run waits and long jobs in the background. Wait for workers with `marathon.py wait <dir> --for <ids>` (it ends at a deadline and reports empty reports); never write a waiter that waits for a report file.
- Output that may run past 40 lines (tests, builds, logs, scraping) goes to a file; print only the result and the failing lines.
- When the user asks about progress (进度, progress, 怎么样了, 还要多久), answer with `marathon.py status <dir> --report` (or the progress skill, if installed), opening with its RUN line (mode, models, hours left). Save a sent implementation report with --mark --save <file> --forecast "..."; answer-only requests authorize no writes.
- Keep progress, targets_met, next, changed and Now current. `note <dir> now "..."` replaces Now and logs the old bullets; --add records concurrent work. Record measured metrics and resources at release; unknown is not zero.
- A thin lead decides, integrates and reads summaries; workers do the bulk and live jobs. Reuse a predecessor's tooling and lessons; its code, data models or art need authorization.
- Work headless, with no desktop input or sound. Follow workers.md's browser lock and your hardware limits. A resource pause holds new starts until the user says to resume; logins and opening the final Chrome window follow authorization.

| Project | Pack / craft |
|---|---|
| Game | [game](packs/game.md) / threejs-game-director |
| Site / atlas / tool | [site](packs/site.md) / design + your deploy workflow |
| Research / strategy | [research](packs/research.md) / research + design if installed; otherwise the lead dispatches research workers per research.md |
| Film / animation | your video and QC tools; check generation credits before moving shots |

[library.md](library.md): asset reuse. [commands](references/commands.md): CLI, tests and budgets. Historical lessons are not read by default.
