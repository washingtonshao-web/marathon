"""Tests for codex_worker.py with a fake Codex (no real model calls). Run: python test_codex_worker.py"""
import csv
import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
SCRATCH = HERE.parents[2] / ".tmp"
SCRATCH.mkdir(exist_ok=True)
TMP = Path(tempfile.mkdtemp(prefix="codex-worker-test-", dir=SCRATCH))
FAILS = []
FAKE = TMP / "fake_codex.py"
FAKE.write_text(r'''
import csv, json, os, stat, subprocess, sys, time
from pathlib import Path
args = sys.argv[1:]
mode = os.environ.get("FAKE_MODE", "ok")
if mode == "timeout-stdin" and "gpt-6-astra" in args:
    time.sleep(90)
prompt = sys.stdin.read()
out = args[args.index("-o") + 1] if "-o" in args else None
model = args[args.index("-m") + 1] if "-m" in args else "?"
backend = "api" if any('env_key="MARATHON_API_KEY"' in a for a in args) else "subscription"
scratch = Path(os.environ["FAKE_SCRATCH"]) if os.environ.get("FAKE_SCRATCH") else None
scratch_before = scratch.exists() if scratch else False
if scratch:
    (scratch / "real").mkdir(parents=True, exist_ok=True)
    for name in ("test.db-wal", "test.db-shm"):
        file = scratch / "real" / name
        file.write_text("scratch", encoding="utf-8")
        if os.environ.get("FAKE_READONLY"):
            file.chmod(stat.S_IREAD)
log = os.environ.get("FAKE_LOG")
if log:
    ledger = Path("audits/workers.csv")
    rows = list(csv.DictReader(ledger.open(encoding="utf-8"))) if ledger.exists() else []
    open(log, "a", encoding="utf-8").write(json.dumps({"backend": backend, "args": args, "prompt": prompt, "rows": rows, "cwd": str(Path.cwd()), "scratch_before": scratch_before, "candidate": Path("candidate.txt").read_text(encoding="utf-8") if Path("candidate.txt").exists() else ""}) + "\n")
if mode == "api-error" and backend == "api":
    if os.environ.get("FAKE_USAGE"):
        print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}))
    print(json.dumps({"type": "error", "message": os.environ.get("FAKE_ERROR", "401 Unauthorized")}))
    sys.exit(1)
if mode == "hold":
    flag = Path(os.environ["FAKE_HOLD"])
    flag.with_suffix(".ready").touch()
    deadline = time.monotonic() + 15
    while not flag.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
if mode == "sibling-change":
    Path("sibling.txt").write_text("another worker changed this", encoding="utf-8")
    print(json.dumps({"type": "error", "message": "usage limit"}))
    sys.exit(1)
if mode == "capacity" and "resume" not in args:
    # mid-run capacity error after real work: no turn.completed, usage only in the session log
    print(json.dumps({"type": "thread.started", "thread_id": "thr-cap"}), flush=True)
    print(json.dumps({"type": "item.started", "item": {"type": "command_execution"}}), flush=True)
    log_dir = Path(os.environ["CODEX_HOME"]) / "sessions" / "2026" / "10" / "21"
    log_dir.mkdir(parents=True, exist_ok=True)
    total = {"input_tokens": 5000, "cached_input_tokens": 4000, "output_tokens": 70, "reasoning_output_tokens": 30}
    (log_dir / "rollout-2026-10-21T00-00-00-thr-cap.jsonl").write_text(
        json.dumps({"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": total}}}) + "\n", encoding="utf-8")
    print(json.dumps({"type": "turn.failed", "error": {"message": "Selected model is at capacity. Please try a different model."}}))
    sys.exit(1)
if mode == "capacity" and "resume" in args:
    log_file = Path(os.environ["CODEX_HOME"]) / "sessions" / "2026" / "10" / "21" / "rollout-2026-10-21T00-00-00-thr-cap.jsonl"
    total = {"input_tokens": 6000, "cached_input_tokens": 4800, "output_tokens": 100, "reasoning_output_tokens": 30}
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": total}}}) + "\n")
    print(json.dumps({"type": "thread.started", "thread_id": "thr-cap"}))
    print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1000, "cached_input_tokens": 800, "output_tokens": 30}}))
    open(out, "w", encoding="utf-8").write("DONE\nresumed and finished\n")
    sys.exit(0)
if mode == "limit" or (mode == "astra-limit" and model == "gpt-6-astra") or (mode == "sol-limit" and model == "gpt-6.1-sol"):
    print(json.dumps({"type": "error", "message": "You've hit your usage limit."}))
    sys.exit(1)
if mode in ("empty", "turn-only", "network"):
    if mode == "turn-only":
        print(json.dumps({"type": "turn.started"}))
    if mode == "network":
        print("network unavailable", file=sys.stderr)
    sys.exit(0)
if mode == "fail-done":
    Path(out).write_text("DONE\nthis attempt actually failed\n", encoding="utf-8")
    sys.exit(1)
if (mode.startswith("timeout") and mode != "timeout-stdin") or mode == "crash-tools":
    if mode in ("timeout-empty", "timeout-change") and model != "gpt-6-astra":
        pass
    else:
        if mode in ("timeout-tools", "crash-tools", "timeout-child"):
            print(json.dumps({"type": "thread.started", "thread_id": "thr-" + model}), flush=True)
            print(json.dumps({"type": "item.started", "item": {"type": "command_execution"}}), flush=True)
        if mode == "timeout-change":
            Path("changed-" + Path(out).stem + ".txt").write_text("partial work", encoding="utf-8")
        if mode == "timeout-child":
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(90)"], stdin=subprocess.DEVNULL)
            Path("child.pid").write_text(str(child.pid), encoding="utf-8")
        if mode == "timeout-done":
            Path(out).write_text("DONE\nnot completed\n", encoding="utf-8")
        if mode == "crash-tools":
            sys.exit(2)
        time.sleep(90)
if mode in ("recovered", "completed-no-status"):
    print("network connection retry recovered; took 503 ms", file=sys.stderr)
    print(json.dumps({"type": "error", "message": "transient connection reset; recovered"}))
print(json.dumps({"type": "thread.started", "thread_id": "thr-" + model}))
print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1000, "cached_input_tokens": 800, "output_tokens": 50}}))
if out:
    message = ("DONE\n" + "Complete evidence. " * 400 + "\nREVIEWER: gpt-6-astra-high\nARTIFACT: abcdef\n"
               "SCORES: quality=8\nVERDICT: FAIL critical=1 major=2\n") if mode == "gate" else (
               mode.upper() + "\nneeds more work\n" if mode in ("partial", "failed") else "DONE\nall items met\n")
    if mode == "completed-no-status":
        print(json.dumps({"type": "item.completed", "item": {"type": "command_execution"}}))
        message = "Review finished without the required status token.\n"
    if mode == "cleanup-only":
        message = "PARTIAL\nOnly cleanup remained: delete my scratch folder.\n"
    open(out, "w", encoding="utf-8").write(message)
''', encoding="utf-8")
CMD = TMP / "fake_codex.cmd"
CMD.write_text(f'@echo off\r\n"{sys.executable}" "{FAKE}" %*\r\n', encoding="utf-8")
if os.name != "nt":
    CMD = TMP / "fake_codex"
    CMD.write_text(f'#!{sys.executable}\nexec(compile(open({str(FAKE)!r}, encoding="utf-8").read(), {str(FAKE)!r}, "exec"))\n', encoding="utf-8")
    CMD.chmod(0o755)
CODEX_HOME = TMP / "codex-home"
CODEX_HOME.mkdir()
(CODEX_HOME / "config.toml").write_text('[mcp_servers.Example]\ncommand="unused"\n', encoding="utf-8")
ENV = dict(os.environ, CODEX_HOME=str(CODEX_HOME), CODEX_WORKER_EXE=str(CMD), MARATHON_CLAUDE_HOME=str(TMP / "home"), PYTHONIOENCODING="utf-8",
           MARATHON_REPOS_ROOT=str(TMP / "repos"), MARATHON_OVERVIEW_GLOBS=str(TMP / "repos" / "*"),
           FAKE_LOG=str(TMP / "calls.jsonl"))
ENV.pop("CLAUDE_CODE_SESSION_ID", None)


def run(script, *args, mode="ok", env=None):
    r = subprocess.run([sys.executable, str(HERE / script), *map(str, args)], capture_output=True, env=dict(ENV, FAKE_MODE=mode, **(env or {})), timeout=120, stdin=subprocess.DEVNULL)
    return (r.stdout + r.stderr).decode("utf-8", "replace")


def same_review(a, b):
    """Gate outputs equal the attempt summary except the REVIEWER line, which the parent sets to the model that ran."""
    strip = lambda x: [l for l in Path(x).read_text(encoding="utf-8").splitlines() if not l.strip().upper().startswith("REVIEWER:")]
    return strip(a) == strip(b)


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(f"{name}: {str(detail)[:600]}")


P = TMP / "proj"
run("marathon.py", "init", P, "--type", "site", "--title", "t", "--anywhere")
run("marathon.py", "set", P, "codex_backends=subscription")
subprocess.run(["git", "init", "-q", str(P)], check=True, capture_output=True, stdin=subprocess.DEVNULL)
(P / ".gitignore").write_text(".tmp/\naudits/\n", encoding="utf-8")
(P / "brief.md").write_text("Make hello.txt\n", encoding="utf-8")
(P / "candidate.txt").write_text("pinned candidate", encoding="utf-8")
subprocess.run(["git", "-C", str(P), "add", "."], check=True, capture_output=True, stdin=subprocess.DEVNULL)
subprocess.run(["git", "-C", str(P), "-c", "user.name=Test", "-c", "user.email=test\x40example.invalid",
                "-c", "core.hooksPath=" + str(TMP / "no-hooks"), "commit", "-qm", "candidate"], check=True, capture_output=True, stdin=subprocess.DEVNULL)
SHA = subprocess.check_output(["git", "-C", str(P), "rev-parse", "HEAD"], text=True, stdin=subprocess.DEVNULL, encoding="utf-8").strip()
SNAPSHOT = P / ".tmp/gate" / SHA[:7]
(P / "candidate.txt").write_text("live checkout changed", encoding="utf-8")

out = run("codex_worker.py", "run", P, "--id", "W1", "--brief", P / "brief.md", "--class", "build")
rows = (P / "audits" / "workers.csv").read_text(encoding="utf-8")
check("run: DONE line with model and tokens", out.startswith("W1 DONE sol61 (gpt-6.1-sol high)") and "summary" in out, out)
check("run: ledger row with usage and thread", "W1," in rows and ",codex,gpt-6.1-sol,high,build,done," in rows and "thr-gpt-6.1-sol" in rows
      and ",1000,800,50," in rows, rows)
call = json.loads((TMP / "calls.jsonl").read_text(encoding="utf-8").splitlines()[-1])
check("run: full access, json, high effort, prompt footer names the project folder",
      'sandbox_mode="danger-full-access"' in call["args"] and "--json" in call["args"] and "model_reasoning_effort=high" in call["args"]
      and "The project folder is" in call["prompt"] and ".tmp/reports/W1.full.md" in call["prompt"], call)

out = run("codex_worker.py", "run", P, "--id", "W2", "--brief", P / "brief.md", "--class", "test", mode="sol-limit")
check("fallback: Sol usage limit → Astra does the job", "W2 DONE astra (gpt-6-astra high)" in out and "after fallback from sol61" in out, out)

out = run("codex_worker.py", "run", P, "--id", "W3", "--brief", P / "brief.md", "--class", "build", mode="limit")
check("fallback: Codex chain exhausted → FALLBACK sonnet for the lead", out.startswith("W3 FALLBACK sonnet"), out)
rows = (P / "audits" / "workers.csv").read_text(encoding="utf-8")
check("fallback row is marked fallback", any(l.startswith("W3,") and ",fallback," in l for l in rows.splitlines()), rows)

run("marathon.py", "set", P, "workers=sol61", "worker_fallback=sonnet")
out = run("codex_worker.py", "run", P, "--id", "W4", "--brief", P / "brief.md", "--class", "build")
check("STATE workers=sol61 is the primary", "W4 DONE sol61" in out, out)

out = run("codex_worker.py", "run", P, "--id", "W5", "--brief", P / "brief.md", "--model", "astra-xhigh", "--class", "gate", "--read-only", "--sha", SHA)
call = json.loads((TMP / "calls.jsonl").read_text(encoding="utf-8").splitlines()[-1])
check("explicit model effort, full-access gate", "model_reasoning_effort=xhigh" in call["args"] and 'sandbox_mode="danger-full-access"' in call["args"], call)

out = run("codex_worker.py", "steer", P, "--id", "W1", "fix the typo")
call = json.loads((TMP / "calls.jsonl").read_text(encoding="utf-8").splitlines()[-1])
rows = (P / "audits" / "workers.csv").read_text(encoding="utf-8")
check("steer resumes the same thread and adds tokens", "resume" in call["args"] and "thr-gpt-6.1-sol" in call["args"]
      and any(l.startswith("W1,") and ",2000,1600,100," in l for l in rows.splitlines()), (call, rows))

def row(wid):
    with (P / "audits/workers.csv").open(encoding="utf-8", newline="") as f:
        found = next((r for r in csv.DictReader(f) if r["id"] == wid), None)
    if found is None:
        check("ledger row exists", False, wid)
    return defaultdict(str, found or {})


def calls():
    return [json.loads(line) for line in (TMP / "calls.jsonl").read_text(encoding="utf-8").splitlines()]


def worker(wid, *args, mode="ok", env=None):
    if "--class" not in args:
        args = (*args, "--class", "build")
    if "gate" in args and "--sha" not in args:
        args = (*args, "--sha", SHA)
    return run("codex_worker.py", "run", P, "--id", wid, "--brief", P / "brief.md", *args, mode=mode, env=env)


reports = P / ".tmp/reports"
check("attempt files survive run, steer and fallback", all((reports / f"{wid}.a{n}{ext}").exists()
      for wid, n in (("W1", 1), ("W1", 2), ("W2", 1), ("W2", 2)) for ext in (".md", ".events.jsonl", ".err.txt")))
check("failed attempt has no promoted summary", not (reports / "W3.md").exists())
check("successful attempt is promoted exactly", (reports / "W2.md").read_bytes() == (reports / "W2.a2.md").read_bytes())
check("attempt ends recorded; overall ended absent during fallback", "a1 sol61 ended" in row("W2")["note"]
      and "a2 astra ended" in row("W2")["note"] and row("W2")["ended"]
      and all(not r["ended"] for c in calls() if "W2.a2.md" in " ".join(c["args"]) for r in c["rows"] if r["id"] == "W2"))
old = (reports / "W1.md").read_bytes()
out = run("codex_worker.py", "steer", P, "--id", "W1", "fail before producing a summary", mode="limit")
check("stale DONE + failing steer is failed and finalized", "W1 FAILED" in out and row("W1")["status"] == "failed"
      and row("W1")["ended"] and (reports / "W1.md").read_bytes() == old, out)
check("failed steer gets its own empty summary", (reports / "W1.a3.md").read_bytes() == b"")
out = run("codex_worker.py", "steer", P, "--id", "W1", "exit nonzero after DONE", mode="fail-done")
check("exit nonzero cannot promote even a fresh DONE", "W1 FAILED" in out and (reports / "W1.md").read_bytes() == old
      and "actually failed" in (reports / "W1.a4.md").read_text(encoding="utf-8"), out)
worker("W1")
check("rerun also increments attempt files", (reports / "W1.a5.md").exists())

# S10: the gate keeps Astra even when the worker chain starts with Sol.
run("marathon.py", "set", P, "profile=codex")
before = len(calls())
worker("s10-gate-default", "--class", "gate", mode="limit")
check("S10 gate default stays Astra; no backward Sol fallback", len(calls()) == before + 1
      and "gpt-6-astra" in calls()[-1]["args"] and row("s10-gate-default")["model"] == "gpt-6-astra")
worker("s10-astra-override", "--model", "astra")
check("S10 explicit Astra worker remains available", row("s10-astra-override")["model"] == "gpt-6-astra")
run("marathon.py", "set", P, "workers=astra")
worker("s10-astra-state")
check("S10 STATE Astra worker is respected", row("s10-astra-state")["model"] == "gpt-6-astra")

run("marathon.py", "set", P, "workers=astra", "worker_fallback=sol61,sonnet", "summary_words=517")
for mode in ("timeout-tools", "crash-tools", "timeout-child"):
    before = len(calls())
    out = worker(mode, "--minutes", "0.1", mode=mode)
    r = row(mode)
    check(f"{mode}: partial work stops fallback and finalizes timeout", " TIMEOUT " in out and r["status"] == "timeout"
          and r["ended"] and "partial work in tree; steer to continue" in r["note"] and len(calls()) == before + 1, out)
child_pid = int((P / "child.pid").read_text(encoding="utf-8")) if (P / "child.pid").exists() else None
if child_pid is None:
    child_dead = False
elif os.name == "nt":
    processes = subprocess.run(["tasklist", "/FI", f"PID eq {child_pid}", "/FO", "CSV", "/NH"], capture_output=True, text=True, stdin=subprocess.DEVNULL, encoding="utf-8").stdout
    child_dead = f'"{child_pid}"' not in processes
else:
    try:
        os.kill(child_pid, 0)
        proc = Path(f"/proc/{child_pid}/stat")
        child_dead = proc.exists() and proc.read_text(encoding="utf-8").split()[2] == "Z"
    except ProcessLookupError:
        child_dead = True
check("timeout kills descendant process", child_dead, child_pid)

out = worker("empty-timeout", "--minutes", "0.1", mode="timeout-empty")
check("timeout with no events or changes falls back", "DONE sol61" in out and row("empty-timeout")["status"] == "done"
      and (reports / "empty-timeout.a1.err.txt").exists(), out)
for mode in ("empty", "network", "timeout-done"):
    out = worker(mode, "--minutes", "0.1", mode=mode)
    check(f"{mode}: infra fallback, no canonical DONE", f"{mode} FALLBACK sonnet" in out and not (reports / f"{mode}.md").exists(), out)
for mode in ("partial", "failed", "turn-only"):
    before = len(calls())
    out = worker(mode, mode=mode)
    check(f"{mode}: task result never falls back", row(mode)["status"] == ("failed" if mode == "turn-only" else mode)
          and len(calls()) == before + 1 and row(mode)["ended"], out)

out = worker("gate", "--class", "gate", "--out", "audits/round-3/astra.md", mode="gate")
call = calls()[-1]
review = P / "audits/round-3/astra.md"
check("gate reviews pinned candidate in detached worktree and prints its path", Path(call["cwd"]) == SNAPSHOT
      and call["candidate"] == "pinned candidate" and str(SNAPSHOT) in out
      and "Review this folder only" in call["prompt"] and "You may run tests and checks" in call["prompt"], out)
check("finalized gate removes snapshot and persists SHA/read-only", not SNAPSHOT.exists()
      and f"sha={SHA}" in row("gate")["note"] and "ro=1" in row("gate")["note"])
check("gate prints paths/status only, never the full review", len(out.splitlines()) == 2 and "Complete evidence" not in out, out)
check("--out copies complete gate review", review.exists() and same_review(review, reports / "gate.a1.md")
      and len(review.read_text(encoding="utf-8").split()) > 517 and review.read_text(encoding="utf-8").endswith("VERDICT: FAIL critical=1 major=2\n"), out)
check("gate footer confines writes to scratch, complete and uncapped", "write only under" in call["prompt"] and ".scratch" in call["prompt"]
      and "complete review" in call["prompt"] and "at most" not in call["prompt"] and ".full.md" not in call["prompt"]
      and all(k + ":" in call["prompt"] for k in ("REVIEWER", "ARTIFACT", "SCORES", "VERDICT"))
      and 'sandbox_mode="danger-full-access"' in call["args"], call)
old_review = review.read_bytes()
run("codex_worker.py", "steer", P, "--id", "gate", "failed review", "--out", "audits/round-3/astra.md", mode="fail-done")
check("failed gate steer preserves output and read-only class", review.read_bytes() == old_review
      and row("gate")["status"] == "failed" and 'sandbox_mode="danger-full-access"' in calls()[-1]["args"])
run("codex_worker.py", "steer", P, "--id", "gate", "complete review", "--out", "audits/round-4/astra.md", mode="gate")
check("gate steer copies full review to --out", same_review(P / "audits/round-4/astra.md", reports / "gate.a3.md"))
check("gate output carries the REVIEWER label of the model that ran", "REVIEWER: astra-high" in (P / "audits/round-4/astra.md").read_text(encoding="utf-8"))
check("gate steer recreates the same pinned snapshot", calls()[-1]["candidate"] == "pinned candidate"
      and Path(calls()[-1]["cwd"]) == SNAPSHOT and not SNAPSHOT.exists())
out = worker("readonly", "--class", "research", "--read-only", "--out", "audits/research.md", mode="gate")
call = calls()[-1]
check("read-only non-gate returns full report for parent delivery", 'sandbox_mode="read-only"' in call["args"]
      and "return the full report" in call["prompt"].lower() and "the parent saves it" in call["prompt"]
      and ".full.md" not in call["prompt"] and "at most" not in call["prompt"]
      and (P / "audits/research.md").read_bytes() == (reports / "readonly.a1.md").read_bytes()
      and "ro=1" in row("readonly")["note"], out)
run("codex_worker.py", "steer", P, "--id", "readonly", "expand report", "--out", "audits/research-2.md", mode="gate")
check("steer retains non-gate read-only flag and parent-saved report", 'sandbox_mode="read-only"' in calls()[-1]["args"]
      and "the parent saves it" in calls()[-1]["prompt"] and ".full.md" not in calls()[-1]["prompt"]
      and "ro=1" in row("readonly")["note"] and (P / "audits/research-2.md").exists())
for mode in ("timeout-change", "sibling-change"):
    before = len(calls())
    out = worker(mode, "--minutes", "0.1", mode=mode)
    check(f"{mode}: unrelated tree changes cannot stop fallback", "TIMEOUT" not in out and len(calls()) == before + 2
          and row(mode)["status"] == ("done" if mode == "timeout-change" else "fallback"), out)
for wid, setting, model, expected in (
        ("gate-default", "sol61,sonnet", "astra", ["gpt-6-astra", "gpt-6.1-sol"]),
        ("gate-sol", "sol61,sonnet", "sol61", ["gpt-6.1-sol"]),
        ("gate-outside", "sol61,sonnet", "luna", ["gpt-6-luna"]),
        ("gate-effort", "sol61,sonnet", "astra-xhigh", ["gpt-6-astra", "gpt-6.1-sol"]),
        ("gate-interleaved", "sonnet,sol61", "astra", ["gpt-6-astra", "gpt-6.1-sol"]),
        ("gate-single", "", "astra", ["gpt-6-astra"]),
        ("gate-claude", "sol61,sonnet", "sonnet", [])):
    run("marathon.py", "set", P, f"worker_fallback={setting}")
    before = len(calls())
    out = worker(wid, "--class", "gate", "--model", model, mode="limit")
    models = [c["args"][c["args"].index("-m") + 1] for c in calls()[before:]]
    check(f"{wid}: only authorized forward Codex models, exhausted status failed", models == expected
          and "ASTRA UNAVAILABLE:" in out and "Normal round: score with --astra-pending; final gate: two configured Claude reviewers (Opus, or Sonnet under sonnet+astra) with --missing-reason." in out
          and "FALLBACK sonnet" not in out and row(wid)["status"] == "failed" and row(wid)["ended"] and not SNAPSHOT.exists(), out)
run("marathon.py", "set", P, "worker_fallback=sol61,sonnet")
for flags, message in (([], "--class"), (["--class", "gate"], "--sha is required"),
                       (["--class", "gate", "--sha", "not-a-commit"], "rev-parse")):
    before = len(calls())
    out = run("codex_worker.py", "run", P, "--id", "missing-required", "--brief", P / "brief.md", *flags)
    check("required class/commit validated before launching", message in out and len(calls()) == before, out)
for bad in ("../escape.md", str(TMP / "absolute.md")):
    before = len(calls())
    out = worker("bad-out", "--out", bad)
    check("--out rejects paths outside project", "--out must be" in out and len(calls()) == before, out)
worker("ops", "--class", "ops")
ops = calls()[-1]["prompt"]
worker("build", "--class", "build")
build = calls()[-1]["prompt"]
check("ops footer scopes authorized operations and forbids commit/push", "Do only the deploy / publish / live operations the brief explicitly authorises (named target and operation); never commit or push" in ops
      and "Do not commit, push, publish or deploy" not in ops)
check("build footer keeps prohibition and STATE summary_words", "Do not commit, push, publish or deploy" in build and "at most 517 words" in build)
run("codex_worker.py", "steer", P, "--id", "ops", "repeat authorized operation")
check("ops steer preserves ops permission", "never commit or push" in calls()[-1]["prompt"] and "Do not commit, push, publish or deploy" not in calls()[-1]["prompt"])
before = len(calls())
out = worker("explicit-sol", "--model", "sol61", mode="limit")
check("explicit Sol never prepends Astra", "FALLBACK sonnet" in out and len(calls()) == before + 1
      and calls()[-1]["args"][calls()[-1]["args"].index("-m") + 1] == "gpt-6.1-sol", out)
before = len(calls())
out = worker("explicit-luna", "--model", "luna", mode="limit")
check("model absent from chain keeps only Claude fallbacks", "FALLBACK sonnet" in out and len(calls()) == before + 1, out)
out = worker("missing-exe", env={"CODEX_WORKER_EXE": str(TMP / "nonexistent.exe")})
check("launch failure finalizes ledger with attempt ends", row("missing-exe")["status"] == "fallback" and row("missing-exe")["ended"]
      and "a1 astra ended" in row("missing-exe")["note"] and "FileNotFoundError" in row("missing-exe")["note"], out)

out = run("codex_worker.py", "steer", P, "--id", "timeout-tools", "continue work", "--minutes", "0.1", mode="timeout-tools")
check("timeout during steer finalizes without fallback", "timeout-tools TIMEOUT" in out and row("timeout-tools")["status"] == "timeout"
      and row("timeout-tools")["ended"] and (reports / "timeout-tools.a2.events.jsonl").exists(), out)
out = run("codex_worker.py", "steer", P, "--id", "timeout-tools", "retry without tool progress", mode="limit")
check("progress from earlier attempts cannot affect this steer", "timeout-tools FAILED" in out
      and row("timeout-tools")["status"] == "failed" and (reports / "timeout-tools.a3.events.jsonl").exists(), out)
out = run("codex_worker.py", "steer", P, "--id", "W1", "launch failure",
          env={"CODEX_WORKER_EXE": str(TMP / "nonexistent.exe")})
check("steer launch failure finalizes as failed", "W1 FAILED" in out and row("W1")["status"] == "failed" and row("W1")["ended"], out)
run("marathon.py", "set", P, "worker_fallback=")
before = len(calls())
out = worker("no-fallback", mode="limit")
check("explicitly empty fallback stops after primary", "no-fallback FAILED" in out and row("no-fallback")["ended"]
      and len(calls()) == before + 1, out)
run("marathon.py", "set", P, "worker_fallback=sol61,sonnet")

out = worker("recovered", "--class", "gate", "--out", "audits/recovered.md", mode="recovered")
check("successful final status wins over recovered warnings/errors", "recovered DONE" in out and row("recovered")["status"] == "done"
      and same_review(P / "audits/recovered.md", reports / "recovered.a1.md"), out)
large_brief = P / "large-brief.md"
large_brief.write_text("Large prompt. " * 12000, encoding="utf-8")
out = run("codex_worker.py", "run", P, "--id", "blocked-stdin", "--brief", large_brief, "--class", "build", "--minutes", "0.1", mode="timeout-stdin")
check("blocked stdin remains bounded and silent timeout falls back", "blocked-stdin DONE sol61" in out
      and "attempt timed out" in (reports / "blocked-stdin.a1.err.txt").read_text(encoding="utf-8"), out)
for reserved in ("audits/workers.csv", ".tmp/reports/W1.a1.md"):
    before = len(calls())
    out = worker("reserved", "--out", reserved)
    check("--out preserves ledger and retained attempt files", "--out must not overwrite" in out and len(calls()) == before, out)
out = worker("../bad-id")
check("worker id cannot escape reports directory", "--id must be a filename component" in out, out)

before = len(calls())
out = worker("completed-no-status", mode="completed-no-status")
check("completed turn without status is failed despite warnings and tools", "completed-no-status FAILED" in out
      and row("completed-no-status")["status"] == "failed" and len(calls()) == before + 1, out)
for directory in ("audits", "."):
    before = len(calls())
    out = worker("directory-out", "--out", directory)
    check("--out rejects existing directories before launch", "--out must name a file" in out and len(calls()) == before, out)
(P / "parent-file").write_text("not a directory", encoding="utf-8")
before = len(calls())
out = worker("delivery-error", "--out", "parent-file/astra.md")
r = row("delivery-error")
check("failed output delivery retains attempt bookkeeping without fallback", "delivery-error FAILED" in out and r["status"] == "failed"
      and r["ended"] and r["thread"] and r["input"] == "1000" and "a1 astra ended" in r["note"]
      and "report delivery failed" in r["note"] and len(calls()) == before + 1, out)
for collision in ("W1.a1", "W1.full"):
    before = len(calls())
    out = worker(collision)
    check("dotted ids cannot overwrite retained reports", "--id must be a filename component" in out and len(calls()) == before, out)
if os.name == "nt":
    before = len(calls())
    out = worker("w1")
    check("Windows case-only id collision is rejected", "existing worker's letter case" in out and len(calls()) == before, out)

sibling = P / ".tmp/sibling-scratch"
sibling.mkdir()
(sibling / "keep.txt").write_text("keep", encoding="utf-8")
for mode, status in (("ok", "done"), ("failed", "failed"), ("cleanup-only", "partial"), ("timeout-tools", "timeout")):
    wid = "scratch-" + mode
    scratch = P / ".tmp" / wid
    out = worker(wid, "--minutes", "0.1", mode=mode, env={"FAKE_SCRATCH": str(scratch)})
    check(f"scratch terminal policy after {status}, status unchanged", scratch.exists() == (status not in ("done", "failed")) and row(wid)["status"] == status, out)
    check("scratch cleanup retains reports, briefs and sibling scratch", reports.exists() and (P / "brief.md").exists()
          and (sibling / "keep.txt").read_text(encoding="utf-8") == "keep")
scratch = P / ".tmp/scratch-readonly"
out = worker("scratch-readonly", env={"FAKE_SCRATCH": str(scratch), "FAKE_READONLY": "1"})
check("read-only SQLite scratch files removed without failing worker", not scratch.exists()
      and row("scratch-readonly")["status"] == "done" and "cleanup leftover" not in row("scratch-readonly")["note"], out)
scratch = P / ".tmp/scratch-fallback"
before = len(calls())
worker("scratch-fallback", mode="astra-limit", env={"FAKE_SCRATCH": str(scratch)})
check("infra scratch survives fallback until terminal completion", not scratch.exists() and len(calls()) == before + 2
      and [c["scratch_before"] for c in calls()[before:]] == [False, True])
scratch = P / ".tmp/scratch-keep"
worker("scratch-keep", "--keep-scratch", env={"FAKE_SCRATCH": str(scratch)})
check("--keep-scratch retains run scratch", (scratch / "real/test.db-wal").exists())
run("codex_worker.py", "steer", P, "--id", "scratch-keep", "continue", "--keep-scratch")
check("--keep-scratch retains steer scratch", scratch.exists())
run("codex_worker.py", "steer", P, "--id", "scratch-keep", "finish")
check("steer cleans scratch by default", not scratch.exists() and row("scratch-keep")["status"] == "done")
scratch = P / ".tmp/scratch-gate"
worker("scratch-gate", "--class", "gate", env={"FAKE_SCRATCH": str(scratch)})
check("gate skips worker scratch cleanup and retains snapshot lifecycle", scratch.exists() and not SNAPSHOT.exists())
check("worker footer delegates cleanup to harness", all("do not delete it yourself" in c["prompt"]
      and "Do not report cleanup as unfinished work" in c["prompt"] for c in calls() if ".full.md" in c["prompt"]))
check("gate and read-only footers do not authorize worker scratch writes", all("Keep scratch files under" not in c["prompt"]
      for c in calls() if ".full.md" not in c["prompt"]))
# Deterministic process/ledger failure injection supplements the real fake-command tests.
sys.path.insert(0, str(HERE))
local_env = patch.dict(os.environ, ENV, clear=True)
local_env.start()
import codex_worker as cw
for wid in (".", "reports", "briefs", "gate", "gpu", "bakeoff", "bakeoff-keys", "bakeoff-logs", "../outside", str(TMP / "outside")):
    with patch.object(cw.shutil, "rmtree") as removed:
        note = cw.cleanup_scratch(P, wid)
    check(f"cleanup refuses protected/outside path {wid}", "refused" in note and not removed.called, note)
scratch = P / ".tmp/scratch-reparse"
scratch.mkdir()
real_lstat = cw.Path.lstat
def reparse_stat(path, *args, **kwargs):
    return (SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
            if path == scratch else real_lstat(path, *args, **kwargs))

with patch.object(cw.Path, "lstat", reparse_stat), patch.object(cw.shutil, "rmtree") as removed:
    note = cw.cleanup_scratch(P, scratch.name)
check("generic Windows reparse attributes prevent deletion", "refused" in note and not removed.called, note)
real_resolve = cw.Path.resolve
def outside_resolve(path, *args, **kwargs):
    return TMP / "outside" if path == scratch else real_resolve(path, *args, **kwargs)

with patch.object(cw.Path, "resolve", outside_resolve), patch.object(cw.shutil, "rmtree") as removed:
    note = cw.cleanup_scratch(P, scratch.name)
check("resolved outside path prevents deletion", "refused" in note and not removed.called, note)
outside = TMP / "outside"
outside.mkdir(exist_ok=True)
(outside / "keep.txt").write_text("keep", encoding="utf-8")
redirect = P / ".tmp/redirect"
if os.name == "nt":
    # mklink only creates this fixed test junction; deletion stays in Python and never follows it.
    subprocess.run(["cmd", "/c", "mklink", "/J", str(redirect), str(outside)], check=True, capture_output=True, stdin=subprocess.DEVNULL)
else:
    redirect.symlink_to(outside, target_is_directory=True)
note = cw.cleanup_scratch(P, "redirect")
check("real junction/symlink cannot delete its outside target", "refused" in note and (outside / "keep.txt").read_text(encoding="utf-8") == "keep"
      and os.path.lexists(redirect), note)
if os.name == "nt":
    redirect.rmdir()
else:
    redirect.unlink()
redirect_target = P / ".tmp/redirect-target"
redirect_target.mkdir()
(redirect_target / "keep.txt").write_text("keep", encoding="utf-8")
if os.name == "nt":
    subprocess.run(["cmd", "/c", "mklink", "/J", str(redirect), str(redirect_target)], check=True, capture_output=True, stdin=subprocess.DEVNULL)
else:
    redirect.symlink_to(redirect_target, target_is_directory=True)
note = cw.cleanup_scratch(P, "redirect")
check("junction/symlink inside .tmp is still refused", "reparse point" in note and (redirect_target / "keep.txt").exists(), note)
worker("redirect")
check("cleanup refusal is logged without failing the worker", row("redirect")["status"] == "done"
      and "scratch cleanup refused" in row("redirect")["note"] and str(redirect) in row("redirect")["note"])
if os.name == "nt":
    redirect.rmdir()
else:
    redirect.unlink()
scratch = P / ".tmp/scratch-retry"
scratch.mkdir()
(scratch / "late.db-wal").write_text("locked briefly", encoding="utf-8")
remove_tree = cw.shutil.rmtree
def delayed_remove(*args, **kwargs):
    if removed.call_count == 1:
        raise PermissionError("sharing violation")
    return remove_tree(*args, **kwargs)

with patch.object(cw.shutil, "rmtree", side_effect=delayed_remove) as removed, \
        patch.object(cw.time, "sleep") as slept:
    note = cw.cleanup_scratch(P, "scratch-retry")
check("late SQLite locks retry with a short sleep", not note and not scratch.exists()
      and removed.call_count == 2 and slept.call_args.args == (0.2,))
scratch = P / ".tmp/scratch-locked"
scratch.mkdir()
locked_args = SimpleNamespace(dir=str(P), id="scratch-locked", brief=str(P / "brief.md"), model="astra", cls="build",
                              read_only=False, out=None, minutes=1, image=None)
with patch.object(cw.shutil, "rmtree", side_effect=PermissionError("still locked")) as removed, patch.object(cw.time, "sleep"):
    cw.cmd_run(locked_args)
check("persistent locks leave path in ledger without failing worker", scratch.exists() and removed.call_count == 4
      and row("scratch-locked")["status"] == "done" and str(scratch) in row("scratch-locked")["note"]
      and "scratch cleanup leftover" in row("scratch-locked")["note"])
scratch = P / ".tmp/scratch-exception"
scratch.mkdir()
locked_args.id = scratch.name
with patch.object(cw, "run_codex", side_effect=RuntimeError("process supervisor failed")):
    try:
        cw.cmd_run(locked_args)
    except RuntimeError:
        pass
check("infra exception preserves scratch and finalizes ledger", scratch.exists()
      and row("scratch-exception")["status"] == "failed" and row("scratch-exception")["ended"])
cw.m.upsert_worker(P, "opus-running", {"class": "gate", "status": "running", "note": f"sha={SHA}"})
out = worker("shared-gate", "--class", "gate")
check("other running gate on same SHA keeps shared snapshot", SNAPSHOT.exists()
      and row("shared-gate")["status"] == "done", out)
(SNAPSHOT / ".scratch" / "kept.txt").write_text("reused", encoding="utf-8")
worker("shared-gate-2", "--class", "gate")
check("same SHA snapshot is reused", (SNAPSHOT / ".scratch" / "kept.txt").read_text(encoding="utf-8") == "reused")
cw.m.upsert_worker(P, "opus-running", {"status": "done"})
cw.m.upsert_worker(P, "other-sha", {"class": "gate", "status": "running", "note": "sha=" + "f" * 40})
worker("last-gate", "--class", "gate")
check("last gate removes snapshot despite another SHA running", not SNAPSHOT.exists())
cw.m.upsert_worker(P, "other-sha", {"status": "done"})
gate_args = SimpleNamespace(dir=str(P), id="gate-exception", brief=str(P / "brief.md"), model="astra", cls="gate",
                            sha=SHA, read_only=False, out=None, minutes=1, image=None)
with patch.object(cw, "attempt", side_effect=RuntimeError("unexpected failure")):
    try:
        cw.cmd_run(gate_args)
    except RuntimeError:
        pass
check("gate exception finalizes ledger and removes snapshot", row("gate-exception")["status"] == "failed"
      and row("gate-exception")["ended"] and not SNAPSHOT.exists())
with patch.object(cw, "snapshot", side_effect=OSError("worktree unavailable")):
    try:
        cw.cmd_run(gate_args)
    except OSError:
        pass
check("snapshot setup failure finalizes gate row", row("gate-exception")["status"] == "failed" and row("gate-exception")["ended"])
check("all worker footers forbid independent review", all("Do not start an independent review" in c["prompt"] for c in calls()))
with patch.dict(os.environ, {"CODEX_WORKER_EXE": ""}), patch.object(cw.Path, "glob", return_value=[]), \
        patch.object(cw.shutil, "which", return_value="codex.cmd"):
    check("Codex discovery supports PATH npm shim", cw.codex_exe() == "codex.cmd")
proc = Mock(pid=12345, returncode=None)
proc.stdin.write.side_effect = BrokenPipeError("fake stdin closed")
proc.wait.return_value = 1
proc.stdin.closed = True
with patch.object(cw.subprocess, "Popen", return_value=proc), patch.object(cw, "kill_tree") as killed:
    code, _ = cw.run_codex(["fake"], P, "prompt", TMP / "pipe.events", TMP / "pipe.err", 1)
check("broken stdin kills and waits via tree supervisor", code == -1 and killed.call_count == 1
      and "BrokenPipeError" in (TMP / "pipe.err").read_text(encoding="utf-8"))
proc = Mock(pid=12345)
proc.poll.return_value = None
with patch.object(cw.os, "name", "nt"), patch.object(cw.subprocess, "run") as taskkill:
    cw.kill_tree(proc)
check("Windows timeout uses taskkill /T /F /PID and waits", taskkill.call_args.args[0] == ["taskkill", "/T", "/F", "/PID", "12345"]
      and proc.wait.called)
proc = Mock(pid=12345)
proc.poll.return_value = 1
with patch.object(cw.os, "name", "posix"), patch.object(cw.os, "killpg", create=True) as killpg, \
        patch.object(cw.signal, "SIGKILL", 9, create=True):
    cw.kill_tree(proc)
check("POSIX timeout kills process group and waits", killpg.call_args.args == (12345, 9) and proc.wait.called)
a = SimpleNamespace(dir=str(P), id="pipe-worker", brief=str(P / "brief.md"), model=None, cls="build", read_only=False,
                    out=None, minutes=1, image=None)
proc = Mock(pid=12345, returncode=None)
proc.stdin.write.side_effect = BrokenPipeError("fake stdin closed")
proc.wait.return_value = 1
proc.stdin.closed = True
with patch.object(cw.subprocess, "Popen", return_value=proc), \
        patch.object(cw, "real_path", side_effect=lambda p: p), patch.object(cw, "kill_tree"):
    cw.cmd_run(a)
check("BrokenPipeError finalizes worker row", row("pipe-worker")["status"] == "fallback" and row("pipe-worker")["ended"]
      and "BrokenPipeError" in row("pipe-worker")["note"])
a.id = "unexpected"
with patch.object(cw, "attempt", side_effect=RuntimeError("unexpected failure")):
    try:
        cw.cmd_run(a)
    except RuntimeError:
        pass
check("unexpected exception still finalizes worker", row("unexpected")["status"] == "failed" and row("unexpected")["ended"])

# Archived direct callers predate --class; their scratch cleanup must still work.
for read_only in (False, True):
    wid = "legacy-direct-" + str(read_only)
    scratch = P / ".tmp" / wid
    scratch.mkdir()
    with patch.object(cw, "run_codex", return_value=(1, 0)) as runner:
        result = cw.attempt(P, P, wid, "astra", "offline", SimpleNamespace(minutes=1, read_only=read_only))
    check("S8 direct infra attempt without cls retains scratch and sandbox", scratch.exists()
          and result["kind"] == "infra"
          and ('sandbox_mode="read-only"' in runner.call_args.args[0]) == read_only)

check("public launcher has no private MCP overrides", cw.disabled_mcp_servers() == [])
for wid in ("scratch-cleanup-only", "scratch-timeout-tools"):
    run("codex_worker.py", "steer", P, "--id", wid, "finish")
    check("S8 later terminal steer cleans retained scratch", not (P / ".tmp" / wid).exists() and row(wid)["status"] == "done")
for command in ("run", "steer"):
    wid = "infra-retain-" + command
    scratch = P / ".tmp" / wid
    worker(wid, "--keep-scratch", env={"FAKE_SCRATCH": str(scratch)})
    if command == "run":
        worker(wid, mode="limit")
    else:
        run("codex_worker.py", "steer", P, "--id", wid, "retry", mode="limit")
    check("S8 infrastructure failure retains scratch " + command, scratch.exists())

# Same-ID ownership covers command setup, process exit, cleanup and finalization.
for direct in (False, True):
    wid = "lifetime-" + str(direct)
    scratch = P / ".tmp" / wid
    scratch.mkdir(); (scratch / "keep.txt").write_text("active", encoding="utf-8")
    entered, finish, cleaning, clean_finish = (threading.Event() for _ in range(4))
    errors = []
    args = SimpleNamespace(dir=str(P), id=wid, brief=str(P / "brief.md"), model="astra", cls="build",
                           read_only=False, out=None, minutes=1, image=None)
    def held_runner(cmd, rd, prompt, events, err, minutes, env=None):
        Path(cmd[cmd.index("-o") + 1]).write_text("DONE\nfinished", encoding="utf-8")
        events.write_text(json.dumps({"type": "thread.started", "thread_id": "test-thread"}) + "\n", encoding="utf-8")
        err.write_text("", encoding="utf-8")
        entered.set()
        assert finish.wait(10)
        return 0, 0
    real_clean = cw.clean_worker
    def held_clean(*args):
        cleaning.set()
        assert clean_finish.wait(10)
        return real_clean(*args)
    def owner():
        try:
            if direct:
                cw.attempt(P, P, wid, "astra", "offline", args)
            else:
                cw.cmd_run(args)
        except BaseException as e:
            errors.append(repr(e))
    def contend(stage):
        before = (P / "audits/workers.csv").read_bytes()
        retained = sorted(p.name for p in reports.glob(wid + ".a*"))
        for operation in ("run", "steer", "direct", "case"):
            other = SimpleNamespace(**vars(args)); other.message = "continue"
            if operation == "case": other.id = wid.upper()
            try:
                if operation in ("direct", "case"):
                    cw.attempt(P, P, other.id, "astra", "offline", other)
                else:
                    getattr(cw, "cmd_" + operation)(other)
            except SystemExit as e:
                rejected = "already active" in str(e)
            else:
                rejected = False
            check(f"S8 lifetime {direct}/{stage}/{operation}: rejects without touching row/scratch", rejected
                  and before == (P / "audits/workers.csv").read_bytes()
                  and (scratch / "keep.txt").read_text(encoding="utf-8") == "active"
                  and retained == sorted(p.name for p in reports.glob(wid + ".a*")))
    with patch.object(cw, "run_codex", side_effect=held_runner), patch.object(cw, "clean_worker", side_effect=held_clean):
        thread = threading.Thread(target=owner); thread.start()
        assert entered.wait(10)
        contend("process")
        finish.set(); assert cleaning.wait(10)
        contend("cleanup")
        clean_finish.set(); thread.join(10)
    check("S8 lifetime owner completes and releases", not thread.is_alive() and not errors and not scratch.exists(), errors)
    if not direct:
        run("codex_worker.py", "steer", P, "--id", wid, "continue")
        check("S8 sequential steer remains valid", row(wid)["status"] == "done")

# Cross-process CLI contenders use the same lifetime lease as direct calls.
wid = "process-lifetime"
scratch = P / ".tmp" / wid
flag = TMP / "release-worker"
owner_proc = subprocess.Popen([sys.executable, str(HERE / "codex_worker.py"), "run", str(P), "--id", wid,
                               "--brief", str(P / "brief.md"), "--class", "build"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=dict(ENV, FAKE_MODE="hold", FAKE_HOLD=str(flag), FAKE_SCRATCH=str(scratch)), stdin=subprocess.DEVNULL)
try:
    deadline = cw.time.monotonic() + 10
    while not flag.with_suffix(".ready").exists() and cw.time.monotonic() < deadline:
        cw.time.sleep(0.02)
    assert flag.with_suffix(".ready").exists()
    before = (P / "audits/workers.csv").read_bytes()
    for command, extra in (("run", ["--brief", str(P / "brief.md"), "--class", "build"]), ("steer", ["continue"])):
        out = run("codex_worker.py", command, P, "--id", wid, *extra)
        check("S8 cross-process same-ID contender " + command, "already active" in out
              and before == (P / "audits/workers.csv").read_bytes() and (scratch / "real/test.db-wal").exists(), out)
finally:
    flag.touch()
    stdout, stderr = owner_proc.communicate(timeout=15)
check("S8 cross-process owner tears down and cleans", owner_proc.returncode == 0 and not scratch.exists(), stderr)

# Public API: offline same-model backend fallback and then model chain.
api_env = {"MARATHON_API_BASE_URL": "https://api.example.invalid/v1", "MARATHON_API_KEY": "fake-api-key"}
run("marathon.py", "set", P, "workers=astra", "worker_fallback=sol61,sonnet", "codex_backends=api,subscription")
for error in ("401 Unauthorized", "403 forbidden", "429 rate limit", "503 Service unavailable", "connection refused", "timeout"):
    before = len(calls())
    worker("api-error-" + error.split()[0], mode="api-error", env=dict(api_env, FAKE_ERROR=error))
    recent = calls()[before:]
    check("same model tries api then subscription: " + error, [c["backend"] for c in recent] == ["api", "subscription"] and all("gpt-6-astra" in c["args"] for c in recent))
before = len(calls()); worker("api-model-chain", mode="astra-limit", env=api_env)
check("all backends before next model", [c["backend"] for c in calls()[before:]] == ["api", "subscription", "api"])
before = len(calls()); worker("api-gate", "--class", "gate", "--model", "astra", mode="api-error", env=api_env)
check("gate uses identical routing", [c["backend"] for c in calls()[before:]] == ["api", "subscription"])
before = len(calls()); worker("api-progress", mode="crash-tools", env=api_env)
check("no backend retry after tools", len(calls()) == before + 1)
worker("api-start", "--backend", "api", env=api_env)
run("marathon.py", "set", P, "codex_backends=subscription")
run("codex_worker.py", "steer", P, "--id", "api-start", "continue", env=api_env)
check("steer retains actual backend", calls()[-1]["backend"] == "api" and "resume" in calls()[-1]["args"])
with patch.dict(os.environ, api_env):
    flags = cw.backend_args("api")
    check("key stays out of provider flags", api_env["MARATHON_API_KEY"] not in str(flags) and 'model_provider=marathon_api' in flags)
    check("configured default is api first", cw.m.run_value({}, "codex_backends") == "api,subscription")
with patch.dict(os.environ, {}, clear=True):
    check("unconfigured default is subscription", cw.m.run_value({}, "codex_backends") == "subscription" and not cw.backend_key("api"))
with patch.dict(os.environ, {"MARATHON_API_KEY": "key"}, clear=True):
    check("both env values required", not cw.backend_key("api") and cw.m.run_value({}, "codex_backends") == "subscription")
run("marathon.py", "set", P, "codex_backends=subscription")
args = [sys.executable, str(HERE / "codex_worker.py"), "run", str(P), "--id", "open-stdin",
        "--brief", str(P / "brief.md"), "--class", "build"]
proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=dict(ENV, FAKE_MODE="ok"))
try:
    proc.wait(timeout=10)
    check("S9 worker CLI exits with caller stdin still open", proc.returncode == 0 and not proc.stdin.closed)
finally:
    if proc.poll() is None: proc.kill()
    proc.communicate(timeout=5)
legacy = TMP / "legacy-ledger"
(legacy / "audits").mkdir(parents=True)
(legacy / "audits/workers.csv").write_text("id,agent,thread,model,status\nold,codex,legacy-thread,gpt-6-astra,done\n", encoding="utf-8")
check("old ledger has empty backend", cw.m.read_workers(legacy)[0]["backend"] == "" and cw.read_workers(legacy)[0]["backend"] == "")
with patch.object(cw, "backend_key", return_value=""):
    result = cw.attempt(legacy, legacy, "legacy-direct", "astra", "offline legacy caller",
                        SimpleNamespace(minutes=1, read_only=False))
check("S9 archived direct callers need no STATE file", result["kind"] == "done" and result["backend"] == "subscription")
local_env.stop()

before = len(calls())
out = worker("cap1", mode="capacity", env={"CODEX_WORKER_RESUME_WAIT": "0"})
new = calls()[before:]
r = row("cap1")
check("capacity: resumes the same thread with the next Codex model, then DONE",
      "CAPACITY" in out and "cap1 DONE" in out and len(new) == 2 and "resume" in new[1]["args"] and "thr-cap" in new[1]["args"]
      and new[1]["args"][new[1]["args"].index("-m") + 1] != new[0]["args"][new[0]["args"].index("-m") + 1], out)
check("capacity: failed attempt's usage read from the session log and added to the resumed turn",
      r["status"] == "done" and r["input"] == "6000" and r["cached"] == "4800" and r["output"] == "130", dict(r))
check("footer: no $skill trigger, context and web rules present",
      "$independent-review" not in new[0]["prompt"] and "read files by line range" in new[0]["prompt"]
      and "keep only what you cite" in new[0]["prompt"], new[0]["prompt"][-1200:])

# S10: legacy rows without a recorded model use this run's chain; gate rows stay Astra.
run("marathon.py", "set", P, "profile=codex", "codex_backends=subscription")
for wid, cls, expected in (("s10-legacy-worker", "build", "gpt-6.1-sol"), ("s10-legacy-gate", "gate", "gpt-6-astra")):
    cw.m.upsert_worker(P, wid, {"agent": "codex", "thread": "legacy-thread", "class": cls, "effort": "high",
                              "note": f"sha={SHA}" if cls == "gate" else ""})
    run("codex_worker.py", "steer", P, "--id", wid, "continue")
    check("S10 model-less steer " + cls, expected in calls()[-1]["args"] and row(wid)["model"] == expected)
run("marathon.py", "set", P, "workers=astra-xhigh")
cw.m.upsert_worker(P, "s10-legacy-effort", {"agent": "codex", "thread": "legacy-thread", "class": "build", "effort": "high"})
run("codex_worker.py", "steer", P, "--id", "s10-legacy-effort", "continue")
check("S10 model-less steer uses run model and recorded effort", row("s10-legacy-effort")["model"] == "gpt-6-astra"
      and row("s10-legacy-effort")["effort"] == "high")
run("marathon.py", "set", P, "workers=gpt-6.1-sol")
cw.m.upsert_worker(P, "s10-legacy-alias", {"agent": "codex", "thread": "legacy-thread", "class": "build", "effort": "xhigh"})
run("codex_worker.py", "steer", P, "--id", "s10-legacy-alias", "continue")
check("S10 model-less steer normalizes full model alias", row("s10-legacy-alias")["model"] == "gpt-6.1-sol"
      and row("s10-legacy-alias")["effort"] == "xhigh")

print(f"\n{len(FAILS)} failure(s)")
for f in FAILS:
    print("-", f)
sys.exit(1 if FAILS else 0)
