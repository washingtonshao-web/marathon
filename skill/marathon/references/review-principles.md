# Review principles: score the way the user does

For anything people read, watch, hear, use or play. `ai_tells.py` comes from the de-ai skill, which installs with Marathon; `writing.md` comes from an optional design skill. Without de-ai, reviewers quote the machine-sounding sentences themselves and skip the script cap. Scoring is set per kind of deliverable in `templates/scoring/<format>.json` (talk, report, tool, film, game); edit those files to match your own judgment. The same profile goes to the builders at kickoff and to the reviewers at the gate.

Why: in one real case both model reviewers passed a talk at 87–89 while its owner gave it 60–65, for AI-sounding prose, a report format where a talk was needed, a poor narration voice and missing sections. Rubrics that reward verifiability over voice and fit, the builder's own framing, and two models sharing the same blind spots explain most of such gaps; the steps below address each.

## 1. Pick the profile at intake
- Decide what the deliverable is, from the user's words: **talk** (they present it: 讲课, 分享会, 汇报), **report** (colleagues read it), **tool** (site, atlas, database, tool: they look things up), **film** (video, animation), **game**. "分享给同事" alone does not say talk or report: ask in the intake batch.
- Start with `marathon.py init <dir> --type <type> --format <format>`. It writes `Format:`, the profile's RUBRIC/FLOOR/PASS_TOTAL and a **Scoring card** into CHARTER. Every worker brief copies the Scoring card, so builders know before they start what is scored, what loses points and what to self-check (`ai_tells.py`, reading the first screen aloud).
- **A revamp is scored as what it revamps**: a revamped talk uses the talk profile, a revamped site the tool profile. Revamp adds only its own pass conditions (blind preference, improvement over the old version).
- **When the deliverable fits no profile, or two equally, use none**: omit `--format`; the generic `rubric-<type>.txt` applies and no profile caps bind. Reviewers still quote `ai_tells.py` as evidence. Write in CHARTER which profiles were considered and why none fits.
- `score` holds a CHARTER with `Format:` to its profile: same keys and weights, floors not lower, `share_ready` re-scored every round. Only the user changes a profile: edit its JSON file (or regenerate the files with `scripts/scoring_profiles.py` from exported settings), run the tests and commit.

## 2. Profiles in brief
- **share_ready** ("愿意拿给同事看 / 同事用 / 给朋友玩") is the heaviest key in every profile (25–30): would the user show it to that audience tomorrow, unchanged.
- **Floors are percentages** of each key's full marks (80% of a 30-point key = 24 points); `FLOOR` writes them on the 0–10 scale (80% = 8). share_ready and accuracy-type keys keep 80%; secondary keys (slides, narration, presentation, pacing, phone, speed, interaction, performance) are 70% (user, 2026-11-05).
- **Caps**, in the order the user ranked them: too many notes; the judgment apparatus itself (probability tables, expiry and review dates, "倾向发生 / 不发生", "判断按……写"; allowed only where a year-end report needs them); first-screen tallies or talk about the document; the `ai_tells.py` suggestion (including stock frames repeated 3+ times); a talk built as a report; missing content a colleague would ask for (the reviewer names it; there is no fixed section checklist); a user reason still open. Each profile names the key a cap limits.
- **Caps are ceilings, never deductions**: when several apply to one key, only the lowest counts; nothing is subtracted on top. **share_ready is never capped**: it is the reviewer's overall judgment, so a cap on it would count the same problem twice.
- **The narration voice is the builder's choice and an ordinary score**: with the `listen` step the builder tries 2–4 voice samples and picks the most natural one; reviewers judge it inside narration (talk) or voice (film), like any other item. No user sign-off and no release hold (user, 2026-11-05). One exception, for children's content with the qc-voice module on: clips that still fail ASR after retakes (at most 50) go on a parent listening page; the parent's marks only clear or redo those clips and never hold a release (user, 2026-11-08).
- No fixed "expected sections" list and no format_fit key by default: checklists make builders write to a template, which reads as AI.

## 3. The user's score is the reference
- **Collect it.** (a) Whenever the user gives a score or a verdict ("只能给 60–65 分"), record it at once. (b) Never ask the user for a score: they said being sent back to score is wrong (2026-11-05). The direction check (SKILL.md) asks about direction only, and revamp previews ask only the go-live question.
- **Record it** in CHARTER: `USER_SCORE: 62.5 sha=<sha7> date=2026-11-04` (the last valid line counts; a range such as 60–65 counts as its midpoint), or `USER_GO: sha=<sha7>` when the user says to ship that artifact; and a **User calibration** table: date, artifact, score, the reasons verbatim, per reason open / fixed (evidence), and the `ai_tells.py` summary line (data for recalibrating its thresholds).
- **What `score` does.** Prints the user's score, the reviewers' total on that artifact under the same weights, the gap and a calibrated estimate. A user score below PASS_TOTAL on this exact artifact: it cannot pass. On an earlier artifact: a reviewer pass becomes **USER CHECK**: keep working; publish a preview, show the user what changed against each reason and ask only whether it may go live, never for a new score; ship only after USER_SCORE ≥ PASS_TOTAL or USER_GO on that commit. A USER CHECK round can be reused for the final once that approval exists. Approvals on a commit `score` cannot find are ignored with a warning; low scores on one still hold. A limited plateau/budget release never ships a commit the user scored below the bar.
- **Report in the user's terms**: "reviewers 88 · user 62 on <sha> · gap 26 · calibrated estimate 70"; each open user reason becomes a G row ("user's reasons fixed: n/3").

## 4. Reviewer steps (paste into the gate prompt with the CHARTER Scoring card)
**Pass A, cold, as the audience (first ~10 minutes, before CHARTER, INTENT, PLAN, fix reports or earlier reviews):**
1. From PROMPTS.md only, write the audience and occasion in one line, in the user's words.
2. Open the deliverable as that person: desktop and phone first screens, two random sections, 30 s of each film with its transcript.
3. Write a three-line first impression, the content that person would ask about and not find (named, specific), and five sentences quoted verbatim that sound machine-written or that no colleague would say.
4. Score `share_ready` now (and `voice` where the profile has it). Pass B may lower them, never raise them.

**Pass B, the rubric:** read CHARTER (Scoring card, User calibration), PROMPTS, evidence. Run `python <de-ai skill>/scripts/ai_tells.py <build>` on the main pages and `--spoken` on narration scripts, quote the summary line. Score every key, apply the Scoring card's caps (the `ai_tells` cap unless you quote the hits and show they are false positives), mark each user reason fixed / not fixed. If your total is more than 10 above the latest USER_SCORE, name the keys that make up the gap and why the user's reasons no longer apply; if you can't, lower them. Pass A skipped or `ai_tells` not run: report PARTIAL.

Builder documents (INTENT inferred lines, PLAN, CONTRACT, fix reports, worker notes) are evidence to check, not the standard. The prompt quotes the user's words on audience and occasion, not a summary. Every round, including bounded rescores, starts with Pass A; a rescore limited to "your own earlier items" is not a gate.

## 5. Benchmark and anchors
10 = the user would show it to its audience unchanged. The benchmark is the best example of the same kind (for a talk: an excellent internal talk by a senior colleague), not of another genre. A style reference ("像券商报告那样精致") sets polish, not format.

## 6. Pass and release
- gate.md's PASS conditions with the profile's floors; an open user reason caps its key (never share_ready) at 70%, which blocks the pass where that key's floor is 80%.
- The user outranks two models that agree: shared blind spots make model consensus no evidence on voice or fit. When reviewers and the user differ by ≥ 15, the user's reasons lead the next wave and the next gate checks each in Pass B.
- After two gates where reviewers and user differ by ≥ 15, write 2–3 options with a recommendation (change the profile, the format, or the brief), send them with `marathon.py ask` and continue on the recommendation; do not stop the fix rounds to wait.
