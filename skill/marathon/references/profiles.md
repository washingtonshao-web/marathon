# Configuration

New runs: codex (default) or claude; read the mode cards. `config --profiles`: bundles; `config --models`: chain; --name: aliases.

Worker chains: mode cards. `set <dir> workers=astra` overrides. Classic: legacy-only; first write pins defaults, preserves overrides. codex-lead = codex; host sets lead.

`set <dir> profile=codex` bundles then overrides, logs Decisions; applies next launch. STATE/task requests win. `codex_backends=api,subscription`: validated list; default subscription, or api,subscription with both MARATHON_API_BASE_URL and MARATHON_API_KEY. Steer weak results. Modes: balanced/efficient 4 workers, fast 10.

Gates: opus+astra, opus, sonnet+astra (consider for biology); final dual review/fallback: gate.md. astra_wait=0 always waits; worker_fallback=none disables fallback; summary_words=300 (0 literal); ask_wait=10 (0 defaults ordinary choices immediately).

Config: requests; claim verifies CLAUDE_MODEL with session ID, else clears stale verification. Keep model/effort evidence. Sonnet = Claude Sonnet 5.5; api / subscription / 订阅 = backends. Resolve unknown names.
