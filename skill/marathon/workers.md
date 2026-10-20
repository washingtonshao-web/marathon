# Build waves

Lead scopes/integrates; workers do bulk/live jobs (SKILL.md caps). Generate docs/WORKER-RULES.md from [worker-rules](references/worker-rules.md). .tmp/briefs/<id>.md: task, ownership, inputs, numeric acceptance, class, time/token/paid budget, report path. Re-read shared files; return exact unowned patches.

No worker commit/push/reviewers. Only ops performs brief-authorized live operations; overrides general shipping rules.

Scratch: .tmp/<id>/, harness cleanup per codex-workers.md; keep deliverables/evidence in audits/ or .tmp/reports/. Gates use gate.md. Leave unrelated integrations unused.

Before any browser: `marathon.py lock <dir> browser --owner <id>`; if held do other work. Close/release with --release. Per-PC lease, TTL 30 min; renew with same owner or --ttl MIN. Never steal live leases; hardware limits apply.

`marathon.py config <dir> --models`: STATE chain; new codex defaults to GPT-6.1-Sol high → GPT-6-Astra high → Claude Sonnet 5.5. Astra: `set <dir> workers=astra`. [codex-workers](references/codex-workers.md): launches. Claude leads use native agents; Codex: [bridge](references/codex.md). Steer weak output.

Every worker needs audits/workers.csv; appended `backend` = actual Codex backend (legacy empty = subscription). Wrapper records itself; native/bridge:

~~~text
marathon.py worker <dir> W12 agent=claude model=sonnet effort=high class=build
marathon.py worker <dir> W12 status=done minutes=12 input=12345 output=678
marathon.py worker <dir> W12 first_pass=y fix_lines=0 critical=0 major=0
~~~

Measure values. Terminal fills empty ended; nonterminal clears unless supplied. Assess first_pass/fix_lines at integration, defects at gate; missing=unknown. `marathon.py worker <dir>` lists; --pool pools by model/effort/class. usage accounts; retain bridge metadata for gaps.

Writable non-gate workers save .tmp/reports/<id>.full.md; return ≤summary_words (default 300), starting DONE/PARTIAL/FAILED: items, files, checks, contact sheet, patches, gaps. Read-only workers return full reports; gates use gate.md. Read summaries, then specific evidence.

Finish threads before steer; long jobs use resumable scripts/STATUS.md/STOP. Stop own servers/browsers. Integrate/check/update STATE, then gate. Wave-1 needs checks; rotate at quiet point.
