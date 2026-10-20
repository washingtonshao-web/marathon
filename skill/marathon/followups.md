# Follow-ups

Ordinary questions, opinions and what-if questions get an answer only: no file or published-deliverable changes. Implement only when the user asks for a change; then apply SKILL.md's logging/status rules and add Q/R rows or parameter-ledger entries.

| Kind | Action |
|---|---|
| Content/what-if question | Answer in chat only |
| Requested scenario | Add a labelled scenario; leave baseline parameters unchanged unless adopted |
| Parameter change | Record date/source; recompute every dependent number, chart and conclusion |
| Small change (roughly <1 h compute) | Implement, run affected hard/visual checks, commit candidate, re-gate per gate.md, republish when release checks pass |
| Large change (new domain/module, doubled coverage, long pipeline) | Resume running with a reason, add targets, full build/gate/final cycle, ship; preserve the old link |

For a small re-gate use the configured reviewers (gate.md), not automatically Opus alone:
marathon.py score `<dir>` --round N --carry-forward --from `<report>` [--from `<other-report>`].
Prepare the evidence pack per gate.md. Astra reviews every key when required; the configured Claude reviewer follows the full/focused cadence. In focused rounds, each omitted Claude key inherits the previous scored regular round and is labelled carried. This requires earlier scores; reports still identify the new candidate. Full rounds omit --carry-forward. Include fresh evidence for affected behavior and full final reports if the change needs the release path; carried-score rounds cannot be reused as a final gate.

Every delivered change gets a dated 更新记录/changelog line: what changed and which conclusions moved, by how much. The parameter ledger in CHARTER is authoritative.

“Resume `<project>`”: keep its assigned repo, follow SKILL.md's resume sequence, inspect the last gate and open Q rows, then set `<dir>` --status running --reason "`<reason>`" if work remains. Use fresh context for a major round; do not reread weeks of transcript.

Parallel forks own separate repos/slugs; do not read another fork's output unless the user requests comparison. When requested, compare what differs and why.
