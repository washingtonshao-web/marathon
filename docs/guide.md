# The Marathon guide

How to install Marathon, start a run, steer it and read what it tells you. Ten minutes to read; most people only need the first three sections.

## Install

1. Download [marathon-skill.zip](/marathon-skill.zip) and unzip it.
2. Windows: double-click `install.cmd`. macOS or Linux: run `sh install.sh` in the unzipped folder.
3. The installer copies the skill to `~/.claude/skills/marathon` when Claude Code is installed and to `~/.codex/skills/marathon` when the Codex CLI is installed. An older copy is moved to `~/.claude/marathon-backups/` (or `~/.codex/marathon-backups/`), outside the skills folders. Nothing else is changed at install time; while a run is active, Marathon adds its own Stop hook to `~/.claude/settings.json` and removes it again when no run is active (uninstall removes it too).

You need Python 3.10 or newer and Claude Code: the lead and the review gate run on Claude. For the default mode you also need the OpenAI Codex CLI signed in to ChatGPT, or your own OpenAI-compatible endpoint (see [Models and costs](#models-and-costs)). Without Codex, choose the all-Claude mode at kickoff.

To remove it, run the installer again with `-Uninstall` (Windows) or `--uninstall` (macOS/Linux). It restores the newest backup if there is one.

## Start a run

In Claude Code or Codex, describe the project and say to use marathon:

```text
Use marathon to build a browser game about the Silk Road: one level, a shop,
save/load, playable on a phone. Budget 8 hours.
```

The session you are talking to becomes the **lead**. Within about ten minutes it reads your material, checks which tools and sign-ins it can use, and shows you:

- the run configuration (mode, workers, review gate, budget);
- direct answers to anything you asked;
- at most five questions, each with a default already selected.

Click your choices and Confirm, or reply in text ("agree", "2B"). If you do not answer within 10 minutes, ordinary questions take their defaults and the run starts. Questions that only you can answer (sign-ins, payments, publishing publicly, deleting things, more budget) never default; they are parked while everything else proceeds.

## What happens during a run

| Phase | What the lead does |
|---|---|
| Charter | Writes the benchmark, numeric targets and the pass mark (for example 78/100 with no critical issues) into `CHARTER.md` |
| Research | Sends workers to collect what the build needs: references, data, prior art |
| Waves | Writes short briefs and launches workers in parallel (four at a time in the default balanced mode); reads only their ≤300-word summaries |
| Gate | Freezes a commit, prepares an evidence pack, and has two reviewers score it independently |
| Fix | Plans the next wave from the reviewers' largest gaps |
| Ship | After a full final gate passes: commits, deploys, checks the live version, writes the decision memo |

It keeps going on its own. A stop hook resumes the lead whenever it would otherwise stop, until one stop rule holds: the target is met, three rounds added fewer than 3 points in total, the budget is used, or only you can unblock it.

Ask "progress" (or "进度") at any time for a short report: a status board, the lead's own assessment with a probability of reaching the target, and at most a few steering questions. Under the status board, a second block shows the last gate round key by key: each reviewer's own score, the score that was used (the lower one, or the lead's ruling) and whose it was, then which models actually ran: lead, workers with runs, hours and fallbacks, the Codex route (API or subscription), sub-agents and reviewers.

## Two modes

| | Codex workers (default) | All Claude |
|---|---|---|
| Lead | The session you talk to | The session you talk to |
| Workers | GPT-6.1-Sol high → GPT-6-Astra high → Claude Sonnet | Claude Sonnet → Claude Opus |
| Review gate | Claude Opus xhigh + GPT-6-Astra high every round | Opus every round, Astra added at the final gate |
| Quota | Workers on your ChatGPT/Codex plan or API; lead and Opus on Claude | Almost all on Claude |

Change at any time in plain words: "workers to Astra", "switch to all Claude", "gate Sonnet plus Astra". Changes apply from the next worker. On measured runs, moving workers to Codex cut Claude spend per active hour by 59–72%.

The fallback order is used only when a worker cannot start (sign-in expired, quota exhausted, crash or timeout before any work). A weak result is not a reason to switch models; the lead tightens the brief and sends the worker back.

## The review gate

Every round, two reviewers who did not build anything score the same frozen commit against the charter: Claude Opus and GPT-6-Astra. Astra reviews everything every round. To save cost, Opus reviews in full on round 1, every third round and the final round, and reviews only what changed in between, carrying its earlier scores for the rest.

When the two disagree a lot (a key 3 points apart, totals 10 apart, or a critical issue seen by only one), `marathon.py score` stops with **ADJUDICATE**. The lead must rule on each point with evidence (a test, a reproduced bug, a screenshot) before the round counts. The final gate always needs a full review from both models.

## Files a run keeps

| File | What it holds |
|---|---|
| `STATE.md` | Status, phase, progress, the next step and the latest five decisions. A new lead resumes from it |
| `DECISIONS.md` | Older decisions and log entries, moved out of STATE.md automatically |
| `CHARTER.md` | Benchmark, targets, pass mark, assumptions |
| `PROMPTS.md` | Your messages, word for word, so nothing you asked gets lost |
| `audits/scores.csv` | Every gate round's scores |
| `audits/workers.csv` | One row per worker: model, minutes, tokens, result |
| `.tmp/reports/` | Full worker and reviewer reports |

## Commands

You rarely need these; the lead runs them. They are useful for checking a run yourself.

| Command | Does |
|---|---|
| `marathon.py status <dir>` | Short status; `--full` for everything, `--report` for the full report; no dir = an overview of the runs it can find (see `status -h`) |
| `marathon.py config <dir>` | Current mode, workers, gate; `--models` shows the worker chain |
| `marathon.py set <dir> workers=astra` | Change one setting (also `profile=claude`, `gate=sonnet+astra`) |
| `marathon.py set <dir> --status paused --reason "…"` | Pause or end a run |
| `marathon.py usage <dir>` | Claude spend by part of the run |
| `marathon.py worker list <dir>` | Worker quality table |
| `marathon.py ask <dir> --status` | Whether a question set is open and how long until defaults apply |

The scripts live in `~/.claude/skills/marathon/scripts/` (or `~/.codex/skills/marathon/scripts/`).

## Models and costs

The Codex workers run through the Codex CLI. By default they use your ChatGPT sign-in. To use an API instead, set two environment variables before starting the run:

```text
MARATHON_API_BASE_URL = https://api.openai.com/v1   (or any OpenAI-compatible Responses endpoint)
MARATHON_API_KEY      = your key
```

With both set, workers try the API first and fall back to your subscription. Keys are passed only to the worker process; they are never written into prompts, logs or files.

`marathon.py usage <dir>` prices the Claude side from the run's own transcripts, separating cache reads and writes, so you can see whether the lead, the reviewers or the workers cost the most.

## Troubleshooting

| Symptom | Fix |
|---|---|
| The run stopped and does not resume | Check `marathon.py status <dir>`: a parked question or a must-decide item is waiting; answer it |
| Workers fall back to Claude every time | The Codex CLI is not signed in or not found; run `codex` once and sign in, or set the API variables |
| "ADJUDICATE" and nothing moves | The lead owes a ruling file; ask it to adjudicate the gate round |
| You want to stop now | Say "pause" or "stop the marathon"; it saves state and stops |

Marathon is free and MIT-licensed. Source and issues are on [GitHub](https://github.com/washingtonshao-web/marathon).
