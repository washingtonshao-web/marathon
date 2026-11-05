# Gate and stop

A gate is an independent review of one committed version. Before it the hard checks pass and the candidate SHA is pinned. Fresh reviewers get that candidate, CHARTER, PROMPTS and the benchmark, and for reader-facing work [review-principles](references/review-principles.md). Gate settings: opus+astra (the codex default), opus (regular rounds Claude only, the final adds Astra) and sonnet+astra (propose it for biology). Reviewers the user names are always used; a mode never removes them.

The Claude reviewer is Opus 5.5 xhigh, or Sonnet 5.5 xhigh with sonnet+astra (labels and paths start opus* or sonnet*). Astra high reviews FULL every round. Claude reviews FULL in round 1, every third regular round, at the final gate and when the lead asks; otherwise FOCUSED.

Ask for a review only when the last round's critical and major problems are fixed, or at least a solid batch of them: a gate after a small fix costs a full Opus and Astra round and adds little. `marathon.py status` shows the open problems and the commits since the last gate.

## Launch and delivery

Run `marathon.py evidence <dir> --round N`: an ops worker fills the evidence pack (checks, counts, screenshots, live checks) without editing or committing the candidate. Write the prompt from [gate-prompt](references/gate-prompt.md), give both reviewers the shared pack and the detached snapshot, and register Claude before Astra:

~~~text
marathon.py worker <dir> GN-opus agent=claude model=opus effort=xhigh class=gate status=running note=sha=<full-sha>
codex_worker.py run <dir> --id GN-astra --brief audits/round-N/prompt.md --class gate --sha <full-sha> --model astra --minutes 45 --out audits/round-N/astra.md
~~~

Use sonnet instead when it is configured; regular opus rounds need only Claude. Astra prints its snapshot folder (.tmp/gate/<sha7>/); share it with Claude. Freeze external inputs separately. Checks write only to .scratch/. Claude checks specific claims (about 80 tool calls focused, 150 full); Astra checks freely.

Claude writes one full audit to audits/round-N/opus.md (or sonnet.md) at the original project's absolute path and returns at most 300 words plus the five closing lines (REVIEWER, ARTIFACT, SCORES, VERDICT, USE). Astra returns the full audit, which the wrapper saves to --out. Never rewrite a review, and never let a reviewer start reviewers, commit or publish. Keep a native or bridge reviewer's invocation evidence and finish its ledger row. A gate on a new SHA removes snapshots no running reviewer uses.

~~~text
marathon.py score <dir> --round N --from audits/round-N/opus.md --from audits/round-N/astra.md
~~~

`score` merges the reports: the lower score per key and the higher problem counts. A split of 3 or more on a key, 10 or more on the total, or a critical problem only one reviewer found returns ADJUDICATE (exit 3); INVALID (exit 2) means a report or the evidence must be corrected.

## Carry and adjudication

- **Carry:** focused rounds use `--carry-forward`. Keys Claude did not re-score keep the previous merged scores, Astra still scores everything, and disputes compare only keys both scored fresh. `marathon.py score <dir> --final --reuse-round N` reuses a passing FULL dual round when HEAD, the rules and the targets are unchanged and the evidence still applies; otherwise run fresh FULL reviews with `--final`.
- **Astra late or unavailable:** after astra_wait, score Claude alone with `--astra-pending` and merge Astra later with `--late`. If Astra fails at the final gate, two fresh configured Claude reviewers score with `--missing-reason "Astra unavailable: <failure>"`, disclosed as 同模型独立复核.
- **Adjudication:** [adjudication](references/adjudication.md) defines the evidence-backed ruling; rescore with `--adjudication <file>`. Lowering the critical count needs a separate fresh reviewer who confirms it.

## Pass and final

Fix the rubric before round 1. It may change later when it proves wrong: add `RUBRIC_CHANGE: <date> <why>` to CHARTER and tell the user in the next progress report. `score` refuses changed rules without that line and counts the plateau again under the new rules. Anchors: 10 = the user would show it to its audience unchanged (same-format benchmark), 8 professional, 6 below benchmark, 4 major gaps, 2 or less broken.

The work is done (TARGET MET, or FINAL PASS at the final gate) only when all of these hold: neither report lists a critical or a major problem, both reviewers end with `USE: yes` (they would use it as is), the total is at least 85 (or PASS_TOTAL), every key is at or above its FLOOR, and every G row is ✅. The score is the floor, not the goal: when it passes while a problem is still open, keep fixing. Only authorized keys may be n/a, and at least 60% of the weight must be scored. Trust `score`, not VERDICT. A `USER_SCORE` below the pass total turns a pass into USER CHECK.

Fix the problem list from the most serious problem down. When a problem belongs to a class (the same stock phrase on many pages, every empty state, every map label), find and fix the whole class across the work, not only the quoted instance; the same applies to a problem the user points out. Log compromises.

The final gate needs a clean committed HEAD, untracked product files included, even with --artifact. Bookkeeping files (STATE, DECISIONS, PROMPTS, CHARTER, REPORTS.md, audits/, research/) may change; keep audits uncommitted until final scoring so the SHA stays the same. PASS → ship; FAIL → fix and review again.

## Stop and memo

Check the hours before every wave and gate: once the budget is used up no new work starts, whatever the score says.
- TARGET MET → final gate, ship, done.
- USER CHECK → keep working: publish a preview, write how each of the user's reasons was fixed and ask only whether it may go live (`marathon.py ask`, default: keep improving). Going live waits for USER_GO or a new USER_SCORE at or above the bar; nothing else waits, and `set --status paused` refuses that reason.
- PLATEAU (less than 3 points gained across 3 intervals, at least 4 rounds under the same rules): `score` sets plateau_review=due and puts the review first in next. Write 2–3 options (hours, expected gain) with a recommendation, send them with `marathon.py ask` (default: the recommendation), keep working on it and `set <dir> plateau_review=sent`.
- BUDGET → strategic review, decision memo, paused. BLOCKED only when a user-only obstacle remains and nothing useful is left.

A limited release at plateau, budget or blocked needs critical=0 and the exact-artifact hard checks, not FINAL PASS; otherwise keep the last verified release. A plateau or budget stop gets a fresh Claude strategy review (history, the last two gates, BRIEF, limits, levers, hours, points) plus the lead's retrospective.

The memo gives progress and the link, round scores (with the user's score and the gap), limits, 2–3 options with hours, gains and a recommendation, and the pack's 3–6 checks only a person can do. Questions and parked choices go through `marathon.py ask`; the timer `ask <dir> --resolve --at-deadline` and replies follow [intake](intake.md). Block only when no independent work is left. Save sent reports with `status <dir> --report --mark --save <file>` when authorized, and notify if available. `set <dir> --status ... --reason "..."` closes the run.
