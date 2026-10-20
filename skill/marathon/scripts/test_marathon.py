"""Regression tests for marathon.py and stop_hook.py. Run: python test_marathon.py  (temp home and repos root; touches nothing real)."""
import json
import csv
import io
import datetime as dt
from contextlib import redirect_stdout, redirect_stderr
from types import SimpleNamespace
from unittest.mock import patch
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
SCRATCH = HERE.parents[2] / ".tmp"
SCRATCH.mkdir(exist_ok=True)
TMP = Path(tempfile.mkdtemp(prefix="marathon-test-", dir=SCRATCH))
REPOS = TMP / "repos"
ENV = dict(os.environ, MARATHON_CLAUDE_HOME=str(TMP / "home"), MARATHON_REPOS_ROOT=str(REPOS), CLAUDE_CODE_SESSION_ID="sess-test",
           MARATHON_OVERVIEW_GLOBS=str(REPOS / "*" / "STATE.md"),
           GIT_CEILING_DIRECTORIES=str(TMP), PYTHONIOENCODING="utf-8", GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
os.environ.update({k: ENV[k] for k in ("MARATHON_CLAUDE_HOME", "MARATHON_REPOS_ROOT",
                                      "MARATHON_OVERVIEW_GLOBS", "CLAUDE_CODE_SESSION_ID")})
FAILS = []
REG = TMP / "home" / "marathon" / "active" / "sess-test.json"


def m(*args, stdin=None, code=0):
    cmd = [sys.executable, "-B", str(HERE / "marathon.py"), *map(str, args)]
    if args[0] == "report":
        cmd[1:2] = ["-B", "-c", "import runpy, sys; from unittest.mock import patch; sys.argv=sys.argv[1:]; "
                    "p=patch('urllib.request.urlopen', side_effect=OSError('offline test')); p.start(); runpy.run_path(sys.argv[0], run_name='__main__')"]
    r = subprocess.run(cmd, input=stdin, capture_output=True, env=ENV, timeout=60, stdin=subprocess.DEVNULL if stdin is None else None)
    out = (r.stdout + r.stderr).decode("utf-8", "replace")
    if code is not None and r.returncode != code:
        FAILS.append(f"marathon {' '.join(map(str, args))}: exit {r.returncode}\n{out}")
    return out


def hook(payload=None, raw=None, cwd=str(TMP)):
    data = raw if raw is not None else json.dumps(payload or {"session_id": "sess-test", "cwd": cwd}).encode()
    r = subprocess.run([sys.executable, str(HERE / "stop_hook.py")], input=data, capture_output=True, env=ENV, timeout=30, stdin=subprocess.DEVNULL if data is None else None)
    if r.returncode != 0:
        FAILS.append(f"hook exit {r.returncode}")
    return r.stdout.decode("utf-8", "replace").strip()


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(f"{name}: {detail}")


def git(d, *args):
    assert (d / ".git").exists(), f"test git command must use an isolated repository: {d}"
    subprocess.run(["git", "-C", str(d), *args], capture_output=True, env=ENV, stdin=subprocess.DEVNULL)


def head(d):
    return subprocess.run(["git", "-C", str(d), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, stdin=subprocess.DEVNULL, encoding="utf-8").stdout.strip()


def gate(d, rnd, scores, verdict="VERDICT: FAIL critical=0 major=2", name="gate.md", reviewer="opus", artifact=None):
    p = d / "audits" / f"round-{rnd}"
    p.mkdir(parents=True, exist_ok=True)
    (p / name).write_text(f"report\n\nREVIEWER: {reviewer}\nARTIFACT: {artifact or head(d)}\nSCORES: {scores}\n{verdict}\n", encoding="utf-8")
    return f"audits/round-{rnd}/{name}"


def targets(d, met, total):
    c = (d / "CHARTER.md").read_text(encoding="utf-8")
    rows = "".join(f"| G{i} | x | y | z | {'✅' if i <= met else '–'} |\n" for i in range(1, total + 1))
    c = re.sub(r"\| G1 \| \| \| \| – \|\n", rows, c)
    (d / "CHARTER.md").write_text(c, encoding="utf-8")


def commit(d):
    git(d, "add", "-A")
    git(d, "commit", "-qm", "x")


SITE9 = "accuracy=9, coverage=9, visual_design=9, map_dataviz=9, phone=9, speed=9, interaction=9"
P = REPOS / "proj"

# SKILL.md front matter must stay valid YAML (a stray ": " once hid the description)
try:
    import yaml
    fm = yaml.safe_load((HERE.parent / "SKILL.md").read_text(encoding="utf-8").split("---")[1])
    check("SKILL.md front matter is valid YAML", fm.get("name") == "marathon" and len(fm.get("description", "")) > 100)
except ImportError:
    print("skip SKILL.md YAML check (no PyYAML)")

# Portable Stop hook: upgrade old commands, retain unrelated hooks, and run with no python on PATH.
settings = TMP / "home/settings.json"
settings.parent.mkdir(parents=True, exist_ok=True)
old_hook = {"type": "command", "command": 'python "$HOME/.claude/skills/marathon/scripts/stop_hook.py"'}
other_hook = {"type": "command", "command": "echo unrelated"}
settings.write_text(json.dumps({"custom": 1, "hooks": {"Stop": [{"matcher": "keep", "hooks": [old_hook, other_hook]}], "Other": []}}), encoding="utf-8")
m("install-hook")
installed = json.loads(settings.read_text(encoding="utf-8"))
commands = [h["command"] for e in installed["hooks"]["Stop"] for h in e["hooks"]]
expected_hook = f'"{Path(sys.executable).resolve().as_posix()}" "{(HERE / "stop_hook.py").resolve().as_posix()}"'
check("hook upgrades legacy python command to quoted absolute interpreter", expected_hook in commands and old_hook["command"] not in commands)
check("hook upgrade preserves unrelated settings and mixed Stop hooks", installed["custom"] == 1 and installed["hooks"]["Other"] == [] and "echo unrelated" in commands)
before_hook = settings.read_bytes()
m("install-hook")
check("portable hook install is idempotent", settings.read_bytes() == before_hook)
run_hook = subprocess.run(expected_hook, shell=True, input=b'{}', capture_output=True, env=dict(ENV, PATH=""), timeout=30)
check("hook runs without python on PATH", run_hook.returncode == 0, run_hook.stderr)
m("install-hook", "--remove")
remaining = json.loads(settings.read_text(encoding="utf-8"))
check("hook removal preserves only unrelated Stop entries", remaining["hooks"]["Stop"] == [{"matcher": "keep", "hooks": [other_hook]}])

# init and lifecycle
check("init accepts a directory outside the overview root", "status intake" in m("init", TMP / "elsewhere", "--type", "site", "--title", "T")
      and (TMP / "elsewhere/STATE.md").exists())
P.mkdir(parents=True)
(P / ".gitignore").write_text("dist/", encoding="utf-8")
out = m("init", P, "--type", "site", "--title", "T")
check("init creates intake project", "status intake" in out and (P / "CHARTER.md").exists(), out)
check("gitignore keeps dist/ and adds .tmp/ on its own line", (P / ".gitignore").read_text(encoding="utf-8").splitlines()[:2] == ["dist/", ".tmp/"])
check("rubric + NA lines written", "RUBRIC: accuracy=20" in (P / "CHARTER.md").read_text(encoding="utf-8"))
before = (P / "PROMPTS.md").read_text(encoding="utf-8")
m("init", P, "--type", "site", "--title", "T", code=1)
check("second init refuses and keeps files", (P / "PROMPTS.md").read_text(encoding="utf-8") == before)
check("hook idle during intake", hook() == "")
m("log", P, "-", stdin="做一个百科全书".encode("utf-8"))
out = m("log", P, "--lead", "1. 覆盖多少？（默认 6000）")
p = (P / "PROMPTS.md").read_text(encoding="utf-8")
check("log numbers user + lead entries", "## #1 · " in p and "· user\n做一个百科全书" in p and "## #2 · " in p and "ledger_through=2" in out, out)
m("set", P, "status=running", code=1)
out = m("set-status", P, "running", "--reason", "answers received")
check("set-status running arms", "armed" in out, out)
check("hook blocks while running", '"decision": "block"' in hook())
outs = [hook() for _ in range(3)]
check("3rd unchanged continue asks for the decision memo", "looks stuck" in outs[2], outs[2])
check("then the stop is allowed (released stale)", hook() == "")
reg = json.loads(REG.read_text(encoding="utf-8"))
check("registry records released=stale", reg.get("released") == "stale", reg)
m("set", P, "next=build wave 1")
check("progress re-arms the hook", '"decision": "block"' in hook())
check("session moved to another folder → hook stands aside", hook(cwd=str(TMP / "other")) == "")
m("claim", P)
reg2 = json.loads(REG.read_text(encoding="utf-8"))
check("claim keeps continue counter and run", reg2["blocks"] == reg["blocks"] + 1 and reg2["run"] == reg["run"], (reg, reg2))
m("wait", P, "workers W1-W3")
check("waiting lets the turn end", hook() == "")
m("wait", P, "--clear")
check("cleared wait blocks again", '"decision": "block"' in hook())
check("other session ignored", hook({"session_id": "other"}) == "")
check("garbage stdin ignored", hook(raw=b"not json") == "")
m("note", P, "parked", "need the BI login")
check("note parked", "- need the BI login" in (P / "STATE.md").read_text(encoding="utf-8"))
st = (P / "STATE.md").read_text(encoding="utf-8").replace("status: running", 'status: "running"')
(P / "STATE.md").write_text("﻿" + st, encoding="utf-8")
m("set", P, "next=quoted+bom")
check("BOM and quoted status still running", '"decision": "block"' in hook())
m("set", P, "budget_hours=0.0001")
m("wait", P, "workers")
check("budget beats waiting: one budget block", "budget" in hook())
m("wait", P, "--clear")
check("after the budget notice, normal continue", "still running" in hook())
m("set", P, "budget_hours=12")
r = json.loads(REG.read_text(encoding="utf-8")); r["blocks"] = 199; REG.write_text(json.dumps(r), encoding="utf-8")
m("set", P, "next=near cap")
check("200th continue asks for the memo", "last automatic continue" in hook())
m("set", P, "next=past cap")
check("after the cap, stops pass", hook() == "")
r = json.loads(REG.read_text(encoding="utf-8")); r["blocks"] = 5; r.pop("released", None); REG.write_text(json.dumps(r), encoding="utf-8")
out = m("status", P, "--full")
check("status shows hours and auto-continue", "/12 h" in out and "auto-continue: armed" in out, out)

# scoring (single-reviewer fixtures explicitly select the Opus gate)
m("set", P, "gate=opus")
commit(P)
out = m("score", P, "--from", gate(P, 1, "accuracy=9, coverage=9"), code=2)
check("missing dimensions → INVALID", "missing dimensions" in out, out)
out = m("score", P, "--from", gate(P, 1, SITE9.replace("phone=9", "phone=11")), code=2)
check("score > 10 → INVALID", "outside 0-10" in out, out)
out = m("score", P, "--from", gate(P, 1, SITE9, "VERDICT: PASS total=99"), code=2)
check("no critical/major → INVALID", "critical= and major=" in out, out)
out = m("score", P, "--from", gate(P, 1, SITE9, "VERDICT: PASS critical=0.5 major=0.5"), code=2)
check("decimal defect counts → INVALID", "whole-number" in out, out)
out = m("score", P, "--from", gate(P, 1, SITE9.replace("phone=9", "phone=n/a").replace("speed=9", "speed=n/a")), code=2)
check("n/a not allowed by CHARTER → INVALID", "NA line" in out, out)
out = m("score", P, "--from", gate(P, 1, SITE9, artifact="deadbee"), code=2)
check("report for another artifact → INVALID", "reviewed artifact deadbee" in out, out)
(P / "audits" / "round-1" / "gate.md").write_text("SCORES: " + SITE9 + "\nVERDICT: PASS critical=0 major=0\n", encoding="utf-8")
out = m("score", P, "--from", "audits/round-1/gate.md", code=2)
check("no REVIEWER / ARTIFACT lines → INVALID", "REVIEWER" in out and "ARTIFACT" in out, out)
out = m("score", P, "--from", gate(P, 1, SITE9, "VERDICT: PASS total=999 critical=0 major=0"))
check("all 9s but no ✅ targets → not TARGET MET", "CONTINUE" in out and "targets 0/1" in out, out)
check("total computed locally (90.0)", "total 90.0" in out, out)
targets(P, 2, 3)
commit(P)
out = m("score", P, "--from", gate(P, 2, SITE9, "VERDICT: PASS critical=0 major=0"))
check("targets 2/3 in CHARTER → not met even if STATE said otherwise", "targets 2/3" in out and "TARGET MET" not in out, out)
targets(P, 3, 3) if False else None
c = (P / "CHARTER.md").read_text(encoding="utf-8").replace("| G3 | x | y | z | – |", "| G3 | x | y | z | ✅ |")
(P / "CHARTER.md").write_text(c, encoding="utf-8")
commit(P)
out = m("score", P, "--from", gate(P, 3, SITE9, "VERDICT: PASS critical=0 major=0"))
check("all 9s + 3/3 ✅ → TARGET MET", out.strip().endswith("TARGET MET"), out)
check("STATE targets_met synced from CHARTER", "targets_met: 3/3" in (P / "STATE.md").read_text(encoding="utf-8"))
out = m("score", P, "--from", gate(P, 4, SITE9.replace("phone=9", "phone=7"), "VERDICT: FAIL critical=0 major=1"))
check("one dimension below floor → not met", "phone=7<8" in out and "TARGET MET" not in out, out)
out = m("score", P, "--from", gate(P, 5, SITE9, "VERDICT: FAIL critical=1 major=0"))
check("critical → not met", "TARGET MET" not in out, out)
out = m("score", P, "--from", gate(P, 6, SITE9), "--from", gate(P, 6, SITE9.replace("speed=9", "speed=5"), name="gate-b.md", reviewer="opus-b"))
check("two reports merge by minimum", "speed=5<8" in out, out)
out = m("score", P, "--carry-forward", "--round", "7", "--from", gate(P, 7, "phone=9.5", "VERDICT: PASS critical=0 major=0"))
check("carry-forward re-gate of one key", "INVALID" not in out and "speed=5<8" in out, out)
out = m("score", P, "--final", "--from", gate(P, 8, SITE9, "VERDICT: PASS critical=0 major=0"), code=2)
check("final with one reviewer → INVALID", "two different reviewers" in out, out)
(P / "dirty.txt").write_text("x", encoding="utf-8"); git(P, "add", "dirty.txt"); commit(P); (P / "dirty.txt").write_text("changed", encoding="utf-8")
out = m("score", P, "--final", "--from", gate(P, 8, SITE9, "VERDICT: PASS critical=0 major=0"),
        "--from", gate(P, 8, SITE9, "VERDICT: PASS critical=0 major=0", name="astra.md", reviewer="astra"), code=2)
check("final on a dirty tree → INVALID", "committed, clean" in out, out)
commit(P)
src = ["--from", gate(P, 8, SITE9, "VERDICT: PASS critical=0 major=0"),
       "--from", gate(P, 8, SITE9, "VERDICT: FAIL critical=1 major=0", name="astra.md", reviewer="astra")]
out = m("score", P, "--final", *src, code=3)
check("final: critical from Astra only → ADJUDICATE (the lead rules)", out.startswith("ADJUDICATE") and "critical: opus=0 vs astra=1" in out
      and "the lead rules" in out and "the lead (Opus" not in out, out)
(P / "audits" / "adj-keep.md").write_text("CRITICAL = 1 because the crash reproduces on the release build (astra.md, step 3)\n", encoding="utf-8")
out = m("score", P, "--final", *src, "--adjudication", "audits/adj-keep.md")
check("final: lead upholds Astra's critical → FINAL FAIL", out.strip().endswith("FINAL FAIL"), out)
(P / "audits" / "adj-drop.md").write_text("CRITICAL = 0 because the reported crash is a stale cached build; release commit is clean (shot 4)\n", encoding="utf-8")
out = m("score", P, "--final", *src, "--adjudication", "audits/adj-drop.md", code=2)
check("B3: dismissing critical requires a confirming fresh review", "confirming fresh review" in out, out)
(P / "audits" / "confirm.md").write_text("REVIEWER: opus-fresh\nCONFIRM: dismiss\n", encoding="utf-8")
with (P / "audits" / "adj-drop.md").open("a", encoding="utf-8") as f:
    f.write("CONFIRMED BY audits/confirm.md\n")
out = m("score", P, "--final", *src, "--adjudication", "audits/adj-drop.md")
check("final: lead dismisses it with a reason → FINAL PASS, ruling recorded", out.strip().endswith("FINAL PASS") and
      "lead-ruling" in (P / "audits" / "scores.csv").read_text(encoding="utf-8"), out)
(P / "audits" / "adj-short.md").write_text("CRITICAL = 0 because no\n", encoding="utf-8")
out = m("score", P, "--final", *src, "--adjudication", "audits/adj-short.md", code=2)
check("final: a ruling without a real reason → INVALID", "no CRITICAL ruling" in out, out)
out = m("score", P, "--round", "9", "--from", gate(P, 9, SITE9), "--from",
        gate(P, 9, SITE9.replace("speed=9", "speed=5"), name="astra.md", reviewer="astra-high"), code=3)
check("round: a key 4 points apart between Opus and Astra → ADJUDICATE", "key speed: opus=9 vs astra-high=5" in out, out)
out = m("score", P, "--final", "--from", gate(P, 8, SITE9, "VERDICT: PASS critical=0 major=0"),
        "--from", gate(P, 8, SITE9, "VERDICT: PASS critical=0 major=0", name="astra.md", reviewer="astra"))
check("final: both pass → FINAL PASS", out.strip().endswith("FINAL PASS"), out)

# plateau
GAME = "core_loop={0}, visual_art={0}, ui_ux={0}, feel={0}, content={0}, performance={0}, stability={0}"
for name, vals, want in (("p2", [6.0, 6.1, 6.2, 6.2], "PLATEAU"), ("p3", [6.0, 6.1, 6.2, 6.3], "CONTINUE")):
    Q = REPOS / name
    m("init", Q, "--type", "game", "--title", name)
    m("set", Q, "gate=opus")
    commit(Q)
    res = [m("score", Q, "--from", gate(Q, i, GAME.format(v))).strip().splitlines()[-1] for i, v in enumerate(vals, 1)]
    check(f"{','.join(f'{v*10:.0f}' for v in vals)} → {want}", res[-1] == want, res)

out = m("set-status", P, "paused", "--reason", "test")
check("pause releases", "released" in out and hook() == "")
check("pause banks work hours", re.search(r"^running_since: *$", (P / "STATE.md").read_text(encoding="utf-8"), re.M) is not None)
out = m("claim", P)
check("claim on paused does not arm", "nothing armed" in out, out)

# on-demand hook install / removal
SET = TMP / "home" / "settings.json"
SET.write_text(json.dumps({"permissions": {"allow": ["Bash(ls:*)"]},
                           "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "python usage_log.py"}]}]}}), encoding="utf-8")


def hooked():
    return "marathon/scripts/stop_hook.py" in SET.read_text(encoding="utf-8")


A, B = REPOS / "ha", REPOS / "hb"
m("init", A, "--type", "site", "--title", "A")
m("init", B, "--type", "site", "--title", "B")
check("no hook while nothing runs", not hooked())
m("set-status", A, "running", "--reason", "go")
check("set-status running installs the hook", hooked())
ENV2 = dict(ENV, CLAUDE_CODE_SESSION_ID="sess-two")
subprocess.run([sys.executable, str(HERE / "marathon.py"), "set-status", str(B), "running", "--reason", "go"], capture_output=True, env=ENV2, stdin=subprocess.DEVNULL)
out = m("set-status", A, "paused", "--reason", "x")
check("hook kept while another marathon runs", hooked() and "kept" in out, out)
(B / "STATE.md").write_text((B / "STATE.md").read_text(encoding="utf-8").replace("status: running", "status: done"), encoding="utf-8")
hook({"session_id": "sess-two", "cwd": str(TMP)})
check("hook removes itself when the last marathon ended by hand", not hooked())
cfg = json.loads(SET.read_text(encoding="utf-8"))
check("other settings and hooks preserved",
      cfg["permissions"]["allow"] == ["Bash(ls:*)"] and cfg["hooks"]["Stop"][0]["hooks"][0]["command"] == "python usage_log.py", cfg)

# progress report (report / --mark / note now / metrics)
R = REPOS / "rep"
m("init", R, "--type", "game", "--title", "Rep")
commit(R)
m("set-status", R, "running", "--reason", "go")
m("note", R, "now", "wave 1 running")
m("note", R, "now", "worker B running", "--add")
out = m("note", R, "now", "wave 2 running")
st = (R / "STATE.md").read_text(encoding="utf-8")
now_sec = st.split("## Now\n", 1)[1].split("\n## ", 1)[0]
check("note now replaces the section", now_sec.strip() == "- wave 2 running" and "replaced 2" in out, (out, now_sec))
check("replaced Now bullets go to Log", st.count("was now:") == 2 and "was now: worker B running" in st, st)
check("note now --add keeps both", "- worker B running" not in now_sec)
out = m("report", R, "--no-live")
check("first report counts from project start", "(project start," in out and "commits since: 1" in out, out)
check("unset metrics/resources flagged", "metrics/resources not set" in out, out)
check("no FLAGS for a fresh project except metrics", out.count("⚠") == 1, out)
vis = out.split("VISUAL", 1)[1].split("status ", 1)[0] if "VISUAL" in out else ""
check("visual block: progress and budget bars, 20 cells", "Progress  ░░░░░░░░░░░░░░░░░░░░  0%" in vis and "Budget    " in vis, out)
out = m("report", REPOS / "p2", "--no-live")
check("visual block: score trend scaled to the pass mark + weakest dims", re.search(r"Score     [▁-█]{4}  60\.0 → 62\.0 · pass 85", out)
      and "Weakest   " in out and "(floor 8)" in out, out)
check("visual block: last 3 rounds listed by number", "Last 3    R2 61.0 · R3 62.0 · R4 62.0" in out, out)
check("pace line and verdict", re.search(r"Pace      [+-]\d\.\d/round · 85 ", out) and re.search(r"pace \(last 3 rounds\): .*(keep going|plateau)", out), out)
sys.path.insert(0, str(HERE)); import marathon as M  # noqa: E402
check("pace: rounds to pass, out of reach, reached", M.pace([70, 71, 72], 85)[0] == "+1.0/round · 85 in ~13 rounds"
      and "out of reach" in M.pace([72, 72, 71], 85)[0] and "reached" in M.pace([80, 86], 85)[0]
      and M.pace([70], 85) is None and M.pace([60, 62, 64], 85)[1].startswith("keep going") and M.pace([70, 70.5, 71], 85)[1].startswith("plateau"))
check("bookkeeping files are not 'uncommitted product'", "uncommitted: none" in out, out)
(R / "game.js").write_text("x", encoding="utf-8"); git(R, "add", "game.js"); commit(R)
(R / "game.js").write_text("changed", encoding="utf-8")
old = __import__("time").time() - 2 * 3600
os.utime(R / "game.js", (old, old))
st = (R / "STATE.md").read_text(encoding="utf-8")
st = re.sub(r"^waiting_on:.*$", "waiting_on: workers W1", st, flags=re.M)
st = re.sub(r"^waiting_since:.*$", "waiting_since: 2020-01-01T00:00", st, flags=re.M)
(R / "STATE.md").write_text(st, encoding="utf-8")
m("set", R, "metrics=phone 28 fps; load 17 s", "resources=tripo 16k/22k cr", "link=http://127.0.0.1:9/")
out = m("report", R)
check("stale wait flagged", "waiting for" in out and "> 90 min" in out, out)
check("old uncommitted product change flagged", "uncommitted product changes (1 files)" in out and "game.js" in out, out)
check("unreachable live link flagged, report still exits 0", "live link not reachable" in out, out)
check("metrics flag gone once set", "metrics/resources not set" not in out, out)
check("status block shows metrics", "> Measured: phone 28 fps" in m("status", R, "--full"))
(R / ".tmp").mkdir(exist_ok=True)
(R / ".tmp" / "answer.md").write_text("**目标**：测试\n- 完成 r1", encoding="utf-8")
out = m("report", R, "--mark", "--save", R / ".tmp" / "answer.md")
st = (R / "STATE.md").read_text(encoding="utf-8")
rp = (R / "REPORTS.md").read_text(encoding="utf-8")
check("--mark sets reported_at and reported_commit", re.search(r"^reported_at: \d{4}-", st, re.M) and re.search(r"^reported_commit: \w{7}", st, re.M), st)
check("--save appends the answer to REPORTS.md", "## " in rp and "**目标**：测试" in rp and "since " in rp, rp)
m("report", R, "--mark", "--save", "-", stdin="second report".encode("utf-8"))
check("second --save appends, keeps the first", (R / "REPORTS.md").read_text(encoding="utf-8").count("\n## ") == 2)
out = m("report", R, "--no-live")
check("next report counts from the last report", "(last report," in out and "commits since: 0" in out, out)
m("log", R, "where are we?")
check("user messages since the last report listed", "#1 where are we?" in m("report", R, "--no-live"))
check("REPORTS.md does not make the gate artifact dirty",
      not subprocess.run(["git", "-C", str(R), "status", "--porcelain", "--untracked-files=no", "--", ".", ":!REPORTS.md", ":!STATE.md",
                          ":!PROMPTS.md", ":!game.js"], capture_output=True, text=True, stdin=subprocess.DEVNULL, encoding="utf-8").stdout.strip())
m("set-status", R, "paused", "--reason", "test done")

# rate, change since the last report, forecasts, overview
Q = REPOS / "p2"
check("score records work hours", "hours" in (Q / "audits" / "scores.csv").read_text(encoding="utf-8").splitlines()[0])
check("rate: points per work hour and what the hours left buy",
      M.rate([{"total": "60", "hours": "2"}, {"total": "62", "hours": "4"}, {"total": "64", "hours": "6"}], {"budget_hours": "10", "work_hours": "6"}) == "+1.00/h · 4.0 h left ≈ +4.0"
      and M.rate([{"total": "60", "hours": ""}, {"total": "62", "hours": "4"}], {}) is None)
(Q / ".tmp").mkdir(exist_ok=True)
(Q / ".tmp" / "r.md").write_text("**还差 23 分。**\n\n**我的评估**\n- **总体**：一般，涨分慢\n- **目标**：85 分 · 把握约 10% · 预计停在约 66\n\n**完成**：r4", encoding="utf-8")
m("report", Q, "--mark", "--save", Q / ".tmp" / "r.md", "--forecast", "next=63 end=66 chance=10")
check("forecast recorded after the latest round", "after_round" in (Q / "audits" / "forecasts.csv").read_text(encoding="utf-8")
      and ",4," in (Q / "audits" / "forecasts.csv").read_text(encoding="utf-8"))
out = m("report", Q, "--no-live")
check("forecast without a new gate says so", "next gate 63, end 66, chance 10% · no new gate since" in out, out)
m("score", Q, "--from", gate(Q, 5, GAME.format(6.4)))
out = m("report", Q, "--no-live")
check("forecast compared with the next gate", "→ actual R5 64.0 (+1.0)" in out, out)
check("change since the last report", "since last report: score 62.0 → 64.0 (+2.0)" in out, out)
m("report", Q, "--mark", "--forecast", "next=66 end=68 chance=15")
m("score", Q, "--from", gate(Q, 6, GAME.format(6.5)))
out = m("report", Q, "--no-live")
check("average miss once two forecasts have an outcome", "next-gate forecasts with an outcome: 2, average miss 1.0 points" in out, out)
(REPOS / "plain").mkdir(exist_ok=True)
(REPOS / "plain" / "STATE.md").write_text("# notes, not a marathon\n", encoding="utf-8")
ENV["MARATHON_OVERVIEW_GLOBS"] = str(REPOS / "*" / "STATE.md")
out = m("overview")
check("overview lists marathon projects with last 3 and pace", "p2 · " in out and "last 3: R4 62.0 · R5 64.0 · R6 65.0" in out and "pace +1.5/round" in out, out)
check("overview shows the saved assessment lines", "**总体**：一般，涨分慢" in out, out)
check("overview skips a STATE.md without marathon front matter", "plain" not in out, out)
import shutil as _sh
m("set", Q, "link=https://p2.example.test/")
_sh.copytree(Q, REPOS / "p2-old-copy", ignore=_sh.ignore_patterns(".git"))
check("overview hides an old copy of the same project in another folder", "p2-old-copy" not in m("overview"))
(TMP / "sess.json").write_text(json.dumps({"p2": {"id": "local_abc", "title": "P2 session"}}), encoding="utf-8")
out = m("overview", "--sessions", TMP / "sess.json", "--widget", TMP / "w.html", "--markdown")
w = (TMP / "w.html").read_text(encoding="utf-8")
check("overview --widget: a card per project, status word from 总体, buttons that send prompts with the session id",
      '<span class="n">p2</span>' in w and ">一般<" in w and "sendPrompt" in w and "［会话 local_abc］" in w and "<html" not in w, w[:300])
check("overview --markdown: phone table with session links", "| [p2](#local_abc) | 一般 |" in out, out)
js = json.loads(m("overview", "--json"))
check("overview --json: one entry per project, scores as [round, total]", any(x["name"] == "p2" and x["scores"][-1] == [6, 65.0] for x in js), js)

# ---- worker models, production quality, usage, handoff (2026-10-19) ----
check("models: spoken '6.1 Sol' is GPT-6.1-Sol high", m("models", "--name", "6.1 Sol").strip() == "codex gpt-6.1-sol high")
check("models: astra-xhigh keeps the effort", m("models", "--name", "astra-xhigh").strip() == "codex gpt-6-astra xhigh")
check("models: sonnet is the Claude model", m("models", "--name", "sonnet").strip() == "claude sonnet")
m("models", "--name", "gpt-9", code=1)
out = m("models", Q)
check("models: default chain sol61 > astra > sonnet", re.findall(r"^(primary|fallback)\s+(\w+)", out, re.M) ==
      [("primary", "sol61"), ("fallback", "astra"), ("fallback", "sonnet")], out)
m("set", Q, "workers=bogus", code=1)
m("set", Q, "workers=sonnet", "worker_fallback=astra")
check("set workers= changes the chain", "primary  sonnet" in m("models", Q) and "fallback astra" in m("models", Q))
m("set", Q, "workers=astra", "worker_fallback=sol61,sonnet")
m("worker", Q, "W1", "agent=codex", "model=gpt-6-astra", "class=build", "input=100", "output=10")
m("worker", Q, "W1", "input=+50", "status=done", "first_pass=y", "ended=2026-10-19T01:00")
rows = (Q / "audits" / "workers.csv").read_text(encoding="utf-8")
check("worker: +N adds to a number", ",150," in rows and ",done," in rows, rows)
m("worker", Q, "W1", "colour=red", code=1)
m("worker", Q, "W1", "class=painting", code=1)
for i in range(8):
    m("worker", Q, f"C{i}", "agent=codex", "model=gpt-6-astra", "effort=high", "class=test", "status=done", f"first_pass={'y' if i < 4 else 'n'}",
      "critical=1", "major=0", "ended=x")
m("worker", Q, "F1", "agent=codex", "model=gpt-6-astra", "class=test", "status=fallback", "ended=x")
out = m("workers", Q)
check("workers: fallback rows are not quality runs", re.search(r"gpt-6-astra/high\s+test\s+8\s", out) is not None, out)
check("usage: ledger has lead, Claude sub-agents, Codex runs", all(x in m("usage", Q) for x in ("lead", "Claude sub-agents", "Codex runs")))
m("worker", Q, "W9", "agent=codex", "model=gpt-6-astra", "class=build")
check("handoff refuses while a worker is still running", "workers still running (W9)" in m("handoff", Q, "--why", "context 180k", code=1))
m("worker", Q, "W9", "status=done", "ended=x")
armed_before_handoff = REG.exists()
out = m("handoff", Q, "--why", "context 180k", "--note", "W10 brief ready in .tmp/briefs")
st = (Q / "STATE.md").read_text(encoding="utf-8")
check("handoff writes the Handoff section and the resume prompt", "## Handoff" in st and "rotation 1: context 180k" in st and
      "W10 brief ready" in st and "Resume marathon" in out and "rotations: 1" in st, out + st[-400:])
check("handoff preserves this session until successor claim", REG.exists() == armed_before_handoff and "handoff_pending:" in st)
m("claim", Q)
check("claim records the lead session", "lead_sessions: sess-test" in (Q / "STATE.md").read_text(encoding="utf-8"))

# ---- run profiles, config printout, Astra timeout and late merge (2026-10-19) ----
out = m("config", Q, "--profiles")
check("config --profiles offers two new-run modes", all(k in out for k in ("claude", "codex")) and
      not any(k in out for k in ("classic", "codex-lead")), out)
out = m("set", Q, "profile=全 Claude")
st = (Q / "STATE.md").read_text(encoding="utf-8")
check("profile=全 Claude sets the Claude bundle and prints the config", "profile: claude" in st and "workers: sonnet" in st and
      "gate: opus" in st and "Run config · All Claude" in out and "Claude Sonnet 5.5" in out, out)
check("a run-config change is logged under Decisions", "run config: " in st)
out = m("set", Q, "profile=codex", "gate=opus", "summary_words=500")
check("keys named with a profile override its bundle", "Gate requested: Opus 5.5 xhigh (final adds Astra)" in out and "≤500 words" in out and "GPT-6-Astra high" in out, out)
m("set", Q, "gate=everyone", code=1)
m("set", Q, "astra_wait=soon", code=1)
m("set", Q, "profile=codex")
check("status shows the one-line config", "⚙ Codex workers" in m("status", Q))
r = 21
G9 = GAME.format(9)
out = m("score", Q, "--round", r, "--from", gate(Q, r, G9), "--astra-pending")
st = (Q / "STATE.md").read_text(encoding="utf-8")
check("--astra-pending scores with Opus alone and marks Astra as out", "astra_pending: round-21" in st and
      "opus+astra-pending" in (Q / "audits" / "scores.csv").read_text(encoding="utf-8") and "Astra for round-21 still out" in m("status", Q), out + st[-300:])
out = m("score", Q, "--late", "--round", r, "--from", gate(Q, r, G9), "--from",
        gate(Q, r, G9, "VERDICT: FAIL critical=1 major=0", name="astra.md", reviewer="astra-high"), code=3)
check("late Astra with a critical only it saw → ADJUDICATE", out.startswith("ADJUDICATE"), out)
(Q / "audits" / "round-21" / "ADJUDICATION.md").write_text("CRITICAL = 1 because Astra's broken export reproduces on the candidate (step 2)\n", encoding="utf-8")
out = m("score", Q, "--late", "--round", r, "--from", gate(Q, r, G9), "--from", "audits/round-21/astra.md",
        "--adjudication", "audits/round-21/ADJUDICATION.md")
csvt = (Q / "audits" / "scores.csv").read_text(encoding="utf-8")
check("late merge replaces the round's row, reports the changed verdict, clears astra_pending",
      "LATE MERGE round 21" in out and "changed the verdict" in out and csvt.count("\n21,") == 1 and "+late" in csvt
      and "astra_pending: round-21" not in (Q / "STATE.md").read_text(encoding="utf-8"), out)
out = m("score", Q, "--final", "--astra-pending", "--from", gate(Q, 22, G9), code=2)
check("the final gate cannot skip Astra", "final gate waits for both" in out, out)

# usage run from a session that is not this project's lead must not count that session (2026-10-19 project finding)
tr = TMP / "home" / "projects" / "elsewhere"
tr.mkdir(parents=True, exist_ok=True)
(tr / "sess-other.jsonl").write_text(json.dumps({"timestamp": "2099-01-01T00:00:00Z", "uuid": "u1", "message": {
    "id": "m1", "usage": {"input_tokens": 5, "cache_read_input_tokens": 7000000, "output_tokens": 5}}}) + "\n", encoding="utf-8")
ENV["CLAUDE_CODE_SESSION_ID"] = "sess-other"
out = m("usage", Q)
ENV["CLAUDE_CODE_SESSION_ID"] = "sess-test"
check("usage from an unregistered session leaves that session out", "7.0M" not in out, out)

# ---- F1 gate validation regressions (A1/A2/A9-A12/B3-B5) ----
G = REPOS / "f1-gates"
m("init", G, "--type", "site", "--title", "Gate regressions")
targets(G, 1, 1)
(G / "app.js").write_text("version 1", encoding="utf-8")
commit(G)
old_head = head(G)


def pair(d, rnd, scores=SITE9, artifact=None):
    return ["--from", gate(d, rnd, scores, artifact=artifact), "--from",
            gate(d, rnd, scores, name="astra.md", reviewer="astra", artifact=artifact)]


def score_rows(d):
    with (d / "audits" / "scores.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# A1: explicit artifacts cannot mask either tracked or untracked product edits.
for kind in ("tracked", "untracked"):
    dirty = G / ("app.js" if kind == "tracked" else "new-product.js")
    dirty.write_text("unreviewed", encoding="utf-8")
    for override in ([], ["--artifact", old_head]):
        out = m("score", G, "--final", *pair(G, 1), *override, code=2)
        check(f"A1: {kind} edits rejected with artifact override={bool(override)}", "committed, clean" in out, out)
    if kind == "tracked":
        dirty.write_text("version 1", encoding="utf-8")
    else:
        dirty.unlink()
out = m("score", G, "--final", *pair(G, 1), "--artifact", "not-a-real-commit", code=2)
check("A1: nonexistent --artifact rejected", "must resolve to a real commit" in out, out)
out = m("score", G, "--final", *pair(G, 1), "--artifact", "HEAD:app.js", code=2)
check("A1: blob --artifact rejected", "must resolve to a real commit" in out, out)
(G / "app.js").write_text("version 2", encoding="utf-8"); commit(G)
out = m("score", G, "--final", *pair(G, 1, artifact=old_head), "--artifact", old_head, code=2)
check("A1: real older commit rejected at final gate", "must match HEAD" in out, out)
(G / "research").mkdir(exist_ok=True)
(G / "research" / "new-note.md").write_text("bookkeeping", encoding="utf-8")
out = m("score", G, "--final", *pair(G, 1), "--artifact", "HEAD")
check("A1: clean final with bookkeeping edits and symbolic artifact passes", out.strip().endswith("FINAL PASS"), out)

# A11: actual gate policy, known families, explicit missing-family explanations.
one = ["--from", gate(G, 2, SITE9)]
out = m("score", G, "--round", 2, *one, code=2)
check("A11: default dual gate rejects Opus alone", "required reviewer models (opus/claude, astra/gpt): gpt" in out, out)
for reason in ("short", "          "):
    out = m("score", G, "--round", 2, *one, "--missing-reason", reason, code=2)
    check("A11: missing reason needs 10 non-padding characters", "at least 10" in out, out)
reason = "Astra service unavailable after timeout"
m("score", G, "--round", 2, *one, "--missing-reason", reason)
check("A11: missing family and reason are recorded", "+missing:gpt" in score_rows(G)[0]["reviewers"] and
      reason in (G / "STATE.md").read_text(encoding="utf-8"))
# R2 A-R1/O-R11: the requested models, not broad provider families, fill gate slots.
for policy in ("astra", "opus+opus"):
    out = m("set", G, f"gate={policy}", code=1)
    check(f"R2 O-R11: removed gate {policy} rejected", "gate must be one of opus+astra, opus" in out, out)
for policy, labels, expected in (("opus", ["opus-5.5"], 0), ("opus", ["sonnet-5.5"], 2),
                                 ("opus", ["fable-5.1"], 2), ("opus", ["opus+astra"], 2), ("opus+astra", ["opus-5.5", "astra-high"], 0),
                                 ("opus+astra", ["sonnet", "sol61"], 2), ("opus+astra", ["opus", "sol"], 2),
                                 ("opus+astra", ["opus", "luna"], 2), ("opus+astra", ["sonnet", "astra"], 2)):
    m("set", G, f"gate={policy}")
    args = []
    for i, label in enumerate(labels):
        args += ["--from", gate(G, 2, SITE9, name=f"model-{i}.md", reviewer=label)]
    out = m("score", G, "--round", 2, *args, code=expected)
    check(f"R2 A-R1: gate {policy} labels {labels}", ("INVALID" in out) == bool(expected), out)
m("set", G, "gate=opus+astra")
out = m("score", G, "--round", 2, "--from", gate(G, 2, SITE9, reviewer="astra"), "--astra-pending", code=2)
check("A11: pending cannot waive missing Claude", "only when Astra is the missing" in out, out)
out = m("score", G, "--round", 2, *pair(G, 2), "--astra-pending", code=2)
check("A11: pending rejected when Astra already present", "only when Astra is the missing" in out, out)
for labels, reason_args, expected in ((["opus", "opus-second"], [], 2), (["opus"], ["--missing-reason", reason], 2),
                                      (["astra", "gpt-6-sol"], ["--missing-reason", reason], 2),
                                      (["sonnet", "sonnet-second"], ["--missing-reason", reason], 2),
                                      (["opus", "sonnet-second"], ["--missing-reason", reason], 2),
                                      (["opus", "opus-second"], ["--missing-reason", reason], 0)):
    args = []
    for i, label in enumerate(labels):
        args += ["--from", gate(G, 3, SITE9, name=f"r{i}.md", reviewer=label)]
    out = m("score", G, "--final", *args, *reason_args, code=expected)
    check(f"A11: final fallback {labels}, reason={bool(reason_args)}", ("INVALID" in out) == bool(expected), out)

# A2: total-only disputes need an explicit covering ruling; malformed values never pass.
adj = G / "audits" / "ruling.md"
total_args = ["--from", gate(G, 4, SITE9), "--from",
              gate(G, 4, SITE9.replace("=9", "=7"), name="astra.md", reviewer="astra")]
for ruling in ("", "Some narrative without a ruling", "MAJOR = 0 because verified in app.js:1", "TOTAL ACCEPTED because looks good",
               "TOTAL ACCEPTED because everything is certainly correct", "TOTAL ACCEPTED because stepwise reasoning is convincing", "TOTAL ACCEPTED because the test looks good",
               "TOTAL ACCEPTED because took a shot at it", "TOTAL ACCEPTED because i.e. everything is good"):
    adj.write_text(ruling, encoding="utf-8")
    out = m("score", G, "--round", 4, *total_args, "--adjudication", adj, code=2)
    check(f"A2: empty/non-covering/unsupported total ruling rejected ({ruling[:30]})", out.startswith("INVALID"), out)
for ruling in ("TOTAL ACCEPTED because checked in screenshot 2", "KEY accuracy = 8 because test_accuracy verifies the data", "TOTAL ACCEPTED because Makefile:12 checks pass"):
    adj.write_text(ruling, encoding="utf-8")
    out = m("score", G, "--round", 4, *total_args, "--adjudication", adj)
    check("A2: total dispute accepts evidence-backed TOTAL or KEY", "INVALID" not in out and "ADJUDICATE" not in out, out)
key_args = ["--from", gate(G, 5, SITE9), "--from",
            gate(G, 5, SITE9.replace("speed=9", "speed=5"), name="astra.md", reviewer="astra")]
for value in ("99", "-1", "nan", "inf", "1.2.3"):
    adj.write_text(f"KEY speed = {value} because checked app.js:1", encoding="utf-8")
    out = m("score", G, "--round", 5, *key_args, "--adjudication", adj, code=2)
    check(f"A2: invalid adjudicated score {value}", "0-10" in out, out)
for field in ("CRITICAL", "MAJOR"):
    for value in ("-1", "0.5", "nan"):
        adj.write_text(f"KEY speed = 8 because app.js:1 verified\n{field} = {value} because app.js:1 verified", encoding="utf-8")
        out = m("score", G, "--round", 5, *key_args, "--adjudication", adj, code=2)
        check(f"A2: {field} rejects {value}", "non-negative integers" in out, out)
for ruling in ("TOTAL ACCEPTED because app.js:1 verifies the total", "KEY speed = 8 because app.js:1\n", "KEY accuracy = 8 because app.js:1 verified"):
    adj.write_text(ruling, encoding="utf-8")
    out = m("score", G, "--round", 5, *key_args, "--adjudication", adj, code=2)
    check("A2: each disputed key needs a valid reason and KEY ruling", "no ruling for disputed key speed" in out, out)
for value in (0, 10):
    adj.write_text(f"KEY speed = {value} because https://example.test/check confirms the result", encoding="utf-8")
    out = m("score", G, "--round", 5, *key_args, "--adjudication", adj)
    check(f"A2: score boundary {value} is valid", "INVALID" not in out, out)

# Independent-review regressions: a ruling cannot invent a score dispute.
adj.write_text("\n".join(f"KEY {key} = 10 because app.js:1 confirms it" for key in M.charter_rules(G)["weights"]), encoding="utf-8")
out = m("score", G, "--round", 8, *pair(G, 8, SITE9.replace("=9", "=8")), "--adjudication", adj, code=2)
check("review: matching reviewers cannot be inflated by an adjudication", "no dispute" in out, out)
adj.write_text("KEY speed = 8 because app.js:1 confirms it\nKEY accuracy = 10 because app.js:1 confirms it", encoding="utf-8")
out = m("score", G, "--round", 5, *key_args, "--adjudication", adj, code=2)
check("review: unrelated KEY cannot ride along with a disputed KEY", "no dispute covers" in out, out)

# B3: confirmation required for every reduction, even if both reviewers reported criticals.
crit_args = ["--from", gate(G, 6, SITE9, "VERDICT: FAIL critical=2 major=0"), "--from",
             gate(G, 6, SITE9, "VERDICT: FAIL critical=1 major=0", name="astra.md", reviewer="astra")]
confirm = G / "audits" / "confirm.md"
for content in (None, "REVIEWER: opus-fresh\n", "CONFIRM: dismiss\n", "REVIEWER: opus-fresh\nCONFIRM: keep\n",
                "REVIEWER: opus-fresh\nCONFIRM: dismiss\n"):
    if content is not None:
        confirm.write_text(content, encoding="utf-8")
    adj.write_text("CRITICAL = 1 because step 3 reproduces only one finding\nCONFIRMED BY audits/confirm.md\n", encoding="utf-8")
    valid = content is not None and "REVIEWER:" in content and "CONFIRM: dismiss" in content
    out = m("score", G, "--round", 6, *crit_args, "--adjudication", adj, code=0 if valid else 2)
    check(f"B3: confirming review validation {content!r}", ("confirming fresh review" not in out) == valid, out)

# A12: all Claude/GPT pairs contribute, including criticals seen only by later reviewers.
reports = [{"reviewer": name, "dims": {"quality": value}, "critical": critical}
           for name, value, critical in (("opus-first", 9, 0), ("opus-second", 5, 1), ("astra-first", 9, 0), ("gpt-second", 9, 0))]
splits = M.disagreements(reports, {"quality": 100})
check("A12: second Claude compared with each GPT report", len(splits) == 6 and all(any(f"opus-second" in s and gpt in s
      for s in splits if s.startswith(kind)) for gpt in ("astra-first", "gpt-second") for kind in ("key", "total", "critical")), splits)
args = []
for i, report in enumerate(reports):
    args += ["--from", gate(G, 7, SITE9.replace("speed=9", f"speed={report['dims']['quality']}"),
                           f"VERDICT: FAIL critical={report['critical']} major=0", name=f"pair{i}.md", reviewer=report["reviewer"])]
out = m("score", G, "--round", 7, *args, code=3)
check("A12: CLI reports each pair's disputes", "opus-second=5 vs astra-first=9" in out and "opus-second=5 vs gpt-second=9" in out, out)

# A9/A10: multiple pending rounds, new HEAD, current rubric, stable row order/final-last.
L = REPOS / "late-gates"
m("init", L, "--type", "game", "--title", "Late gates")
targets(L, 1, 1); commit(L)
first_head = head(L)
for rnd in (1, 2):
    m("score", L, "--round", rnd, "--from", gate(L, rnd, GAME.format(9)), "--astra-pending")
check("A10: pending rounds accumulate and status shows both", M.read_state(L)[0]["astra_pending"] == "round-1,round-2" and
      "Astra for round-1,round-2 still out" in m("status", L))
(L / "game.js").write_text("new wave", encoding="utf-8"); commit(L)
m("score", L, "--final", *pair(L, 3, GAME.format(9)))
charter = L / "CHARTER.md"
charter.write_text(charter.read_text(encoding="utf-8").replace("core_loop=20", "core_loop=100"), encoding="utf-8")
late_args = pair(L, 1, GAME.format(9).replace("core_loop=9", "core_loop=8"), artifact=first_head)
out = m("score", L, "--late", "--round", 1, *late_args)
rows = score_rows(L)
check("A9: late reports bind to earlier artifact and current rubric", "current CHARTER rubric" in out and "total 84.4" in out and
      rows[0]["artifact"] == first_head and rows[0]["total"] == "84.4", out)
check("A10: late replacement preserves round order and final last", [r["round"] for r in rows] == ["1", "2", "final"], rows)
check("A10: only merged pending round removed; current gate unchanged", M.read_state(L)[0]["astra_pending"] == "round-2" and
      M.read_state(L)[0]["gate_round"] == "2" and M.read_state(L)[0]["last_score"] == "90/100")
out = m("score", L, "--late", "--round", 1, *pair(L, 1, GAME.format(9)), code=2)
check("A9: current HEAD reports rejected for a historical late merge", "reviewed artifact" in out, out)
out = m("score", L, "--late", "--round", 99, *pair(L, 99, GAME.format(9)), code=2)
check("A9: late merge needs an existing row", "no earlier score" in out, out)
m("score", L, "--late", "--round", 2, *pair(L, 2, GAME.format(9), artifact=first_head))
check("A10: all merged rounds clears pending", M.read_state(L)[0]["astra_pending"] == "")

# Preserve ordinary re-score history; only --late replaces an existing round.
m("score", L, "--round", 1, *pair(L, 1, GAME.format(9)))
check("review: ordinary historical re-score keeps current gate", M.read_state(L)[0]["gate_round"] == "2")
m("score", L, "--final", *pair(L, 4, GAME.format(9)))
check("review: repeated final gates retain audit rows", sum(r["round"] == "final" for r in score_rows(L)) == 2)

out = m("score", L, "--late", "--round", 1, *pair(L, 1, GAME.format(9)))
ones = [r for r in score_rows(L) if r["round"] == "1"]
check("review: late merge after re-score binds newest artifact and retains older audit", len(ones) == 2 and
      ones[0]["artifact"] == first_head and ones[-1]["artifact"] == head(L) and "+late" in ones[-1]["reviewers"], out)

# B4: persisted timer, wait expiry, zero always waits, and round binding.
out = m("gate-wait", G, "--round", 8, code=1)
check("B4: timer query requires start", "--start" in out, out)
m("gate-wait", G, "--round", 8, "--start")
fm, body = M.read_state(G)
check("B4: start persists seconds-precision ISO time and round", dt.datetime.fromisoformat(fm["gate_started"]) and
      re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", fm["gate_started"]) and fm["gate_round_open"] == "8")
out = m("gate-wait", G, "--round", 8)
check("B4: fresh gate waits", "minutes elapsed" in out and "WAIT (" in out and "of 10" in out, out)
fm["gate_started"] = (dt.datetime.now() - dt.timedelta(minutes=11)).isoformat(); M.write_state(G, fm, body)
out = m("gate-wait", G, "--round", 8)
check("B4: expired timer recommends pending score", "GO: Astra is past astra_wait; score with --astra-pending" in out, out)
m("set", G, "astra_wait=0")
out = m("gate-wait", G, "--round", 8)
check("B4: zero always waits", "WAIT (" in out and "always wait" in out and "GO:" not in out, out)
out = m("gate-wait", G, "--round", 9, code=1)
check("B4: timer cannot be reused for another round", "no open gate timer" in out, out)

# B5/U1: status never reads token accounting, including obsolete session baselines.
for baseline in (None, "", "100|1"):
    fm, body = M.read_state(G)
    if baseline is None:
        fm.pop("tokens_at_start", None)
    else:
        fm["tokens_at_start"] = baseline
    M.write_state(G, fm, body)
    output = io.StringIO()
    with patch.object(M, "usage_row", side_effect=AssertionError("status must stay cheap")), \
            patch.object(M, "usage_ledger", side_effect=AssertionError("no transcript scans in status")), redirect_stdout(output):
        M.cmd_status(SimpleNamespace(dir=G))
    check(f"B5/U1: status omits tokens with baseline {baseline!r}", "tokens" not in output.getvalue() and "API" not in output.getvalue(), output.getvalue())

# R2 A-R2: reuse a complete passing regular round, without reading or launching new reviews.
U = REPOS / "reuse"
m("init", U, "--type", "site", "--title", "Reuse")
(U / "app.js").write_text("candidate", encoding="utf-8")
targets(U, 1, 1); commit(U)
m("score", U, "--round", 1, *pair(U, 1))
reviewers = score_rows(U)[0]["reviewers"]
# Persisted validated scores suffice; source report files are not reread.
(U / "audits" / "round-1" / "gate.md").unlink()
out = m("score", U, "--final", "--reuse-round", 1)
check("R2 A-R2: clean passing dual round reuses both reviewers", out.strip().endswith("FINAL PASS") and
      score_rows(U)[-1]["reviewers"] == reviewers + "+reuse-round:1", out)
for args in (("--reuse-round", 1), ("--final",), ("--final", "--reuse-round", 99),
             ("--final", "--reuse-round", 1, "--from", "audits/round-1/astra.md"),
             ("--final", "--reuse-round", 1, "--missing-reason", reason),
             ("--final", "--reuse-round", 1, "--carry-forward"),
             ("--final", "--reuse-round", 1, "--adjudication", "audits/ruling.md"),
             ("--final", "--reuse-round", 1, "--astra-pending"), ("--final", "--reuse-round", 1, "--late")):
    before = (U / "audits" / "scores.csv").read_bytes()
    out = m("score", U, *args, code=2)
    check(f"R2 A-R2: invalid reuse arguments {args}", "INVALID" in out and
          (U / "audits" / "scores.csv").read_bytes() == before, out)
for filename in ("app.js", "untracked.js"):
    file = U / filename
    file.write_text("unreviewed", encoding="utf-8")
    out = m("score", U, "--final", "--reuse-round", 1, "--artifact", "HEAD", code=2)
    check(f"R2 A-R2: reuse rejects dirty {filename}", "committed, clean" in out, out)
    if filename == "app.js":
        file.write_text("candidate", encoding="utf-8")
    else:
        file.unlink()
charter = (U / "CHARTER.md").read_text(encoding="utf-8")
for change in (charter.replace("accuracy=20", "accuracy=21"), charter + "\nFLOOR: accuracy=9.5\n",
               charter + "\nPASS_TOTAL: 95\n", charter.replace("✅", "–")):
    (U / "CHARTER.md").write_text(change, encoding="utf-8")
    out = m("score", U, "--final", "--reuse-round", 1, code=2)
    check("R2 A-R2: reuse rejects changed scoring rules", "unchanged scoring rules" in out, out)
(U / "CHARTER.md").write_text(charter, encoding="utf-8")
m("score", U, "--round", 2, *pair(U, 2, SITE9.replace("=9", "=7")))
out = m("score", U, "--final", "--reuse-round", 2, code=2)
check("R2 A-R2: nonpassing regular round cannot be reused", "passing regular round" in out, out)
m("score", U, "--round", 3, "--from", gate(U, 3, SITE9), "--astra-pending")
out = m("score", U, "--final", "--reuse-round", 3, code=2)
check("R2 A-R2: pending round cannot be reused", "complete dual round" in out, out)
m("set", U, "gate=opus")
m("score", U, "--round", 4, "--from", gate(U, 4, SITE9))
out = m("score", U, "--final", "--reuse-round", 4, code=2)
check("R2 A-R2: single-model round cannot be reused", "required reviewer models" in out, out)
m("set", U, "gate=opus+astra")
m("score", U, "--round", 5, *pair(U, 5))
# Older rows without the rubric snapshot cannot establish that it stayed unchanged.
rows = score_rows(U); rows[-2].pop("rubric", None)
with (U / "audits" / "scores.csv").open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=M.CSV_FIELDS); writer.writeheader(); writer.writerows(rows)
out = m("score", U, "--final", "--reuse-round", 5, code=2)
check("R2 A-R2: legacy round without rubric cannot be reused", "unchanged scoring rules" in out, out)
(U / "app.js").write_text("new candidate", encoding="utf-8"); commit(U)
out = m("score", U, "--final", "--reuse-round", 1, code=2)
check("R2 A-R2: changed candidate SHA cannot be reused", "current clean candidate SHA" in out, out)


# AB-A/B: evidence packs and asymmetric full/focused gates.
E = REPOS / "evidence-gates"
m("init", E, "--type", "site", "--title", "Evidence gates")
out = m("evidence", E, "--round", 1, code=1)
check("AB-B: uncommitted candidate rejected", "committed, clean" in out and not (E / "audits/round-1/evidence").exists(), out)
targets(E, 1, 1)
(E / "app.js").write_text("initial", encoding="utf-8")
(E / "old.txt").write_text("rename me", encoding="utf-8")
(E / "removed.txt").write_text("remove me", encoding="utf-8")
commit(E)
first_sha = M.resolve_artifact(E, "HEAD")
for rnd in (0, -1):
    out = m("evidence", E, "--round", rnd, code=1)
    check("AB-B: round must be positive", "must be positive" in out, out)
out = m("evidence", E, "--round", 1)
pack1 = E / "audits/round-1/evidence"
changed = (pack1 / "CHANGED.md").read_text(encoding="utf-8")
index = (pack1 / "EVIDENCE.md").read_text(encoding="utf-8")
check("AB-B: first pack prints path and includes initial inventory", str(pack1.resolve()) in out and first_sha in changed and
      "project start (empty tree" in changed and "app.js" in changed and "git diff --stat" in changed and "--name-status" in changed, changed)
check("AB-B: evidence index is explicitly unfilled with all required sections", "NOT FILLED" in index and first_sha in index and
      all(section in index for section in ("Hard-check outputs and test counts", "Screenshots/contact sheets", "Live URL checks",
                                          "Known open defects carried from the last round", "No earlier scored round", "Review inputs")), index)
(pack1 / "EVIDENCE.md").write_text(index + "worker findings\n", encoding="utf-8")
out = m("evidence", E, "--round", 1, code=1)
check("AB-B: rerun protects worker-filled evidence", "already exists" in out and
      (pack1 / "EVIDENCE.md").read_text(encoding="utf-8").endswith("worker findings\n"), out)
m("score", E, "--round", 1, *pair(E, 1))
(E / "app.js").write_text("new candidate", encoding="utf-8")
(E / "old.txt").rename(E / "renamed.txt")
(E / "removed.txt").unlink()
(E / "added.txt").write_text("added", encoding="utf-8")
out = m("evidence", E, "--round", 2, code=1)
check("AB-B: dirty candidate cannot freeze misleading evidence", "committed, clean" in out and not (E / "audits/round-2/evidence").exists(), out)
commit(E)
# A future scored round and final row must not become the baseline for round 2.
m("score", E, "--round", 5, *pair(E, 5, SITE9.replace("=9", "=8")))
m("score", E, "--final", *pair(E, 6))
out = m("evidence", E, "--round", 2)
pack2 = E / "audits/round-2/evidence"
changed = (pack2 / "CHANGED.md").read_text(encoding="utf-8")
index = (pack2 / "EVIDENCE.md").read_text(encoding="utf-8")
check("AB-B: diff pins previous regular artifact and current full SHA", f"Baseline: round 1 ({first_sha})" in changed and
      f"Artifact: {M.resolve_artifact(E, 'HEAD')}" in changed and
      all(name in changed for name in ("app.js", "old.txt", "renamed.txt", "removed.txt", "added.txt")), changed)
check("AB-B: previous defect counts and reports indexed", "Round 1: critical=0, major=2" in index and "audits/round-1/" in index, index)
# A missing historical artifact is a failure, not a fabricated project-start diff.
score_file = E / "audits/scores.csv"
saved_scores = score_file.read_bytes()
rows = score_rows(E); rows[0]["artifact"] = "missing-ab-artifact"
with score_file.open("w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=M.CSV_FIELDS); w.writeheader(); w.writerows(rows)
out = m("evidence", E, "--round", 3, code=1)
check("AB-B: unresolved baseline fails without a partial pack", "cannot be resolved" in out and not (E / "audits/round-3/evidence").exists(), out)
score_file.write_bytes(saved_scores)
real_run = M._run
with patch.object(M, "_run", side_effect=lambda cmd, **kw: None if "diff" in cmd else real_run(cmd, **kw)):
    try:
        M.cmd_evidence(SimpleNamespace(dir=E, round=3))
        failed_diff = False
    except SystemExit as ex:
        failed_diff = "git diff failed" in str(ex)
check("AB-B: failed diff cannot create a partial evidence pack", failed_diff and not (E / "audits/round-3/evidence").exists())

focused = ["--from", gate(E, 2, "accuracy=9", name="focused.md"), "--from",
           gate(E, 2, SITE9.replace("coverage=9", "coverage=5").replace("speed=9", "speed=10"), name="full.md", reviewer="astra")]
out = m("score", E, "--round", 2, *focused, "--carry-forward")
row = next(r for r in score_rows(E) if r["round"] == "2")
carried = json.loads(row["carried"])
check("AB-A: focused Opus plus full Astra compares only shared fresh keys", "ADJUDICATE" not in out and "coverage=5<8" in out, out)
check("AB-A: each omitted Opus key carries conservatively despite full Astra", json.loads(row["dims"])["speed"] == 9 and
      carried["round"] == "1" and carried["reviewers"]["opus"]["speed"] == 9 and "accuracy" not in carried["reviewers"]["opus"] and
      "carried from round 1 for opus:" in out, (row, out))
out = m("score", E, "--late", "--round", 2, *focused, "--carry-forward")
check("AB-A: late carry uses earlier round, never itself or a future round", "carried from round 1" in out, out)
out = m("score", E, "--round", 2, *focused, code=2)
check("AB-A: focused report needs explicit carry-forward", "missing dimensions" in out, out)
out = m("score", E, "--round", 1, *focused, "--carry-forward", code=2)
check("AB-A: first round cannot carry later history", "needs an earlier scored round" in out, out)
out = m("score", E, "--round", 3, *focused, "--carry-forward", code=2)
check("AB-A: every third regular Opus review must be full", "every third regular round" in out, out)
out = m("score", E, "--round", 2, "--carry-forward", "--from", gate(E, 2, SITE9), "--from",
        gate(E, 2, "accuracy=9", name="partial-astra.md", reviewer="astra"), code=2)
check("AB-A: Astra cannot become focused", "Astra must score every key" in out, out)
out = m("score", E, "--final", *pair(E, 7), "--carry-forward", code=2)
check("AB-A: final never carries scores", "final gate requires full reviews" in out, out)
# Carried passing rounds need fresh full release reviews; full regular rounds retain reuse.
out = m("score", E, "--round", 2, "--carry-forward", "--from", gate(E, 2, "accuracy=9", name="focused.md"), "--from",
        gate(E, 2, SITE9, name="full.md", reviewer="astra"))
check("AB-A: focused round can pass regular targets", out.strip().endswith("TARGET MET"), out)
out = m("score", E, "--final", "--reuse-round", 2, code=2)
check("AB-A: focused round cannot be reused as full final review", "full reviews; this round has carried scores" in out, out)
m("score", E, "--round", 3, *pair(E, 3))
out = m("score", E, "--final", "--reuse-round", 3)
check("AB-A: full periodic round still supports final reuse", out.strip().endswith("FINAL PASS"), out)

# Pending focused rounds preserve scores, and late Astra uses the same earlier baseline.
out = m("score", E, "--round", 4, "--carry-forward", "--astra-pending", "--from",
        gate(E, 4, "accuracy=9", name="focused.md"))
check("AB-A: pending focused Opus carries round 3", "carried from round 3" in out and
      "round-4" in M.read_state(E)[0]["astra_pending"], out)
out = m("score", E, "--round", 4, "--late", "--carry-forward", "--from", "audits/round-4/focused.md", "--from",
        gate(E, 4, SITE9, name="astra.md", reviewer="astra"))
check("AB-A: late full Astra preserves carry provenance and clears pending", "carried from round 3" in out and
      "round-4" not in M.read_state(E)[0]["astra_pending"], out)
# A newly added rubric key cannot silently become n/a via carry-forward.
charter = (E / "CHARTER.md").read_text(encoding="utf-8")
(E / "CHARTER.md").write_text(charter.replace("accuracy=20", "new_key=10, accuracy=20"), encoding="utf-8")
out = m("score", E, "--round", 7, "--carry-forward", "--from", gate(E, 7, "accuracy=9"), "--from",
        gate(E, 7, SITE9 + ", new_key=9", name="astra.md", reviewer="astra"), code=2)
check("AB-A: new rubric keys require fresh review", "cannot supply new rubric keys" in out, out)
(E / "CHARTER.md").write_text(charter, encoding="utf-8")

# Dispute thresholds are unchanged, but totals share the same actually reviewed denominator.
for av, bv, expect_total, expect_key in ((9, 9, False, False), (9, 8, True, False), (9, 6, True, True)):
    reports = [{"reviewer": "opus", "dims": {"a": av}, "critical": 0},
               {"reviewer": "astra", "dims": {"a": bv, "b": 0}, "critical": 0}]
    split = M.disagreements(reports, {"a": 20, "b": 80})
    check(f"AB-A: shared key/total thresholds {av}/{bv}", any(x.startswith("total:") for x in split) == expect_total and
          any(x.startswith("key ") for x in split) == expect_key, split)
reports = [{"reviewer": "opus", "dims": {"a": 9}, "critical": 1},
           {"reviewer": "astra", "dims": {"b": 1}, "critical": 0}]
check("AB-A: critical disputes survive non-overlapping scope", M.disagreements(reports, {"a": 50, "b": 50}) ==
      ["critical: opus=1 vs astra=0"])
# Lead-read core stays within the agreed character budget, and required prompt scopes remain explicit.
core = ("SKILL.md", "workers.md", "gate.md")
base_chars = 12000  # public lead-core budget baseline
now_chars = sum(len((HERE.parent / name).read_text(encoding="utf-8")) for name in core)
check("AB: lead-read core grows at most 1500 characters", now_chars - base_chars <= 1500, now_chars - base_chars)
prompt = (HERE.parent / "references/gate-prompt.md").read_text(encoding="utf-8")
check("AB: prompt retains delivery and focused-review requirements", all(text in prompt for text in
      ("≤300 words", "four score lines", "80 tool calls", "150 FULL", "rounds 3/6/9/", "ALL open critical/major",
       "highest-weight", "previous round", "PARTIAL")), prompt)

# ---------- S1: merged CLI aliases and compact status ----------
help_text = m("--help")
visible = "init claim status set note log wait score evidence preflight worker usage handoff config install-hook ask lock".split()
check("S1: help exposes exactly 17 commands", "{" + ",".join(visible) + "}" in help_text, help_text)
for alias in ("overview", "report", "set-status", "gate-wait", "workers", "handoff-abort", "logins", "models"):
    check(f"S1: hidden alias {alias}", not re.search(r"^\s+" + alias + r"(?:\s|$)", help_text, re.M), help_text)
# Compare parsing through the same handler, including every legacy option.
for handler, alias_old, alias_new in (
    ("cmd_status", ["overview", "--days", "3", "--json", "--sessions", "s.json", "--widget", "w.html", "--markdown"],
     ["status", "--days", "3", "--json", "--sessions", "s.json", "--widget", "w.html", "--markdown"]),
    ("cmd_status", ["report", str(Q), "--since", "2026-01-01", "--mark", "--save", "-", "--forecast", "next=80", "--no-live"],
     ["status", str(Q), "--report", "--since", "2026-01-01", "--mark", "--save", "-", "--forecast", "next=80", "--no-live"]),
    ("cmd_wait", ["gate-wait", str(Q), "--round", "2", "--start"], ["wait", str(Q), "--gate", "--round", "2", "--start"]),
    ("cmd_worker", ["workers", str(Q), "--pool"], ["worker", str(Q), "--pool"]),
    ("cmd_handoff", ["handoff-abort", str(Q)], ["handoff", str(Q), "--abort"]),
    ("cmd_config", ["models", "--name", "astra"], ["config", "--models", "--name", "astra"]),
    ("cmd_config", ["models", str(Q)], ["config", str(Q), "--models"]),
    ("cmd_config", ["models"], ["config", "--models"]),
):
    parsed = []
    for argv in (alias_old, alias_new):
        with patch.object(M, handler) as target, patch.object(sys, "argv", ["marathon.py", *argv]), \
                patch.object(sys, "stdin", SimpleNamespace(buffer=io.BytesIO())):
            M.main()
        parsed.append({k: v for k, v in vars(target.call_args.args[0]).items() if k not in ("cmd", "f")})
    check(f"S1: alias arguments {alias_old[0]}", parsed[0] == parsed[1], parsed)
# Login aliases use a fake launcher: never open a browser during tests.
login_results = []
for argv in (["logins", "https://one.invalid", "https://two.invalid"],
             ["preflight", "--logins", "https://one.invalid", "https://two.invalid"]):
    out = io.StringIO()
    with patch.object(sys, "argv", ["marathon.py", *argv]), patch.object(M.os.path, "exists", return_value=True), \
            patch.object(M.subprocess, "Popen") as launch, redirect_stdout(out):
        M.main()
    login_results.append((launch.call_args, out.getvalue()))
check("S1: login alias preserves launch args and output", login_results[0] == login_results[1], login_results)
for args in (("set-status", Q, "running"), ("set", Q, "--status", "running"), ("set", Q),
             ("gate-wait", Q), ("wait", Q, "--gate"), ("report",), ("status", "--report"),
             ("handoff", Q), ("logins",), ("config",)):
    m(*args, code=2)
fm = dict(status="running", phase="3", progress="40", targets_met="1/3", budget_hours="12", last_score="82", gate_round="4",
          mode="fast", link="https://example.invalid", changed="built it", metrics="42 checks", next="gate", waiting_on="W1")
with patch.object(M, "read_state", return_value=(fm, "")), patch.object(M, "work_hours", return_value=2.5), \
        patch.object(M, "run_config", return_value=["config"]), patch.object(M, "registry_info", return_value={"blocks": 2}), \
        patch.object(M, "read_scores", return_value=[dict(total=str(n)) for n in (60, 70, 78, 82)]), \
        patch.object(M, "read_workers", return_value=[dict(id="W1", started="x", status="running"),
                                                    dict(id="W2", started="x", status="done")]):
    out = io.StringIO()
    with redirect_stdout(out): M.cmd_status(SimpleNamespace(dir=Q))
    short = out.getvalue()
    out = io.StringIO()
    with redirect_stdout(out): M.cmd_status(SimpleNamespace(dir=Q, full=True))
    full = out.getvalue()
expected = ("> **running** · Phase 3 · 40% · targets 1/3 · 2.5/12 h · ~3.8 h left (rough) · gate R4 82 · mode fast\n"
            "> config\n> Try it: https://example.invalid\n> Changed: built it\n> Measured: 42 checks\n> Next: gate\n"
            "<!-- auto-continue: armed, 2 continues; waiting on W1 -->\n")
check("S1: full status preserves previous output exactly", full == expected, full)
check("S1: short status is at most 12 lines with decision facts", len(short.splitlines()) <= 12 and all(x in short for x in
      ("Phase 3", "40%", "2.5/12 h", "70 → 78 → 82", "Running workers (1): W1", "Waiting on: W1", "Next: gate", "config")), short)
check("S1: short status omits detailed fields", all(x not in short for x in ("Try it:", "Changed:", "Measured:", "auto-continue:")), short)

# S2: golden rows captured against the pre-refactor scorer; only SHA is fixture-dependent.
S2 = REPOS / "s2-replay"
m("init", S2, "--type", "site", "--title", "S2 replay")
(S2 / "CHARTER.md").write_text("RUBRIC: a=60, b=40\n| G1 | fixture | ✅ |\n", encoding="utf-8")
(S2 / "app.js").write_text("candidate", encoding="utf-8")
commit(S2)
S2_SHA = head(S2)
S2_RUBRIC = '{"floors": {"a": 8.0, "b": 8.0}, "na": [], "pass_total": 85.0, "targets": [1, 1], "weights": {"a": 60.0, "b": 40.0}}'


def s2_score(d=S2, code=0, **kwargs):
    args = dict(dir=d, final=False, carry_forward=False, astra_pending=False, late=False, reuse_round=None,
                src=[], round=None, artifact=None, adjudication=None, missing_reason=None)
    args.update(kwargs)
    output, status = io.StringIO(), 0
    with patch.object(M, "iso", return_value="2026-10-20T12:00"), redirect_stdout(output):
        try:
            M.cmd_score(SimpleNamespace(**args))
        except SystemExit as ex:
            status = ex.code
    check(f"S2 score exit {code}: {kwargs}", status == code, output.getvalue())
    return output.getvalue()


def s2_reports(rnd, left="a=9, b=9", right="a=9, b=9", claude="opus", d=S2, major=2):
    return [gate(d, rnd, left, reviewer=claude, name="claude.md"),
            gate(d, rnd, right, reviewer="astra", name="astra.md", verdict=f"VERDICT: PASS critical=0 major={major}")]


def s2_expected(rnd, reviewers, total="90.0", result="TARGET MET", dims='{"a": 9.0, "b": 9.0}', major="2", carried="{}"):
    return dict(round=str(rnd), date="2026-10-20T12:00", reviewers=reviewers, artifact=S2_SHA, total=total,
                critical="0", major=major, result=result, dims=dims, hours="0.00", rubric=S2_RUBRIC, carried=carried)


def s2_row(label, expected):
    actual = next(r for r in reversed(score_rows(S2)) if r["round"] == expected["round"])
    check("S2 golden " + label, actual == expected, (actual, expected))


s2_score(round=1, src=s2_reports(1))
s2_row("full baseline", s2_expected(1, "opus+astra"))
s2_score(round=2, src=s2_reports(2, "a=9, b=8.5")[:1], astra_pending=True)
s2_row("--astra-pending", s2_expected(2, "opus+astra-pending", "88.0", dims='{"a": 9.0, "b": 8.5}'))
check("S2 pending marker", M.read_state(S2)[0]["astra_pending"] == "round-2")
s2_score(round=2, src=s2_reports(2, "a=9, b=8.5", "a=8.5, b=8.5"), late=True)
s2_row("--late", s2_expected(2, "opus+astra+late", "85.0", dims='{"a": 8.5, "b": 8.5}'))
check("S2 late replaces row and clears marker", len(score_rows(S2)) == 2 and M.read_state(S2)[0]["astra_pending"] == "")
s2_score(round=3, src=s2_reports(3))
s2_score(round=4, src=s2_reports(4, "a=8.5"), carry_forward=True)
s2_row("--carry-forward", s2_expected(4, "opus+astra", "87.0", dims='{"b": 9.0, "a": 8.5}',
       carried='{"round": "3", "reviewers": {"opus": {"b": 9.0}}}'))
s2_score(final=True, reuse_round=1)
s2_row("--reuse-round", s2_expected("final", "opus+astra+reuse-round:1", result="FINAL PASS"))
second = gate(S2, 6, "a=9.5, b=9.5", reviewer="opus-second", name="second.md", verdict="VERDICT: PASS critical=0 major=3")
s2_score(final=True, src=[s2_reports(6)[0], second], missing_reason="Astra unavailable: fixture failure")
s2_row("--missing-reason", s2_expected("final", "opus+opus-second+missing:gpt", result="FINAL PASS", major="3"))
disputed = s2_reports(5, "a=6, b=9")
before = (S2 / "audits/scores.csv").read_bytes()
s2_score(round=5, src=disputed, code=3)
check("S2 dispute leaves rows intact", (S2 / "audits/scores.csv").read_bytes() == before)
ruling = S2 / "audits/ruling.md"
ruling.write_text("KEY a = 8.5 because tests/fixture.py reproduces the accepted result.\n", encoding="utf-8")
s2_score(round=5, src=disputed, adjudication=str(ruling))
s2_row("--adjudication", s2_expected(5, "opus+astra+lead-ruling", "87.0", dims='{"a": 8.5, "b": 9.0}'))


# S2 profiles: reads do not migrate files; every state writer pins missing legacy keys once.
check("S2 profiles retain classic, claude, codex only", set(M.PROFILES) == {"classic", "claude", "codex"})
legacy_keys = dict(profile="classic", lead_style="hands-on", rotate_at="0", workers="opus", worker_fallback="sonnet",
                   gate="opus", astra_wait="0", summary_words="300")
for explicit in ({}, {"workers": "sonnet", "worker_fallback": "", "gate": "opus+astra", "summary_words": "500"}):
    legacy = REPOS / ("s2-legacy-override" if explicit else "s2-legacy")
    legacy.mkdir()
    original = "---\nstatus: intake\n" + "".join(f"{k}: {v}\n" for k, v in explicit.items()) + "---\n## Decisions\n"
    (legacy / "STATE.md").write_text(original, encoding="utf-8")
    fm, body = M.read_state(legacy)
    effective = {k: M.run_value(fm, k) for k in legacy_keys}
    check("S2 legacy read is unchanged", (legacy / "STATE.md").read_text(encoding="utf-8") == original)
    output = io.StringIO()
    with redirect_stdout(output):
        M.write_state(legacy, fm, body)
    saved, body = M.read_state(legacy)
    notice = "legacy run pinned to classic (no behaviour change)"
    check("S2 legacy explicit keys win and behaviour stays", all(saved[k] == v for k, v in (legacy_keys | explicit).items()) and
          effective == {k: M.run_value(saved, k) for k in legacy_keys}, saved)
    check("S2 legacy emits one notice and one Decisions entry", output.getvalue().splitlines() == [notice] and
          body.count(notice) == 1 and notice in "\n".join(M.section_lines(body, "Decisions")), (output.getvalue(), body))
    before = (legacy / "STATE.md").read_bytes()
    output = io.StringIO()
    with redirect_stdout(output):
        M.write_state(legacy, saved, body)
    check("S2 legacy pin is idempotent", not output.getvalue() and (legacy / "STATE.md").read_bytes() == before)
    out = m("config", legacy, "--profiles")
    check("S2 classic is offered for existing classic run", all(x in out for x in ("classic", "claude", "codex")) and "codex-lead" not in out, out)
legacy = REPOS / "s2-legacy-command"
legacy.mkdir()
(legacy / "STATE.md").write_text("---\nstatus: intake\n---\n", encoding="utf-8")
out = m("note", legacy, "decision", "fixture mutation")
check("S2 ordinary writer pins legacy", out.count("legacy run pinned to classic") == 1 and M.read_state(legacy)[0]["profile"] == "classic", out)
(legacy / "STATE.md").write_text("---\nprofile: codex-lead\n---\n", encoding="utf-8")
output = io.StringIO()
with redirect_stderr(output):
    fm, body = M.read_state(legacy)
check("S2 codex-lead reads as codex with one notice", fm["profile"] == "codex" and len(output.getvalue().splitlines()) == 1 and
      "codex-lead is now codex" in output.getvalue() and "profile: codex-lead" in (legacy / "STATE.md").read_text(encoding="utf-8"), output.getvalue())
check("S2 alias uses codex defaults even for raw mappings", M.worker_chain({"profile": "codex-lead"}) == ["sol61", "astra", "sonnet"] and
      M.run_value({"profile": "codex-lead"}, "profile") == "codex")
out = m("set", legacy, "profile=codex-lead")
check("S2 old profile spelling remains an alias", M.read_state(legacy)[0]["profile"] == "codex", out)
with patch.dict(os.environ, {"CODEX_THREAD_ID": "fixture"}):
    check("S2 Codex host requests Codex lead without a fourth mode", "requested GPT-6-Astra high (Codex)" in "\n".join(M.run_config({"profile": "codex"})))

# S2 Sonnet substitutes for the Claude slot, including full/focused and final/fallback rules.
check("S2 gate choices", M.GATES == ("opus+astra", "opus", "sonnet+astra"))
out = m("set", S2, "gate=sonnet+astra")
check("S2 set accepts and describes Sonnet gate", "Sonnet 5.5" in out and M.read_state(S2)[0]["gate"] == "sonnet+astra", out)
for setting in ("opus", "opus+astra", "sonnet+astra"):
    for final in (False, True):
        problems = M.gate_reviewers({"gate": setting}, ["sonnet-5.5", "astra-high"], final, False, "")[1]
        check(f"S2 Sonnet labels only under own gate {setting}/{final}", bool(problems) == (setting != "sonnet+astra"), problems)
        problems = M.gate_reviewers({"gate": setting}, ["opus-5.5", "astra-high"], final, False, "")[1]
        check(f"S2 required Claude model {setting}/{final}", bool(problems) == (setting == "sonnet+astra"), problems)
    if setting != "sonnet+astra":
        check("S8 legacy missing reason accepts supplemental Sonnet label", not M.gate_reviewers({"gate": setting}, ["sonnet", "astra"],
              False, False, "fixture technical failure")[1])
for labels, bad in ((["sonnet", "sonnet-second"], False), (["sonnet", "sonnet"], True), (["opus", "opus-second"], True),
                    (["sonnet", "opus-second"], True), (["astra", "astra-second"], True)):
    problems = M.gate_reviewers({"gate": "sonnet+astra"}, labels, True, False, "Astra unavailable: fixture failure")[1]
    check(f"S2 final fallback needs two distinct Sonnet reviewers {labels}", bool(problems) == bad, problems)
sonnet = s2_reports(7, claude="sonnet-5.5")
s2_score(round=7, src=sonnet[:1], astra_pending=True)
s2_row("Sonnet pending", s2_expected(7, "sonnet-5.5+astra-pending"))
s2_score(round=7, src=sonnet, late=True)
s2_row("Sonnet late", s2_expected(7, "sonnet-5.5+astra+late"))
s2_score(final=True, reuse_round=7)
s2_row("Sonnet reuse", s2_expected("final", "sonnet-5.5+astra+late+reuse-round:7", result="FINAL PASS"))
s2_score(round=8, src=s2_reports(8, "a=8.5", claude="sonnet-5.5"), carry_forward=True)
s2_row("Sonnet focused", s2_expected(8, "sonnet-5.5+astra", "87.0", dims='{"b": 9.0, "a": 8.5}',
       carried='{"round": "7", "reviewers": {"sonnet-5.5": {"b": 9.0}}}'))
out = s2_score(round=9, src=s2_reports(9, "a=9", claude="sonnet-5.5"), carry_forward=True, code=2)
check("S2 third Sonnet round requires full review", "Sonnet must score every key every third regular round" in out, out)
sonnet = s2_reports(10, claude="sonnet-5.5")
s2_score(final=True, src=sonnet)
s2_row("Sonnet final dual", s2_expected("final", "sonnet-5.5+astra", result="FINAL PASS"))
second = gate(S2, 10, "a=9, b=9", reviewer="sonnet-second", name="second.md")
s2_score(final=True, src=[sonnet[0], second], missing_reason="Astra unavailable: fixture failure")
s2_row("Sonnet final fallback", s2_expected("final", "sonnet-5.5+sonnet-second+missing:gpt", result="FINAL PASS"))
# Prefix labels accepted by gate_reviewers must also participate in dispute checks.
out = s2_score(round=11, src=s2_reports(11, "a=6, b=9", claude="sonnet55"), code=3)
check("S2 Sonnet prefix disputes block", "Sonnet and GPT disagree" in out and "key a:" in out, out)
s2_score(round=11, src=s2_reports(11, "a=6, b=9", claude="sonnet55"), adjudication=str(ruling))
s2_row("Sonnet adjudication", s2_expected(11, "sonnet55+astra+lead-ruling", "87.0", dims='{"a": 8.5, "b": 9.0}'))
# Preserve CSV dimension order when reusing full rounds with a different report key order.
s2_score(round=12, src=s2_reports(12, "b=9, a=9", "b=9, a=9", claude="sonnet"))
s2_score(final=True, reuse_round=12)
s2_row("reuse dimension order", s2_expected("final", "sonnet+astra+reuse-round:12", result="FINAL PASS", dims='{"b": 9.0, "a": 9.0}'))


# Preserve even historical non-round CSV entries; read_scores intentionally filters them for status.
blank = dict.fromkeys(M.CSV_FIELDS, ""); blank["reviewers"] = "historical note\r\nsecond line"
with (S2 / "audits/scores.csv").open("a", encoding="utf-8", newline="") as f:
    csv.DictWriter(f, fieldnames=M.CSV_FIELDS).writerow(blank)
s2_score(round=13, src=s2_reports(13, claude="sonnet"))
check("S2 scoring preserves non-round rows and embedded newlines", blank in score_rows(S2))
output = io.StringIO()
with redirect_stdout(output):
    M.cmd_config(SimpleNamespace(dir=None, profiles=True))
check("S2 new-run listing without a run offers two modes", [x.split()[0] for x in output.getvalue().splitlines()] == ["claude", "codex"], output.getvalue())

# S3: STATE archive, ask panel/deadlines, and machine-wide browser lease.
S3 = REPOS / "s3"
m("init", S3, "--type", "site", "--title", "S3")
fm, _ = M.read_state(S3)
fm["custom_future_key"] = "keep me: v2"
stamp = M.iso()
entries = {name: [f"- {stamp} {name} {i}\n  continuation {i}\n\n" for i in range(12)] for name in ("Decisions", "Log")}
body = "# State\n\n## Now\n- working\n\n" + "".join(f"## {name}\n" + "".join(rows) for name, rows in entries.items()) + "## Parked for the user\n"
M.write_state(S3, fm, body)
kept = M.read_state(S3)
archived = (S3 / "DECISIONS.md").read_text(encoding="utf-8")
check("S3 cap: all frontmatter keys and unrelated sections survive", kept[0] == fm and "## Now\n- working" in kept[1])
for name, rows in entries.items():
    check(f"S3 cap: latest five {name}, verbatim older multiline entries in order",
          "".join(rows[:7]) in archived and "".join(rows[7:]) in kept[1] and rows[0] not in kept[1])
check("S3 cap: exactly one archive pointer", kept[1].count("Older decisions and log: DECISIONS.md") == 1)
before = [(S3 / n).read_bytes() for n in ("STATE.md", "DECISIONS.md")]
M.write_state(S3, *kept)
check("S3 cap: repeat write is byte-idempotent", before == [(S3 / n).read_bytes() for n in ("STATE.md", "DECISIONS.md")])
out = m("report", S3, "--no-live", "--since", stamp[:10])
check("S3 report: counts both archived and current decisions/log", "decisions since: 12" in out and "log since: 12" in out, out)
m("note", S3, "decision", "next decision")
check("S3 cap: subsequent archive appends without losing history", all(l in (S3 / "DECISIONS.md").read_text(encoding="utf-8") for l in archived.splitlines())
      and len([l for l in M.history_lines(S3, M.read_state(S3)[1], "Decisions") if l.startswith("- ")]) == 13)
# Exercise the raw-frontmatter checkpoint path, which must also cap STATE.
(S3 / "STATE.md").write_text("---\n" + "\n".join(f"{k}: {v}" for k, v in fm.items()) + "\n---\n" + body, encoding="utf-8")
m("handoff", S3, "--save-only", "--why", "S3 checkpoint")
check("S3 cap: checkpoint path caps entries and preserves custom key", len([l for l in M.section_lines(M.read_state(S3)[1], "Decisions") if l.startswith("- ")]) == 5
      and M.read_state(S3)[0]["custom_future_key"] == "keep me: v2")

# A crash between the two replacements is replayed once before the next read.
crash = REPOS / "s3-crash"; crash.mkdir()
M.write_state(crash, fm, "## Decisions\n")
real_atomic = M.atomic_write
def s3_fail_state(path, text):
    if path.name == "STATE.md":
        raise OSError("simulated crash")
    real_atomic(path, text)
try:
    with patch.object(M, "atomic_write", side_effect=s3_fail_state):
        M.write_state(crash, fm, body)
except OSError:
    pass
recovered = M.read_state(crash)
check("S3 cap: interrupted transaction recovers without loss/duplicates", recovered[0] == fm and
      M.history_lines(crash, recovered[1], "Decisions") == M.section_lines(body, "Decisions") and not (crash / ".tmp/state-write.json").exists())
procs = [subprocess.Popen([sys.executable, "-B", str(HERE / "marathon.py"), "note", str(crash), "decision", f"concurrent-{i}"],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=ENV, stdin=subprocess.DEVNULL) for i in range(8)]
for proc in procs:
    proc.communicate(timeout=20)
all_decisions = "\n".join(M.history_lines(crash, M.read_state(crash)[1], "Decisions"))
check("S3 cap: concurrent notes serialize with no lost updates", all(p.returncode == 0 for p in procs)
      and all(all_decisions.count(f"concurrent-{i}") == 1 for i in range(8)))

# Real STATE is read only, copied into the isolated fixture before using the writer.
real_state = Path(os.environ.get("MARATHON_TEST_STATE_FIXTURE", str(TMP / "unavailable-frozen-state")))
if real_state.exists():
    real = REPOS / "s3-real-copy"
    real.mkdir()
    original = real_state.read_bytes()
    (real / "STATE.md").write_bytes(original)
    raw = (real / "STATE.md").read_text(encoding="utf-8-sig")
    original_fm, original_body = M.read_state(real)
    M.write_state(real, original_fm, original_body)
    compact = (real / "STATE.md").read_text(encoding="utf-8")
    check("S3 real copy: frontmatter preserved; source untouched", M.read_state(real)[0] == original_fm and real_state.read_bytes() == original)
    for name in ("Decisions", "Log"):
        check(f"S3 real copy: every {name} line retained", M.history_lines(real, M.read_state(real)[1], name) == M.section_lines(original_body, name))
    print(f"S3 REAL STATE: {len(raw)} chars/{len(raw.splitlines())} lines -> {len(compact)} chars/{len(compact.splitlines())} lines")
    print("S3 REAL sections: " + ", ".join(f"{name}={sum(len(x)+1 for x in M.section_lines(M.read_state(real)[1], name))} chars" for name in ("Now", "Next 3 steps", "Decisions", "Log", "Parked for the user", "Handoff")))
else:
    print("S3 REAL STATE: not checked (source unavailable on this machine)")

qfile = S3 / "questions.json"
questions = [{"id": "q1", "text": "Build pace?", "options": ["Steady", "Fast"], "default": "Steady"},
             {"id": "q2", "text": "Publish now?", "options": ["Yes", "Later"], "default": "Later", "must_decide": True}]
def s3_questions(qs=questions):
    qfile.write_text(json.dumps(qs, ensure_ascii=False), encoding="utf-8")
def s3_expire():
    sfm, sb = M.read_state(S3)
    data = json.loads(sfm["asking"])
    data["deadline"] = (M.now() - dt.timedelta(seconds=1)).isoformat()
    sfm["asking"] = json.dumps(data, ensure_ascii=False)
    M.write_state(S3, sfm, sb)
s3_questions()
out = m("ask", S3, "--file", qfile)
data = json.loads(M.read_state(S3)[0]["asking"])
widget = out.split("\n\nPlain-text fallback:")[0]
(S3 / "ask-widget.html").write_text(widget, encoding="utf-8")
check("S3 ask: widget <=6 KB, self-contained, escaped and callback present", len(widget.encode("utf-8")) <= 6144 and "sendPrompt(" in widget and "ASK " + data["id"] in widget
      and "<script src=" not in widget and '<meta charset="utf-8">' in widget)
check("S3 ask: defaults only for non-must-decide, confirm starts disabled", 'name="q1" value="A" checked' in widget and 'name="q2" value="B" checked' not in widget
      and '<button disabled>Confirm' in widget)
check("S3 ask: default wait 10, fallback and defaults recorded", 598 <= (dt.datetime.fromisoformat(data["deadline"]) - M.now()).total_seconds() <= 600
      and data["defaults"] == {"q1": "A", "q2": "B"} and "reply 同意 / agree / ok" in out)
check("S3 ask: open status", "OPEN " + data["id"] in m("ask", S3, "--status"))
check("S3 ask: refuses to replace open questions", "already open" in m("ask", S3, "--file", qfile, code=1))
check("S3 ask: no premature defaults", "WAIT" in m("ask", S3, "--resolve") and M.read_state(S3)[0]["asking"])
for answer in ("同意", "agree", "ok"):
    check(f"S3 ask: {answer} never decides must-decide", "WAIT" in m("ask", S3, "--resolve", "--answers", answer) and M.read_state(S3)[0]["asking"])
check("S3 ask: invalid choice rejected", "invalid" in m("ask", S3, "--resolve", "--answers", "q2=Z", code=1))
check("S3 ask: wrong set rejected", "wrong question set" in m("ask", S3, "--resolve", "--answers", "ASK wrong: q2=A", code=1))
out = m("ask", S3, "--resolve", "--answers", "2B")
check("S3 ask: shorthand resolves, clears and logs", "q2=B (Later; answer)" in out and not M.read_state(S3)[0]["asking"] and "ASK " + data["id"] in M.read_state(S3)[1])
check("S3 ask: closed status and idempotent resolve", "CLOSED" in m("ask", S3, "--status") and "CLOSED" in m("ask", S3, "--resolve"))
m("ask", S3, "--file", qfile)
s3_expire()
out = m("ask", S3, "--resolve")
check("S3 ask: timeout defaults non-must and parks must-decide", "q1=A (Steady; default)" in out and "q2=parked" in out
      and "Publish now? (must decide)" in "\n".join(M.section_lines(M.read_state(S3)[1], "Parked for the user")))
m("set", S3, "ask_wait=0")
out = m("ask", S3, "--file", qfile)
check("S3 ask: ask_wait=0 applies defaults immediately", "q2=parked" in out and not M.read_state(S3)[0]["asking"])
m("set", S3, "ask_wait=-1", code=1)
m("ask", S3, "--file", qfile, "--wait", "-1", code=1)
m("ask", S3, "--file", qfile, "--wait", "nan", code=1)
m("ask", S3, "--file", qfile, "--wait", "1")
data = json.loads(M.read_state(S3)[0]["asking"])
out = m("ask", S3, "--resolve", "--answers", f"ASK {data['id']}: q1=B q2=A")
check("S3 ask: widget payload accepted", "q1=B (Fast; answer)" in out and "q2=A (Yes; answer)" in out)
for bad in ([], questions * 3, [questions[0], questions[0]], [{**questions[0], "default": "missing"}],
            [{**questions[0], "options": []}], [{**questions[0], "must_decide": "false"}], [{**questions[0], "id": "q'1"}],
            [{**questions[0], "text": "x" * 7000}]):
    s3_questions(bad)
    check("S3 ask: validates schema/size before writing", "questions:" in m("ask", S3, "--file", qfile, code=1) and not M.read_state(S3)[0]["asking"])
qfile.write_text("{bad json", encoding="utf-8")
check("S3 ask: invalid JSON rejected", "questions:" in m("ask", S3, "--file", qfile, code=1))
m("set", S3, "ask_wait=10")
s3_questions([{**questions[0], "text": '</script><img src=x onerror="bad()">'}])
out = m("ask", S3, "--file", qfile)
check("S3 ask: HTML question text escaped", "&lt;/script&gt;&lt;img" in out.split("Plain-text fallback:")[0])
m("ask", S3, "--resolve", "--answers", "ok")

lockfile = TMP / "home" / "marathon" / "browser.lock"
check("S3 lock: acquire in isolated home", "ACQUIRED" in m("lock", S3, "browser", "--owner", "alpha") and lockfile.exists())
lease = json.loads(lockfile.read_text(encoding="utf-8"))
check("S3 lock: owner/run/time/default ttl recorded", lease["owner"] == "alpha" and lease["dir"] == str(S3.resolve()) and lease["ttl"] == 30 and lease["time"] > 0)
check("S3 lock: cross-project contention exit 2 with owner and age", "alpha" in m("lock", P, "browser", "--owner", "beta", code=2))
check("S3 lock: status held by other exits 2", "age " in m("lock", P, "browser", "--owner", "beta", "--status", code=2))
check("S3 lock: wrong owner cannot release", "HELD" in m("lock", P, "browser", "--owner", "beta", "--release", code=2) and lockfile.exists())
check("S3 lock: same owner renews", "ACQUIRED" in m("lock", S3, "browser", "--owner", "alpha", "--ttl", "2") and json.loads(lockfile.read_text(encoding="utf-8"))["ttl"] == 2)
check("S3 lock: same owner status/release", "HELD" in m("lock", S3, "browser", "--owner", "alpha", "--status")
      and "RELEASED" in m("lock", S3, "browser", "--owner", "alpha", "--release") and not lockfile.exists())
check("S3 lock: free status", "FREE" in m("lock", S3, "browser", "--owner", "alpha", "--status"))
m("lock", S3, "browser", "--owner", "alpha")
check("S3 lock: force release by other owner", "RELEASED" in m("lock", P, "browser", "--owner", "beta", "--release", "--force") and not lockfile.exists())
m("lock", S3, "browser", "--owner", "alpha", "--ttl", "1")
lease = json.loads(lockfile.read_text(encoding="utf-8")); lease["time"] -= 61
lockfile.write_text(json.dumps(lease), encoding="utf-8")
check("S3 lock: stale holder recovered using recorded ttl", "ACQUIRED" in m("lock", P, "browser", "--owner", "beta") and json.loads(lockfile.read_text(encoding="utf-8"))["owner"] == "beta")
m("lock", P, "browser", "--owner", "beta", "--release")
for ttl in ("0", "-1", "nan", "inf"):
    check("S3 lock: invalid ttl rejected", "positive finite" in m("lock", S3, "browser", "--owner", "alpha", "--ttl", ttl, code=1))
# Concurrent contenders must have exactly one winner, independent of run directory.
procs = [subprocess.Popen([sys.executable, "-B", str(HERE / "marathon.py"), "lock", str(d), "browser", "--owner", f"racer{i}"],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=ENV, stdin=subprocess.DEVNULL) for i, d in enumerate((S3, P, Q, R))]
for proc in procs:
    proc.communicate(timeout=15)
check("S3 lock: atomic concurrent acquisition", sorted(p.returncode for p in procs) == [0, 2, 2, 2])
m("lock", S3, "browser", "--owner", "cleanup", "--release", "--force")
lockfile.write_text("{incomplete", encoding="utf-8")
check("S3 lock: fresh incomplete lease stays held", "<incomplete>" in m("lock", S3, "browser", "--owner", "alpha", code=2))
stale_lease_time = __import__("time").time() - 2 * 3600
os.utime(lockfile, (stale_lease_time, stale_lease_time))
check("S3 lock: stale incomplete lease recovers", "ACQUIRED" in m("lock", S3, "browser", "--owner", "alpha"))
m("lock", S3, "browser", "--owner", "alpha", "--release")
check("S3 lock: force cannot bypass acquisition", "--force needs" in m("lock", S3, "browser", "--owner", "alpha", "--force", code=1))
check("S3 ask: modifiers cannot silently be ignored", "--answers needs" in m("ask", S3, "--status", "--answers", "ok", code=1)
      and "--wait needs" in m("ask", S3, "--resolve", "--wait", "0", code=1))
print(f"S3 fixtures: {S3}")

# S7: shared reporting must retain the different charter-failure contracts.
with patch.object(M, "charter_rules", side_effect=OSError("unreadable charter")):
    try:
        M.visual_block(Q, {}, [])
    except OSError:
        strict_visual = True
    else:
        strict_visual = False
    check("S7: visual summary retains charter I/O errors", strict_visual)
    check("S7: overview tolerates charter I/O errors", M.project_summary(Q)["pass"] is None)
with patch.object(M, "charter_rules", side_effect=SystemExit("invalid charter")):
    check("S7: visual summary tolerates invalid charter", M.visual_block(Q, {}, []) == ["Progress  " + M.bar(0) + "  0%"])
    check("S7: overview tolerates invalid charter", M.project_summary(Q)["pass"] is None)
for argv, message in ((["report"], "status --report requires dir"),
                      (["gate-wait", str(Q)], "--gate requires --round"),
                      (["handoff", str(Q)], "handoff requires --why or --abort"),
                      (["config"], "config requires dir or --models"),
                      (["logins"], "logins requires urls"),
                      (["set", str(Q)], "set requires key=value pairs or --status with --reason"),
                      (["set", str(Q), "--status", "running"], "--status requires --reason and no key=value pairs")):
    check("S7: exact CLI validation " + argv[0], m(*argv, code=2).rstrip().endswith("error: " + message))

# S8: review regressions, all isolated and offline.
check("S8 directory-free profiles CLI", "codex" in m("config", "--profiles"))
for setting in ("opus", "opus+astra"):
    for final in (False, True):
        check(f"S8 supplemental Sonnet retains pre-slim validity {setting}/{final}", not M.gate_reviewers(
              {"gate": setting}, ["opus", "sonnet", "astra"], final, False, "")[1])
legacy_json = REPOS / "legacy-json"; legacy_json.mkdir()
(legacy_json / "STATE.md").write_text("---\nprofile: codex-lead\nstatus: running\n---\n", encoding="utf-8")
for command in ("status", "overview"):
    proc = subprocess.run([sys.executable, str(HERE / "marathon.py"), command, "--json"], env=ENV, capture_output=True, stdin=subprocess.DEVNULL)
    check("S8 legacy profile leaves JSON stdout parseable " + command, proc.returncode == 0
          and isinstance(json.loads(proc.stdout), list) and b"codex-lead" in proc.stderr)

m("lock", S3, "browser", "--owner", "W1")
for flag in ([], ["--release"]):
    check("S8 browser same ID other project cannot renew/release", "HELD" in m("lock", P, "browser", "--owner", "W1", *flag, code=2))
check("S8 canonical same-project spelling renews", "ACQUIRED" in m("lock", S3 / ".." / S3.name, "browser", "--owner", "W1"))
m("lock", S3, "browser", "--owner", "W1", "--release")

ordinary = [{"id": "pace", "text": "Pace?", "options": ["Steady", "Fast"], "default": "Steady"},
            {"id": "scope", "text": "Scope?", "options": ["Small", "Large"], "default": "Small"}]
s3_questions(ordinary)
m("ask", S3, "--file", qfile)
first_id = json.loads(M.read_state(S3)[0]["asking"])["id"]
out = m("ask", S3, "--resolve", "--answers", "1B")
check("S8 ordinary partial waits and lists unanswered", "WAIT" in out and "unanswered: scope" in out
      and json.loads(M.read_state(S3)[0]["asking"])["answers"] == {"pace": "B"})
out = m("ask", S3, "--resolve", "--answers", "q2=B")
check("S8 second ordinary answer completes", "pace=B (Fast; answer)" in out and "scope=B (Large; answer)" in out and not M.read_state(S3)[0]["asking"])
out = m("ask", S3, "--resolve", "--answers", "1A")
check("S8 late reply retained, not applied", "late answer 1A (not applied; lead decides)" in out and "late answer 1A" in M.read_state(S3)[1])
m("ask", S3, "--file", qfile)
replacement = M.read_state(S3)[0]["asking"]
out = m("ask", S3, "--resolve", "--answers", f"ASK {first_id}: 1B")
check("S8 old widget answer is logged without changing replacement set", "late answer" in out
      and replacement == M.read_state(S3)[0]["asking"])
m("ask", S3, "--resolve", "--answers", "ok")
for reply in ("q2=B", "2B", "2 B", "２Ｂ", "同意 2A", "agree 2B", "ok,2B"):
    data = {"id": "fixture", "questions": ordinary, "defaults": {"pace": "A", "scope": "A"}}
    parsed = M.ask_answers(data, reply)
    check("S8 fallback/voice form " + reply, parsed["scope"] == ("A" if reply == "同意 2A" else "B")
          and (not reply.startswith(("同意", "agree", "ok")) or parsed["pace"] == "A"))
m("ask", S3, "--file", qfile)
m("ask", S3, "--resolve", "--answers", "1B")
s3_expire(); out = m("ask", S3, "--resolve")
check("S8 deadline defaults only unanswered ordinary choices", "pace=B (Fast; answer)" in out and "scope=A (Small; default)" in out)
for reply in ("同意", "agree", "ok"):
    m("ask", S3, "--file", qfile)
    out = m("ask", S3, "--resolve", "--answers", reply)
    check("S8 explicit ordinary default acceptance " + reply, out.count("; answer)") == 2 and not M.read_state(S3)[0]["asking"])
s3_questions([{**ordinary[0], "text": "Voice\u2028line\u0085separator"}])
m("ask", S3, "--file", qfile)
check("S8 Unicode line separators do not break STATE", json.loads(M.read_state(S3)[0]["asking"])["questions"][0]["text"] == "Voice\u2028line\u0085separator")
m("ask", S3, "--resolve", "--answers", "ok")
for qs in ([{**ordinary[0], "text": "x" * 161}], [{**ordinary[0], "options": list("ABCDEFGHI"), "default": "A"}]):
    s3_questions(qs)
    check("S8 question bounds checked before writing", "questions:" in m("ask", S3, "--file", qfile, code=1) and not M.read_state(S3)[0]["asking"])
s3_questions(ordinary)
out = m("ask", S3, "--file", qfile, "--wait", "0")
check("S8 zero wait prints outcome without dead widget", "default)" in out and "<script>" not in out)

# Timer sleeps outside both locks; the subprocess can accept a reply during its poll interval.
m("ask", S3, "--file", qfile, "--wait", "0.01")
started = __import__("time").monotonic()
out = m("ask", S3, "--resolve", "--at-deadline")
check("S8 timer expires and resolves", "default)" in out and not M.read_state(S3)[0]["asking"]
      and __import__("time").monotonic() - started >= 0.1)
m("ask", S3, "--file", qfile)
timer = subprocess.Popen([sys.executable, str(HERE / "marathon.py"), "ask", str(S3), "--resolve", "--at-deadline"],
                         env=ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
check("S8 timer initially waits", b"WAIT" in timer.stdout.readline())
reply = m("ask", S3, "--resolve", "--answers", "ok")
m("ask", S3, "--file", qfile)
replacement = M.read_state(S3)[0]["asking"]
timer_out, timer_err = timer.communicate(timeout=20)
check("S8 timer reply/replacement wake does not resolve new set", timer.returncode == 0 and b"CLOSED" in timer_out
      and replacement == M.read_state(S3)[0]["asking"] and "answer)" in reply, timer_err)
m("ask", S3, "--resolve", "--answers", "ok")
# Mocked clock proves exact 15-second polling and both lock releases without a long sleep.
m("ask", S3, "--file", qfile)
args = SimpleNamespace(dir=str(S3), file=None, wait=None, answers=None, resolve=True, status=False, at_deadline=True)
sleeps = []
def polling(seconds):
    sleeps.append(seconds)
    with M.file_lock(S3 / ".tmp/state-command.lock", timeout=0), M.file_lock(S3 / ".tmp/ask.lock", timeout=0):
        sf, sb = M.read_state(S3); sf["asking"] = ""; M.write_state(S3, sf, sb)
with patch.object(M.time, "sleep", side_effect=polling):
    M.cmd_ask(args)
check("S8 timer polls each 15s outside locks", sleeps == [15])
check("S8 at-deadline requires resolve", "--at-deadline needs" in m("ask", S3, "--status", "--at-deadline", code=1))
for argv in (["wait", str(S3), "brief contention"], ["ask", str(S3), "--status"],
             ["handoff", str(S3), "--save-only", "--why", "contention"], ["status", str(S3), "--report", "--mark", "--no-live"]):
    with M.file_lock(S3 / ".tmp/state-command.lock"):
        contender = subprocess.Popen([sys.executable, str(HERE / "marathon.py"), *argv], env=ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
        __import__("time").sleep(0.25)
        alive = contender.poll() is None
    stdout, stderr = contender.communicate(timeout=15)
    check("S8 short state contention waits " + argv[0], alive and contender.returncode == 0, stderr)
m("wait", S3, "--clear")

# Archive ownership, one header per section, and crash recovery with a later manual edit.
archive = (S3 / "DECISIONS.md").read_text(encoding="utf-8")
check("S8 archive headers occur once", archive.count("# Older decisions and log") == 1
      and archive.count("## Decisions") == 1 and archive.count("## Log") <= 1)
foreign = REPOS / "foreign-archive"; foreign.mkdir()
(foreign / "DECISIONS.md").write_text("# Product decisions\nkeep this\n", encoding="utf-8")
original = (foreign / "DECISIONS.md").read_bytes()
try:
    M.write_state(foreign, {"profile": "codex"}, "## Decisions\n" + "- decision\n" * 6)
except SystemExit as exc:
    refused = "not marathon's" in str(exc)
else:
    refused = False
check("S8 foreign DECISIONS is never adopted or hidden from Git", refused and original == (foreign / "DECISIONS.md").read_bytes()
      and ":!DECISIONS.md" not in M.bookkeeping(foreign) and M.history_lines(foreign, "", "Decisions") == [])
manual = REPOS / "manual-after-crash"; manual.mkdir()
M.write_state(manual, {"profile": "codex"}, "## Decisions\n- original\n")
try:
    with patch.object(M, "atomic_write", side_effect=s3_fail_state):
        M.write_state(manual, {"profile": "codex"}, "## Decisions\n" + "- original\n" * 7)
except OSError:
    pass
(manual / "STATE.md").write_text("---\nprofile: codex\nnext: manual edit\n---\n## Decisions\n- latest\n", encoding="utf-8")
newer = (manual / "STATE.md").read_bytes()
check("S8 replay preserves manual STATE and parks stale journal", M.read_state(manual)[0]["next"] == "manual edit"
      and newer == (manual / "STATE.md").read_bytes() and (manual / ".tmp/state-write.stale").exists()
      and not (manual / ".tmp/state-write.json").exists())

# Documentation regressions are counted on the complete lead reading path.
root = HERE.parent
base = ["SKILL.md", "workers.md", "gate.md", "intake.md", "references/commands.md", "references/profiles.md",
        "references/adjudication.md", "references/rotation.md", "references/codex-workers.md"]
for card in ("mode-codex.md", "mode-claude.md"):
    text = (root / card).read_text(encoding="utf-8")
    size = sum(len((root / p).read_text(encoding="utf-8")) for p in [*base, card])
    codex_size = size + len((root / "references/codex.md").read_text(encoding="utf-8"))
    check("S8 mode card and lead budgets " + card, len(text) <= 1600 and size <= 25000 and codex_size <= 29000,
          f"card={len(text)}, Claude={size}, Codex={codex_size}")
    print(f"S8 budgets {card}: card={len(text)} Claude={size} Codex={codex_size}")
check("S8 ask scope excludes answer-only STATE writes", "Answer-only progress" in (root / "SKILL.md").read_text(encoding="utf-8"))
for name in ("intake.md", "gate.md", "references/codex.md"):
    check("S8 concrete timer docs " + name, "--resolve --at-deadline" in (root / name).read_text(encoding="utf-8"))
check("S8 configured Claude fallback wording", "two configured Claude reviewers" in m("score", "--help")
      and "two configured Claude reviewers" in (HERE / "codex_worker.py").read_text(encoding="utf-8"))

# S9: backend settings and explicit-only stdin.
check("S9 default backend order", M.run_value({}, "codex_backends") == "subscription")
for value in ("api,subscription", "api,订阅", "subscription"):
    out = m("set", S3, "codex_backends=" + value)
    check("S9 set normalises backend aliases " + value, "codex_backends" in out and "Codex backends:" in out)
for value in ("", "bogus", "subscription,subscription", "api,", ",api"):
    check("S9 invalid backend order " + value, "codex_backends:" in m("set", S3, "codex_backends=" + value, code=1))
check("S9 config --models displays backends", "codex_backends subscription" in m("config", S3, "--models"))
for default in ("missing", None):
    q = {"id": "permission", "text": "Proceed?", "options": ["Yes", "No"], "must_decide": True}
    if default is None: q["default"] = None
    s3_questions([q]); m("set", S3, "ask_wait=10")
    out = m("ask", S3, "--file", qfile)
    data = json.loads(M.read_state(S3)[0]["asking"])
    check("S9 must-decide accepts absent/null default " + str(default), data["defaults"] == {} and " checked" not in out)
    out = m("ask", S3, "--resolve", "--answers", "permission=B")
    check("S9 explicit must-decide reply without default", "permission=B (No; answer)" in out)
    q["must_decide"] = False; s3_questions([q])
    check("S9 ordinary questions still need default", "default must be in options" in m("ask", S3, "--file", qfile, code=1))
for args, expected in ((("log", S3), 1), (("config", S3), 0), (("status", S3), 0)):
    proc = subprocess.Popen([sys.executable, str(HERE / "marathon.py"), *map(str, args)],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=ENV)
    try:
        proc.wait(timeout=5)  # Keep stdin open throughout; communicate would close it.
        check("S9 CLI never implicitly reads open stdin " + args[0], proc.returncode == expected)
    finally:
        if proc.poll() is None: proc.kill()
        proc.communicate(timeout=5)

# Windows sharing violation: a reader holding the ledger open must delay, not break, a concurrent write
_tries = {"n": 0}
def _busy_then_ok():
    _tries["n"] += 1
    if _tries["n"] < 4:
        raise PermissionError(32, "being used by another process")
    return "done"
check("retry_sharing waits out a brief sharing violation", M.retry_sharing(_busy_then_ok) == "done" and _tries["n"] == 4, _tries)
def _always_busy():
    raise PermissionError(32, "being used by another process")
try:
    M.retry_sharing(_always_busy, tries=3); _gave_up = False
except PermissionError:
    _gave_up = True
check("retry_sharing gives up after its limit", _gave_up)
_race = Path(tempfile.mkdtemp(dir=TMP)) / "workers.csv"
M.atomic_write(_race, "a\n")
import threading
_held = open(_race, "rb")  # Python opens without FILE_SHARE_DELETE on Windows, so os.replace fails while held
threading.Timer(0.3, _held.close).start()
M.atomic_write(_race, "b\n")
check("atomic_write succeeds once the other reader closes the file", _race.read_text(encoding="utf-8") == "b\n" and not list(_race.parent.glob(".workers.csv.*.tmp")))

print(f"\n{len(FAILS)} failure(s)")
for f in FAILS:
    print("-", f[:500])
sys.exit(1 if FAILS else 0)
