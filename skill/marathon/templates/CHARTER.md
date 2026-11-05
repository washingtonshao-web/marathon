# {title}: charter

Type: {type} · Started: {date} · Folder: `{dir}` · Budget, mode and progress: see STATE.md

## Goal
<one paragraph in the user's own words; quote the key sentence from PROMPTS.md>

## What the user will do with it
Written at intake from PROMPTS.md, quoted, never paraphrased. Copy this section unchanged into every worker brief and every gate prompt; reviewers check it first.
- In the user's words: <quote: who it is for, what for, on which occasion>
- They will: <e.g. present it to colleagues at the Friday meeting / pick the extraction method for the lab / send the link to friends>
- Wrong if: <2–3 concrete misses, e.g. "lists evidence without a recommendation", "five days chosen but only nearby places recommended", "a history film where a city promo was asked for">

## The user's problems (reproduce before marking fixed)
Every problem the user points out gets a row in their words, plus the steps that show it. Mark it fixed only with evidence from the same steps (a screenshot, clip or measurement); `marathon.py status` counts them and reviewers re-check each row. Before fixing one, look for the same kind of problem elsewhere.
| # | The user's words | How to reproduce | Status (open / fixed) | Evidence |
|---|---|---|---|---|
| U1 | | | open | |

## Benchmark
Format: <set by init --format (talk | report | tool | film | game); left like this when the deliverable fits no profile>
<the gold standard of that same format, and what "as good as it" concretely means here>

Adjusted bar (only when the benchmark is out of reach; also edit the FLOOR line below):
| Dimension key | 10 means | 8 means |
|---|---|---|

## Acceptance targets
Hard targets, each checked by a script or a count. Put ✅ in the Status cell only when the check passed on the current build; `marathon.py score` counts ✅ rows and requires all of them for TARGET MET.
| # | Criterion | Target | How measured | Status |
|---|---|---|---|---|
| G1 | | | | – |

## Gate rubric
Machine-read by `marathon.py score`: keys must match the gate's SCORES line exactly; weights sum to 100. Optional lines: `FLOOR: key=7, …` (default 8 per key), `PASS_TOTAL: 85`, and `NA:` listing the only keys a reviewer may mark n/a (e.g. map_dataviz for a site without maps). Fix these before the first gate.
{rubric}
NA: 

## User calibration
The user's own 0-100 scores outrank the reviewers (references/review-principles.md). One line per score; the last counts. `marathon.py score` turns a reviewer pass into USER CHECK while the latest is below the pass total.
<!-- USER_SCORE: 62 sha=abc1234 date=2026-11-04 -->
| Date | Artifact | Score | Reasons (verbatim) | Status per reason |
|---|---|---|---|---|

## Intake (ask batch, defaults, answers; must-decide never defaults)
| # | Question | Default offered | Answer |
|---|---|---|---|

## Ledger: requirements (R) and questions (Q) from PROMPTS.md
Every user message is checked against this table. Q items are answered directly; R items are built.
| id | Requirement or question | Date | Status (open / done / answered / rejected: why) |
|---|---|---|---|
| R-1 | | | open |

## Rejected options and don'ts
-

## References and inputs
| Input | Use (build on / reference only / tooling only) |
|---|---|

## Tools & access
- Tools: <from preflight>
- Logins verified: <list, date>
- Paid tools approved: none (subscription and free routes only)

## Assumptions (defaults taken without asking)
-

## Parameter ledger (research and models)
| Parameter | Value | Date | Source |
|---|---|---|---|
