# Gate prompt

Save audits/round-N/prompt.md with actual paths/SHA/rubric/evidence. With a CHARTER `Format:` paste section 4 of [review-principles](review-principles.md) and the CHARTER Scoring card, and the user's own words on audience and occasion (quoted from PROMPTS, not summarised) together with CHARTER's "What the user will do with it"; leave the User calibration table in CHARTER for Pass B and never send INTENT/PLAN/fix reports as the standard. Both reviewers use gate.md's snapshot; supply a frozen evidence pack for inputs absent from Git. For the Claude reviewer (Fable by default), append the scope and delivery overrides below in fable-prompt.md (opus-/sonnet-prompt.md under those gates). Record `Claude scope: full|focused` explicitly; full wins if the lead requests it. With `gate=sonnet+astra` (or an opus gate), Claude Sonnet 5.5 (or Opus 5.5) replaces Fable throughout this prompt: use sonnet* (opus*) labels and sonnet.md (opus.md) paths, with the same full/focused and delivery rules.

~~~text
You are a fresh independent gate reviewer with no build history.
Review <full SHA> in <shared snapshot>, never the changing main checkout.
Do not edit candidate files. Checks may write only to <snapshot>/.scratch/.
Do not commit, push, publish, deploy or launch independent reviewers.
First read CHARTER "What the user will do with it" (older CHARTERs: Goal) and
say in one line whether this work does that job. If it does not, that is a critical problem.
For a game, site or tool, use it for 10 minutes in a real headless browser as
a first-time user: click, type, press keys and follow the main path.
Screenshots alone are not a review. List each moment you did not know what to
do next, and check: body text under 14 px, Chinese and English mixed on one
screen, the system cursor in a game, visible lag (record fps or load time),
and missing onboarding. Each one found is a problem in the list below.
With a CHARTER Format/Scoring card: first do Pass A (review-principles
section 4) cold, from PROMPTS only: audience, first impression, missing
content a colleague would ask for, five quoted machine-sounding sentences;
score share_ready (and voice if present). Then run de-ai ai_tells.py (--spoken
for narration), apply the Scoring card caps, mark each User calibration
reason FIXED / NOT FIXED, and explain any total more than 10 above the
latest USER_SCORE.
Read CHARTER (targets/rubric/R-Q), PROMPTS (dropped requests), BRIEF section 1,
benchmark contact sheet and <versioned checks/screenshots/data>.
First re-check every problem from the last round and every row of CHARTER
"The user's problems" by repeating its steps: FIXED / NOT FIXED with what you
saw. Then look for new problems; new problems lower the score as usual.
Add one line: since the last round, what was fixed, what is new, and why the
score moved.
Score every rubric key 0–10 with evidence and benchmark comparison.
Start the report with the problem list: critical, then major, then minor.
For each give where it is, what the person using it would think, the minimal
fix, hours, and where else the same kind of problem is likely to appear.
Critical blocks the job in "What the user will do with it", core facts or the
core loop; major is visible within 10 minutes; minor is polish. Then one line:
"Would I use it as is: yes/no, because ...". Mark R/Q items met/partly/not and
name the largest gap. Scores come after all of this.
Return the complete review, starting DONE/PARTIAL/FAILED, ending exactly:
REVIEWER: <actual label, e.g. fable-5.2-high or astra-high>
ARTIFACT: <full reviewed SHA>
SCORES: <every rubric key>=<0-10|n/a>, ...
VERDICT: PASS|FAIL critical=<integer> major=<integer>
USE: yes|no
~~~

Claude delivery override: write the full audit yourself to exactly one file, `<absolute original-project>/audits/round-N/fable.md` (`opus.md` / `sonnet.md` under those gates). This is the only report-write exception to scratch-only checks. Return ≤300 words of top defects plus those five closing lines; the lead never rewrites the review. Astra retains complete final-message delivery through --out.

Use n/a only for NA-authorized keys. Labels must start fable* (opus* only with an opus gate, sonnet* only with `gate=sonnet+astra`) or astra* for their slots, be distinct and contain no +; Sol/Luna cannot fill the Astra slot. Verify provider identity/freshness from invocation evidence; labels alone prove neither. score recomputes the result. A second Claude confirmation/fallback gets a distinct ID/report path, preserving each reviewer’s one-file ownership. Final missing-Astra fallback requires two distinct reviewers of the gate's Claude model (Fable by default; Opus or Sonnet when the gate names them), plus `--missing-reason`.

## Pack and scope

Before each gate, including a fresh final gate, run `marathon.py evidence <dir> --round N` with a fresh positive round number and the committed clean candidate. CHANGED.md pins HEAD and the latest scored regular round below N (including a pending score), ignoring later/final rows. With no earlier score it compares the empty tree to HEAD, including the initial inventory. An unresolved prior artifact fails; restore it, never silently reset the baseline. Existing packs are protected against overwrite.

Give one Codex ops worker the candidate SHA and pack path. It runs hard checks/tests, captures desktop/mobile screenshots or contact sheets where applicable, checks live URLs and fills EVIDENCE.md with commands, exit codes, test counts, timestamps and relative evidence links. Mark unavailable/not-applicable checks explicitly. Copy external inputs and previous reports/rulings into the pack; enumerate every open critical/major finding from the last scored round, including pending findings. Verify which deployment the live checks cover. No commits, candidate edits or publishing; generated outputs go in the pack or scratch.

Freeze the completed pack for both reviewers at the same absolute path; it need not be in the Git snapshot. Supply SHA, snapshot and pack paths in both prompts. Keep evidence and reports until scoring/adjudication finishes. Astra always reads all common-prompt inputs, reviews every rubric key and performs a FULL independent audit each round. Share its current findings with the Claude reviewer if ready; otherwise use the previous round's frozen findings and identify the source round. Do not wait solely for current findings or mutate an in-use pack; any new supplement is versioned and made available to both.

Append this Claude scope override (replace placeholders):

~~~text
Claude scope: <full|focused>; round <N>; final gate <yes|no>.
Start from <pack>/EVIDENCE.md and CHANGED.md. Read CHARTER and PROMPTS.
FULL: round 1, rounds 3/6/9/…, every final gate, or lead-requested full.
Review all common-prompt inputs and every rubric key.
FOCUSED: review the CHANGED.md file list and the actual changed content,
Astra's <current|previous round N> findings, ALL open critical/major defects
from the last scored round, and CHARTER's highest-weight rubric keys
(all keys tied for maximum weight). Use benchmark/source evidence for those
areas; expand scope for dependencies or a suspected regression as needed.
With a Scoring card: Pass A and share_ready every round, FULL or FOCUSED.
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

Use `score --carry-forward` for focused rounds, including delayed/late merges. Each omitted reviewer key retains the previous scored round's merged value and participates in the conservative merge with fresh scores; CSV and CLI identify its source round, reviewer and values. Astra must still score every key. Key and weighted-total disputes use only keys freshly scored by both reviewers; critical disagreements and all adjudication rules are unchanged. Round 1 needs full reports; every third regular round and final scoring reject a focused Claude review. After a gate change (e.g. opus → fable on 2026-11-12) rounds scored by the old Claude model cannot be reused or late-merged; run a fresh gate. A carried-score round cannot satisfy `--final --reuse-round`; obtain full release reviews. A lead-requested full review also uses the full prompt and omits carry-forward.
