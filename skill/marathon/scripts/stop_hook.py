#!/usr/bin/env python
"""Claude Code Stop hook: keep a running marathon project going.

Acts only for a session registered by `marathon.py set <dir> --status running` (or `claim`) whose STATE.md says
`status: running`. Every other session and status: exit 0 silently.
- the event's cwd differs from the session's first one → the session moved to other work: stand aside.
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
        reg.unlink()
        release_if_idle()
        return
    fm = front(state.read_text(encoding="utf-8-sig"))
    if fm.get("status") != "running":
        reg.unlink()
        release_if_idle()
        return
    cwd = os.path.normcase(os.path.realpath(data.get("cwd") or ""))
    if cwd:
        info.setdefault("cwd", cwd)
        if info["cwd"] != cwd:  # the session moved to other work: stand aside
            return
    tool = 'python ~/.claude/skills/marathon/scripts/marathon.py'
    try:
        work = float(fm.get("work_hours") or 0) + (minutes_since(fm.get("running_since")) / 60 if fm.get("running_since") else 0)
        budget = float(fm.get("budget_hours") or 0)
    except ValueError:
        work, budget = 0.0, 0.0
    if fm.get("waiting_on") and minutes_since(fm.get("waiting_since")) < WAIT_MAX_MIN and not (budget and work >= budget):
        save(reg, info)
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
        return
    info["blocks"] = info.get("blocks", 0) + 1
    info.pop("released", None)
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
          f"Auto-continue {info['blocks']}.")


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
