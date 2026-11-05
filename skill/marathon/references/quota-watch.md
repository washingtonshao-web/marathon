# Quota watch: continue after a Claude usage limit

Claude lead only. Codex has no background wake; an outside resume tool, if you run one, stays as the backstop.

## Kickoff question

Add this to the intake ask set unless the user already said. It does not count toward the 5-question budget (`ask` allows it as a sixth):

```json
{"id":"auto_resume","text":"Claude 额度用完后，额度恢复时自动接着跑？","options":["on","off"],"default":"on"}
```

Apply the answer with `marathon.py set <dir> auto_resume=<on|off>`. A missing value means on, so projects started before this option are covered.

## How it works

- Every `claim` (start, resume, after compaction, `set --status running`) ends with `quota watch: n/2 armed`. When fewer than 2 are armed it gives the command; start each missing watcher as its own Bash call with `run_in_background`.
- `scripts/quota_watch.py` uses no tokens and talks to nothing while it waits: every 60 s it reads the tail of this session's own transcript (`~/.claude/projects/*/<CLAUDE_CODE_SESSION_ID>.jsonl`). It only acts when the last turn is a usage-limit error (`isApiErrorMessage` with `quotaLimits.resetsAt`).
- Three minutes after that reset it prints one line and exits. The exit wakes the idle session, and that turn is the continuation: start one replacement watcher, run `claim`, continue from `next`.
- Each error is claimed once (`~/.claude/quota-watch/<session>/claimed/<error id>`). The second watcher covers a wake that hits the limit again, with the new reset time.
- Separate sessions never cross: a watcher reads only its own session's transcript.
- `auto_resume: off` makes claim report `off` and ask for none. Watchers already running stay until they fire or expire (7 days).

## How it reports

Nobody has to watch for it. Both readers scan the lead sessions' transcripts for usage-limit stops, so a resume by an outside tool or by the user counts too, not only one by a watcher:

- `status --report` adds `Resume    2/2 armed · N limits hit · last reset <time> → resumed +3 min (watcher | outside tool or user)` to the visual block. It flags ⚠ when a stop is still open 15 min after its reset, or when a resume came more than 15 min after the reset. A stop followed by a later lead session counts as taken over, not failed.
- `claim` writes each resumed stop once to STATE Log (`usage limit stopped session … at …, reset …, resumed … (+N min, by)`), marked in `~/.claude/quota-watch/<session>/logged/`. The woken turn runs claim, so the first real limit records itself.

## Limits

- A watcher is a child of the session's process. Closing Claude or restarting the PC ends it; an outside resume tool covers that case.
- Not verified on a real usage limit yet (2026-11-02, none hit since 10-20): the wake path, the report and the log were tested with synthetic transcripts (`scripts/test_quota_watch.py`). The first real limit shows up in the report and the Log either way.
