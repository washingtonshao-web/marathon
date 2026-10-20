# Gate and stop

Hard checks pass; pin committed SHA/show config. Fresh reviewers get that candidate, CHARTER/PROMPTS/benchmark. Gates: opus+astra (codex default), opus (regular Claude-only, final adds Astra), sonnet+astra (propose for biology). Honor named reviewers; modes cannot remove them.

Claude = Opus 5.5 xhigh, or Sonnet 5.5 xhigh for sonnet+astra (opus*/sonnet* labels/paths). Astra high is FULL every round. Claude is FULL in round 1, every third regular round, final or on lead request; otherwise FOCUSED.

## Launch and delivery

`marathon.py evidence <dir> --round N`: ops fills/finalizes checks/counts/screenshots/live evidence, no candidate edits/commits. Use [gate-prompt](references/gate-prompt.md), shared pack/detached snapshot; register Claude before Astra to prevent cleanup:

~~~text
marathon.py worker <dir> GN-opus agent=claude model=opus effort=xhigh class=gate status=running note=sha=<full-sha>
codex_worker.py run <dir> --id GN-astra --brief audits/round-N/prompt.md --class gate --sha <full-sha> --model astra --minutes 45 --out audits/round-N/astra.md
~~~

Substitute sonnet when configured; opus regular rounds need only Claude. Astra prints .tmp/gate/<sha7>/; share it with Claude. Freeze external inputs separately. Checks write .scratch/ only. Claude checks specific claims (80 calls focused/150 full); Astra checks freely.

Claude writes one full audit to the absolute original-project audits/round-N/opus.md (or sonnet.md); returns ≤300 words plus four score lines. Astra returns the full audit; wrapper saves --out. Never rewrite reviews or permit recursion/commits/publishing. Fresh native Claude/Codex bridge: retain invocation evidence and finalize ledger rows. Remove the exact snapshot only with no same-SHA reviewer running.

~~~text
marathon.py score <dir> --round N --from audits/round-N/opus.md --from audits/round-N/astra.md
~~~

Supply required reports; merge lower scores/max defects. ≥3 key split, ≥10 total split or one-sided critical → ADJUDICATE (exit 3); INVALID (exit 2) needs report/evidence correction.

## Four special cases

1. **Partial-then-merge:** Claude first: `marathon.py wait <dir> --gate --round N --start` once; query without --start. GO after astra_wait (default 10 min; zero always waits) permits `score <dir> --round N --from <claude-report> --astra-pending`. Later rescore both with --late --round N. Replaces original round/artifact using current rules/budget; apply defects to current work. Timer is advisory, never sets waiting_on. No partial final; retain live snapshots. Other regular technical absences need --missing-reason (≥10 characters).
2. **Carry:** focused rounds use --carry-forward; omitted Claude keys retain previous merged scores, Astra stays full, disputes compare fresh shared keys. `marathon.py score <dir> --final --reuse-round N` reuses a passing FULL dual round on unchanged clean HEAD/rules/targets. Rejects pending/missing/single-family/carried rows or absent rule snapshot. Evidence must still apply; otherwise fresh FULL reviews + --final.
3. **Final fallback:** FAILED/ASTRA UNAVAILABLE, never elapsed wait. Get a second fresh configured Claude reviewer, distinct label/report; score both with --final --missing-reason "Astra unavailable: <failure>". Disclose 同模型独立复核. No two-Astra replacement for Claude; no Sol/Luna in astra*.
4. **Adjudication:** [adjudication](references/adjudication.md) defines the evidence-backed ruling; rescore with --adjudication <file>. Reducing max critical needs a separate fresh confirming reviewer.

## Pass and final

Fix rubric before round 1/log changes. Anchors: 10 benchmark, 8 professional, 6 functional/below benchmark, 4 major gaps, ≤2 broken. PASS: total ≥85 (or PASS_TOTAL), each key ≥8 (or FLOOR), critical=0, ≥1 G target and all G rows ✅. Only authorized n/a; ≥60% rubric weight scored. Trust score, not VERDICT. Fix highest user-impact/hour defects; record compromises.

Final needs clean committed HEAD including untracked product files, even with --artifact. Bookkeeping: STATE/DECISIONS/PROMPTS/CHARTER/REPORTS.md, audits/, research/. Keep audits uncommitted until final scoring to preserve SHA. PASS → ship; FAIL → fix/review. Direction: fresh Claude compares 3–4 benchmarked options.

## Stop and memo

Check hours before wave/gate: budget stops new work even if score suggests otherwise. TARGET MET → final/ship/done. PLATEAU (<3 gained across 3 intervals, ≥4 rounds) or BUDGET → strategic review/memo/paused. BLOCKED means user-only obstacle and nothing useful remains. User pause is immediate.

Limited plateau/budget/blocked release: critical=0 + exact-artifact hard checks; no FINAL PASS required. Otherwise keep last verified release. Plateau/budget gets fresh configured Claude strategy review: history, last two gates, BRIEF, limits/levers/hours/points; add lead retrospective.

Memo: progress/link, round scores, limits, 2–3 options with hours/gains/recommendation, pack's 3–6 human checks. Questions/parked choices: `marathon.py ask`, ≤5, defaults selected, one Confirm, show-widget/text fallback. [Intake](intake.md): `marathon.py ask <dir> --resolve --at-deadline` (10 min); Claude uses run_in_background, Codex waits foreground only when idle, otherwise checks `ask <dir> --status` next step. Replies: `ask <dir> --resolve --answers "<reply>"`; must-decide never defaults. Block only without independent work. Save sent reports with `status <dir> --report --mark --save <file>` when authorized; notify if available. `set <dir> --status ... --reason "..."` closes the run.
