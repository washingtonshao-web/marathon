# Marathon

**Hand an AI a multi-hour project. Marathon runs it to a scored finish.**

Marathon is a free skill for **Claude Code** and the **OpenAI Codex CLI**. You describe a project that takes hours — a web app, a browser game, a data site, a sourced research report — and the session you are talking to becomes its lead. It agrees numeric targets with you, sends parallel workers to build, has **two different models grade every round**, and keeps going until the target is met, the score stops improving or the budget runs out. Then it ships and writes you a decision memo. Nobody types "continue".

[**Download the one-click installer**](https://marathon.falconshire.com/marathon-skill.zip) · [Website](https://marathon.falconshire.com) · [Guide](https://marathon.falconshire.com/docs/) · [中文说明](README.zh-CN.md)

```text
● running · build wave 9 · 47.9 / 57 h
Progress ████████████░░░░░░░░ 58%
Targets  14 / 22 met
Score    73.5 → 76.5 → 77.0   pass 75
Workers  3 running · GPT-6.1-Sol high
Gate     Opus 5.5 xhigh + GPT-6-Astra high
```
<sub>Simplified from the status board of a real business-system run (57-hour budget, 47.9 h used).</sub>

## Measured on real runs

| | Result |
|---|---|
| Claude spend per active hour after moving workers to Codex | **−72%** on a business-system run, **−59%** on a browser game |
| A run that had stalled at 65.5–67.5 | passed within three rounds of the switch (76.5, final **77.0**; pass mark 75) |
| Blind re-run of 6 finished tasks, GPT-6-Astra workers vs Claude Opus workers | Codex passed first time **5 of 6** (Opus 3 of 6); critical issues **2 vs 8** |

Costs are priced from the runs' own transcripts by token type; Codex ran on a subscription and is not included.

## What it does

- **Asks once, then works.** At most five kickoff questions, defaults preselected, one click to confirm. Away? After 10 minutes it starts on the defaults.
- **Targets you can check.** Benchmark, numeric targets and a pass mark are fixed before work starts.
- **Parallel workers.** Several bounded workers (four at a time in the default balanced mode) write code, research, test and polish; each returns a ≤300-word summary, full reports go to files.
- **Two-model review gate.** Claude Opus and GPT-6-Astra score the same frozen commit independently; big disagreements are ruled on with evidence.
- **Never needs "continue".** A stop hook keeps the run going until a stop rule holds.
- **Survives long contexts.** State lives in `STATE.md`; a fresh lead takes over at a quiet point past 150k tokens.
- **Counts the cost.** A ledger row per worker and Claude spend priced by token type.
- **Ships, then reports.** Commit, deploy, verify the live version, then a memo with limits and options.
- **Never decides the risky things for you.** Sign-ins, payments, public publishing, deletions and extra budget always wait for your answer.

## Two modes

| | Codex workers (default) | All Claude |
|---|---|---|
| Workers | GPT-6.1-Sol high → GPT-6-Astra high → Claude Sonnet | Claude Sonnet → Claude Opus |
| Review gate | Opus xhigh + Astra high every round | Opus every round, Astra at the final gate |
| Quota | Workers on your ChatGPT/Codex plan or your own API; lead and Opus on Claude | Almost all on Claude |

Switch any time in plain words ("workers to Astra", "switch to all Claude").

## Install

1. Download [marathon-skill.zip](https://marathon.falconshire.com/marathon-skill.zip) (or the latest [release](https://github.com/washingtonshao-web/marathon/releases/latest)) and unzip it.
2. Windows: double-click `install.cmd`. macOS / Linux: `sh install.sh`.
3. In Claude Code or Codex: *"Use marathon to build …"*

Requires Python 3.10+ and Claude Code (the lead and the review gate run on Claude); the Codex CLI is needed for the default Codex-worker mode. To use an API instead of a ChatGPT sign-in for Codex workers, set `MARATHON_API_BASE_URL` and `MARATHON_API_KEY` (any OpenAI-compatible Responses endpoint). Uninstall with `-Uninstall` / `--uninstall`.

## Repository layout

| Path | What |
|---|---|
| `skill/marathon/` | The skill: `SKILL.md`, workflow docs, mode cards, `scripts/marathon.py`, `scripts/codex_worker.py`, tests |
| `install/` | `install.cmd` + `install.ps1` (Windows), `install.sh` (macOS/Linux) |
| `docs/` | The guide in English and Chinese |
| `site/` | Source of marathon.falconshire.com (built with a design kit that is not part of this repo; the published pages are self-contained) |
| `tools/make_zip.py` | Builds the installer zip |

Run the tests with `python skill/marathon/scripts/test_marathon.py` (and the other `test_*.py` files).

## Licence

MIT. Marathon works with Claude Code and the OpenAI Codex CLI; it is not made by or affiliated with Anthropic or OpenAI.
