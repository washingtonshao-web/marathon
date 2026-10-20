# Claude mode

## 1 Lead
Current session leads (Claude: Opus 5.5; Codex: current model). Decide/integrate. Past 150k tokens with no live workers, Claude transfers after a fresh claim; Codex checkpoints/resumes unless fresh transfer is verified.

## 2 Workers
Sonnet 5.5 workers → Opus 5.5 on launch failure only. Steer poor results. Caps: balanced 4, efficient 4, fast 10. Scratch: .tmp/<id>/. Lock browser before use.

## 3 Gate
Opus 5.5 xhigh for regular rounds; final adds Astra high. You can request opus+astra every round. Consider sonnet+astra for biology. Reviewers cannot build their candidate.

## 4 Quota
Claude workers and reviewers use your Claude account. Astra uses subscription by default; both MARATHON_API_BASE_URL and MARATHON_API_KEY enable api,subscription. The lead uses its host account. Worker-heavy projects consume more Claude quota.

## 5 Use
Choose when Codex is unavailable, Claude-only tools are essential, or you explicitly want Claude to build.
