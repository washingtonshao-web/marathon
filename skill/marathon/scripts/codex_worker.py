#!/usr/bin/env python
"""Run/steer a bounded Codex worker; retain attempt reports and audits/workers.csv usage.
Run requires --class; gate also requires --sha and reviews a detached worktree with full access,
scratch-only writes and a GPT-only model chain. Read-only workers return full reports for parent delivery.
Use run -h or steer -h for options; references/codex-workers.md owns the launch/report protocol.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import shlex
import signal
import stat
import subprocess
import sys
import threading
import time
import hashlib
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import marathon as m  # noqa: E402

BACKENDS = {"api": ("MARATHON_API_KEY", ""), "subscription": ("", "")}


def backend_key(backend: str) -> str:
    return os.environ.get("MARATHON_API_KEY", "") if backend == "api" and os.environ.get("MARATHON_API_BASE_URL") else ""


def backend_args(backend: str) -> list[str]:
    if backend == "subscription":
        return []
    url = os.environ.get("MARATHON_API_BASE_URL", "")
    from urllib.parse import urlsplit
    parsed = urlsplit(url)
    if parsed.scheme not in ("https", "http") or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SystemExit("MARATHON_API_BASE_URL must be an HTTP(S) base URL without credentials, query or fragment")
    provider = '{name="marathon-api",base_url=' + json.dumps(url) + ',wire_api="responses",env_key="MARATHON_API_KEY"}'
    return ["-c", "model_provider=marathon_api", "-c", "model_providers.marathon_api=" + provider]


def backend_order(d: Path, start: str | None = None) -> list[str]:
    value = m.run_value(m.read_state(d)[0] if (d / "STATE.md").exists() else {}, "codex_backends")
    m.check_run_key("codex_backends", value)
    order = value.split(",")
    if start:
        order = order[order.index(start):] if start in order else list(m.CODEX_BACKENDS)[m.CODEX_BACKENDS.index(start):]
    return order


DISABLED_MCP_SERVERS = ()
PROTECTED_SCRATCH = {"reports", "briefs", "gate", "gpu", "bakeoff", "bakeoff-keys", "bakeoff-logs"}
_HELD = threading.local()


@contextmanager
def worker_lifetime(d: Path, wid: str):
    if not re.fullmatch(r"[\w-]+", wid):
        raise SystemExit("--id must be a filename component")
    key = (m.project_key(d), wid.casefold())
    held = getattr(_HELD, "keys", set())
    if key in held:
        yield
        return
    path = d / ".tmp" / "reports" / ("worker-" + hashlib.sha256(wid.casefold().encode()).hexdigest() + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as f:
        if not path.stat().st_size:
            f.write(b"0"); f.flush()
        f.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise SystemExit(f"{wid}: worker ID already active in this run")
        _HELD.keys = held | {key}
        try:
            yield
        finally:
            _HELD.keys = held
            f.seek(0)
            if os.name == "nt":
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def worker_command(fn):
    def locked(a):
        d = Path(a.dir).resolve()
        with worker_lifetime(d, a.id):
            if os.name == "nt" and any(r["id"] != a.id and r["id"].casefold() == a.id.casefold() for r in read_workers(d)):
                raise SystemExit("--id must use the existing worker's letter case on Windows")
            a.cleanup_terminal = False
            return fn(a)
    return locked


def clean_worker(d: Path, wid: str, a) -> None:
    if getattr(a, "cls", None) != "gate" and not getattr(a, "keep_scratch", False):
        note = cleanup_scratch(d, wid)
        if note:
            row = next((r for r in read_workers(d) if r.get("id") == wid), {})
            m.upsert_worker(d, wid, {"note": "; ".join(filter(None, [row.get("note"), note]))})

FALLBACK_ERRORS = re.compile(r"usage limit|rate limit|quota|429|401|403|unauthori[sz]ed|not logged in|log ?in again|"
                             r"\bauth(?:entication|orization)?\b|sign.?in|network|timed? out|timeout|crash|stream (?:error|disconnected)|connection|internal server error|5\d\d ",
                             re.I)
# Errors that end a run early through no fault of the work: resume the same thread instead of waiting for the lead.
CAPACITY_ERRORS = re.compile(r"at capacity|overloaded|try a different model|rate.?limit|too many requests|\b429\b|"
                             r"internal server error|server.?error|(?:status|http|code)[ :=]*5\d\d\b|stream (?:error|disconnected)", re.I)
AUTO_RESUMES = 2
RESUME_MESSAGE = ("The previous attempt stopped on a model capacity or server error, not on your work. Continue the task "
                  "from where it stopped: check what is already in the tree, do not redo finished steps.")
FOOTER = """

---
Worker rules (from the marathon lead):
- The project folder is {project}. Work there: it overrides any rule in AGENTS.md about where workspaces or repos
  live, so do not create or use another folder. Relative paths in this brief are relative to it.
- Read docs/WORKER-RULES.md first if the project has one; it wins over anything here except this footer.
- Do not start an independent review of your own work (not the independent-review skill, no Claude or sub-agent
  reviewers): the marathon gate reviews it. Run the brief's tests and checks instead.
- Keep your context small: find text with rg and read files by line range, not whole files over ~200 lines; send long
  command output to a file and read only the part you need.
- Web: a few queries or pages per call; save long source text to files (curl or a script) and keep only what you cite.
{report_rules}
- {permissions}, and do not change files outside the ones the brief gives you.
"""


def footer(d: Path, rd: Path, wid: str, cls: str, read_only: bool = False) -> str:
    if cls == "gate" or read_only:
        report = ("- Return the full report in your final message, without a length cap, starting with DONE, PARTIAL or "
                  "FAILED; the parent saves it. Do not edit project files.")
        if cls == "gate":
            report += (f" Review this folder only: {rd}. You may run tests and checks; write only under {rd / '.scratch'}/.\n"
                       "- Return the complete review. End with exactly the REVIEWER/ARTIFACT/SCORES/VERDICT lines from gate.md:\n"
                       "REVIEWER: <model>\nARTIFACT: <commit reviewed>\n"
                       "SCORES: <rubric-key>=<0-10|n/a>, ...\nVERDICT: PASS|FAIL critical=<integer> major=<integer>")
        else:
            report += " This worker is read-only: do not write files."
    else:
        words = m.run_value(m.read_state(d)[0], "summary_words") or 300
        report = (f"- Write the full report (DONE / PARTIAL per item, files changed, measured numbers, open issues, "
                  f"exact patches for files you do not own) to .tmp/reports/{wid}.full.md.\n"
                  f"- Your final message is at most {words} words and starts with one status word: DONE, PARTIAL or FAILED.")
        report += (f"\n- Keep scratch files under .tmp/{wid}/; do not delete it yourself "
                   "(the harness removes it after DONE/FAILED). Keep cited evidence in audits/ or .tmp/reports/. Do not report cleanup as unfinished work.")
    permissions = ("Do only the deploy / publish / live operations the brief explicitly authorises (named target and "
                   "operation); never commit or push" if cls == "ops" else "Do not commit, push, publish or deploy")
    return FOOTER.format(project=rd, report_rules=report, permissions=permissions)


def output_path(d: Path, value: str | None) -> Path | None:
    if not value:
        return None
    p = Path(value)
    if p.is_absolute() or p.drive or not (d / p).resolve().is_relative_to(d):
        raise SystemExit("--out must be a path relative to the project and inside it")
    target = (d / p).resolve()
    if target.is_dir():
        raise SystemExit("--out must name a file, not an existing directory")
    if target == d / "audits" / "workers.csv" or target.is_relative_to(d / ".tmp" / "reports"):
        raise SystemExit("--out must not overwrite the worker ledger or attempt reports")
    return target


def codex_exe() -> str:
    if os.environ.get("CODEX_WORKER_EXE"):   # tests
        return os.environ["CODEX_WORKER_EXE"]
    exes = []
    if os.name == "nt":
        exes = list(Path(os.environ.get("LOCALAPPDATA", "")).glob("OpenAI/Codex/bin/*/codex.exe"))
    elif sys.platform == "darwin":
        exes = [p for root in (Path("/Applications/Codex.app/Contents/Resources"), Path.home() / "Applications/Codex.app/Contents/Resources") for p in root.glob("**/codex") if p.is_file() and os.access(p, os.X_OK)]
    exes.sort(key=lambda p: p.stat().st_mtime)
    return str(exes[-1]) if exes else shutil.which("codex") or "codex"


def real_path(p: Path) -> Path:
    """Resolve Windows substituted drives for sandbox access."""
    if os.name != "nt":
        return p
    drive = p.drive.upper()
    if not drive:
        return p
    try:
        out = subprocess.run(["subst"], capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL).stdout
    except (OSError, subprocess.TimeoutExpired):
        return p
    for line in out.splitlines():
        mm = re.match(r"^([A-Z]:)\\: => (.+)$", line.strip())
        if mm and mm.group(1) == drive:
            return Path(mm.group(2).rstrip("\\") + "\\" + str(p)[3:])
    return p


def parse_events(path: Path) -> dict:
    out = {"thread": "", "input": 0, "cached": 0, "output": 0, "errors": [], "turns": 0, "tools": 0, "completed": False}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        t = ev.get("type", "")
        if t.startswith("turn."):
            out["turns"] += 1
        if t == "turn.completed":
            out["completed"] = True
        if t.startswith("item.") and ev.get("item", {}).get("type") in (
                "command_execution", "file_change", "mcp_tool_call", "web_search", "tool_call", "image_generation"):
            out["tools"] += 1
        if t == "thread.started":
            out["thread"] = ev.get("thread_id", "")
        elif t == "turn.completed" and isinstance(ev.get("usage"), dict):
            u = ev["usage"]
            out["input"] += int(u.get("input_tokens") or 0)
            out["cached"] += int(u.get("cached_input_tokens") or 0)
            out["output"] += int(u.get("output_tokens") or 0) + int(u.get("reasoning_output_tokens") or 0)
        elif t in ("error", "turn.failed"):
            msg = ev.get("message") or (ev.get("error") or {}).get("message") or json.dumps(ev)[:300]
            out["errors"].append(str(msg))
    return out


def rollout_usage(thread: str) -> dict | None:
    """Cumulative usage of a Codex thread from its session log; used when a run ends without turn.completed."""
    if not re.fullmatch(r"[\w-]+", thread or ""):
        return None
    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    files = sorted(home.glob(f"sessions/*/*/*/rollout-*-{thread}.jsonl"))
    if not files:
        return None
    total = None
    try:
        for line in files[-1].read_text(encoding="utf-8", errors="replace").splitlines():
            if '"token_count"' in line:
                try:
                    total = (json.loads(line).get("payload", {}).get("info") or {}).get("total_token_usage") or total
                except ValueError:
                    continue
    except OSError:
        return None
    if not total:
        return None
    return {"input": int(total.get("input_tokens") or 0), "cached": int(total.get("cached_input_tokens") or 0),
            "output": int(total.get("output_tokens") or 0) + int(total.get("reasoning_output_tokens") or 0)}


def kill_tree(p, err=None) -> None:
    try:
        if os.name == "nt":
            r = subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, timeout=30, stdin=subprocess.DEVNULL)
            if r.returncode and err:
                err.write(f"taskkill exit {r.returncode}: {r.stderr.decode('utf-8', 'replace')[-500:]}\n")
        elif hasattr(os, "killpg"):
            os.killpg(p.pid, signal.SIGKILL)
        else:
            p.kill()
    except (OSError, subprocess.TimeoutExpired) as e:
        if err:
            err.write(f"process tree cleanup: {e}\n")
    finally:
        if p.poll() is None:
            try:
                p.kill()
            except ProcessLookupError:
                pass
        p.wait()


def run_codex(cmd: list[str], cwd: Path, prompt: str, events: Path, err: Path, minutes: float, env: dict | None = None) -> tuple[int | None, float]:
    t0 = time.monotonic()
    p, writer, code, errors = None, None, -1, []
    with events.open("w", encoding="utf-8") as fo, err.open("w", encoding="utf-8") as fe:
        try:
            p = subprocess.Popen(cmd, cwd=str(cwd), stdin=subprocess.PIPE, stdout=fo, stderr=fe, text=True,
                                 encoding="utf-8", env=env, start_new_session=os.name != "nt")

            def send() -> None:
                try:
                    p.stdin.write(prompt)
                    p.stdin.close()
                except OSError as e:
                    errors.append(e)

            writer = threading.Thread(target=send, daemon=True)
            writer.start()
            deadline = t0 + minutes * 60
            while True:
                if errors:
                    raise errors[0]
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(cmd, minutes * 60)
                try:
                    code = p.wait(timeout=min(0.2, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
            writer.join(timeout=max(0, deadline - time.monotonic()))
            if writer.is_alive():
                raise subprocess.TimeoutExpired(cmd, minutes * 60)
            if errors:
                raise errors[0]
        except subprocess.TimeoutExpired:
            code = None
            fe.write("attempt timed out\n")
        except OSError as e:   # includes BrokenPipeError while sending the prompt
            code = -1
            fe.write(f"{type(e).__name__}: {e}\n")
        finally:
            if p is not None:
                if code in (None, -1) or p.poll() is None:
                    kill_tree(p, fe)
                else:
                    p.wait()
                if writer:
                    writer.join(timeout=5)
                if (not writer or not writer.is_alive()) and p.stdin and not p.stdin.closed:
                    try:
                        p.stdin.close()
                    except OSError:
                        pass
    return code, (time.monotonic() - t0) / 60


def read_workers(d: Path) -> list[dict]:
    p = d / "audits" / "workers.csv"
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig", newline="") as f:
        return [dict(r, backend=r.get("backend") or "") for r in csv.DictReader(f)]


def cleanup_scratch(d: Path, wid: str) -> str:
    root, target = d / ".tmp", d / ".tmp" / wid
    reason = "path changed during cleanup"

    def reparse(p: Path) -> bool:
        s = p.lstat()
        return stat.S_ISLNK(s.st_mode) or bool(getattr(s, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)

    def writable(func, path, exc) -> None:
        p = Path(path)
        if reparse(p):
            raise exc
        p.chmod(p.stat().st_mode | stat.S_IWRITE)
        func(path)

    def walk_error(exc) -> None:
        raise exc

    for n in range(4):
        try:
            if target == root or target.parent != root or target.name.casefold() in PROTECTED_SCRATCH:
                return f"scratch cleanup refused (protected/outside path): {target}"
            if reparse(root) or reparse(target):
                return f"scratch cleanup refused (symlink/junction/reparse point): {target}"
            base, resolved = root.resolve(), target.resolve()
            if resolved == base or not resolved.is_relative_to(base) or resolved.parent != base \
                    or resolved.name.casefold() in PROTECTED_SCRATCH:
                return f"scratch cleanup refused (protected/outside path): {target}"
            # Refuse nested redirectors too, including those on paths retried after a sharing violation.
            for parent, dirs, files in os.walk(target, onerror=walk_error):
                if any(reparse(Path(parent) / name) for name in dirs + files):
                    return f"scratch cleanup refused (nested symlink/junction/reparse point): {target}"
            shutil.rmtree(resolved, onexc=writable)
            return ""
        except FileNotFoundError:
            if not os.path.lexists(target):
                return ""
        except (OSError, ValueError, RuntimeError) as e:
            reason = f"{type(e).__name__}: {e}"
        if n < 3:
            time.sleep(0.2 * (n + 1))
    return f"scratch cleanup leftover: {target} ({reason})"


def git(d: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL).stdout.strip()


def snapshot(d: Path, sha: str) -> Path:
    rd = real_path(d / ".tmp" / "gate" / sha[:7])
    if not rd.exists():
        rd.parent.mkdir(parents=True, exist_ok=True)
        git(d, "worktree", "add", "--detach", str(rd), sha)
    if not (rd / ".git").is_file() or git(rd, "rev-parse", "HEAD") != sha:
        raise SystemExit(f"gate snapshot does not match {sha}: {rd}")
    (rd / ".scratch").mkdir(exist_ok=True)
    return rd


def finalize(d: Path, a, status: str) -> None:
    if status in ("done", "failed") and getattr(a, "cleanup_terminal", False):
        clean_worker(d, a.id, a)
    m.upsert_worker(d, a.id, {"status": status, "ended": time.strftime("%Y-%m-%dT%H:%M")})
    if a.cls == "gate" and a.sha and not any(r.get("class") == "gate" and r.get("status") == "running"
            and f"sha={a.sha}" in r.get("note", "").split("; ") for r in read_workers(d)):
        rd = real_path(d / ".tmp" / "gate" / a.sha[:7])
        if (rd / ".git").is_file() and git(rd, "rev-parse", "HEAD") == a.sha:
            git(d, "worktree", "remove", "--force", str(rd))


def status_word(summary: Path) -> str:
    try:
        first = summary.read_text(encoding="utf-8", errors="replace").strip().split(None, 1)[0].strip("*:#").upper()
    except (OSError, IndexError):
        return ""
    return first.lower() if first in ("DONE", "PARTIAL", "FAILED") else ""


def disabled_mcp_servers() -> list[str]:
    return []


def base_cmd(model: str, effort: str, read_only: bool, summary: Path) -> list[str]:
    return ["-m", model, "-c", f"model_reasoning_effort={effort or 'high'}",
            "-c", f'sandbox_mode="{"read-only" if read_only else "danger-full-access"}"',
            "--skip-git-repo-check", "--json", "-o", str(summary),
            *[arg for server in disabled_mcp_servers() for arg in ("-c", f"mcp_servers.{server}.enabled=false")]]


def attempt(d: Path, rd: Path, wid: str, name: str, prompt: str, a, resume_thread: str = "") -> dict:
    direct = (m.project_key(d), wid.casefold()) not in getattr(_HELD, "keys", set())
    with worker_lifetime(d, wid):
        order = [getattr(a, "recorded_backend", "subscription")] if resume_thread else backend_order(d, getattr(a, "backend", None))
        available = [(backend, backend_key(backend)) for backend in order]
        available = [(backend, key) for backend, key in available if key or backend == "subscription"]
        if not available:
            available = [(order[-1], "")]
        for i, (backend, key) in enumerate(available):
            result = _attempt(d, rd, wid, name, prompt, a, resume_thread, backend, key,
                              unavailable=backend != "subscription" and not key)
            result["prior"] = i > 0
            if not result["infra"] or resume_thread or i == len(available) - 1:
                break
            record(d, wid, a, result, add=True)
        if direct and result["kind"] in ("done", "failed"):
            clean_worker(d, wid, a)
        return result


def _attempt(d: Path, rd: Path, wid: str, name: str, prompt: str, a, resume_thread: str = "", backend: str = "subscription", key: str = "", unavailable: bool = False) -> dict:
    agent, model, effort = m.resolve_model(name)
    rep = d / ".tmp" / "reports"
    rep.mkdir(parents=True, exist_ok=True)
    numbers = [int(mm.group(1)) for p in rep.iterdir()
               if (mm := re.fullmatch(re.escape(wid) + r"\.a(\d+)\.(?:md|events\.jsonl|err\.txt)", p.name, re.I if os.name == "nt" else 0))]
    n = max(numbers, default=0) + 1
    summary, events, err = (rep / f"{wid}.a{n}{ext}" for ext in (".md", ".events.jsonl", ".err.txt"))
    summary.touch(exist_ok=False)
    exe = codex_exe()
    gate = getattr(a, "cls", None) == "gate"
    if resume_thread:
        cmd = [exe, "exec", "resume", *base_cmd(model, effort, a.read_only and not gate, summary), resume_thread, "-"]
    else:
        cmd = [exe, "exec", *base_cmd(model, effort, a.read_only and not gate, summary), "-C", str(rd)]
        for img in getattr(a, "image", None) or []:
            cmd += ["-i", img]
        cmd.append("-")
    pos = 3 if resume_thread else 2
    cmd[pos:pos] = backend_args(backend)
    child_env = dict(os.environ)
    if backend != "subscription":
        child_env[BACKENDS[backend][0]] = key
    before = rollout_usage(resume_thread) if resume_thread else None
    if unavailable:
        code, minutes = -1, 0
        err.write_text(f"{backend}: key missing", encoding="utf-8")
    else:
        code, minutes = run_codex(cmd, rd, prompt, events, err, a.minutes, env=child_env)
    if key:
        for path in (summary, events, err):
            if path.exists():
                text = path.read_text(encoding="utf-8", errors="replace")
                if key in text:
                    path.write_text(text.replace(key, "[redacted]"), encoding="utf-8")
    ev = parse_events(events)
    if not ev["completed"] and not ev["input"] and (ev["thread"] or resume_thread):
        # A failed or killed turn emits no usage event; the session log still has the running total.
        after = rollout_usage(ev["thread"] or resume_thread)
        if after:
            for k in ("input", "cached", "output"):
                ev[k] = max(0, after[k] - (before or {}).get(k, 0))
    try:
        err_text = err.read_text(encoding="utf-8", errors="replace")[-4000:]
    except OSError:
        err_text = ""
    word = status_word(summary)
    progress = ev["tools"] > 0
    success = code == 0 and bool(word)
    interrupted = not success and (code != 0 or ev["errors"] or FALLBACK_ERRORS.search(err_text))
    if success:
        kind = word
    elif code == 0 and ev["completed"]:
        kind = "failed"
    elif interrupted:
        kind = "timeout-partial" if progress else "infra"
    elif not ev["turns"] and not progress:
        kind = "infra"
    else:
        kind = "failed"
    if success:
        try:
            shutil.copyfile(summary, rep / f"{wid}.md")
            target = output_path(d, getattr(a, "out", None))
            if target:
                target.parent.mkdir(parents=True, exist_ok=True)
                text = summary.read_text(encoding="utf-8", errors="replace")
                if gate:   # the parent knows which model ran: score matches labels by model name
                    alias = next((k for k, v in m.MODEL_ALIASES.items() if v[1] == model), model)
                    label = f"REVIEWER: {alias}-{effort}" if effort else f"REVIEWER: {alias}"
                    text, n = re.subn(r"(?im)^\s*REVIEWER:.*$", label, text)
                    if not n:   # keep the score lines last: put the label right before ARTIFACT, else append it
                        text, n = re.subn(r"(?im)^(\s*ARTIFACT:)", label + r"\n\1", text, count=1)
                        if not n:
                            text = text.rstrip("\n") + "\n" + label + "\n"
                target.write_text(text, encoding="utf-8")
        except OSError as e:
            kind = "failed"
            ev["errors"].append(f"report delivery failed: {type(e).__name__}: {e}")
            try:
                with err.open("a", encoding="utf-8") as f:
                    f.write(ev["errors"][-1] + "\n")
            except OSError:
                pass
    return {"name": name, "backend": backend, "model": model, "effort": effort, "code": code, "minutes": minutes, "word": word,
            "kind": kind, "infra": kind == "infra", "ev": ev, "summary": summary, "attempt": n, "end": time.strftime("%Y-%m-%dT%H:%M"),
            "err": (ev["errors"] or [err_text.strip()[-300:]])[-1],
            "capacity": kind == "timeout-partial" and code is not None and bool(CAPACITY_ERRORS.search(" ".join(ev["errors"]) + " " + err_text))}


def record(d: Path, wid: str, a, r: dict, add: bool = False) -> None:
    ev = r["ev"]
    plus = "+" if add or r.get("prior") else ""
    row = next((x for x in read_workers(d) if x.get("id") == wid), {})
    note = f"a{r['attempt']} {r['name']} ended {r['end']}: {r['kind']} ({r['backend']})"
    if r["kind"] == "timeout-partial":
        note += "; partial work in tree; steer to continue"
    if r["err"]:
        note += f"; {r['err'][:300]}"
    fields = {"backend": r["backend"], "agent": "codex", "model": r["model"], "effort": r["effort"], "status": "running",
              "minutes": f"{plus}{r['minutes']:.1f}", "input": f"{plus}{ev['input']}", "cached": f"{plus}{ev['cached']}",
              "output": f"{plus}{ev['output']}", "report": str(r["summary"].relative_to(d)),
              "note": "; ".join(filter(None, [row.get("note"), note]))}
    if ev["thread"]:
        fields["thread"] = ev["thread"]
    if getattr(a, "cls", None):
        fields["class"] = a.cls
    m.upsert_worker(d, wid, fields)


@worker_command
def cmd_run(a) -> None:
    d = Path(a.dir).resolve()
    fm, _ = m.read_state(d)
    chain = m.chain_from(fm, a.model or ("astra" if a.cls == "gate" else None))
    if a.cls == "gate":
        configured = m.chain_from(fm)
        start = next((i for i, n in enumerate(configured) if m.resolve_model(n)[:2] == m.resolve_model(chain[0])[:2]), len(configured))
        chain = [n for n in [chain[0], *configured[start + 1:]] if m.resolve_model(n)[0] == "codex"]
    output_path(d, a.out)
    brief = Path(a.brief).read_text(encoding="utf-8")
    a.read_only = a.read_only or a.cls == "gate"
    a.sha = git(d, "rev-parse", "--verify", "--end-of-options", a.sha + "^{commit}") if a.cls == "gate" else ""
    m.upsert_worker(d, a.id, {"started": time.strftime("%Y-%m-%dT%H:%M"), "ended": "", "class": a.cls, "status": "running",
                            "note": f"ro={int(a.read_only)}" + (f"; sha={a.sha}" if a.sha else "")})
    tried, status = [], "failed"
    try:
        rd = snapshot(d, a.sha) if a.cls == "gate" else real_path(d)
        if a.cls == "gate":
            print(f"{a.id} SNAPSHOT {rd} (share this folder with Opus)", flush=True)
        prompt = brief + footer(d, rd, a.id, a.cls, a.read_only)
        for name in chain:
            agent, model, _ = m.resolve_model(name)
            if agent != "codex":
                status = "fallback"
                print(f"{a.id} FALLBACK {name}: start a Claude worker ({name}) with the same brief {a.brief}; "
                      f"Codex tried: {'; '.join(tried) or 'none'}")
                return
            r = attempt(d, rd, a.id, name, prompt, a)
            record(d, a.id, a, r, add=bool(tried))
            if r["infra"]:
                tried.append(f"{name}: {' '.join(r['err'].split())[:120] or 'no completed attempt'}")
                continue
            used, resumes = r["minutes"], 0
            while r.get("capacity") and r["ev"]["thread"] and resumes < AUTO_RESUMES:
                # Capacity/server error mid-run: continue the same thread (next Codex model in the chain, else the same
                # model after a pause) instead of leaving a timeout for the lead to steer.
                resumes += 1
                later = [n for n in chain[chain.index(name) + 1:] if m.resolve_model(n)[0] == "codex"]
                nxt = later[0] if later else name
                print(f"{a.id} CAPACITY {name}: {' '.join(r['err'].split())[:120]} · resuming the thread with {nxt}", flush=True)
                if nxt == name:
                    time.sleep(float(os.environ.get("CODEX_WORKER_RESUME_WAIT", "60")))
                a.recorded_backend, budget = r["backend"], a.minutes
                a.minutes = max(10.0, budget - used)
                try:
                    r2 = attempt(d, rd, a.id, nxt, RESUME_MESSAGE + footer(d, rd, a.id, a.cls, a.read_only), a,
                                 resume_thread=r["ev"]["thread"])
                finally:
                    a.minutes = budget
                r2["ev"]["thread"] = r2["ev"]["thread"] or r["ev"]["thread"]
                record(d, a.id, a, r2, add=True)
                if r2["infra"]:
                    break
                r, name, used = r2, nxt, used + r2["minutes"]
                model = m.resolve_model(name)[1]
            a.cleanup_terminal = r["kind"] in ("done", "failed")
            status = "timeout" if r["kind"] == "timeout-partial" else r["kind"]
            ev = r["ev"]
            print(f"{a.id} {status.upper()} {name} ({model} {r['effort']}) {r['minutes']:.1f} min · "
                  f"{ev['input'] / 1e6:.2f}M in ({ev['cached'] / 1e6:.2f}M cached) / {ev['output'] / 1e3:.0f}k out · "
                  f"summary {r['summary']}"
                  + (" · partial work in tree; steer to continue" if status == "timeout" else "")
                  + (f" · after fallback from {'; '.join(tried)}" if tried else ""))
            return
        reason = ' '.join('; '.join(tried).split()) or 'no Codex model in the requested chain'
        print(f"ASTRA UNAVAILABLE: {reason}. Normal round: score with --astra-pending; final gate: two configured Claude reviewers (Opus, or Sonnet under sonnet+astra) with --missing-reason."
              if a.cls == "gate" else f"{a.id} FAILED: every model in the chain failed: {reason}")
    finally:
        finalize(d, a, status)


@worker_command
def cmd_steer(a) -> None:
    d = Path(a.dir).resolve()
    row = next((r for r in read_workers(d) if r.get("id") == a.id), None)
    if not row or not row.get("thread"):
        raise SystemExit(f"{a.id}: no Codex thread recorded in audits/workers.csv")
    output_path(d, a.out)
    name = next((n for n, v in m.MODEL_ALIASES.items() if v[1] == row.get("model")), None)
    if name is None:
        name = "astra" if row.get("class") == "gate" else next(
            (n for n in m.chain_from(m.read_state(d)[0]) if m.resolve_model(n)[0] == "codex"), m.DEFAULT_WORKERS)
        _, model, effort = m.resolve_model(name)
        name = next(n for n, v in m.MODEL_ALIASES.items() if v[1] == model) + (f"-{effort}" if effort else "")
    if row.get("effort"):
        name = name.removesuffix("-" + m.resolve_model(name)[2]) + f"-{row['effort']}"
    a.recorded_backend = row.get("backend") or "subscription"
    a.cls = row.get("class")
    a.read_only = a.cls == "gate" or "ro=1" in row.get("note", "").split("; ")
    a.sha = next((s[4:] for s in row.get("note", "").split("; ") if s.startswith("sha=")), "")
    if a.cls == "gate" and not a.sha:
        raise SystemExit("gate thread has no pinned SHA; launch a new gate with --sha")
    m.upsert_worker(d, a.id, {"status": "running", "ended": ""})
    status = "failed"
    try:
        rd = snapshot(d, a.sha) if a.cls == "gate" else real_path(d)
        if a.cls == "gate":
            print(f"{a.id} SNAPSHOT {rd} (share this folder with Opus)", flush=True)
        r = attempt(d, rd, a.id, name, a.message + footer(d, rd, a.id, a.cls, a.read_only),
                    a, resume_thread=row["thread"])
        record(d, a.id, a, r, add=True)
        a.cleanup_terminal = r["kind"] in ("done", "failed")
        status = "failed" if r["infra"] else "timeout" if r["kind"] == "timeout-partial" else r["kind"]
        print(f"{a.id} {status.upper()} (steered) {r['minutes']:.1f} min · summary {r['summary']}"
              + (" · partial work in tree; steer to continue" if status == "timeout" else ""))
    finally:
        finalize(d, a, status)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("run"); p.add_argument("dir"); p.add_argument("--id", required=True); p.add_argument("--brief", required=True)
    p.add_argument("--class", dest="cls", choices=m.WORKER_CLASSES, required=True); p.add_argument("--model")
    p.add_argument("--minutes", type=float, default=60); p.add_argument("--read-only", action="store_true")
    p.add_argument("--keep-scratch", action="store_true", help="retain this worker's .tmp/<id>/ scratch folder")
    p.add_argument("--image", action="append"); p.add_argument("--out"); p.add_argument("--sha"); p.set_defaults(f=cmd_run)
    p = sp.add_parser("steer"); p.add_argument("dir"); p.add_argument("--id", required=True); p.add_argument("message")
    p.add_argument("--minutes", type=float, default=30); p.add_argument("--out"); p.set_defaults(f=cmd_steer)
    p.add_argument("--keep-scratch", action="store_true", help="retain this worker's .tmp/<id>/ scratch folder")
    p = sp.add_parser("backend-args", help="print shell-quoted provider flags (no keys)")
    p.add_argument("backend", choices=BACKENDS)
    p = sp.choices["run"]
    p.add_argument("--backend", choices=BACKENDS, help="start at this backend for this launch")
    a = ap.parse_args()
    if a.cmd == "backend-args":
        print(shlex.join(backend_args(a.backend)))
        return
    if a.cmd == "run" and a.cls == "gate" and not a.sha:
        ap.error("--sha is required for --class gate")
    if not re.fullmatch(r"[\w-]+", a.id):
        ap.error("--id must be a filename component (letters, digits, underscores or hyphens; no dots)")
    a.f(a)


if __name__ == "__main__":
    main()
