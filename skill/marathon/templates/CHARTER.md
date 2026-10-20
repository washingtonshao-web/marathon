# {title}: charter

Type: {type} · Started: {date} · Folder: `{dir}` · Budget, mode and progress: see STATE.md

## Goal
<one paragraph in the user's own words; quote the key sentence from PROMPTS.md>

## Benchmark
<the gold standard, and what "as good as it" concretely means here>

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
