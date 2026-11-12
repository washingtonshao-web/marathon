# Build waves

The lead scopes and integrates; workers do the bulk and live jobs within SKILL.md's caps. Generate docs/WORKER-RULES.md from [worker-rules](references/worker-rules.md). A brief at .tmp/briefs/<id>.md gives the task, owned files, inputs, CHARTER's "What the user will do with it" and Scoring card, numeric acceptance, class, time, token and paid budgets, and the report path. Workers re-read shared files and return exact patches for files they do not own.

A fix brief names the files to change and the problems to fix, quoting the reviewer or the user; the worker reads only those files and what they directly reference. Mechanical edits (layout, wording, bulk replacements, data clean-up) go to Codex first; on quota or capacity errors the fallback chain moves them to Claude.

Workers never commit, push or start reviewers. Only an ops worker performs a live operation its brief authorizes; this overrides the general shipping rules. Scratch goes to .tmp/<id>/ (harness cleanup per codex-workers.md); deliverables and evidence go to audits/ or .tmp/reports/. Leave unrelated integrations unused.

To drive or measure a page in a browser, `marathon.py lock <dir> browser --owner <id>`; if held, do other work (research reads need no lease). Close it and release with --release. The lease is per PC with a 30-minute TTL; renew with the same owner or --ttl MIN, and never steal a live lease. Heavy jobs: one at a time.

`marathon.py config <dir> --models` shows the STATE chain; new codex projects default to GPT-6.1-Sol high → GPT-6-Astra high → Claude Sonnet 5.5, and `set <dir> workers=astra` opts into Astra. [codex-workers](references/codex-workers.md) covers launches. Claude leads use native agents; Codex leads use the [bridge](references/codex.md). Steer weak output.

Every worker has a row in audits/workers.csv; `backend` is the actual Codex backend (empty in old rows = subscription). The wrapper records its own workers; record native and bridge workers yourself:

~~~text
marathon.py worker <dir> W12 agent=claude model=sonnet effort=high class=build
marathon.py worker <dir> W12 status=done minutes=12 input=12345 output=678
marathon.py worker <dir> W12 first_pass=y fix_lines=0 critical=0 major=0
~~~

Record measured values. A final status fills an empty ended; any other clears it unless given. `marathon.py worker <dir>` lists workers (--pool groups them); `usage` does the accounting. `status` lists workers without new output for 30 minutes.

Writable non-gate workers save .tmp/reports/<id>.full.md and return at most summary_words (default 300), starting DONE, PARTIAL or FAILED: items, files, checks, contact sheet, patches, gaps. Read-only workers return full reports. Read summaries, then specific evidence.

Finish a thread before steering it; long jobs run as resumable scripts with STATUS.md and a STOP file. Stop your own servers and browsers. Integrate, check, update STATE, then gate.
