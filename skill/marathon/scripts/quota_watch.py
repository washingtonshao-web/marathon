#!/usr/bin/env python
"""Wake a Claude Code session once its usage limit has reset.

Start it from the session as a background Bash command (run_in_background). While it waits it uses no tokens and
talks to nothing: every --poll seconds it reads the tail of this session's transcript. When the session's last turn
ended in a usage-limit error and that error's reset time plus --grace has passed, it prints one line and exits; the
exit is what wakes the idle session, and that turn is the continuation.

Each session keeps SLOTS watchers. Each error is claimed once, so the second watcher covers a wake that hit the limit
again; the woken turn starts a replacement (`--status` says how many are missing). A watcher lives at most
--max-hours and ends with the session's process (closing Claude ends it). Claude only: Codex has no such wake.
"""
import argparse
import glob
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SLOTS = 2

p = argparse.ArgumentParser()
p.add_argument("--session", default=os.environ.get("CLAUDE_CODE_SESSION_ID"))
p.add_argument("--transcript", help="transcript path (tests); default: found from --session")
p.add_argument("--grace", type=int, default=180, help="seconds after the reset before waking")
p.add_argument("--poll", type=int, default=60)
p.add_argument("--state", default=str(Path.home() / ".claude" / "quota-watch"))
p.add_argument("--max-hours", type=float, default=7 * 24)
p.add_argument("--status", action="store_true", help="print how many watchers run for this session, then exit")


def live(slot: Path, poll: int) -> bool:
    try:
        return time.time() - slot.stat().st_mtime < 3 * poll + 30
    except FileNotFoundError:
        return False


def find_transcript(session):
    hits = glob.glob(str(Path.home() / ".claude" / "projects" / "*" / f"{session}.jsonl"))
    return max(hits, key=os.path.getmtime) if hits else None


def transcript(a):
    return a.transcript or find_transcript(a.session)


def last_turn(path):
    """The last main-chain user/assistant record (reads only the tail)."""
    with open(path, "rb") as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - 400_000))
        lines = f.read().decode("utf-8", "replace").splitlines()
    for line in reversed(lines):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") in ("user", "assistant") and not d.get("isSidechain"):
            return d
    return None


def reset_of(d):
    """(error id, reset epoch) when the record is a usage-limit error, else None."""
    if not d or not d.get("isApiErrorMessage"):
        return None
    q = d.get("quotaLimits") or {}
    if q.get("resetsAt"):
        return d.get("uuid"), float(q["resetsAt"])
    if d.get("error") == "rate_limit":  # no reset time recorded: try 30 minutes after the error
        t = datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00")).timestamp()
        return d.get("uuid"), t + 1800
    return None


def stamp(d):
    return datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00")).timestamp()


def events(path, claimed=None):
    """Every usage-limit stop in a transcript and how it ended, oldest first: dicts with error, reset, stopped and
    resumed (epoch of the first normal reply after it, None while still stopped), by (watcher when a watcher claimed
    it, else outside tool or user), again (the wake hit the limit again)."""
    out, open_ = [], None
    if not path or not os.path.exists(path):
        return out
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if "isApiErrorMessage" not in line and (open_ is None or '"assistant"' not in line):
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("type") != "assistant" or d.get("isSidechain") or not d.get("timestamp"):
                continue
            hit = reset_of(d)
            if hit:
                if open_:
                    open_["again"] = True
                open_ = {"error": hit[0], "reset": hit[1], "stopped": stamp(d), "resumed": None, "again": False,
                         "by": "watcher" if claimed and (Path(claimed) / str(hit[0])).exists() else "outside tool or user"}
                out.append(open_)
            elif open_ and not d.get("isApiErrorMessage"):
                open_["resumed"], open_ = stamp(d), None
    return out


def main():
    a = p.parse_args()
    if not a.session and not a.transcript:
        sys.exit("no CLAUDE_CODE_SESSION_ID: run this from a Claude Code session")
    state = Path(a.state) / (a.session or "test")
    (state / "claimed").mkdir(parents=True, exist_ok=True)
    slots = [state / f"slot-{i}" for i in range(1, SLOTS + 1)]
    free = [s for s in slots if not live(s, a.poll)]
    if a.status:
        print(f"{SLOTS - len(free)}/{SLOTS}")
        return
    slot, lock = None, state / "lock"
    for _ in range(50):  # two watchers started together must not take the same slot
        try:
            lock.mkdir()
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > 10:
                    lock.rmdir()
            except OSError:
                pass
            time.sleep(0.2)
    try:
        slot = next((s for s in slots if not live(s, a.poll)), None)
        if slot:
            slot.write_text(str(os.getpid()))
    finally:
        try:
            lock.rmdir()
        except OSError:
            pass
    if not slot:
        print(f"quota watch already armed ({SLOTS}/{SLOTS}); nothing started")
        return
    deadline = time.time() + a.max_hours * 3600
    try:
        while time.time() < deadline:
            slot.touch()
            path = transcript(a)
            hit = reset_of(last_turn(path)) if path else None
            if hit and time.time() >= hit[1] + a.grace:
                try:
                    (state / "claimed" / str(hit[0])).mkdir()  # each error wakes the session once
                except FileExistsError:
                    pass
                else:
                    at = datetime.fromtimestamp(hit[1], timezone.utc).astimezone().strftime("%H:%M")
                    print(f"QUOTA RESET: the usage limit that stopped this session reset at {at}. Start one replacement "
                          f"watcher (run_in_background): python \"{Path(__file__).resolve().as_posix()}\" - then continue the "
                          "task from where it stopped (a marathon lead runs marathon.py claim first).")
                    return
            time.sleep(a.poll)
        print("quota watch expired; start a new one if the session still runs long work")
    finally:
        slot.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
