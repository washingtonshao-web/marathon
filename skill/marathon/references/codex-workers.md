# External Codex workers

Installed paths:

~~~text
codex_worker.py run <dir> --id W12 --brief .tmp/briefs/W12.md --class build --minutes 60
codex_worker.py steer <dir> --id W12 "correction" --minutes 30
~~~

New codex: GPT-6.1-Sol high → GPT-6-Astra high → Claude Sonnet 5.5; `set <dir> workers=astra` opts in. STATE wins; gates default to Astra high.

Classes: build/ui/test/data/research/ops/gate; gate needs --sha (gate.md). --model overrides. --brief: caller-relative/absolute; --out: project-relative, no escape/directories/workers.csv/.tmp/reports/. Repeatable --image on run. IDs: letters/digits/_/-, consistent case, unique/task.

Newest desktop Codex; subst drives resolved. Non-gates: full access unless --read-only; gates: pinned snapshot, scratch-only writes.

Harness deletes .tmp/<id>/ after non-gate DONE/FAILED; TIMEOUT/PARTIAL/infra or --keep-scratch retains it. Shared folders excluded; leftovers reported. Unrelated integrations stay unused. Browser: `marathon.py lock <dir> browser --owner <id>`; if held do other work; close/--release, renew before TTL.

Attempts: .tmp/reports/<id>.a<N>.md/events/errors. Only zero-exit DONE/PARTIAL/FAILED promotes <id>.md/--out. Failed attempts retain old output; inspect current ledger/report.

`codex_backends`: subscription by default; both MARATHON_API_BASE_URL and MARATHON_API_KEY enable api,subscription. Use a Responses-compatible base URL (e.g. https://api.openai.com/v1). --backend api overrides the start once. Keys stay in the child environment; no permanent config edits. Gates use identical routing.
Before tools, infra failure (401/403/429/5xx/connect/timeout) retries the SAME model across backends before advancing models. After tools, capacity/5xx/stream error (not time limit) resumes the same thread ≤2 times with the next Codex model (same model after 60 s if none), retaining usage; otherwise inspect/steer. weak/PARTIAL/FAILED are task results. Without turn.completed, usage comes from the session log. Chains only advance; in-chain overrides start there, others keep Claude fallbacks only. FALLBACK: lead launches Claude with the same brief. Gates try subsequent configured GPT models only; only astra* satisfies score. ASTRA UNAVAILABLE: gate.md. worker_fallback=none disables model fallback.

run: 60 min/attempt; steer: 30. Zero exit may mean FAILED/TIMEOUT/FALLBACK. steer waits for exit, resumes saved thread/model/effort/read-only/backend (legacy blank = subscription), adds usage/time, no fallback. Gates recreate pinned SHA; absent SHA needs new run. Claude: each run/steer gets its own run_in_background Bash call (never nohup/&) to wake lead on exit. Codex: check `marathon.py worker <dir>` between steps.
