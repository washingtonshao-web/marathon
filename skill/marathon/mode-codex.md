# Codex mode (default)

## 1 Lead
Current session leads (Claude: Opus 5.5; Codex: current model). Decide/integrate; delegate long work. Past 150k tokens at a quiet point, Claude transfers after a fresh claim; Codex checkpoints unless fresh transfer is verified. Follow STATE.md.

## 2 Workers
GPT-6.1-Sol high → GPT-6-Astra high → Claude Sonnet 5.5 via codex_worker.py. `set <dir> workers=astra` overrides. Fallback: launch failure only; steer poor results. Caps: balanced 4, efficient 4, fast 10. Scratch .tmp/<id>/: harness cleans DONE/FAILED, keeps resumable partials. Lock browser first.

## 3 Gate
Independent Opus 5.5 xhigh + Astra high. Astra: full each round; Opus: full round 1/every third/final, otherwise focused. Biology: consider sonnet+astra.

## 4 Quota
Default: subscription. MARATHON_API_BASE_URL + MARATHON_API_KEY enable api,subscription before model fallback. Claude workers/reviewers use Claude quota; lead uses host quota.

## 5 Use
Most long code, testing, research and website projects.
