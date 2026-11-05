#!/usr/bin/env python
"""Claude Code Stop hook: keep a running marathon project going.

Acts only for a session registered by `marathon.py set <dir> --status running` (or `claim`) whose STATE.md says
`status: running`. Every other session and status: exit 0 silently.
The registry file is per session (`active/<session_id>.json`), so the folder the lead works in does not matter: a lead
that changes folders is still the same session. To use the window for other work, pause the project first.
Every time a registered session is allowed to stop, one line goes to ~/.claude/marathon/hook-log.txt with the reason.
- waiting_on set (lead waits for background workers or commands, which notify the session when they finish or fail) and
  younger than WAIT_MAX_MIN, with budget left → allow the turn to end. The limit only applies at the next Stop event; it is
  not a timer.
- budget reached (work hours ≥ budget_hours) → block once: ship the best verified version, write the decision memo.
- otherwise block and tell Claude to continue. Progress = a change in the key STATE fields; after STALE_LIMIT
  continues without progress, block one last time asking for the decision memo, then allow stops (recorded as
  released=stale in the registry; progress re-arms it). The MAX_BLOCKS-th continue asks for the memo; after that, stops pass.
Errors never break the session: they are logged to ~/.claude/marathon/hook-errors.log and the stop is allowed.
API failures fire StopFailure, not Stop; your runtime handles quota recovery.
"""
import datetime as dt
import hashlib
import json
import os
import re
import sys
import tempfile
import traceback
from pathlib import Path

MAX_BLOCKS = 200
STALE_LIMIT = 3
WAIT_MAX_MIN = 90
BASE = Path(os.environ.get("MARATHON_CLAUDE_HOME") or Path.home() / ".claude") / "marathon"  # override for tests
REGISTRY = BASE / "active"
KEYS = ("phase", "progress", "targets_met", "gate_round", "last_score", "next", "changed", "link", "waiting_on")
IDLE_MIN = 30        # a gap longer than this without activity is not work time ...
WAIT_IDLE_MIN = 90   # ... or this long while the lead has said it waits for background work (waiting_on)
ROTATE_DEFAULT_K = 300   # thousands of context tokens; the old default 150 counts as 300 (user, 2026-11-05)
ROTATE_REMINDERS = 3
TERMINAL = {"done", "partial", "failed", "timeout", "fallback"}
# What to do now, per phase: shown when the hook continues the lead and at the end of `marathon.py status`.
PHASE_TODO = {
    "intake": ("Write CHARTER 'What the user will do with it' in the user's words, with 2-3 ways it could be wrong.",
               "Ask at most 5 questions with marathon.py ask (one line: ask <dir> \"question\" --options \"A|B\"); defaults apply after 10 minutes.",
               "Start research while the questions are open."),
    "research": ("Put 3-5 of the best examples of the same kind in research/benchmark/ and write BORROW.md before the first build worker.",
                 "Researchers write notes to disk; read only the short summary."),
    "build": ("Every brief carries 'What the user will do with it'; a fix brief names its files and the problems to fix.",
              "At 15-20% of the budget send the direction preview (marathon.py ask, default keep going).",
              "Wait for workers in the background (marathon.py wait <dir> --for <ids>); when the user writes, answer in a sentence or two first."),
    "gate": ("Fix the problem list from the most serious down, and fix whole classes, not single instances.",
             "Done = no critical or major problem and both reviewers USE: yes; the score is only the floor.",
             "Never pause to wait for the user's score; only going live waits for the user."),
    "ship": ("Release only the exact reviewed commit after the hard checks; go live on the user's word where CHARTER says so.",
             "Report what changed, what is left and the links."),
}


def record_activity(project, waiting):
    """Mark the project active now. If the last activity (.tmp/activity or STATE.md, whichever is newer) is older than the
    allowed idle time, first append the uncounted part of the gap to .tmp/idle-gaps ("<start> <end>" epoch seconds), so
    every later reading of the budget clock leaves it out, whoever touched first."""
    tmp = Path(project) / ".tmp"
    mark, state = tmp / "activity", Path(project) / "STATE.md"
    times = [p.stat().st_mtime for p in (mark, state) if p.exists()]
    t_now = dt.datetime.now().timestamp()
    tmp.mkdir(parents=True, exist_ok=True)
    if times:
        allow = (WAIT_IDLE_MIN if waiting else IDLE_MIN) * 60
        last = max(times)
        if t_now - last > allow:
            with (tmp / "idle-gaps").open("a", encoding="utf-8") as f:
                f.write(f"{last + allow:.0f} {t_now:.0f}\n")
    mark.touch()


def idle_hours_since(project, start_ts):
    """Uncounted idle hours recorded after start_ts (the start of the open running segment)."""
    total = 0.0
    try:
        for line in (Path(project) / ".tmp" / "idle-gaps").read_text(encoding="utf-8").splitlines():
            a, _, b = line.partition(" ")
            total += max(0.0, float(b) - max(float(a), start_ts))
    except (OSError, ValueError):
        pass
    return total / 3600


def last_activity(project):
    times = [p.stat().st_mtime for p in (Path(project) / ".tmp" / "activity", Path(project) / "STATE.md") if p.exists()]
    return max(times) if times else None


def phase_key(phase):
    p = (phase or "").lower()[:30]  # the phase name, not the notes after it
    for key, words in (("intake", ("intake", "准备")), ("research", ("research", "研究", "调研")),
                       ("ship", ("ship", "release", "deliver", "发布", "交付", "上线")), ("gate", ("gate", "review", "评审", "终审"))):
        if any(w in p for w in words):
            return key
    return "build"


def context_tokens(path):
    """Context size of the latest assistant turn, read from the tail of the session transcript (0 when unknown)."""
    try:
        p = Path(path)
        size = p.stat().st_size
        with p.open("rb") as f:
            f.seek(max(0, size - 400_000))
            tail = f.read().decode("utf-8", "replace")
    except (OSError, TypeError, ValueError):
        return 0
    for line in reversed(tail.splitlines()):
        if '"usage"' not in line:
            continue
        try:
            u = (json.loads(line).get("message") or {}).get("usage") or {}
        except (ValueError, AttributeError):
            continue
        n = sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
        if n:
            return n
    return 0


def workers_running(project):
    p = Path(project) / "audits" / "workers.csv"
    try:
        import csv
        with p.open(encoding="utf-8", newline="") as f:
            return any(r.get("started") and not r.get("ended") and r.get("status") not in TERMINAL for r in csv.DictReader(f))
    except OSError:
        return False


def save(path, info):
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".reg.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(info, f)
    os.replace(tmp, path)


def front(text):
    text = text.lstrip("﻿").replace("\r\n", "\n")
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    fm = {}
    for line in (m.group(1).splitlines() if m else []):
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm


def minutes_since(stamp):
    try:
        return (dt.datetime.now() - dt.datetime.fromisoformat(stamp)).total_seconds() / 60
    except (TypeError, ValueError):
        return 1e9


def release_if_idle():
    """The last running marathon here ended outside marathon.py (STATE edited by hand): take the hook out of settings."""
    if not any(REGISTRY.glob("*.json")):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import marathon  # noqa: E402  (only on this rare path)
        marathon.release_hook_if_idle()


def log_release(sid, project, reason):
    """One line per allowed stop of a registered session, so a stop can be explained afterwards."""
    try:
        BASE.mkdir(parents=True, exist_ok=True)
        with (BASE / "hook-log.txt").open("a", encoding="utf-8") as f:
            f.write(f"{dt.datetime.now().isoformat(timespec='seconds')} {sid} {Path(project).name}: {reason}\n")
    except OSError:
        pass


def block(reason):
    print(json.dumps({"decision": "block", "reason": reason}))


def main():
    data = json.loads(sys.stdin.buffer.read().decode("utf-8-sig") or "{}")
    sid = data.get("session_id")
    if not sid:
        return
    reg = REGISTRY / f"{sid}.json"
    if not reg.exists():
        return
    info = json.loads(reg.read_text(encoding="utf-8"))
    project = Path(info["project"])
    state = project / "STATE.md"
    if not state.exists():
        log_release(sid, project, "STATE.md missing: unregistered")
        reg.unlink()
        release_if_idle()
        return
    fm = front(state.read_text(encoding="utf-8-sig"))
    if fm.get("status") != "running":
        log_release(sid, project, f"status {fm.get('status') or '?'}: unregistered")
        reg.unlink()
        release_if_idle()
        return
    tool = 'python ~/.claude/skills/marathon/scripts/marathon.py'
    try:
        record_activity(project, bool(fm.get("waiting_on")))  # the lead just ended a turn: the project is active
    except OSError:
        pass
    try:
        open_h = 0.0
        if fm.get("running_since"):
            start = dt.datetime.fromisoformat(fm["running_since"]).timestamp()
            open_h = max(0.0, (dt.datetime.now().timestamp() - start) / 3600 - idle_hours_since(project, start))
        work = float(fm.get("work_hours") or 0) + open_h
        budget = float(fm.get("budget_hours") or 0)
    except ValueError:
        work, budget = 0.0, 0.0
    if fm.get("waiting_on") and minutes_since(fm.get("waiting_since")) < WAIT_MAX_MIN and not (budget and work >= budget):
        save(reg, info)
        log_release(sid, project, f"waiting on {fm.get('waiting_on')}")
        return
    if budget and work >= budget and not info.get("budget_told"):
        info["budget_told"] = True
        save(reg, info)
        block(f"Marathon project {project.name}: the work budget ({budget:g} h) is used up ({work:.1f} h). Do the BUDGET stop in the "
              f"marathon skill's gate.md now: ship the best version that passes the release checks, write the decision memo, then "
              f"`{tool} set \"{project}\" --status paused --reason budget` and stop.")
        return
    sig = hashlib.sha1("|".join(fm.get(k, "") for k in KEYS).encode("utf-8")).hexdigest()
    info["stale"] = info.get("stale", 0) + 1 if sig == info.get("sig") else 0
    info["sig"] = sig
    if info.get("blocks", 0) >= MAX_BLOCKS or info["stale"] > STALE_LIMIT:
        info["released"] = "cap" if info.get("blocks", 0) >= MAX_BLOCKS else "stale"
        save(reg, info)
        log_release(sid, project, "auto-continue cap reached" if info["released"] == "cap" else f"no STATE change across {STALE_LIMIT} continues")
        return
    info["blocks"] = info.get("blocks", 0) + 1
    info.pop("released", None)
    extra = []
    rot = fm.get("rotate_at", "")
    k = int(rot) if rot.isdigit() else ROTATE_DEFAULT_K
    k = ROTATE_DEFAULT_K if k == 150 else k
    k = 0 if fm.get("lead_style") == "hands-on" else k  # a hands-on lead does not rotate (rotation.md)
    if k and info.get("rotate_told", 0) < ROTATE_REMINDERS and not workers_running(project):
        used = context_tokens(data.get("transcript_path"))
        if used > k * 1000:
            info["rotate_told"] = info.get("rotate_told", 0) + 1
            extra.append(f"Context is {used // 1000}k tokens (hand off at {k}k) and no worker is running: hand off now "
                         f"(references/rotation.md, `{tool} handoff \"{project}\" --why \"context threshold\"`). "
                         f"Reminder {info['rotate_told']}/{ROTATE_REMINDERS}.")
    review = fm.get("plateau_review") or ""
    if review.startswith("due") and info.get("plateau_told") != review:
        info["plateau_told"] = review
        extra.append("Plateau review due: write 2-3 options with a recommendation, send them with marathon.py ask, keep going on the recommendation.")
    save(reg, info)
    if info["blocks"] == MAX_BLOCKS:
        block(f"Marathon project {project.name}: this is the last automatic continue ({MAX_BLOCKS}). Finish the current step, write the "
              f"decision memo (gate.md, Stop and memo), then `{tool} set \"{project}\" --status paused --reason \"auto-continue cap\"` and stop.")
        return
    if info["stale"] == STALE_LIMIT:
        block(f"Marathon project {project.name}: STATE.md has not changed across {STALE_LIMIT} continues, so the run looks stuck. "
              f"Do not loop again. Write the decision memo (gate.md, Stop and memo: what blocks progress, options, parked questions), "
              f"then `{tool} set \"{project}\" --status blocked --reason \"...\"` (or paused) and stop.")
        return
    block(f"Marathon project {project.name} is still running (phase {fm.get('phase', '?')}; next: {fm.get('next', '?')}). "
          "Don't stop now; questions for the user go through `marathon.py ask` (defaults apply after ask_wait). Re-read STATE.md, do the next step, and update STATE (marathon.py set / note) as you go. "
          "Park questions with `marathon.py note <dir> parked`. While background workers run and nothing else is useful, "
          "`marathon.py wait <dir> \"<what>\"` lets the turn end until they report. To end the run, use `marathon.py set <dir> --status "
          "done|paused|blocked --reason ...`, and only when a stop condition in gate.md holds. "
          f"Auto-continue {info['blocks']}."
          + "".join(f"\n{x}" for x in extra)
          + f"\nNow ({phase_key(fm.get('phase'))}):" + "".join(f"\n- {x}" for x in PHASE_TODO[phase_key(fm.get('phase'))]))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        try:
            BASE.mkdir(parents=True, exist_ok=True)
            with (BASE / "hook-errors.log").open("a", encoding="utf-8") as f:
                f.write(f"{dt.datetime.now().isoformat()} {traceback.format_exc()}\n")
        except OSError:
            pass
    sys.exit(0)
