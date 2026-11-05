"""Tests for quota_watch.py and the quota-watch line of marathon claim. Run: python test_quota_watch.py"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "quota_watch.py"
FAILED = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" -- {detail}"))
    if not cond:
        FAILED.append(name)


def transcript(path, last):
    rows = [{"type": "user", "uuid": "u1", "message": {"role": "user", "content": "go"}}, last]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def quota_error(uid, reset):
    return {"type": "assistant", "uuid": uid, "timestamp": "2026-10-21T18:10:00Z", "isApiErrorMessage": True,
            "error": "rate_limit", "quotaLimits": {"status": "rejected", "resetsAt": reset, "rateLimitType": "five_hour"},
            "message": {"role": "assistant", "content": []}}


def run(tmp, t, *extra, timeout=30):
    args = [sys.executable, str(SCRIPT), "--session", "s1", "--transcript", str(t), "--state", str(tmp / "state"),
            "--grace", "0", "--poll", "1", *extra]
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout).stdout


def main():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        t = tmp / "s1.jsonl"

        transcript(t, quota_error("e1", time.time() + 2))
        start = time.time()
        out = run(tmp, t)
        check("wakes once the reset has passed", "QUOTA RESET" in out and 2 <= time.time() - start < 6, out)

        out = run(tmp, t, "--max-hours", "0.001")
        check("the same error never wakes twice", "expired" in out and "QUOTA RESET" not in out, out)

        transcript(t, quota_error("e2", time.time() - 10))
        check("a repeated limit (new error) wakes again", "QUOTA RESET" in run(tmp, t))

        transcript(t, {"type": "assistant", "uuid": "a1", "message": {"role": "assistant", "content": "done"}})
        out = run(tmp, t, "--max-hours", "0.001")
        check("a normal last turn never wakes", "QUOTA RESET" not in out, out)

        args = [sys.executable, str(SCRIPT), "--session", "s1", "--transcript", str(t), "--state", str(tmp / "state"), "--poll", "1"]
        procs = [subprocess.Popen(args, stdout=subprocess.PIPE, text=True) for _ in range(2)]  # started together
        time.sleep(2)
        status = subprocess.run(args + ["--status"], capture_output=True, text=True).stdout.strip()
        third = subprocess.run(args, capture_output=True, text=True, timeout=10).stdout
        check("two watchers started together take two slots", status == "2/2", status)
        check("a third watcher starts nothing", "already armed" in third, third)
        for p in procs:
            p.kill()
            p.wait()

        sys.path.insert(0, str(HERE))
        import marathon
        proj = tmp / "proj"
        proj.mkdir()
        (proj / "STATE.md").write_text("---\nstatus: running\nauto_resume: off\n---\n# State\n", encoding="utf-8")
        check("auto_resume: off reports off", "quota watch: off" in marathon.quota_watch_line("nobody", proj))
        (proj / "STATE.md").write_text("---\nstatus: running\n---\n# State\n", encoding="utf-8")
        line = marathon.quota_watch_line("nobody-" + os.urandom(4).hex(), proj)
        check("missing auto_resume means on and asks for 2 watchers", "0/2 armed - start 2" in line and "quota_watch.py" in line, line)

        q = lambda i: {"id": i, "text": "?", "options": ["a", "b"], "default": "a"}
        qf = tmp / "q.json"
        qf.write_text(json.dumps([q(f"q{i}") for i in range(5)] + [{"id": "auto_resume", "text": "auto?", "options": ["on", "off"], "default": "on"}]))
        check("auto_resume rides outside the 5-question budget", len(marathon.ask_questions(str(qf))) == 6)
        qf.write_text(json.dumps([q(f"q{i}") for i in range(6)]))
        try:
            marathon.ask_questions(str(qf))
            check("a sixth ordinary question is still refused", False)
        except SystemExit:
            check("a sixth ordinary question is still refused", True)

        resume_reports(tmp, marathon)

    print("ALL PASS" if not FAILED else f"{len(FAILED)} FAILED: {FAILED}")
    sys.exit(1 if FAILED else 0)


def stamped(rec, t):
    return dict(rec, timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t)))


def reply(uid, t):
    return stamped({"type": "assistant", "uuid": uid, "message": {"role": "assistant", "content": "ok"}}, t)


def resume_reports(tmp, marathon):
    """Usage-limit stops as the progress report and claim see them (marathon.resume_status, quota_watch_line)."""
    qw = marathon.qw_module()
    paths = {}
    qw.find_transcript = lambda sid: paths.get(sid)
    marathon.QUOTA_DIR = tmp / "qw"
    os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
    now = time.time()

    def session(sid, *rows):
        paths[sid] = tmp / f"{sid}.jsonl"
        paths[sid].write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    def status(*sids):
        marathon._RESUME_CACHE.clear()
        return marathon.resume_status({"lead_sessions": ",".join(sids)})

    session("r1", stamped(quota_error("x1", now - 3600), now - 5 * 3600), reply("y1", now - 3600 + 200))
    (tmp / "qw" / "r1" / "claimed" / "x1").mkdir(parents=True)
    line, flags = status("r1")
    check("report: resumed by the watcher, on time", "1 limit hit" in line and "resumed +3 min (watcher)" in line and not flags,
          f"{line} {flags}")

    session("r2", stamped(quota_error("x2", now - 7200), now - 6 * 3600), reply("y2", now - 7200 + 3000))
    line, flags = status("r2")
    check("report: a resume 50 min after the reset is flagged late", "outside tool or user" in line and any("late" in f for f in flags),
          f"{line} {flags}")

    session("r3", stamped(quota_error("x3", now - 3600), now - 5 * 3600))
    line, flags = status("r3")
    check("report: still stopped past the reset is flagged", "not resumed" in line and any("nothing resumed it" in f for f in flags),
          f"{line} {flags}")

    session("r4", stamped(quota_error("x4", now + 600), now - 3600))
    line, flags = status("r4")
    check("report: stopped before the reset is waiting, no flag", "stopped, reset at" in line and not flags, f"{line} {flags}")

    session("r5", stamped(quota_error("x5", now - 3600), now - 5 * 3600), stamped(quota_error("x6", now - 1800), now - 3000),
            reply("y5", now - 1800 + 120))
    line, flags = status("r5")
    check("report: a wake that hit the limit again counts once, resumed after the second", "1 limit hit" in line and "+2 min" in line
          and not flags, f"{line} {flags}")

    os.environ["CLAUDE_CODE_SESSION_ID"] = "r3"
    line, flags = status("r3")
    check("report: an open stop in the session running the report is resumed now", "resumed" in line and not any("nothing" in f for f in flags),
          f"{line} {flags}")
    os.environ.pop("CLAUDE_CODE_SESSION_ID")

    session("r6", reply("z1", now - 60))
    line, flags = status("r3", "r6")
    check("report: a later lead session taking over is not a failure", "took over" in line and not flags, f"{line} {flags}")

    line, flags = status()
    check("report: no limits hit", "0 limits hit" in line and not flags, line)

    proj = tmp / "proj2"
    proj.mkdir()
    (proj / "STATE.md").write_text("---\nstatus: running\nlead_sessions: r1,r2\n---\n# State\n\n## Log\n- start\n", encoding="utf-8")
    first = marathon.quota_watch_line("r1", proj)
    second = marathon.quota_watch_line("r1", proj)
    log = (proj / "STATE.md").read_text(encoding="utf-8")
    check("claim logs each resumed stop to STATE Log once", "logged to STATE Log" in first and "logged" not in second
          and log.count("usage limit stopped session") == 2, f"{first!r} {second!r}\n{log}")


if __name__ == "__main__":
    main()
