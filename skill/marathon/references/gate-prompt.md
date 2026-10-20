# Gate prompt

Save audits/round-N/prompt.md with actual paths/SHA/rubric/evidence. Both reviewers use gate.md's snapshot; supply a frozen evidence pack for inputs absent from Git. For Opus, append the scope and delivery overrides below in opus-prompt.md. Record `Opus scope: full|focused` explicitly; full wins if the lead requests it. With `gate=sonnet+astra`, Claude Sonnet 5.5 replaces Opus throughout this prompt: use sonnet* labels, Sonnet scope and sonnet.md paths, with the same full/focused and delivery rules.

~~~text
You are a fresh independent gate reviewer with no build history.
Review <full SHA> in <shared snapshot>, never the changing main checkout.
Do not edit candidate files. Checks may write only to <snapshot>/.scratch/.
Do not commit, push, publish, deploy or launch independent reviewers.
Read CHARTER (targets/rubric/R-Q), PROMPTS (dropped requests), BRIEF section 1,
benchmark contact sheet and <versioned checks/screenshots/data>.
Re-audit <earlier defects> as FIXED / NOT FIXED.
Score every rubric key 0–10 with evidence and benchmark comparison.
For each critical/major/minor defect give user effect, minimal fix, hours and
impact/hour rank. Critical blocks use/core facts/loop; major is visible within
10 minutes; minor is polish. Mark R/Q items met/partly/not; name the largest gap.
Return the complete review, starting DONE/PARTIAL/FAILED, ending exactly:
REVIEWER: <actual label, e.g. opus-5.5-xhigh or astra-high>
ARTIFACT: <full reviewed SHA>
SCORES: <every rubric key>=<0-10|n/a>, ...
VERDICT: PASS|FAIL critical=<integer> major=<integer>
~~~

Opus delivery override: write the full audit yourself to exactly one file, `<absolute original-project>/audits/round-N/opus.md`. This is the only report-write exception to scratch-only checks. Return ≤300 words of top defects plus those four score lines; the lead never rewrites the review. Astra retains complete final-message delivery through --out.

Use n/a only for NA-authorized keys. Labels must start opus* (sonnet* only with `gate=sonnet+astra`) or astra* for their slots, be distinct and contain no +; Sol/Luna cannot fill the Astra slot. Verify provider identity/freshness from invocation evidence; labels alone prove neither. score recomputes the result. A second Claude confirmation/fallback gets a distinct ID/report path, preserving each reviewer’s one-file ownership. Final missing-Astra fallback requires two distinct Opus reviewers, or two distinct Sonnet reviewers with `gate=sonnet+astra`, plus `--missing-reason`.

## Pack and scope

Before each gate, including a fresh final gate, run `marathon.py evidence <dir> --round N` with a fresh positive round number and the committed clean candidate. CHANGED.md pins HEAD and the latest scored regular round below N (including a pending score), ignoring later/final rows. With no earlier score it compares the empty tree to HEAD, including the initial inventory. An unresolved prior artifact fails; restore it, never silently reset the baseline. Existing packs are protected against overwrite.

Give one Codex ops worker the candidate SHA and pack path. It runs hard checks/tests, captures desktop/mobile screenshots or contact sheets where applicable, checks live URLs and fills EVIDENCE.md with commands, exit codes, test counts, timestamps and relative evidence links. Mark unavailable/not-applicable checks explicitly. Copy external inputs and previous reports/rulings into the pack; enumerate every open critical/major finding from the last scored round, including pending findings. Verify which deployment the live checks cover. No commits, candidate edits or publishing; generated outputs go in the pack or scratch.

Freeze the completed pack for both reviewers at the same absolute path; it need not be in the Git snapshot. Supply SHA, snapshot and pack paths in both prompts. Keep evidence and reports until scoring/adjudication finishes. Astra always reads all common-prompt inputs, reviews every rubric key and performs a FULL independent audit each round. Share its current findings with Opus if ready; otherwise use the previous round's frozen findings and identify the source round. Do not wait solely for current findings or mutate an in-use pack; any new supplement is versioned and made available to both.

Append this Opus scope override (replace placeholders):

~~~text
Opus scope: <full|focused>; round <N>; final gate <yes|no>.
Start from <pack>/EVIDENCE.md and CHANGED.md. Read CHARTER and PROMPTS.
FULL: round 1, rounds 3/6/9/…, every final gate, or lead-requested full.
Review all common-prompt inputs and every rubric key.
FOCUSED: review the CHANGED.md file list and the actual changed content,
Astra's <current|previous round N> findings, ALL open critical/major defects
from the last scored round, and CHARTER's highest-weight rubric keys
(all keys tied for maximum weight). Use benchmark/source evidence for those
areas; expand scope for dependencies or a suspected regression as needed.
Reassess changed/implicated keys and all maximum-weight keys. List omitted
keys as CARRIED from scored round <N>; do not put them in SCORES.
The SCORES line contains only keys actually re-assessed. Omitted scores
carry the previous round's merged values, not an invented fresh assessment.
VERDICT counts include every still-open critical/major defect; silence or
an omitted key never closes a defect. Cite prior evidence for carried findings.
Run your own checks only to verify/refute a specific evidence claim or a
suspected defect. Budget about 80 tool calls FOCUSED or 150 FULL; count calls.
At the cap stop and write your report, stating calls used and unchecked areas.
If required scope is unfinished, mark PARTIAL; the lead must complete it before
scoring a complete gate. Never claim unperformed checks or fabricate scores.
~~~

Use `score --carry-forward` for focused rounds, including delayed/late merges. Each omitted reviewer key retains the previous scored round's merged value and participates in the conservative merge with fresh scores; CSV and CLI identify its source round, reviewer and values. Astra must still score every key. Key and weighted-total disputes use only keys freshly scored by both reviewers; critical disagreements and all adjudication rules are unchanged. Round 1 needs full reports; every third regular round and final scoring reject focused Opus. A carried-score round cannot satisfy `--final --reuse-round`; obtain full release reviews. A lead-requested full review also uses the full prompt and omits carry-forward.
