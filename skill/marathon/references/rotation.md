# Quiet-point rotation

rotate_at is context tokens in thousands (thin default 150; 0/hands-on disables). Use get_usage if available; otherwise the runtime meter or a conservative estimate in STATE.md. Trigger after an integrated wave/scored gate, with no live workers.

Claude:
1. Update STATE/ledger; `marathon.py handoff <dir> --why "context threshold"` (optional --note). Never --force past live workers. The resume prompt is saved in STATE.md, Handoff.
2. Use a successor launcher if installed; none is bundled. Otherwise the user starts a fresh lead session with that prompt. A Stop hook resumes in a fresh session only if the host supports it; this hook does not launch sessions. Old lead owns pending transfer; freeze writes.
3. Successor reads/claims with a new CLAUDE_CODE_SESSION_ID. Verify “handoff complete”; old lead never reclaims. On launch failure: `handoff <dir> --abort`; continue old lead and prevent delayed claims.

Codex: `handoff <dir> --save-only --why "checkpoint"` saves notes, even with workers; registry/pending/rotation count stay unchanged. No checkpoint abort. Without Claude session ID, claim cannot complete Claude transfer. Resume the saved thread per codex.md; do not claim fresh rotation.
