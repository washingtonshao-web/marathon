# Codex lead

Use AGENTS.md and the shared lifecycle. Optionally set MARATHON_REPOS_ROOT for the overview scan; resume assigned projects in place and keep scratch in .tmp/. Scripts live in ~/.codex/skills/marathon/scripts/ (or CODEX_HOME/skills/marathon/scripts/).

Launch Codex workers through codex_worker.py. Claude workers and gates use the installed Claude Code CLI: `claude -p --model sonnet --effort high --output-format json` with the brief on stdin; use opus/xhigh for gates, or sonnet/xhigh when configured. Launch a fresh process per reviewer. Explicitly enforce the brief's read/write permissions with the CLI's allowed-tools settings or a read-only snapshot. Do not bypass permission prompts. Register each worker with marathon.py worker before launch, then finalize its row from the JSON response: status, model, session ID, elapsed minutes and measured usage. Save raw JSON under .tmp/reports/. A successful process is not proof of DONE: inspect the answer. Retain requested and confirmed model/effort separately; unknown stays unknown. Claude must write its full audit or the parent must save the complete answer to its audit path. Register same-SHA reviewers before starting Astra. Gate reviewers never recursively review.

## Ask timer

Run `marathon.py ask <dir> --resolve --at-deadline` foreground only when idle; otherwise continue work, then `ask <dir> --status` and resolve when due. Replies: `ask <dir> --resolve --answers "<reply>"`. Never end a turn expecting a background wake. Answer-only progress uses runtime questions and no STATE writes.

## Continuation

Without CLAUDE_CODE_SESSION_ID, claim arms no Claude Stop hook. Save the Codex thread/session ID; `handoff <dir> --save-only --why "checkpoint"` checkpoints rather than verifying a new lead. Resume with `codex exec resume <saved-session-id> "Resume Marathon: read STATE.md, CHARTER.md and PROMPTS.md; reconcile, claim, continue from next."` Reuse the discovered desktop binary or codex on PATH. set --status changes Marathon state, not an external scheduler.
