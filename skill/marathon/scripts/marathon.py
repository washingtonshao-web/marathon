#!/usr/bin/env python
"""Marathon project helper. Standard library only (contact_sheet.py needs Pillow).

Lifecycle: init -> intake -> set --status running --reason R -> paused | blocked | done.
Use COMMAND --help for syntax. status without a directory lists projects;
status --report gives the progress fact sheet. status/usage --full retain detailed output.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import html
import hashlib
import unicodedata
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
import uuid
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SKILL = Path(__file__).resolve().parent.parent
HOME = Path(os.environ.get("MARATHON_CLAUDE_HOME") or Path.home() / ".claude")  # override for tests
REGISTRY = HOME / "marathon" / "active"
STATUSES = ("intake", "running", "paused", "blocked", "done")
SETTABLE = {"ledger_through", "phase", "progress", "targets_met", "next", "changed", "link", "mode", "budget_hours", "gate_round", "last_score",
            "metrics", "resources", "workers", "worker_fallback", "profile", "lead_style", "rotate_at", "gate", "astra_wait",
            "summary_words", "astra_pending", "ask_wait", "codex_backends"}
DEFAULT_PASS_TOTAL, DEFAULT_FLOOR, PLATEAU_GAIN, PLATEAU_ROUNDS = 85.0, 8.0, 3.0, 3
GITIGNORE = [".tmp/", "research/raw/", "node_modules/", "__pycache__/", "*.bam", "*.bai", "*.cram", "*.crai", "*.fastq.gz", "*.fq.gz", "*.vcf.gz"]
CSV_FIELDS = ["round", "date", "reviewers", "artifact", "total", "critical", "major", "result", "dims", "hours", "rubric", "carried"]
FORECAST_FIELDS = ["date", "after_round", "hours", "next", "end", "chance"]
OVERVIEW_GLOBS = [str(root / "*" / "STATE.md") for root in ([Path(os.environ["MARATHON_REPOS_ROOT"])] if os.environ.get("MARATHON_REPOS_ROOT") else [Path.home() / "repos", Path.cwd().parent])]
# Worker models the user can name (decided 2026-10-19): Codex models run high unless an effort is given ("astra-xhigh");
# "sonnet" / "opus" mean the current Claude models. Default workers: sol61; fallback chain: astra, then sonnet.
MODEL_ALIASES = {"astra": ("codex", "gpt-6-astra", "high"), "sol61": ("codex", "gpt-6.1-sol", "high"),
                 "sol": ("codex", "gpt-6-sol", "high"), "luna": ("codex", "gpt-6-luna", "high"),
                 "sonnet": ("claude", "sonnet", ""), "opus": ("claude", "opus", ""), "fable": ("claude", "fable", ""),
                 "haiku": ("claude", "haiku", "")}
SPOKEN = {"6.1 sol": "sol61", "6.1sol": "sol61", "gpt-6.1-sol": "sol61", "6.1 " + "sonnet": "sol61", "sol 6.1": "sol61",
          "gpt-6-astra": "astra", "gpt-6-sol": "sol", "gpt-6-luna": "luna", "sonnet 5.5": "sonnet", "opus 5.5": "opus"}
CODEX_BACKENDS = ("api", "subscription")
DEFAULT_CODEX_BACKENDS = "subscription"
SPOKEN.update({"api": "api", "subscription": "subscription", "订阅": "subscription"})
DEFAULT_WORKERS, DEFAULT_FALLBACK = "sol61", "astra,sonnet"
# Run modes the user picks by name (2026-10-19). A profile sets a bundle of keys; any key can be changed afterwards.
GATES = ("opus+astra", "opus", "sonnet+astra")
PROFILES = {
    "classic": {"name": "Classic", "about": "as before 2026-10-19: the lead also does hands-on work; Opus/Sonnet workers; Opus gate, Astra at the final gate. Uses the most Claude quota: workers are ~89% of Claude tokens in a run",
                "keys": {"profile": "classic", "lead_style": "hands-on", "rotate_at": "0", "workers": "opus", "worker_fallback": "sonnet",
                         "gate": "opus", "astra_wait": "0", "summary_words": "300"}},
    "claude": {"name": "All Claude", "about": "Claude only: thin rotating Opus lead, Sonnet workers, Opus gate. Workers stay on Claude quota (~89% of a run's Claude tokens)",
               "keys": {"profile": "claude", "lead_style": "thin", "rotate_at": "150", "workers": "sonnet", "worker_fallback": "opus",
                        "gate": "opus", "astra_wait": "0", "summary_words": "300"}},
    "codex": {"name": "Codex workers", "about": "default: thin rotating lead (Claude or Codex host), GPT-6.1-Sol high workers (Astra optional), Opus + Astra gate",
              "keys": {"profile": "codex", "lead_style": "thin", "rotate_at": "150", "workers": "sol61", "worker_fallback": "astra,sonnet",
                       "gate": "opus+astra", "astra_wait": "10", "summary_words": "300"}},
}
DEFAULT_PROFILE = "codex"
LEGACY_PROFILE = "classic"
RUN_KEYS = {"profile", "lead_style", "rotate_at", "workers", "worker_fallback", "gate", "astra_wait", "summary_words", "mode", "codex_backends"}
SPOKEN_PROFILES = {"经典": "classic", "原来": "classic", "全 claude": "claude", "全claude": "claude", "全 " + "cloud": "claude",
                   "codex 工人": "codex", "codex": "codex", "主 codex": "codex", "主codex": "codex", "codex-lead": "codex"}


def run_value(fm: dict, key: str) -> str:
    """Explicit STATE settings win; projects predating profiles retain classic behaviour."""
    profile = "codex" if fm.get("profile") == "codex-lead" else fm.get("profile") or LEGACY_PROFILE
    if key == "profile":
        return profile
    if key in fm and (fm[key] or key == "worker_fallback"):
        return "" if key == "worker_fallback" and fm[key].strip().lower() == "none" else fm[key]
    if key == "codex_backends":
        return "api,subscription" if os.environ.get("MARATHON_API_BASE_URL") and os.environ.get("MARATHON_API_KEY") else DEFAULT_CODEX_BACKENDS
    prof = PROFILES.get(profile, PROFILES[LEGACY_PROFILE])
    return prof["keys"].get(key, "")


MODEL_NICE = {"gpt-6-astra": "GPT-6-Astra", "gpt-6.1-sol": "GPT-6.1-Sol", "gpt-6-sol": "GPT-6-Sol", "gpt-6-luna": "GPT-6-Luna",
              "sonnet": "Claude Sonnet 5.5", "opus": "Claude Opus 5.5", "fable": "Claude Fable 5.1", "haiku": "Claude Haiku 5.5"}


def describe_model(name: str) -> str:
    agent, model, eff = resolve_model(name)
    return MODEL_NICE.get(model, model) + (f" {eff}" if eff else "")


def model_name(name: str, claude_prefix: bool = False) -> str:
    """Ledger, transcript or reviewer label -> display name: 'claude-opus-5-5' / 'opus-5.5-xhigh' / 'astra-high' / 'gpt-6.1-sol'."""
    n = (name or "").strip().lower()
    eff = re.search(r"(?:^|-)(low|medium|high|xhigh|max)(?:-|$)", n)
    eff = f" {eff.group(1)}" if eff else ""
    m = re.match(r"(?:claude-)?(opus|sonnet|haiku|fable)(?:-(\d+)[-.](\d+))?", n)
    if m:
        base = f"{m[1].title()} {m[2]}.{m[3]}" if m[2] else MODEL_NICE[m[1]].removeprefix("Claude ")
        return ("Claude " if claude_prefix else "") + base + eff
    m = re.match(r"gpt-(\d+(?:\.\d+)?)-([a-z]+)", n)
    if m:
        return f"GPT-{m[1]}-{m[2].title()}{eff}"
    base = SPOKEN.get(n.split("-")[0], n.split("-")[0])
    return MODEL_NICE.get(MODEL_ALIASES[base][1], base) + eff if base in MODEL_ALIASES else (name or "?")


def run_config(fm: dict, short: bool = False) -> list[str]:
    """The run's model and process settings, printed at kickoff, every wave and gate start, and after any change."""
    prof_key = run_value(fm, "profile") or DEFAULT_PROFILE
    prof = PROFILES.get(prof_key, PROFILES[DEFAULT_PROFILE])
    chain = worker_chain(fm)
    codex_host = bool(os.environ.get("CODEX_THREAD_ID"))
    lead = "GPT-6-Astra high (Codex)" if codex_host else "Claude Opus 5.5"
    lead = f"verified {fm['lead_verified']}" if fm.get("lead_verified") else f"requested {lead}"
    thin = run_value(fm, "lead_style") != "hands-on"
    rot = int(run_value(fm, "rotate_at") or 0)
    gate = run_value(fm, "gate") or "opus+astra"
    wait = int(run_value(fm, "astra_wait") or 0)
    gate_txt = {"opus+astra": "Opus 5.5 xhigh + Astra high", "opus": "Opus 5.5 xhigh (final adds Astra)",
                "sonnet+astra": "Sonnet 5.5 xhigh + Astra high"}[gate]
    if gate.endswith("+astra"):
        gate_txt += f"; Astra late after {wait} min → go on with {gate.split('+')[0].title()}, merge Astra when it lands" if wait else "; always wait for Astra"
    workers = describe_model(chain[0]) + (" → fallback " + " → ".join(describe_model(n) for n in chain[1:]) if chain[1:] else "")
    notices = (["No profile chosen yet (older project): running as Classic. Use profile=codex to switch."]
               if "profile" not in fm else [])
    if fm.get("handoff_pending"):
        notices.append(f"handoff_pending={fm['handoff_pending']}: start the successor; the current lead remains armed until claim.")
    if short:
        return [f"⚙ {prof['name']} · lead {lead}{' thin' if thin else ' hands-on'} · workers requested {workers} · backends {run_value(fm, 'codex_backends')} · gate requested {gate_txt.split(';')[0]}"
                + (" · " + " · ".join(notices) if notices else "")]
    rotation = f"requested: rotate at the first quiet point past {rot}k tokens" if thin and rot else "no rotation requested"
    if codex_host:
        rotation += "; Codex checkpoint: handoff --save-only"
    return notices + [f"Run config · {prof['name']} (profile {prof_key})",
            f"- Lead: {lead}; {'thin' if thin else 'hands-on'}; {rotation}",
            f"- Workers requested: {workers}; summaries ≤{run_value(fm, 'summary_words') or 300} words",
            f"- Gate requested: {gate_txt}", f"- Codex backends: {run_value(fm, 'codex_backends')}", f"- Mode: {fm.get('mode', 'balanced')}"]


def resolve_model(name: str) -> tuple[str, str, str]:
    """'astra' / 'astra-xhigh' / '6.1 Sol' / 'sonnet' -> (agent, model, effort)."""
    n = name.strip().lower()
    n = SPOKEN.get(n, n)
    base, _, effort = n.partition("-")
    if base not in MODEL_ALIASES or effort not in ("", "low", "medium", "high", "xhigh", "max"):
        raise SystemExit(f"unknown worker model '{name}'; use one of {', '.join(MODEL_ALIASES)} (optionally -low/-medium/-high/-xhigh)")
    agent, model, eff = MODEL_ALIASES[base]
    return agent, model, (effort or eff)


def worker_chain(fm: dict) -> list[str]:
    """Primary worker model first, then the fallbacks, as STATE says (defaults when unset)."""
    names = [run_value(fm, "workers") or DEFAULT_WORKERS] + run_value(fm, "worker_fallback").split(",")
    out = []
    for n in (x.strip() for x in names if x.strip()):
        resolved = resolve_model(n)
        if resolved not in [resolve_model(x) for x in out]:
            out.append(n)
    return out


def chain_from(fm: dict, explicit_model: str | None = None) -> list[str]:
    """A task override may only move forward along the project's authorized chain."""
    chain = worker_chain(fm)
    if not explicit_model:
        return chain
    model = resolve_model(explicit_model)
    for i, name in enumerate(chain):
        if resolve_model(name) == model:
            return [explicit_model] + chain[i + 1:]
    return [explicit_model] + [n for n in chain if resolve_model(n)[0] == "claude"]


def now() -> dt.datetime:
    return dt.datetime.now().replace(microsecond=0)


def iso(t: dt.datetime | None = None) -> str:
    return (t or now()).isoformat(timespec="minutes")


def retry_sharing(fn, tries: int = 40):
    """Windows refuses to replace or open a file another process has open (PermissionError); wait and retry, ~6 s."""
    for i in range(tries):
        try:
            return fn()
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(0.05 + 0.01 * i)


def atomic_write(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    try:
        retry_sharing(lambda: os.replace(tmp, path))
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def read_csv(path: Path, encoding: str = "utf-8") -> list[dict]:
    if not path.exists():
        return []
    def read():
        with path.open(encoding=encoding, newline="") as f:
            return list(csv.DictReader(f))
    return retry_sharing(read)


def write_csv(path: Path, rows: list[dict], fields: list[str], **kw) -> None:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fields, restval="", **kw)
    writer.writeheader()
    writer.writerows(rows)
    atomic_write(path, out.getvalue())


# ---------- STATE.md: "key: value" front matter (same parser as stop_hook.py) ----------
def parse_front(text: str) -> tuple[dict, str]:
    text = text.lstrip("\ufeff").replace("\r\n", "\n")
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        raise SystemExit("STATE.md: no front matter")
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm, m.group(2)


def read_state(d: Path) -> tuple[dict, str]:
    p = d / "STATE.md"
    if (d / ".tmp" / "state-write.json").exists():
        state_transaction(d)
    if not p.exists():
        raise SystemExit(f"{p} not found (run init first)")
    fm, body = parse_front(p.read_text(encoding="utf-8-sig"))
    if fm.get("profile") == "codex-lead":
        fm["profile"] = "codex"
        print("profile codex-lead is now codex (same worker and gate settings)", file=sys.stderr)
    return fm, body


def write_state(d: Path, fm: dict, body: str) -> None:
    if "profile" not in fm:
        for k, v in PROFILES[LEGACY_PROFILE]["keys"].items():
            fm.setdefault(k, v)
        notice = "legacy run pinned to classic (no behaviour change)"
        body = add_to_section(body, "Decisions", f"{iso()} · {notice}")
        print(notice)
    state_transaction(d, "---\n" + "\n".join(f"{k}: {v}" for k, v in fm.items()) + "\n---\n" + body)


def section_parts(body: str, title: str) -> tuple[str, str, str]:
    head, marker, tail = body.partition(f"## {title}\n")
    if not marker:
        return "", "", ""
    end = tail.find("\n## ")
    return head + marker, tail if end == -1 else tail[:end], "" if end == -1 else tail[end:]


def add_to_section(body: str, title: str, line: str) -> str:
    head, section, rest = section_parts(body, title)
    if not head:
        return body.rstrip("\n") + f"\n\n## {title}\n- {line}\n"
    kept = "\n".join(l for l in section.rstrip("\n").splitlines() if l.strip() not in ("-", "1."))
    return head + (kept + "\n" if kept.strip() else "") + f"- {line}\n" + rest


def section_lines(body: str, title: str) -> list[str]:
    return [line for line in section_parts(body, title)[1].splitlines() if line.strip()]


def set_section(body: str, title: str, lines: list[str]) -> str:
    head, section, rest = section_parts(body, title)
    return head + "".join(l + "\n" for l in lines) + ("\n" + rest.lstrip("\n") if rest else "") if head else body


def hours(x) -> float:
    try:
        return float(x or 0)
    except ValueError:
        return 0.0


def work_hours(fm: dict) -> float:
    w = hours(fm.get("work_hours"))
    if fm.get("status") == "running" and fm.get("running_since"):
        try:
            w += (now() - dt.datetime.fromisoformat(fm["running_since"])).total_seconds() / 3600
        except ValueError:
            pass
    return w


# ---------- session registry (read by stop_hook.py) ----------
def reg_path() -> Path | None:
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID")
    return REGISTRY / f"{sid}.json" if sid else None


def claim(d: Path, new_run: bool) -> str:
    p = reg_path()
    if not p:
        fm, body = read_state(d)
        if fm.pop("lead_verified", None):
            write_state(d, fm, body)
        return "no CLAUDE_CODE_SESSION_ID in the environment: auto-continue not registered"
    REGISTRY.mkdir(parents=True, exist_ok=True)
    info = {}
    if p.exists() and not new_run:
        try:
            info = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            info = {}
        if Path(info.get("project", "")) != d:
            info = {}
    if not info:
        info = {"project": str(d), "run": uuid.uuid4().hex[:8], "blocks": 0, "stale": 0, "sig": ""}
    info["claimed"] = iso()
    info.pop("released", None)
    atomic_write(p, json.dumps(info))
    complete = False
    try:   # arm the successor before retiring any earlier lead
        fm, body = read_state(d)
        fm.pop("lead_verified", None)
        if os.environ.get("CLAUDE_MODEL"):
            fm["lead_verified"] = os.environ["CLAUDE_MODEL"]
        ids = lead_sessions(fm, include_current=False)
        complete = bool(fm.get("handoff_pending")) and p.stem not in ids
        fm["lead_sessions"] = ",".join(dict.fromkeys(ids + [p.stem]))
        if complete:
            for old in REGISTRY.glob("*.json"):
                if old.stem not in ids or old.stem == p.stem:
                    continue
                try:
                    project = json.loads(old.read_text(encoding="utf-8")).get("project")
                except (FileNotFoundError, ValueError):
                    continue
                if project and project_key(Path(project)) == project_key(d):
                    old.unlink(missing_ok=True)
            fm.pop("handoff_pending", None)
        write_state(d, fm, body)
    except SystemExit:
        pass
    return ("handoff complete; " if complete else "") + f"auto-continue armed for session {p.stem[:8]} (run {info['run']}, {info['blocks']} continues so far); {set_hook(True)}"


def registered_projects():
    for path in REGISTRY.glob("*.json"):
        try:
            yield path, Path(json.loads(path.read_text(encoding="utf-8"))["project"])
        except (OSError, ValueError, KeyError):
            pass


def unclaim(d: Path) -> str:
    for path, project in registered_projects():
        if project == d:
            try:
                path.unlink()
            except OSError:
                pass
    return release_hook_if_idle()


def release_hook_if_idle() -> str:
    """Remove the Stop hook when no session on this PC has a running marathon registered."""
    if REGISTRY.exists() and any(REGISTRY.glob("*.json")):
        return "hook kept (another marathon is running here)"
    return set_hook(False)


def registry_info(d: Path) -> dict | None:
    p = reg_path()
    if p and p.exists():
        try:
            info = json.loads(p.read_text(encoding="utf-8"))
            return info if Path(info.get("project", "")) == d else None
        except ValueError:
            return None
    return None


# ---------- commands ----------
def cmd_init(a) -> None:
    d = Path(a.dir).resolve()
    existing = [n for n in ("CHARTER.md", "STATE.md", "PROMPTS.md") if (d / n).exists()]
    if existing:
        raise SystemExit(f"{d} already has {', '.join(existing)}; nothing written (resume with claim / set-status running)")
    d.mkdir(parents=True, exist_ok=True)
    subs = {"{title}": a.title, "{type}": a.type, "{date}": iso()[:10], "{datetime}": iso(), "{dir}": str(d),
            "{budget}": f"{a.budget:g}", "{mode}": a.mode}
    for name in ("CHARTER.md", "STATE.md", "PROMPTS.md"):
        t = (SKILL / "templates" / name).read_text(encoding="utf-8")
        for k, v in subs.items():
            t = t.replace(k, v)
        if name == "STATE.md":
            t = re.sub(r"(?m)^(?:ask_wait: 10|asking: *)\n", "", t)  # defaults materialize when used
            state_transaction(d, t)
        else:
            atomic_write(d / name, t)
    rubric = (SKILL / "templates" / f"rubric-{a.type}.txt").read_text(encoding="utf-8").strip()
    ch = (d / "CHARTER.md").read_text(encoding="utf-8").replace("{rubric}", rubric)
    atomic_write(d / "CHARTER.md", ch)
    for sub in ("research/raw", "research/notes", "research/benchmark", "audits", ".tmp"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    gi = d / ".gitignore"
    lines = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    have = {l.strip() for l in lines}
    lines += [x for x in GITIGNORE if x not in have]
    atomic_write(gi, "\n".join(lines) + "\n")
    r = subprocess.run(["git", "-C", str(d), "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        subprocess.run(["git", "-C", str(d), "init", "-q", "-b", "main"], check=False, stdin=subprocess.DEVNULL)
    print(f"created {d} (status intake; the hook stays idle until set-status running)")


def cmd_set_status(a) -> None:
    d = Path(a.dir).resolve()
    fm, body = read_state(d)
    old = fm.get("status")
    if old == "running" and a.status != "running":
        fm["work_hours"] = f"{work_hours(fm):.2f}"
        fm["running_since"] = ""
    if a.status == "running" and old != "running":
        fm["running_since"] = iso()
        u = usage_row()
        if u and not fm.get("tokens_at_start"):
            fm["tokens_at_start"] = f"{u.get('total_tokens', 0)}|{u.get('est_api_cost_usd', 0)}"
    fm["status"] = a.status
    fm["waiting_on"] = ""
    body = add_to_section(body, "Log", f"{iso()} · status {old} → {a.status}: {a.reason}")
    write_state(d, fm, body)
    if a.status == "running":
        print(claim(d, new_run=(old != "running")))
    else:
        print(f"status {a.status}; auto-continue released; {unclaim(d)}")


def cmd_claim(a) -> None:
    d = Path(a.dir).resolve()
    fm, _ = read_state(d)
    if fm.get("status") != "running":
        print(f"status is {fm.get('status')}: nothing armed. To restart the run: set-status {d} running --reason ...")
    else:
        print(claim(d, new_run=False))
    print(f"phase={fm.get('phase')} next={fm.get('next')}")


def cmd_wait(a) -> None:
    if getattr(a, "gate", False):
        return cmd_gate_wait(a)
    d = Path(a.dir).resolve()
    fm, body = read_state(d)
    if a.clear:
        fm["waiting_on"], fm["waiting_since"] = "", ""
    else:
        if not a.what:
            raise SystemExit("say what you wait for, e.g. wait <dir> \"workers W1-W4\"")
        fm["waiting_on"], fm["waiting_since"] = a.what.replace("\n", " "), iso()
    write_state(d, fm, body)
    print("waiting cleared" if a.clear else f"waiting on {fm['waiting_on']} (the hook lets turns end for up to 90 min)")


def input_text() -> str:
    raw = sys.stdin.buffer.read()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("gbk", errors="replace")


def cmd_log(a) -> None:
    d = Path(a.dir).resolve()
    if a.text is None:
        raise SystemExit("log requires text (use - to read stdin)")
    text = a.piped_text if hasattr(a, "piped_text") else input_text() if a.text == "-" else a.text
    who = "lead" if a.lead else "user"
    n = len(re.findall(r"^## #\d+ ", (d / "PROMPTS.md").read_text(encoding="utf-8"), re.M)) + 1
    with (d / "PROMPTS.md").open("a", encoding="utf-8") as f:
        f.write(f"\n## #{n} · {a.at or iso()} · {who}\n{text.strip()}\n")
    print(f"logged #{n} ({who}, {len(text.strip())} chars); after updating the ledger: set <dir> ledger_through={n}")


def cmd_note(a) -> None:
    d = Path(a.dir).resolve()
    fm, body = read_state(d)
    title = {"parked": "Parked for the user", "decision": "Decisions", "next": "Next 3 steps", "now": "Now"}[a.section]
    moved = 0
    if a.section == "now" and not a.add:   # Now says what is true now: replace it, keep the old lines as history in Log
        old = [l[2:].strip() for l in section_lines(body, "Now") if l.startswith("- ") and l[2:].strip()]
        body = set_section(body, "Now", [])
        for l in old:
            body = add_to_section(body, "Log", f"{iso()} · was now: {l}")
        moved = len(old)
    body = add_to_section(body, title, f"{iso()[:10]} {a.text}" if a.section == "decision" else a.text)
    write_state(d, fm, body)
    print(f"added to {title}" + (f" (replaced {moved} old bullet(s), moved to Log)" if moved else ""))


def check_run_key(k: str, v: str) -> None:
    if k == "worker_fallback" and v.strip().lower() == "none":
        return
    if k == "workers" and (not v.strip() or "," in v):
        raise SystemExit("workers takes one primary model")
    if k in ("workers", "worker_fallback"):
        for n in v.split(","):
            if n.strip():
                resolve_model(n)
    elif k == "codex_backends":
        names = v.split(",")
        if not names or any(n not in CODEX_BACKENDS for n in names) or len(set(names)) != len(names):
            raise SystemExit("codex_backends: use a unique comma list of " + ",".join(CODEX_BACKENDS))
    elif k == "profile" and v not in PROFILES:
        raise SystemExit(f"profile must be one of {', '.join(PROFILES)}")
    elif k == "gate" and v not in GATES:
        raise SystemExit(f"gate must be one of {', '.join(GATES)}")
    elif k == "lead_style" and v not in ("thin", "hands-on"):
        raise SystemExit("lead_style must be thin or hands-on")
    elif k in ("astra_wait", "ask_wait", "rotate_at", "summary_words") and not v.isdigit():
        raise SystemExit(f"{k} takes whole minutes / thousands of tokens (0 = off)")


def cmd_set(a) -> None:
    if getattr(a, "status", None):
        return cmd_set_status(a)
    pairs = []
    for kv in a.pairs:
        if "=" not in kv:
            raise SystemExit(f"expected key=value, got {kv}")
        k, v = (x.strip() for x in kv.split("=", 1))
        if k == "codex_backends":
            v = ",".join(SPOKEN.get(n.strip().lower(), n.strip().lower()) for n in v.split(","))
        pairs.append((k, SPOKEN_PROFILES.get(v.lower(), v) if k == "profile" else v))
    for k, v in pairs:
        check_run_key(k, v)
    d = Path(a.dir).resolve()
    fm, body = read_state(d)
    keys = []
    prof = next((v for k, v in pairs if k == "profile"), None)
    if prof:   # a profile sets its whole bundle first; keys named in the same command override it
        fm.update(PROFILES[prof]["keys"])
        keys += [k for k in PROFILES[prof]["keys"] if k not in dict(pairs)]
    for k, v in pairs:
        if k not in SETTABLE:
            raise SystemExit(f"{k} is not settable here (status: set-status; waiting: wait; hours are computed)")
        fm[k] = v.replace("\n", " ")
        keys.append(k)
    if "changed" in keys:
        body = add_to_section(body, "Log", f"{iso()} · {fm['changed']}")
    if set(keys) & RUN_KEYS:
        body = add_to_section(body, "Decisions", f"{iso()} · run config: " + ", ".join(f"{k}={fm[k]}" for k in keys if k in RUN_KEYS))
    write_state(d, fm, body)
    print("STATE updated:", ", ".join(keys))
    if set(keys) & RUN_KEYS:
        print("\n".join(run_config(fm)))


def usage_row(d: Path | None = None) -> dict | None:
    """Report totals only when project transcripts exist; old session baselines are unused."""
    if d is None:
        return None
    rows = usage_ledger(d)
    return {r["part"]: r for r in rows} if any(r["runs"] for r in rows if r["part"] != "Codex runs") else None


def cmd_status(a) -> None:
    if getattr(a, "report", False):
        return cmd_report(a)
    if not a.dir:
        return cmd_overview(a)
    d = Path(a.dir).resolve()
    fm, _ = read_state(d)
    w, budget = work_hours(fm), hours(fm.get("budget_hours"))
    prog = hours(fm.get("progress"))
    eta = f"~{w * (100 - prog) / prog:.1f} h left (rough)" if 10 <= prog < 100 and w >= 0.1 else ""
    parts = [f"**{fm.get('status', '?')}**", f"Phase {fm.get('phase', '?')}", f"{prog:g}%", f"targets {fm.get('targets_met', '?')}",
             f"{w:.1f}/{budget:g} h"] + ([eta] if eta else [])
    if fm.get("last_score"):
        parts.append(f"gate R{fm.get('gate_round')} {fm['last_score']}")
    if fm.get("mode") and fm["mode"] != "balanced":
        parts.append(f"mode {fm['mode']}")
    print("> " + " · ".join(parts))
    print("> " + run_config(fm, short=True)[0] + (f" · Astra for {fm['astra_pending']} still out" if fm.get("astra_pending") else ""))
    if not getattr(a, "full", False):
        scores = [r["total"] for r in read_scores(d) if r.get("total")][-3:]
        running = running_workers(d)
        print("> Gates: " + (" → ".join(scores) or "none"))
        print(f"> Running workers ({len(running)}): " + (", ".join(running) or "none"))
        print("> Waiting on: " + (fm.get("waiting_on") or "none"))
        print("> Next: " + fm.get("next", "").replace("\n", " "))
        return
    for key, label in (("link", "Try it"), ("changed", "Changed"), ("metrics", "Measured")):
        if fm.get(key):
            print(f"> {label}: {fm[key]}")
    print(f"> Next: {fm.get('next', '')}")
    if fm.get("status") == "running":
        info = registry_info(d)
        state = "not armed in this session (run claim)" if not info else (f"released ({info['released']})" if info.get("released") else f"armed, {info.get('blocks', 0)} continues")
        print(f"<!-- auto-continue: {state}{'; waiting on ' + fm['waiting_on'] if fm.get('waiting_on') else ''} -->")


# ---------- progress report (fact sheet for the progress skill) ----------
BOOKKEEPING = (".", ":!STATE.md", ":!DECISIONS.md", ":!PROMPTS.md", ":!CHARTER.md", ":!REPORTS.md", ":!audits", ":!research")
ARCHIVE_MARKER = "# Older decisions and log"


def marathon_archive(d: Path) -> bool:
    p = d / "DECISIONS.md"
    return p.exists() and p.read_text(encoding="utf-8-sig").splitlines()[:1] == [ARCHIVE_MARKER]


def bookkeeping(d: Path):
    return BOOKKEEPING if not (d / "DECISIONS.md").exists() or marathon_archive(d) else tuple(x for x in BOOKKEEPING if x != ":!DECISIONS.md")


WAIT_MAX_MIN, BUNDLE = 90, r"assets/[\w.-]+?-[\w-]{6,}\.js"


def parse_time(s: str) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(s.strip()[:16])
    except (ValueError, AttributeError):
        return None


def ago(t: dt.datetime) -> str:
    h = (now() - t).total_seconds() / 3600
    return f"{h * 60:.0f} min" if h < 1 else f"{h:.1f} h"


def charter_goal(d: Path) -> str:
    p = d / "CHARTER.md"
    if not p.exists():
        return ""
    m = re.search(r"^## Goal\n+(.+?)(?:\n\n|\n## |\Z)", p.read_text(encoding="utf-8-sig").replace("\r\n", "\n"), re.S | re.M)
    g = " ".join(m.group(1).split()) if m else ""
    return g if len(g) <= 240 else g[:237] + "…"


def live_check(url: str, d: Path) -> tuple[str, list[str]]:
    import urllib.request
    flags = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "marathon-report"})
        with urllib.request.urlopen(req, timeout=10) as r:
            code, html = r.status, r.read(400_000).decode("utf-8", "replace")
    except Exception as e:  # HTTPError (401/404/500), timeouts, DNS: report it, never fail the report
        code, html = getattr(e, "code", None), ""
        if code is None:
            return f"{url} → not reachable ({type(e).__name__})", [f"live link not reachable: {url}"]
    line = f"{url} → HTTP {code}"
    if 'type="password"' in html:
        return line + ", password page (bundle not compared; open it with the Playwright profile to see the build)", flags
    if code != 200:
        flags.append(f"live link answers HTTP {code}" + (" (password page?)" if code in (401, 403) else ""))
    live = re.findall(BUNDLE, html)
    local_html = d / "dist" / "index.html"
    local = re.findall(BUNDLE, local_html.read_text(encoding="utf-8", errors="replace")) if local_html.exists() else []
    if live:
        line += f", bundle {live[0].split('/')[-1]}"
        if local:
            same = set(live) == set(local)
            line += " = local dist/" if same else f" ≠ local dist/ ({local[0].split('/')[-1]})"
            if not same:
                flags.append("live site is not the local dist/ build (a newer build is unreleased, or the release did not land)")
    return line, flags


def bar(frac: float, width: int = 20) -> str:
    n = max(0, min(width, round(frac * width)))
    return "█" * n + "░" * (width - n)


def spark(vals: list[float], top: float | None = None) -> str:
    ticks = "▁▂▃▄▅▆▇█"
    lo, hi = min(vals), max(vals + [top or 0])   # scaled up to the pass mark, so the gap to the goal stays visible
    return "".join(ticks[3] if hi == lo else ticks[round((v - lo) / (hi - lo) * 7)] for v in vals)


def pace(totals: list[float], pass_total: float | None) -> tuple[str, str] | None:
    """Points per round over the last 3 rounds, rounds left to the pass mark, and a keep-going/stop verdict on the plateau rule."""
    last = totals[-3:]
    if len(last) < 2:
        return None
    per = (last[-1] - last[0]) / (len(last) - 1)
    line = f"{per:+.1f}/round"
    if pass_total is not None:
        if last[-1] >= pass_total:
            line += f" · {pass_total:g} reached"
        elif per > 0:
            line += f" · {pass_total:g} in ~{math.ceil((pass_total - last[-1]) / per)} rounds"
        else:
            line += f" · {pass_total:g} out of reach"
    if per >= PLATEAU_GAIN / PLATEAU_ROUNDS:
        verdict = f"keep going: {per:+.1f}/round is at or above the plateau line ({PLATEAU_GAIN / PLATEAU_ROUNDS:.1f}/round)"
    else:
        verdict = (f"plateau: {per:+.1f}/round is under {PLATEAU_GAIN / PLATEAU_ROUNDS:.1f}/round; "
                   "change the plan or the goal, or stop")
    return line, verdict


def rate(num: list[dict], fm: dict) -> str | None:
    """Points per work hour over the last 3 scored rounds that recorded their hours, and what the hours left would buy at that rate."""
    rec = [(float(r["total"]), float(r["hours"])) for r in num[-3:] if (r.get("hours") or "").strip()]
    if len(rec) < 2 or rec[-1][1] - rec[0][1] < 0.1:
        return None
    per = (rec[-1][0] - rec[0][0]) / (rec[-1][1] - rec[0][1])
    left = hours(fm.get("budget_hours")) - work_hours(fm)
    return f"{per:+.2f}/h" + (f" · {left:.1f} h left ≈ {per * left:+.1f}" if left > 0 else "")


def read_forecasts(d: Path) -> list[dict]:
    return [r for r in read_csv(d / "audits" / "forecasts.csv") if r.get("date")]


def forecast_lines(d: Path, num: list[dict]) -> list[str]:
    """The last recorded forecast against what happened, and the average miss of all next-gate forecasts that have an outcome."""
    fcs = read_forecasts(d)
    if not fcs:
        return []
    totals = {int(r["round"]): float(r["total"]) for r in num}
    misses = []
    for f in fcs:
        after = int(f["after_round"] or 0)
        nxt = min((k for k in totals if k > after), default=None)
        if nxt is not None and (f.get("next") or "").strip():
            misses.append((f, nxt, totals[nxt] - float(f["next"])))
    f = fcs[-1]
    head = (f"last forecast ({f['date']}, after R{f['after_round']}): next gate {f.get('next') or '?'}, "
            f"end {f.get('end') or '?'}, chance {f.get('chance') or '?'}%")
    hit = next((m for m in misses if m[0] is f), None)
    out = [head + (f" → actual R{hit[1]} {totals[hit[1]]:.1f} ({hit[2]:+.1f})" if hit else " · no new gate since")]
    if len(misses) >= 2:
        out.append(f"next-gate forecasts with an outcome: {len(misses)}, average miss {sum(abs(m[2]) for m in misses) / len(misses):.1f} points"
                   f" (bias {sum(m[2] for m in misses) / len(misses):+.1f})")
    return out


def score_data(d: Path, rows: list[dict], strict: bool = False) -> tuple[list, list, dict | None]:
    try:
        rules = charter_rules(d)
    except (SystemExit, OSError) as exc:
        if strict and isinstance(exc, OSError):
            raise
        rules = None
    num = [r for r in rows if r["round"].isdigit()]
    return num, [float(r["total"]) for r in num], rules


def visual_block(d: Path, fm: dict, rows: list[dict]) -> list[str]:
    """Text-drawn summary for the top of a progress report: bars and a score trend that read the same on phone and PC."""
    prog = hours(fm.get("progress"))
    out = [f"Progress  {bar(prog / 100)}  {prog:g}%"]
    w, budget = work_hours(fm), hours(fm.get("budget_hours"))
    if budget:
        out.append(f"Budget    {bar(w / budget)}  {w:.1f}/{budget:g} h")
    num, totals, rules = score_data(d, rows, strict=True)
    if num:
        goal = f" · pass {rules['pass_total']:g}" if rules else ""
        out.append(f"Score     {spark(totals[-8:], rules["pass_total"] if rules else None)}  {totals[max(0, len(totals) - 8)]:.1f} → {totals[-1]:.1f}{goal}")
        out.append("Last 3    " + " · ".join(f"R{r['round']} {float(r['total']):.1f}" for r in num[-3:]))
        p = pace(totals, rules["pass_total"] if rules else None)
        if p:
            out.append("Pace      " + p[0])
        rt = rate(num, fm)
        if rt:
            out.append("Rate      " + rt)
        try:
            dims = {k: v for k, v in json.loads(num[-1]["dims"]).items() if v is not None}
        except ValueError:
            dims = {}
        if dims:
            floors = rules["floors"] if rules else {}
            low = sorted(dims.items(), key=lambda kv: kv[1])[:2]
            out.append("Weakest   " + " · ".join(f"{k} {v:.1f}" + (f" (floor {floors[k]:g})" if k in floors and v < floors[k] else "")
                                               for k, v in low))
        out += review_table(d, num[-1])[0]
    if fm.get("targets_met"):
        out.append(f"Targets   {fm['targets_met']}")
    return out


def read_scores(d: Path) -> list[dict]:
    return [r for r in read_csv(d / "audits" / "scores.csv") if r.get("round")]


def round_reviews(d: Path, row: dict) -> tuple[list[dict], list[dict], dict]:
    """Each gate reviewer's own report for a scored round (same artifact), the confirming reviews, and the round's weights."""
    try:
        weights = json.loads(row.get("rubric") or "{}").get("weights") or {}
    except ValueError:
        weights = {}
    try:
        order = list(charter_rules(d)["weights"])
    except (SystemExit, OSError):
        order = []
    weights = dict(sorted(weights.items(), key=lambda kv: (-kv[1], order.index(kv[0]) if kv[0] in order else len(order))))
    art = (row.get("artifact") or "").removesuffix("-dirty")
    reviews, confirms = [], []
    for p in sorted((d / "audits" / f"round-{row['round']}").glob("*.md")):
        text = p.read_text(encoding="utf-8-sig", errors="replace")
        who = re.findall(r"^\s*REVIEWER:\s*(\S+)", text, re.M)   # the structured upper-case line, not prose like "Reviewer: fresh …"
        if not who or p.name.upper().startswith("ADJUDICATION"):
            continue
        conf = re.findall(r"^\s*CONFIRM:\s*(\S+)", text, re.M)
        if conf:
            confirms.append({"reviewer": who[-1].lower(), "confirm": conf[-1].lower(), "file": p.name})
            continue
        r = parse_report(p, set(weights), set())
        n = min(len(art), len(r["artifact"] or ""))
        if r["dims"] and (not art or not r["artifact"] or (n >= 7 and art[:n] == r["artifact"][:n])):
            reviews.append(r)
    reviews.sort(key=lambda r: {"claude": 0, "gpt": 1}.get(reviewer_family(r["reviewer"]), 2))
    return reviews, confirms, weights


def weighted(dims: dict, weights: dict) -> float | None:
    ks = [k for k in weights if dims.get(k) is not None]
    return sum(weights[k] * dims[k] for k in ks) / sum(weights[k] for k in ks) * 10 if ks and sum(weights[k] for k in ks) else None


def width(s: str) -> int:
    """Characters a monospace block shows: Chinese characters take two cells."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def cell(s: str, n: int, right: bool = False) -> str:
    pad = " " * max(0, n - width(s))
    return pad + s if right else s + pad


def review_table(d: Path, row: dict) -> tuple[list[str], list[str]]:
    """(two VISUAL lines, per-key table): each reviewer's scores beside the score used, and whose score it was."""
    reviews, _, weights = round_reviews(d, row)
    if not reviews:
        return [], []
    names = []
    for r in reviews:
        base = re.split(r"[-\d]", r["reviewer"] or "?")[0].title() or "?"
        names.append(base if base not in names else f"{base}{sum(n.startswith(base) for n in names) + 1}")
    try:
        used = json.loads(row.get("dims") or "{}")
        carried = json.loads(row.get("carried") or "{}")
    except ValueError:
        used, carried = {}, {}
    ruled = "lead-ruling" in (row.get("reviewers") or "")
    both = "same" if len(names) == 2 else "all same"
    fmt = lambda v: "-" if v is None else f"{v:g}"
    kw = max(8, min(13, max(len(k) for k in weights) if weights else 8))
    line = lambda label, vals, u, src: cell(label, kw) + "".join(" " + cell(v, 5, True) for v in vals) + " " + cell(u, 5, True) + "  " + src
    lines = [f"Gate round {row['round']} · each key uses the lower score" if len(names) == 2 else f"Gate round {row['round']} · each key uses the lowest score",
             line("key", names, "used", "whose")]
    n_ruled = 0
    for k in weights:
        vals, u = [r["dims"].get(k) for r in reviews], used.get(k)
        present = [v for v in vals if v is not None]
        took = [n for n, v in zip(names, vals) if v is not None and v == u]
        if u is None:
            src = "n/a"
        elif took and len(present) > 1 and u > min(present):
            src, n_ruled = "lead ruling", n_ruled + 1
        elif len(took) == len(names) > 1:
            src = both
        elif took:
            src = "+".join(took) + (" lower" if len(present) > 1 else "")
        elif any(k in c and c[k] == u for c in carried.values()):
            src = "carried"
        else:
            src, n_ruled = ("lead ruling" if ruled else "?"), n_ruled + 1
        lines.append(line(k[:kw], [fmt(v) for v in vals], fmt(u), src))
    tots = [weighted(r["dims"], weights) for r in reviews]
    lines.append(line("total", ["-" if t is None else f"{t:.1f}" for t in tots], f"{float(row['total']):.1f}", "from used"))
    crits = [r["critical"] for r in reviews]
    crit, top = int(row.get("critical") or 0), max([c or 0 for c in crits])
    took = [n for n, c in zip(names, crits) if c == crit]
    src = ("lead ruling" if crit < top else both if len(took) == len(names) > 1 else "+".join(took) + " (more)" if took else "?")
    lines.append(line("critical", [fmt(c) for c in crits], str(crit), src))
    pend = "astra-pending" in (row.get("reviewers") or "")
    visual = [f"Reviews   R{row['round']} " + " · ".join(f"{n} {'-' if t is None else f'{t:.1f}'}" for n, t in zip(names, tots))
              + (" · Astra pending" if pend else ""),
              f"Used      {float(row['total']):.1f} lower per key" + (f" · crit {top}→{crit}" if crit != top else "")
              + (f" · {n_ruled} key{'s' if n_ruled > 1 else ''} ruled" if n_ruled else "")]
    return visual, lines


CODEX_ROUTES = {"api": "API", "subscription": "Codex subscription"}


def models_lines(d: Path, fm: dict, rows: list[dict], usage: dict | None) -> list[str]:
    """Which models actually ran: lead and Claude sub-agents from the transcripts, workers from workers.csv, reviewers from the gates."""
    def by_model(models: dict) -> str:
        top = sorted(((model_name(m), r["runs"]) for m, r in models.items() if not m.startswith("<")), key=lambda x: -x[1])
        return " · ".join(f"{n} ×{c}" for n, c in top)
    out = []
    lead = {m: r for m, r in (usage or {}).get("lead", {}).get("models", {}).items() if not m.startswith("<")}
    if lead:
        out.append("Lead     " + " · ".join(model_name(m, True) for m in sorted(lead, key=lambda m: -lead[m]["runs"])))
    else:
        out.append("Lead     " + (fm.get("lead_verified") or ("GPT-6-Astra high (Codex)" if os.environ.get("CODEX_THREAD_ID") else "Claude Opus 5.5")
                                  + " (requested; no Claude transcript)"))
    ws = read_workers(d)
    jobs = [r for r in ws if r.get("class") != "gate" and not (r.get("note") or "").startswith("bake-off ")]
    try:
        primary = model_key({"model": worker_chain(fm)[0]}).split("/")[0]
    except SystemExit:
        primary = ""
    groups: dict = {}
    for r in jobs:
        if r.get("model"):
            g = groups.setdefault(model_key(r), {"runs": 0, "min": 0.0, "row": r})
            g["runs"] += 1
            g["min"] += hours(r.get("minutes"))
    running = sum(1 for r in jobs if r.get("status") not in TERMINAL_WORKER_STATUSES and not r.get("ended"))
    blank = sum(1 for r in jobs if not r.get("model") and r.get("status") in TERMINAL_WORKER_STATUSES)
    total_min = sum(g["min"] for g in groups.values())
    out.append(f"Workers  {len(jobs)} runs · {total_min / 60:.1f} worker-h")
    for key, g in sorted(groups.items(), key=lambda kv: -kv[1]["runs"]):
        name, eff = key.split("/")
        label = model_name(name) + ("" if eff == "unspecified" else " " + eff)
        out.append(f"  {label:<17}{g['runs']:>3} · {g['min'] / 60:.1f} h" + (" fallback" if primary and name != primary else ""))
    if running or blank:
        out.append("  " + " · ".join(x for x in (f"{running} running" if running else "", f"{blank} ended, no model recorded" if blank else "") if x))
    routes: dict = {}
    for r in ws:   # workers and gate runs: which Codex account or API route each used
        if model_family(r) == "codex":
            route = CODEX_ROUTES.get(r.get("backend") or "", r.get("backend") or "not recorded")
            routes[route] = routes.get(route, 0) + 1
    if routes:
        out.append("Codex    " + " · ".join(f"{k} ×{v}" for k, v in sorted(routes.items(), key=lambda kv: -kv[1])))
    subs = (usage or {}).get("Claude sub-agents", {})
    if subs.get("runs"):
        out.append(f"Agents   {by_model(subs['models'])}")   # Claude sub-agents
    runs: list = []   # consecutive rounds with the same reviewers
    for r in rows:
        labels = [x for x in (r.get("reviewers") or "").split("+") if x and x != "lead-ruling" and not x.startswith(("missing:", "astra-pending"))]
        who = " + ".join(re.sub(r"GPT-6-(\w+)", r"\1", model_name(x)) for x in labels) or "?"   # Astra, not GPT-6-Astra: fits 40 columns
        if runs and runs[-1][0] == who:
            runs[-1][1].append(r["round"])
        else:
            runs.append((who, [r["round"]]))
    for who, rnds in runs[-3:]:
        span = f"Gate R{rnds[0]}" + (f"–R{rnds[-1]}" if len(rnds) > 1 else "")
        out.append(f"{span:<8} {who}")
    for r in rows:
        if r["round"].isdigit() and (d / "audits" / f"round-{r['round']}").is_dir():
            for c in round_reviews(d, r)[1]:
                out.append(f"Confirm  R{r['round']} {model_name(c['reviewer'])} · " + ("critical dismissed" if c["confirm"] == "dismiss" else c["confirm"]))
    return out


def print_lines(lines, prefix: str = "  ") -> None:
    for line in lines:
        print(prefix + line)


def cmd_report(a) -> None:
    d = Path(a.dir).resolve()
    fm, body = read_state(d)
    if a.mark:
        text = ""
        if a.save:
            text = (a.saved_text if hasattr(a, "saved_text") else
                    sys.stdin.buffer.read().decode("utf-8-sig") if a.save == "-" else Path(a.save).read_text(encoding="utf-8-sig")).strip()
        sha = _run(["git", "-C", str(d), "rev-parse", "--short", "HEAD"])
        since = fm.get("reported_at") or fm.get("started", "")
        fm["reported_at"], fm["reported_commit"] = iso(), (sha.stdout.strip() if sha and sha.returncode == 0 else "")
        fm["reported_hours"] = f"{work_hours(fm):.2f}"
        fm["reported_score"] = next((r["total"] for r in reversed(read_scores(d)) if r["round"].isdigit()), "")
        write_state(d, fm, body)
        if a.forecast:
            kv = dict(re.findall(r"(next|end|chance)\s*=\s*([\d.]+)", a.forecast))
            if not kv:
                raise SystemExit("--forecast needs next=<score> end=<score> chance=<0-100>")
            num = [r for r in read_scores(d) if r["round"].isdigit()]
            rows_f = read_forecasts(d) + [{"date": iso(), "after_round": num[-1]["round"] if num else "0", "hours": f"{work_hours(fm):.2f}",
                                           "next": kv.get("next", ""), "end": kv.get("end", ""), "chance": kv.get("chance", "")}]
            (d / "audits").mkdir(parents=True, exist_ok=True)
            write_csv(d / "audits" / "forecasts.csv", rows_f, FORECAST_FIELDS)
        if text:
            rp = d / "REPORTS.md"
            old = rp.read_text(encoding="utf-8-sig") if rp.exists() else (
                "# Progress reports\n\nEvery progress report sent to the user, newest last (`marathon.py report --mark --save`).\n")
            atomic_write(rp, old.rstrip("\n") + f"\n\n## {iso()} · since {since[:16]}\n{text}\n")
        print(f"report recorded at {fm['reported_at']} ({fm['reported_commit'] or 'no commit'})" + ("; appended to REPORTS.md" if text else ""))
        return

    flags = []
    since = parse_time(a.since or fm.get("reported_at") or fm.get("started", "")) or now() - dt.timedelta(hours=24)
    label = "given" if a.since else ("last report" if fm.get("reported_at") else "project start")
    print(f"REPORT {d.name} · now {iso()} · since {iso(since)} ({label}, {ago(since)} ago)")
    goal = charter_goal(d)
    if goal:
        print(f"goal: {goal}")
    rows = read_scores(d)
    print("VISUAL (paste as is inside a ``` block, right under the headline):")
    print_lines(visual_block(d, fm, rows))
    u = usage_row(d)
    num_rows = [r for r in rows if r["round"].isdigit()]
    table = review_table(d, num_rows[-1])[1] if num_rows else []
    print("REVIEWS AND MODELS (paste as is inside a second ``` block, right under the visual block):")
    print_lines(table + ([""] if table else []) + models_lines(d, fm, rows, u))

    w, budget = work_hours(fm), hours(fm.get("budget_hours"))
    running = fm.get("status") == "running"
    print(f"status {fm.get('status', '?')} · phase {fm.get('phase', '?')} · progress {fm.get('progress', '?')}% · "
          f"targets {fm.get('targets_met', '?')} · mode {fm.get('mode', 'balanced')}")
    print(f"hours {w:.1f}/{budget:g}" + (f" ({w / budget * 100:.0f}%)" if budget else ""))
    prog = hours(fm.get("progress"))
    print("eta: " + (f"~{w * (100 - prog) / prog:.1f} h left at the pace so far (rough)" if 10 <= prog < 100 and w >= 0.1 else
                     "no reliable estimate from progress: estimate the hours left from the next steps, marked as an estimate"))
    if budget and running:
        if w >= budget:
            flags.append(f"budget used up: {w:.1f}/{budget:g} h, the BUDGET stop is due")
        elif w >= 0.8 * budget:
            flags.append(f"budget at {w / budget * 100:.0f}% ({w:.1f}/{budget:g} h)")
    if u:
        print(f"API-equivalent: lead {usage_dollars(u['lead'])} · Claude sub-agents {usage_dollars(u['Claude sub-agents'])} "
              f"(output lower bound) · Codex {u['Codex runs']['total']:,} tokens (subscription)")
    print(f"worker models {' > '.join(worker_chain(fm))}")
    for key in ("metrics", "resources"):
        print(f"{key}: {fm.get(key) or '(not set)'}")
    if running and not (fm.get("metrics") and fm.get("resources")):
        flags.append("metrics/resources not set in STATE: take the numbers from the files, then `set metrics=… resources=…`")

    if rows:
        num, totals, rules = score_data(d, rows)
        new = [r for r in rows if (parse_time(r["date"]) or since) >= since]
        last = rows[-1]
        trend = " → ".join(f"R{r['round']} {float(r['total']):.1f}" for r in num[-6:])
        print(f"gates: {trend} · last {last['result']} (critical {last['critical']}, major {last['major']}, {last['artifact']})"
              f" · {len(new)} new since")
        p = pace(totals, rules["pass_total"] if rules else None)
        if p:
            print(f"pace (last 3 rounds): {p[0]} · {p[1]}")
        rt = rate(num, fm)
        print(f"rate (points per work hour, last 3 rounds): {rt or 'not measured yet (needs 2 rounds scored by this version, which records hours)'}")
        if label == "last report":
            before = [r for r in num if (parse_time(r["date"]) or since) < since]
            s0 = float(fm["reported_score"]) if (fm.get("reported_score") or "").strip() else (float(before[-1]["total"]) if before else None)
            dh = work_hours(fm) - hours(fm.get("reported_hours")) if fm.get("reported_hours") else None
            print("since last report: " + (f"score {s0:.1f} → {totals[-1]:.1f} ({totals[-1] - s0:+.1f})" if s0 is not None else "no earlier gate")
                  + (f" · +{dh:.1f} work h" if dh is not None else ""))
        for l in forecast_lines(d, num):
            print(l)
        if len(totals) > PLATEAU_ROUNDS and totals[-1] - totals[-1 - PLATEAU_ROUNDS] < PLATEAU_GAIN:
            flags.append(f"score plateau: +{totals[-1] - totals[-1 - PLATEAU_ROUNDS]:.1f} over the last {PLATEAU_ROUNDS} rounds")
    else:
        print("gates: none scored yet")
    scored = {r["round"] for r in rows}
    for rd in sorted((d / "audits").glob("round-*"), key=lambda p: int(re.sub(r"\D", "", p.name) or 0)):
        n = rd.name.split("-", 1)[1]
        if n not in scored:
            print(f"gate R{n}: {'report written, not scored' if (rd / 'gate.md').exists() else 'prompt ready, no report yet'}")

    if fm.get("link") and not a.no_live:
        line, fl = live_check(fm["link"], d)
        print("live " + line)
        flags += fl

    inside = _run(["git", "-C", str(d), "rev-parse", "--is-inside-work-tree"])
    if inside and inside.returncode == 0:
        rc = fm.get("reported_commit") if label == "last report" else ""   # exact range when the last report recorded its commit
        rng = [f"{rc}..HEAD"] if rc and getattr(_run(["git", "-C", str(d), "cat-file", "-e", rc]), "returncode", 1) == 0 else [f"--since={since.isoformat()}"]
        lg = _run(["git", "-C", str(d), "log", *rng, "--format=%h %ad %s", "--date=format:%m-%d %H:%M"])
        commits = lg.stdout.strip().splitlines() if lg and lg.returncode == 0 else []
        print(f"commits since: {len(commits)}")
        print_lines(commits[:8])
        if len(commits) > 8:
            print(f"  … {len(commits) - 8} older")
        lt = _run(["git", "-C", str(d), "log", "-1", "--format=%ct"])
        if running and lt and lt.returncode == 0 and lt.stdout.strip():
            last_c = dt.datetime.fromtimestamp(int(lt.stdout.strip()))
            if (now() - last_c).total_seconds() > 3 * 3600:
                flags.append(f"no commit for {ago(last_c)} while running")
        st = _run(["git", "-C", str(d), "status", "--porcelain", "--", *bookkeeping(d)])
        dirty = [l for l in (st.stdout.splitlines() if st and st.returncode == 0 else []) if l.strip()]
        if dirty:
            mod = [l for l in dirty if not l.startswith("??")]
            names = [l[3:].strip().strip('"') for l in dirty]
            mt = [(d / n).stat().st_mtime for n in names if (d / n).exists()]
            oldest = dt.datetime.fromtimestamp(min(mt)) if mt else None
            print(f"uncommitted: {len(mod)} modified, {len(dirty) - len(mod)} untracked" + (f", oldest change {ago(oldest)} ago" if oldest else ""))
            print_lines(names[:5])
            if mod and oldest and (now() - oldest).total_seconds() > 3600:
                flags.append(f"uncommitted product changes ({len(mod)} files), the oldest {ago(oldest)} old")
        else:
            print("uncommitted: none")

    nxt = [re.sub(r"^(- |\d+\. )", "", l.strip()) for l in section_lines(body, "Next 3 steps") if re.match(r"^(- |\d+\. )\S", l.strip())]
    print(f"next: {fm.get('next') or '(empty)'}")
    print_lines(nxt, "  - ")
    if not fm.get("next") and not nxt:
        flags.append("no next step recorded")
    if fm.get("waiting_on"):
        ws = parse_time(fm.get("waiting_since", ""))
        print(f"waiting on: {fm['waiting_on']}" + (f" (since {iso(ws)}, {ago(ws)})" if ws else ""))
        if ws and (now() - ws).total_seconds() > WAIT_MAX_MIN * 60:
            flags.append(f"waiting for {ago(ws)} (> {WAIT_MAX_MIN} min): check the workers, or `wait --clear`")
    now_lines = [l for l in section_lines(body, "Now") if l.startswith("- ")]
    if len(now_lines) > 6:
        flags.append(f"STATE 'Now' has {len(now_lines)} bullets (old history): the next `note now` replaces it")

    day0 = since.replace(hour=0, minute=0)
    dated = [l for l in history_lines(d, body, "Decisions") if (parse_time(l[2:12]) or dt.datetime.min) >= day0]
    log = [l for l in history_lines(d, body, "Log") if (parse_time(l[2:18]) or dt.datetime.min) >= since and "was now:" not in l]
    for label, lines in (("decisions", dated), ("log", log)):
        print(f"{label} since: {len(lines)}")
        print_lines([l[2:] for l in lines[-8:]])
    parked = [l for l in section_lines(body, "Parked for the user") if l.startswith("- ")]
    print(f"parked for the user: {len(parked)} (candidates for a decision)")
    print_lines([l[2:] for l in parked])

    pr = d / "PROMPTS.md"
    if pr.exists():
        msgs = re.findall(r"^## #(\d+) · (\S+) · user\n(.*?)(?=\n## #|\Z)", pr.read_text(encoding="utf-8-sig").replace("\r\n", "\n"), re.S | re.M)
        new = [(n, " ".join(t.split())) for n, ts, t in msgs if (parse_time(ts) or dt.datetime.min) >= since]
        print(f"user messages since: {len(new)}" + (f" (#{new[0][0]}–#{new[-1][0]})" if new else ""))
        for n, t in new[-6:]:
            print(f"  #{n} {t[:110]}{'…' if len(t) > 110 else ''}")
    print("FLAGS" + ("" if flags else ": none"))
    print_lines(flags, "⚠ ")
    print("(background agents and tasks are not visible to this script: add the ones you are running)")


# ---------- overview of every marathon project on this PC ----------
def project_globs() -> list[str]:
    override = os.environ.get("MARATHON_OVERVIEW_GLOBS")
    return override.split(os.pathsep) if override else list(OVERVIEW_GLOBS)


def find_projects(days: float) -> list[Path]:
    cands = [Path(f) for pat in project_globs() for f in glob.glob(pat)]
    cands += [project / "STATE.md" for _, project in registered_projects()]
    seen, out = set(), []
    for sp in cands:
        try:
            st = sp.stat()
        except OSError:
            continue
        key = (st.st_dev, st.st_ino) if st.st_ino else str(sp.resolve()).lower()   # Deduplicate files reached through multiple paths.
        if key in seen:
            continue
        seen.add(key)
        try:
            fm, _ = read_state(sp.parent)
        except (SystemExit, OSError, ValueError):   # a STATE.md from a non-marathon project
            continue
        if fm.get("status") not in STATUSES or "phase" not in fm:
            continue
        if fm["status"] != "running" and (now().timestamp() - st.st_mtime) > days * 86400:
            continue
        out.append(sp.parent)
    return out


def last_report(d: Path) -> dict:
    rp = d / "REPORTS.md"
    if not rp.exists():
        return {}
    parts = re.split(r"^## (\S+) · since \S*\n", rp.read_text(encoding="utf-8-sig").replace("\r\n", "\n"), flags=re.M)
    if len(parts) < 3:
        return {}
    when, text = parts[-2], parts[-1].strip()
    head = next((l.strip().strip("*").strip() for l in text.splitlines() if l.startswith("**")), "")
    m = re.search(r"^\*\*(?:我的评估|My assessment)\*\*[：:]?\s*\n((?:- .+\n?)+)", text, re.M)
    assess = [l[2:].strip() for l in m.group(1).splitlines() if l.startswith("- ")] if m else []
    items = {m[1].strip(): m[2].strip() for line in assess
             if (m := re.match(r"\*\*(.+?)\*\*\s*[：:]\s*(.*)$", line))}
    if not assess:
        m = re.search(r"^\*\*(?:我的判断|My read)\*\*[：:]\s*(.+)$", text, re.M)
        assess = [m.group(1).strip()] if m else []
    return {"at": when, "headline": head, "assessment": assess, "items": items}


STATUS_WORDS = {"顺利": "ok", "On track": "ok", "一般": "mid", "Mixed": "mid", "有风险": "risk", "At risk": "risk", "偏离": "off", "Off track": "off"}


def item(items: dict, *keys: str) -> str:
    return next((items[k] for k in keys if items.get(k)), "")


def overall(x: dict) -> tuple[str, str, bool]:
    """(word, tone, estimated): the 总体 word from the last structured report, else an estimate from the numbers."""
    o = item(x["last_report"].get("items", {}), "总体", "Overall")
    for w, tone in STATUS_WORDS.items():
        if o.startswith(w):
            return w, tone, False
    if x["status"] == "done":
        return "已收尾", "ok", False
    if not x["scores"]:
        return "太早", "mid", True
    if x["pace"].startswith("-") or "out of reach" in x["pace"] or x["verdict"].startswith("plateau"):
        return "有风险", "risk", True
    return "一般", "mid", True


def age_text(ts: str) -> tuple[str, float]:
    t = parse_time(ts)
    if not t:
        return "还没有报告", 1e9
    h = (now() - t).total_seconds() / 3600
    return (f"{max(1, round(h * 60))} 分钟前" if h < 1 else f"{h:.0f} 小时前" if h < 48 else f"{h / 24:.0f} 天前"), h


def suggestions(items: dict) -> list[str]:
    out = [item(items, f"建议 {i}", f"建议{i}", f"Recommendation {i}") for i in (1, 2, 3)]
    out = [s for s in out if s]
    return out or ([item(items, "建议", "Recommendation")] if item(items, "建议", "Recommendation") else [])


def project_summary(d: Path) -> dict:
    fm, _ = read_state(d)
    num, totals, rules = score_data(d, read_scores(d))
    p = pace(totals, rules["pass_total"] if rules else None) if totals else None
    session = ""
    for path, project in registered_projects():
        if project.resolve() == d.resolve():
            session = path.stem
    prog = hours(fm.get("progress"))
    return {"name": d.name, "dir": str(d), "goal": charter_goal(d), "status": fm.get("status", ""), "phase": fm.get("phase", ""),
            "progress": prog, "hours": round(work_hours(fm), 1), "budget": hours(fm.get("budget_hours")),
            "targets": fm.get("targets_met", ""), "pass": rules["pass_total"] if rules else None,
            "scores": [[int(r["round"]), float(r["total"])] for r in num[-8:]], "pace": p[0] if p else "", "verdict": p[1] if p else "",
            "rate": rate(num, fm) or "", "link": fm.get("link", ""), "waiting_on": fm.get("waiting_on", ""), "next": fm.get("next", ""),
            "reported_at": fm.get("reported_at", ""), "last_report": last_report(d), "cli_session": session,
            "updated": iso(dt.datetime.fromtimestamp((d / "STATE.md").stat().st_mtime))}


def spark_svg(scores: list, pass_total: float | None) -> str:
    w, h, pad = 120, 40, 3
    if not scores:
        return (f'<svg width="{w}" height="{h}" aria-hidden="true"><line x1="0" y1="{h / 2}" x2="{w}" y2="{h / 2}" '
                f'stroke="var(--border-strong)" stroke-dasharray="3 3"/></svg>')
    vals = [t for _, t in scores] + ([pass_total] if pass_total else [])
    lo, hi = min(vals) - 2, max(vals) + 1
    x = lambda i: w / 2 if len(scores) == 1 else pad + i * (w - 2 * pad) / (len(scores) - 1)
    y = lambda v: h - pad - (v - lo) / (hi - lo) * (h - 2 * pad)
    pts = " ".join(f"{x(i):.1f},{y(t):.1f}" for i, (_, t) in enumerate(scores))
    line = (f'<line x1="0" x2="{w}" y1="{y(pass_total):.1f}" y2="{y(pass_total):.1f}" stroke="var(--text-warning)" '
            f'stroke-dasharray="3 3"/>') if pass_total else ""
    return (f'<svg width="{w}" height="{h}" role="img" aria-label="分数趋势">{line}'
            f'<polyline points="{pts}" fill="none" stroke="var(--text-accent)" stroke-width="2"/>'
            f'<circle cx="{x(len(scores) - 1):.1f}" cy="{y(scores[-1][1]):.1f}" r="3" fill="var(--text-accent)"/></svg>')


STATUS_ZH = {"running": "进行中", "paused": "暂停", "blocked": "卡住", "intake": "准备中", "done": "已结束"}
TONE_CSS = {"ok": ("--bg-success", "--text-success"), "mid": ("--surface-1", "--text-secondary"),
            "risk": ("--bg-warning", "--text-warning"), "off": ("--bg-danger", "--text-danger")}


def widget_html(projs: list[dict], sessions: dict) -> str:
    e = html.escape
    cards = []
    for x in projs:
        word, tone, est = overall(x)
        bg, fg = TONE_CSS[tone]
        items = x["last_report"].get("items", {})
        sugs = suggestions(items)
        nm = x["name"]
        age, age_h = age_text(x["reported_at"])
        stale = x["status"] == "running" and 6 < age_h < 1e8
        sess = sessions.get(x["dir"]) or sessions.get(x["name"]) or {}
        sid, label = sess.get("id", ""), sess.get("title") or x["name"]
        tag = f"［会话 {sid}］" if sid else "［会话未找到］"
        left = max(0.0, x["budget"] - x["hours"])
        l3 = " · ".join(f'R{r} <b style="font-weight:500">{t:.1f}</b>' for r, t in x["scores"][-3:]) or "还没评过分"
        pace = x["pace"].replace("/round", "/轮").replace(" in ~", " 约需 ").replace(" rounds", " 轮").replace(" out of reach", " 照现在到不了").replace(" reached", " 已达到")
        rows = []
        for k, v in (("目标", item(items, "目标", "Goal")), ("卡点", item(items, "卡点", "Main problem")),
                     ("改计划", item(items, "改计划", "Plan change")), ("新发现", item(items, "新发现", "New insight"))):
            if v:
                rows.append(f'<dt>{k}</dt><dd>{e(v)}</dd>')
        rows += [f'<dt>建议 {i}</dt><dd>{e(v)}</dd>' for i, v in enumerate(sugs, 1)]
        if not rows:
            rows.append(f'<dt>上次</dt><dd>{e(x["last_report"].get("headline") or "还没有报告")}</dd>')
        btns = []
        if sugs:
            btns.append(f'<button data-p="{e(f"转告「{nm}」：同意建议 1（{sugs[0]}）{tag}")}">同意建议 1 ↗</button>')
        btns.append(f'<button data-p="{e(f"让「{nm}」现在按新格式汇报一次进度{tag}")}">让它汇报 ↗</button>')
        btns.append(f'<button data-p="{e(f"打开「{nm}」的会话{tag}")}">去会话 ↗</button>')
        cards.append(f'''<div class="c"><div class="t"><span class="n">{e(x["name"])}</span><span class="chip" style="background:var({bg});color:var({fg})">{word}{"（估）" if est else ""}</span></div>
<div class="g">{e(x["goal"][:60] + ("…" if len(x["goal"]) > 60 else ""))}</div>
<div class="r"><span>进度</span><div class="b"><i style="width:{min(100, x["progress"]):g}%"></i></div><span>{x["progress"]:g}%</span></div>
<div class="r"><span>预算</span><div class="b"><i class="u" style="width:{min(100, x["hours"] / x["budget"] * 100) if x["budget"] else 0:.0f}%"></i></div><span>{x["hours"]:g}/{x["budget"]:g} h</span></div>
<div class="s">{spark_svg(x["scores"], x["pass"])}<div>{l3}<br>{e(pace) or "—"}<br>{f"及格 {x['pass']:g} · " if x["pass"] else ""}剩 {left:.1f} h</div></div>
<dl>{"".join(rows)}</dl>
<div class="a{" w" if stale or not x["reported_at"] else ""}">报告：{age}{"，已过时" if stale else ""} · {STATUS_ZH.get(x["status"], x["status"])}</div>
<div class="k">{"".join(btns)}</div></div>''')
    return ('''<h2 class="sr-only">所有 marathon 项目的进度卡片：状态、进度、预算、分数趋势和建议</h2>
<style>.ov{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:12px;padding:.5rem 0}
.c{background:var(--surface-2);border:.5px solid var(--border);border-radius:12px;padding:1rem 1.25rem;display:flex;flex-direction:column;gap:8px;font-size:13px}
.t{display:flex;justify-content:space-between;align-items:center;gap:8px}.n{font-weight:500;font-size:16px}
.chip{font-size:12px;padding:2px 10px;border-radius:var(--radius);white-space:nowrap}.g{color:var(--text-secondary)}
.r{display:grid;grid-template-columns:32px minmax(0,1fr) auto;gap:8px;align-items:center;color:var(--text-secondary);font-size:12px}
.b{height:6px;background:var(--surface-1);border-radius:3px;overflow:hidden}.b i{display:block;height:100%;background:var(--text-accent)}.b i.u{background:var(--text-muted)}
.s{display:flex;gap:10px;align-items:center;color:var(--text-secondary);font-size:12px;line-height:1.5}.s svg{flex:0 0 120px}
dl{margin:0;display:grid;grid-template-columns:44px minmax(0,1fr);gap:3px 8px}dt{color:var(--text-secondary)}dd{margin:0}
.a{font-size:12px;color:var(--text-muted)}.a.w{color:var(--text-warning)}.k{display:flex;flex-wrap:wrap;gap:6px;margin-top:auto}.k button{font-size:13px}</style>
<div class="ov">''' + "\n".join(cards) + '''</div>
<script>document.querySelectorAll('.k button').forEach(b=>b.addEventListener('click',()=>sendPrompt(b.dataset.p)));</script>''')


def markdown_table(projs: list[dict], sessions: dict) -> str:
    out = ["| 项目 | 总体 | 进度 / 预算 | 最近三轮 / 速度 | 建议 1（报告时间） |", "|---|---|---|---|---|"]
    for x in projs:
        word, _, est = overall(x)
        sess = sessions.get(x["dir"]) or sessions.get(x["name"]) or {}
        name = f'[{x["name"]}](#{sess["id"]})' if sess.get("id") else x["name"]
        l3 = " · ".join(f"{t:.1f}" for _, t in x["scores"][-3:]) or "还没评分"
        pace = x["pace"].split(" · ")[0].replace("/round", "/轮") if x["pace"] else ""
        sugs = suggestions(x["last_report"].get("items", {}))
        head = x["last_report"].get("headline", "")
        sug = sugs[0] if sugs else (f"上次：{head}" if head else "")
        age, _ = age_text(x["reported_at"])
        cell = f"{sug.replace('|', '/')[:60]}（{age}）" if sug else age
        out.append(f'| {name} | {word}{"（估）" if est else ""} | {x["progress"]:g}% · {x["hours"]:g}/{x["budget"]:g} h | {l3}'
                   f'{" · " + pace if pace else ""} | {cell} |')
    return "\n".join(out)


def cmd_overview(a) -> None:
    order = {"running": 0, "blocked": 1, "paused": 2, "intake": 3, "done": 4}
    best = {}
    for x in (project_summary(d) for d in find_projects(a.days)):
        goal = x["goal"] if x["goal"] and not x["goal"].startswith("<") else ""   # "<…>" is the unfilled template
        key = x["link"] or goal or x["dir"]   # an old copy of a project in another folder has the same live link or goal
        if key not in best or (order.get(x["status"], 9), "~" + best[key]["updated"]) < (order.get(best[key]["status"], 9), "~" + x["updated"]):
            best[key] = x
    projs = sorted(best.values(), key=lambda x: (order.get(x["status"], 9), x["name"]))
    sessions = json.loads(Path(a.sessions).read_text(encoding="utf-8-sig")) if a.sessions else {}
    if a.widget or a.markdown:
        if a.widget:
            Path(a.widget).write_text(widget_html(projs, sessions), encoding="utf-8")
            print(f"widget written to {a.widget} ({len(projs)} projects)")
        if a.markdown:
            print(markdown_table(projs, sessions))
        return
    if a.json:
        print(json.dumps(projs, ensure_ascii=False, indent=1))
        return
    print(f"OVERVIEW · {len(projs)} marathon project(s) · now {iso()} (running, or touched in the last {a.days:g} days)")
    for x in projs:
        sc = " · ".join(f"R{r} {t:.1f}" for r, t in x["scores"][-3:]) or "no gate yet"
        print(f"\n{x['name']} · {x['status']} · {x['progress']:g}% · {x['hours']}/{x['budget']:g} h · targets {x['targets'] or '?'}"
              + (f" · pass {x['pass']:g}" if x["pass"] else ""))
        print(f"  dir {x['dir']}" + (f" · session {x['cli_session'][:8]}" if x["cli_session"] else ""))
        print(f"  last 3: {sc}" + (f" · pace {x['pace']}" if x["pace"] else "") + (f" · rate {x['rate']}" if x["rate"] else ""))
        lr = x["last_report"]
        if lr:
            print(f"  last report {lr['at']}: {lr['headline'][:160]}")
            print_lines([l[:160] for l in lr["assessment"][:7]], "    ")
        else:
            print("  no saved report yet")
        print(f"  next: {x['next'][:160]}" + (f" · waiting on {x['waiting_on']}" if x["waiting_on"] else ""))


# ---------- gate scoring ----------
INT = r"(\d+)(?![\d.])"


def charter_rules(d: Path) -> dict:
    text = (d / "CHARTER.md").read_text(encoding="utf-8-sig")

    def kv(name):
        m = re.search(rf"^{name}:\s*(.+)$", text, re.M)
        return {k: float(v) for k, v in re.findall(r"([a-z0-9_]+)\s*=\s*([\d.]+)", m.group(1))} if m else {}

    weights = kv("RUBRIC")
    if not weights:
        raise SystemExit("INVALID: CHARTER.md has no 'RUBRIC: key=weight, ...' line")
    floors = {k: DEFAULT_FLOOR for k in weights} | kv("FLOOR")
    na = re.search(r"^NA:[ \t]*(.*)$", text, re.M)
    allowed_na = set(re.findall(r"[a-z0-9_]+", na.group(1))) if na else set()
    t = re.search(r"^PASS_TOTAL:\s*([\d.]+)", text, re.M)
    rows = re.findall(r"^\|\s*(G\d+)\s*\|(.*)\|\s*$", text, re.M)
    met = sum(1 for _, rest in rows if "✅" in rest.split("|")[-1])
    return {"weights": weights, "floors": floors, "na": allowed_na, "pass_total": float(t.group(1)) if t else DEFAULT_PASS_TOTAL,
            "targets": (met, len(rows))}


def report_keys(path: Path) -> set:
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        s = line.strip().strip("`*> ")
        if s.upper().startswith("SCORES:"):
            return set(re.findall(r"([a-z0-9_]+)\s*=", s.split(":", 1)[1]))
    return set()


def parse_report(path: Path, keys: set, allowed_na: set) -> dict:
    r = {"dims": {}, "critical": None, "major": None, "artifact": None, "reviewer": None, "problems": []}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        s = line.strip().strip("`*> ")
        u = s.upper()
        if u.startswith("SCORES:"):
            for k, v in re.findall(r"([a-z0-9_]+)\s*=\s*(n/a|[\d.]+)", s.split(":", 1)[1], re.I):
                r["dims"][k] = None if v.lower() == "n/a" else float(v)
        elif u.startswith("VERDICT"):
            c, mj = re.search(rf"critical\s*=\s*{INT}", s, re.I), re.search(rf"major\s*=\s*{INT}", s, re.I)
            r["critical"], r["major"] = (int(c.group(1)) if c else None), (int(mj.group(1)) if mj else None)
        elif u.startswith("ARTIFACT:"):
            r["artifact"] = s.split(":", 1)[1].strip()
        elif u.startswith("REVIEWER:"):
            r["reviewer"] = s.split(":", 1)[1].strip().lower()
    dims, p, name = r["dims"], r["problems"], path.name
    if keys - dims.keys():
        p.append(f"{name}: missing dimensions {sorted(keys - dims.keys())}")
    if dims.keys() - keys:
        p.append(f"{name}: unknown dimensions {sorted(dims.keys() - keys)}")
    if [k for k, v in dims.items() if v is not None and not 0 <= v <= 10]:
        p.append(f"{name}: scores outside 0-10")
    bad_na = sorted(k for k, v in dims.items() if v is None and k not in allowed_na)
    if bad_na:
        p.append(f"{name}: n/a for keys the CHARTER NA line doesn't allow {bad_na}")
    if r["critical"] is None or r["major"] is None:
        p.append(f"{name}: VERDICT line lacks whole-number critical= and major=")
    if not r["artifact"]:
        p.append(f"{name}: no 'ARTIFACT: <commit>' line")
    if not r["reviewer"]:
        p.append(f"{name}: no 'REVIEWER: <model>' line")
    return r


def current_artifact(d: Path) -> str:
    sha = _run(["git", "-C", str(d), "rev-parse", "--short", "HEAD"])
    # bookkeeping (STATE, PROMPTS, CHARTER, audits, research) changes during gating and is not part of the product
    dirty = _run(["git", "-C", str(d), "status", "--porcelain", "--untracked-files=all", "--", *bookkeeping(d)])
    s = sha.stdout.strip() if sha and sha.returncode == 0 else "uncommitted"
    return s + ("-dirty" if not dirty or dirty.returncode or dirty.stdout.strip() else "")


DISAGREE_POINTS, DISAGREE_TOTAL = 3.0, 10.0   # Opus vs GPT gap that the lead must adjudicate (decided 2026-10-19)


def reviewer_family(name: str) -> str:
    if re.search(r"\b(astra|gpt|codex|sol\d*|luna|openai)\b", name or "", re.I):
        return "gpt"
    return "claude" if (name or "").lower().startswith("sonnet") or re.search(r"\b(claude|opus|sonnet|fable)\b", name or "", re.I) else "unknown"


def disagreements(reports: list[dict], weights: dict) -> list[str]:
    """Compare every Claude/GPT pair: key ≥3, total ≥10, or critical found by only one side."""
    out = []
    tot = lambda r, keys: sum(weights[k] * r["dims"][k] for k in keys) / max(1e-9, sum(weights[k] for k in keys)) * 10
    for a in (r for r in reports if reviewer_family(r["reviewer"]) == "claude"):
        for b in (r for r in reports if reviewer_family(r["reviewer"]) == "gpt"):
            for k in weights:
                va, vb = a["dims"].get(k), b["dims"].get(k)
                if va is not None and vb is not None and abs(va - vb) >= DISAGREE_POINTS:
                    out.append(f"key {k}: {a['reviewer']}={va:g} vs {b['reviewer']}={vb:g}")
            shared = {k for k in weights if a["dims"].get(k) is not None and b["dims"].get(k) is not None}
            if shared and abs(tot(a, shared) - tot(b, shared)) >= DISAGREE_TOTAL:
                out.append(f"total: {a['reviewer']}={tot(a, shared):.1f} vs {b['reviewer']}={tot(b, shared):.1f}")
            if bool(a["critical"]) != bool(b["critical"]):
                out.append(f"critical: {a['reviewer']}={a['critical']} vs {b['reviewer']}={b['critical']}")
    return out


def parse_adjudication(path: Path, weights: dict, *, split: list[str] | None = None, critical: int = 0, d: Path | None = None) -> tuple[dict, dict, list[str]]:
    """Validate bounded rulings and identifiable evidence; counts also holds TOTAL ACCEPTED."""
    keys, counts, problems = {}, {}, []
    if not path.exists():
        return keys, counts, [f"{path} not found"]
    evidence = (r"https?://\S+|[\w.-]+[/\\][\w./\\-]+|\b[\w.-]+:\d+\b|"
                r"[\w.-]+\.(?:py|pyi|js|jsx|ts|tsx|html|css|scss|json|md|txt|csv|tsv|xml|yaml|yml|toml|ini|cfg|"
                r"png|jpe?g|gif|webp|svg|pdf|log|sh|ps1|bat|cmd|sql|go|rs|java|c|cpp|h|hpp|cs|vue|svelte|rb|php)\b|"
                r"\b(?:screenshot|shot|step)\s*#?\s*\d+\b|\btest[_-]\w+")
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        s = line.strip().lstrip("-* ")
        if not re.match(r"(?:KEY|CRITICAL|MAJOR|TOTAL)\b", s, re.I):
            continue
        parts = re.split(r"\s+because\s+", s, maxsplit=1, flags=re.I)
        if len(parts) != 2 or len(parts[1].strip()) < 10 or not re.search(evidence, parts[1], re.I):
            problems.append(f"{path.name}: every ruling needs a because reason of at least 10 characters citing evidence")
            continue
        ruling = parts[0]
        mk = re.fullmatch(r"KEY\s+([a-z0-9_]+)\s*=\s*(\S+)", ruling, re.I)
        mc = re.fullmatch(r"(CRITICAL|MAJOR)\s*=\s*(\d+)", ruling, re.I)
        if mk:
            k = mk.group(1).lower()
            try:
                value = float(mk.group(2))
            except ValueError:
                value = float("nan")
            if k not in weights:
                problems.append(f"{path.name}: unknown key {k}")
            elif not 0 <= value <= 10:
                problems.append(f"{path.name}: KEY {k} must be 0-10")
            else:
                keys[k] = value
        elif mc:
            counts[mc.group(1).lower()] = int(mc.group(2))
        elif re.fullmatch(r"TOTAL\s+ACCEPTED", ruling, re.I):
            counts["total_accepted"] = True
        else:
            problems.append(f"{path.name}: malformed ruling (KEY 0-10; CRITICAL/MAJOR non-negative integers): {ruling}")
    if not keys and not counts:
        problems.append(f"{path.name}: no valid rulings")
    if split is not None:
        disputed = {x.split(":")[0].split()[-1] for x in split if x.startswith("key ")}
        total = any(x.startswith("total:") for x in split)
        if not total and keys.keys() - disputed:
            problems.append(f"{path.name}: no dispute covers KEY rulings {sorted(keys.keys() - disputed)}")
        if not split and not (set(counts) == {"critical"} and not keys and counts["critical"] < critical):
            problems.append(f"{path.name}: no dispute to adjudicate (only a confirmed CRITICAL reduction is allowed)")
        for k in sorted(disputed - keys.keys()):
            problems.append(f"{path.name}: no ruling for disputed key {k}")
        if any(x.startswith("critical") for x in split) and "critical" not in counts:
            problems.append(f"{path.name}: no CRITICAL ruling for the disputed critical count")
        if total and not keys and not counts.get("total_accepted"):
            problems.append(f"{path.name}: no KEY ruling or TOTAL ACCEPTED ruling for the total dispute")
        if counts.get("critical", critical) < critical and not confirmed_dismissal(d, path):
            problems.append(f"{path.name}: lowering CRITICAL needs CONFIRMED BY <file path> to a confirming fresh review "
                            "containing REVIEWER: and CONFIRM: dismiss")
    return keys, counts, problems


def resolve_artifact(d: Path, ref: str) -> str | None:
    r = _run(["git", "-C", str(d), "rev-parse", "--verify", "--end-of-options", ref + "^{commit}"])
    return r.stdout.strip() if r and r.returncode == 0 else None


def gate_reviewers(fm: dict, reviewers: list[str], final: bool, pending: bool, reason: str) -> tuple[str, list[str]]:
    gate = run_value(fm, "gate") or "opus+astra"
    claude = "sonnet" if gate == "sonnet+astra" else "opus"
    gate = f"{claude}+astra" if final else gate
    families = {f: {r for r in reviewers if r.lower().startswith(model)}
                for f, model in (("claude", claude), ("gpt", "astra"))}
    required = {"claude": 1} | ({"gpt": 1} if gate.endswith("+astra") else {})
    missing = [f for f, n in required.items() if len(families[f]) < n]
    problems = ["reviewer labels must not contain +"] if any("+" in r for r in reviewers) else []
    if reason and len(reason.strip()) < 10:
        problems.append("--missing-reason must contain at least 10 characters")
    if pending and (final or missing != ["gpt"] or not families["claude"]):
        problems.append(f"--astra-pending is allowed only when Astra is the missing reviewer and {claude.title()} is present")
    if missing and not (pending and not final and missing == ["gpt"] and families["claude"]):
        allowed = bool(reason and len(reason.strip()) >= 10)
        if final:
            allowed = allowed and missing == ["gpt"] and len(families["claude"]) >= 2
        if not allowed:
            problems.append(f"gate {gate} needs required reviewer models ({claude}/claude, astra/gpt): {', '.join(missing)}" +
                            (f"; final gate needs two different reviewers, or two distinct {claude.title()} reviewers and --missing-reason for Astra" if final else
                             "; supply the reports, --astra-pending for Astra only, or --missing-reason"))
    return "".join(f"+missing:{f}" for f in missing) if reason else "", problems


def confirmed_dismissal(d: Path, path: Path) -> bool:
    for ref in re.findall(r"^\s*CONFIRMED BY\s+(.+?)\s*$", path.read_text(encoding="utf-8-sig"), re.M | re.I):
        file = Path(ref.strip().strip('"'))
        candidates = [file] if file.is_absolute() else [d / file, path.parent / file]
        for candidate in candidates:
            if candidate.is_file() and candidate.resolve() != path.resolve():
                text = candidate.read_text(encoding="utf-8-sig")
                if re.search(r"^\s*REVIEWER:\s*\S+", text, re.M | re.I) and re.search(r"^\s*CONFIRM:\s*dismiss\s*$", text, re.M | re.I):
                    return True
    return False


def previous_round(rows: list[dict], rnd: int) -> dict | None:
    eligible = [r for r in rows if r["round"].isdigit() and int(r["round"]) < rnd]
    return max(enumerate(eligible), key=lambda item: (int(item[1]["round"]), item[0]))[1] if eligible else None


def cmd_evidence(a) -> None:
    d = Path(a.dir).resolve()
    if a.round < 1:
        raise SystemExit("INVALID: --round must be positive")
    head = resolve_artifact(d, "HEAD")
    if not head or current_artifact(d).endswith("-dirty"):
        raise SystemExit("INVALID: evidence needs a committed, clean candidate")
    prev = previous_round(read_scores(d), a.round)
    if prev:
        base = resolve_artifact(d, prev["artifact"])
        if not base:
            raise SystemExit("INVALID: previous scored artifact cannot be resolved; restore it before gathering evidence")
        origin = f"round {prev['round']} ({base})"
    else:
        empty = _run(["git", "-C", str(d), "hash-object", "-t", "tree", "--stdin"], input="", errors="strict")
        base = empty.stdout.strip() if empty and empty.returncode == 0 else None
        origin = "project start (empty tree; includes the initial file inventory)"
    outputs = []
    for flag in ("--stat", "--name-status"):
        result = _run(["git", "-C", str(d), "diff", "--no-ext-diff", "--no-textconv", flag, base or "", head, "--"])
        if not result or result.returncode:
            raise SystemExit("INVALID: git diff failed; no evidence pack written")
        outputs.append(result.stdout.strip() or "(no changes)")
    pack = d / "audits" / f"round-{a.round}" / "evidence"
    if pack.exists():
        raise SystemExit("INVALID: evidence pack already exists; preserve it or archive it before rebuilding this round")
    changed = (f"# Changes for round {a.round}\n\nArtifact: {head}\nBaseline: {origin}\n\n"
               f"## git diff --stat\n\n```text\n{outputs[0]}\n```\n\n"
               f"## Changed files (git diff --name-status)\n\n```text\n{outputs[1]}\n```\n")
    prior = (f"Round {prev['round']}: critical={prev['critical']}, major={prev['major']}; "
             f"read audits/round-{prev['round']}/ reports and rulings.\n" if prev else "No earlier scored round.\n")
    index = (f"# Evidence for round {a.round}\n\nArtifact: {head}\nChanges: [CHANGED.md](CHANGED.md)\n"
             "Status: NOT FILLED — the pre-gate Codex ops worker must replace every TODO.\n\n"
             "## Hard-check outputs and test counts\n\nTODO: commands, environment, exit codes, passed/failed/skipped counts and log paths.\n\n"
             "## Screenshots/contact sheets\n\nTODO: paths, viewports/states and capture commands; include desktop/mobile when applicable.\n\n"
             "## Live URL checks\n\nTODO: URLs, timestamps, responses and deployed artifact identity; mark unavailable/not applicable explicitly.\n\n"
             "## Known open defects carried from the last round\n\n" + prior +
             "TODO: every open critical/major ID, rubric key, evidence, status and prior report/ruling links; verify before writing none.\n\n"
             "## Review inputs\n\nTODO: shared snapshot path, CHARTER/PROMPTS/benchmark copies, highest-weight rubric keys, "
             "Astra current findings when available (otherwise previous round), and frozen external inputs.\n")
    pack.mkdir(parents=True)
    atomic_write(pack / "CHANGED.md", changed)
    atomic_write(pack / "EVIDENCE.md", index)
    print(pack)


def cmd_gate_wait(a) -> None:
    d = Path(a.dir).resolve()
    fm, body = read_state(d)
    if a.start:
        fm["gate_started"], fm["gate_round_open"] = now().isoformat(timespec="seconds"), str(a.round)
        write_state(d, fm, body)
        print(f"gate round {a.round} started {fm['gate_started']}")
        return
    try:
        started = dt.datetime.fromisoformat(fm.get("gate_started") or "")
        elapsed = max(0, (now().astimezone() - started.astimezone()).total_seconds() / 60)
    except ValueError:
        raise SystemExit("INVALID: no valid gate_started; run gate-wait --start first")
    if fm.get("gate_round_open") != str(a.round):
        raise SystemExit("INVALID: this round has no open gate timer; run gate-wait --start")
    wait = int(run_value(fm, "astra_wait") or 0)
    print(f"round {a.round}: {elapsed:.1f} minutes elapsed")
    print("GO: Astra is past astra_wait; score with --astra-pending" if wait and elapsed >= wait else
          f"WAIT ({elapsed:.1f} of {wait} min)" + ("; always wait" if not wait else ""))


def score_invalid(message: str) -> None:
    print("INVALID\n" + message)
    sys.exit(2)


def partial_score(a, fm: dict, rows: list[dict], rnd: str) -> tuple[dict | None, str]:
    before = next((r for r in reversed(rows) if r["round"] == rnd), None) if a.late else None
    if a.late and not before:
        score_invalid(f"--late: round {rnd} has no earlier score to merge into")
    pending = {r.strip() for r in fm.get("astra_pending", "").split(",") if r.strip()}
    if a.astra_pending or a.late:
        (pending.add if a.astra_pending else pending.discard)(f"round-{rnd}")
    fm["astra_pending"] = ",".join(sorted(pending, key=lambda r: int(r.removeprefix("round-"))))
    return before, ("+astra-pending" if a.astra_pending else "") + ("+late" if a.late else "")


def cmd_score(a) -> None:
    if a.final and a.carry_forward:
        score_invalid("final gate requires full reviews; no --carry-forward")
    if a.final and (a.astra_pending or a.late):
        score_invalid("the final gate waits for both reviewers (gate.md): no --astra-pending or --late")
    if a.reuse_round is not None and (not a.final or a.src or a.round or a.carry_forward or a.adjudication or a.missing_reason):
        score_invalid("--reuse-round requires --final without new reports, round, carry-forward or overrides")
    if not a.src and a.reuse_round is None:
        score_invalid("supply --from reports or --final --reuse-round N")
    d = Path(a.dir).resolve()
    rules = charter_rules(d)
    rubric = json.dumps(rules | {"na": sorted(rules["na"])}, sort_keys=True)
    weights, floors = rules["weights"], rules["floors"]
    fm, body = read_state(d)
    merged, crit, major, problems, reviewers, prev, reports, carried = {}, 0, 0, [], [], None, [], {}
    rows = read_csv(d / "audits" / "scores.csv")
    m = re.search(r"round-(\d+)", str(a.src[0]) if a.src else "")
    rnd = "final" if a.final else str(a.round or (m.group(1) if m else ""))
    if not a.final and not rnd.isdigit():
        score_invalid("round number missing: use audits/round-N/ or --round N")
    before, partial = partial_score(a, fm, rows, rnd)
    actual = current_artifact(d) if not a.late else None
    artifact = before["artifact"] if before else a.artifact or actual
    candidate = resolve_artifact(d, artifact.removesuffix("-dirty"))
    if a.artifact is not None:
        supplied = resolve_artifact(d, a.artifact)
        if not supplied:
            problems.append("--artifact must resolve to a real commit")
        elif a.late and supplied != candidate:
            problems.append("--late --artifact must match the artifact recorded for that round")
        elif not a.late:
            artifact, candidate = supplied, supplied
    if a.final:
        if actual.endswith("-dirty") or actual == "uncommitted":
            problems.append("final gate needs a committed, clean candidate (tracked and untracked product files)")
        if candidate != resolve_artifact(d, "HEAD"):
            problems.append("final gate --artifact must match HEAD")
    if a.carry_forward or a.reuse_round is not None:
        prior = (next((r for r in reversed(rows) if r["round"] == str(a.reuse_round)), None)
                 if a.reuse_round is not None else previous_round(rows, int(rnd)))
        prev = json.loads(prior["dims"]) if prior else None
        if a.carry_forward:
            if prev is None:
                problems.append("--carry-forward needs an earlier scored round")
            elif set(weights) - prev.keys():
                problems.append("--carry-forward cannot supply new rubric keys; obtain full reviews")
        elif not prior or prior["result"] != "TARGET MET":
            problems.append("--reuse-round needs a passing regular round")
        elif json.loads(prior.get("carried") or "{}"):
            problems.append("--reuse-round needs full reviews; this round has carried scores")
        elif prior.get("rubric") != rubric:
            problems.append("--reuse-round needs unchanged scoring rules (rubric, floors, NA, pass total and targets)")
        elif prior["artifact"].endswith("-dirty") or resolve_artifact(d, prior["artifact"]) != candidate:
            problems.append("--reuse-round artifact must equal the current clean candidate SHA")
        else:
            reviewers = prior["reviewers"].split("+")
            if any(r.startswith(("missing:", "astra-pending")) for r in reviewers):
                problems.append("--reuse-round needs a complete dual round")
            crit, major = int(prior["critical"]), int(prior["major"])
    for src in a.src or []:
        rp = Path(src) if os.path.isabs(src) else d / src
        if not rp.exists():
            problems.append(f"{rp} not found")
            continue
        keys = (report_keys(rp) & set(weights)) or set(weights) if prev else set(weights)
        r = parse_report(rp, keys, rules["na"])
        problems += r["problems"]
        reports.append(r)
        omitted = set(weights) - r["dims"].keys()
        if prev and omitted:
            if (r["reviewer"] or "").startswith("astra"):
                problems.append(f"{rp.name}: Astra must score every key every round")
            if (r["reviewer"] or "").startswith("sonnet" if run_value(fm, "gate") == "sonnet+astra" else "opus") and int(rnd) % 3 == 0:
                problems.append(f"{rp.name}: {(r['reviewer'] or 'opus').split('-')[0].title()} must score every key every third regular round")
            carried[r["reviewer"] or "?"] = {k: prev.get(k) for k in weights if k in omitted}
            if any(prev.get(k) is None and k not in rules["na"] for k in omitted):
                problems.append(f"{rp.name}: carried n/a is no longer allowed by CHARTER")
        if r["artifact"] and (not candidate or resolve_artifact(d, r["artifact"]) != candidate):
            problems.append(f"{rp.name}: reviewed artifact {r['artifact']} but the candidate is {artifact}")
        reviewers.append(r["reviewer"] or "?")
        crit, major = max(crit, r["critical"] or 0), max(major, r["major"] or 0)
        for k, v in (carried.get(r["reviewer"], {}) | r["dims"]).items():
            if merged.get(k) is None or (v is not None and v < merged[k]):
                merged[k] = v
    missing, more = gate_reviewers(fm, reviewers, a.final, a.astra_pending, a.missing_reason or "")
    problems += more
    adjudicated = ""
    split = [] if problems else disagreements(reports, weights)
    if split or a.adjudication:
        if not a.adjudication:
            print(f"ADJUDICATE\n{'Sonnet' if run_value(fm, 'gate') == 'sonnet+astra' else 'Opus'} and GPT disagree; the lead rules in audits/round-N/ADJUDICATION.md and reruns "
                  "score with --adjudication <file>:\n" + "\n".join("  " + s for s in split) +
                  "\nLines: 'KEY <key> = <score> because …', 'CRITICAL = <n> because …', 'MAJOR = <n> because …'. "
                  "Pick either reviewer's score or set your own; dismissing a finding needs a reason that cites evidence.")
            sys.exit(3)
        ap = Path(a.adjudication) if os.path.isabs(a.adjudication) else d / a.adjudication
        keys, counts, more = parse_adjudication(ap, weights, split=split, critical=crit, d=d)
        problems += more
        merged.update(keys)
        crit, major = counts.get("critical", crit), counts.get("major", major)
        adjudicated = "+lead-ruling"
    if prev:
        for k in weights if a.carry_forward else prev:
            merged.setdefault(k, prev.get(k))
    scored = {k: v for k, v in merged.items() if v is not None}
    if not problems and sum(weights[k] for k in scored) < 0.6 * sum(weights.values()):
        problems.append("less than 60% of the rubric weight was scored")
    if problems:
        score_invalid("\n".join(problems))
    total = sum(weights[k] * v for k, v in scored.items()) / sum(weights[k] for k in scored) * 10
    low = [f"{k}={v:g}<{floors[k]:g}" for k, v in scored.items() if v < floors[k]]
    met, n_targets = rules["targets"]
    targets_ok = n_targets > 0 and met == n_targets
    passed = total >= rules["pass_total"] and not low and crit == 0 and targets_ok
    fm["targets_met"] = f"{met}/{n_targets}"
    rows = [r for r in rows if r is not before]
    history = {int(r["round"]): float(r["total"]) for r in rows if r["round"].isdigit()}
    if not a.final:
        history[int(rnd)] = total
    totals = [history[k] for k in sorted(history) if a.final or k <= int(rnd)]
    over_budget = work_hours(fm) >= hours(fm.get("budget_hours")) > 0
    result = "BUDGET" if over_budget else "FINAL FAIL" if a.final else "CONTINUE"
    if passed:
        result = "FINAL PASS" if a.final else "TARGET MET"
    elif not a.final and len(totals) > PLATEAU_ROUNDS and totals[-1] - totals[-1 - PLATEAU_ROUNDS] < PLATEAU_GAIN:
        result = "PLATEAU"
    who = "+".join(reviewers) + missing + adjudicated + partial
    if a.reuse_round is not None:
        who += f"+reuse-round:{a.reuse_round}"
    rows.append({"round": rnd, "date": iso(), "reviewers": who, "artifact": artifact, "total": f"{total:.1f}",
                 "critical": crit, "major": major, "result": result, "dims": json.dumps(merged, ensure_ascii=False),
                 "hours": f"{work_hours(fm):.2f}", "rubric": rubric,
                 "carried": json.dumps({"round": prior["round"], "reviewers": carried} if carried else {})})
    rows.sort(key=lambda r: (r["round"] == "final", int(r["round"]) if r["round"].isdigit() else 0))
    write_csv(d / "audits" / "scores.csv", rows, CSV_FIELDS)
    if not a.final and int(rnd) >= max(history, default=0):
        fm["gate_round"], fm["last_score"] = rnd, f"{total:.0f}/100"
    if before:
        print(f"LATE MERGE round {rnd}: was {float(before['total']):.1f} {before['result']} (critical {before['critical']}), "
              f"now {total:.1f} {result} (critical {crit}); using the current CHARTER rubric"
              + ("; the late review changed the verdict: act on it in the current wave" if before["result"] != result
                 or int(before["critical"] or 0) != crit else ""))
    if a.missing_reason:
        body = add_to_section(body, "Log", f"{iso()} · gate {rnd} {missing}: {a.missing_reason.strip()}")
    body = add_to_section(body, "Log", f"{iso()} · gate {rnd} ({who}, {artifact}) total {total:.1f}, critical {crit}, major {major}, "
                                       f"targets {met}/{n_targets} → {result}")
    write_state(d, fm, body)
    trend = " → ".join(f"{t:.0f}" for t in totals[-5:])
    print(f"round {rnd}: total {total:.1f} (pass {rules['pass_total']:g}; trend {trend}); below floor: {', '.join(low) or 'none'}; "
          f"critical {crit}; targets {met}/{n_targets}{'' if targets_ok else ' (not all met)'}")
    for reviewer, dims in carried.items():
        values = ", ".join(f"{k}={'n/a' if v is None else f'{v:g}'}" for k, v in dims.items())
        print(f"carried from round {prior['round']} for {reviewer}: {values}")
    print(result)


# ---------- environment ----------
def _run(cmd: list, timeout: int = 15, *, input: str | None = None, errors: str = "replace") -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors=errors, timeout=timeout, input=input, stdin=subprocess.DEVNULL if input is None else None)
    except (OSError, subprocess.TimeoutExpired):
        return None


def cmd_preflight(a) -> None:
    if getattr(a, "logins", None):
        a.urls = a.logins
        return cmd_logins(a)
    rows = []

    def ok(name, good, note=""):
        rows.append((name, "OK" if good else "MISSING", note))

    for exe in ("python", "git", "node", "npx", "gh"):
        ok(exe, bool(shutil.which(exe)))
    if shutil.which("gh"):
        r = _run(["gh", "auth", "status"])
        ok("gh auth (repo + push)", bool(r) and r.returncode == 0, "" if r and r.returncode == 0 else "gh auth login")
    from codex_worker import codex_exe
    codex = codex_exe()
    ok("Codex CLI/desktop", bool(shutil.which(codex) or Path(codex).is_file()), "first real call verifies sign-in")
    for mod, note in (("playwright", "pip install playwright"), ("PIL", "pip install pillow")):
        try:
            __import__(mod)
            ok(f"python {mod}", True)
        except ImportError:
            ok(f"python {mod}", False, note)
    ok("Chrome", bool(chrome_exe()))
    root = Path(os.environ.get("MARATHON_REPOS_ROOT") or Path.home() / "repos")
    ok("repositories folder", root.is_dir(), str(root))
    need = {"research": 200, "game": 50}.get(a.type, 20)
    free = shutil.disk_usage(Path.home()).free / 1e9
    ok(f"disk free (need ≥{need} GB)", free >= need, f"{free:.0f} GB")
    rows.append(("CPU cores", "OK", f"{os.cpu_count()} (respect your hardware limits)"))
    s = HOME / "settings.json"
    hooked = s.exists() and HOOK_ID in s.read_text(encoding="utf-8")
    rows.append(("marathon Stop hook", "OK", "installed (a marathon is running)" if hooked else "added automatically at set-status running"))
    w = max(len(r[0]) for r in rows)
    for name, st, note in rows:
        print(f"{name:<{w}}  {st:<7}  {note}")


def chrome_exe():
    candidates = [os.environ.get("MARATHON_CHROME", ""), shutil.which("google-chrome"), shutil.which("chromium"), shutil.which("chromium-browser"),
                  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    if os.name == "nt":
        candidates += [str(Path(os.environ.get(key, "")) / "Google/Chrome/Application/chrome.exe") for key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
    return next((p for p in candidates if p and Path(p).is_file()), None)


def cmd_logins(a) -> None:
    chrome = chrome_exe()
    if not chrome:
        raise SystemExit("Chrome not found")
    prof = HOME / "playwright-profile"
    subprocess.Popen([chrome, f"--user-data-dir={prof}", "--new-window", *a.urls], close_fds=True, stdin=subprocess.DEVNULL)
    print(f"opened {len(a.urls)} tab(s) on {prof}; close the window after logging in so the cookies are saved")


HOOK_ID = "marathon/scripts/stop_hook.py"
HOOK_CMD = f'"{Path(sys.executable).resolve().as_posix()}" "{(SKILL / "scripts/stop_hook.py").resolve().as_posix()}"'


def set_hook(enabled: bool) -> str:
    """Add or remove the Stop hook in settings.json. It is present only while some marathon project is running here."""
    p = HOME / "settings.json"
    for _ in range(3):
        before = p.read_text(encoding="utf-8-sig") if p.exists() else "{}"
        s = json.loads(before)
        hooks = s.setdefault("hooks", {})
        stop = hooks.setdefault("Stop", [])
        matches = [h for e in stop for h in e.get("hooks", []) if HOOK_ID in h.get("command", "")]
        present = bool(matches)
        if (enabled and len(matches) == 1 and matches[0].get("command") == HOOK_CMD) or (not enabled and not present):
            if not stop:
                hooks.pop("Stop")
            return "hook already " + ("installed" if enabled else "absent")
        kept = []
        for entry in stop:
            remaining = [h for h in entry.get("hooks", []) if HOOK_ID not in h.get("command", "")]
            if remaining or not entry.get("hooks"):
                kept.append(dict(entry, hooks=remaining) if entry.get("hooks") else entry)
        stop[:] = kept
        if enabled:
            stop.append({"matcher": "", "hooks": [{"type": "command", "command": HOOK_CMD, "timeout": 10}]})
        elif not stop:
            hooks.pop("Stop")
        if (p.read_text(encoding="utf-8-sig") if p.exists() else "{}") != before:
            continue  # changed underneath us: redo on the fresh content
        atomic_write(p, json.dumps(s, indent=2, ensure_ascii=False) + "\n")
        return "hook installed" if enabled else "hook removed (no marathon running here)"
    return "settings.json kept changing; hook not updated"


def cmd_install_hook(a) -> None:
    print(set_hook(not a.remove))


# ---------- worker ledger (audits/workers.csv), usage ledger, lead rotation ----------
WORKER_FIELDS = ["id", "started", "ended", "agent", "model", "effort", "class", "status", "first_pass", "fix_lines",
                 "critical", "major", "minutes", "input", "cached", "output", "thread", "report", "note", "backend"]
TERMINAL_WORKER_STATUSES = {"done", "partial", "failed", "timeout", "fallback"}
WORKER_CLASSES = ("build", "ui", "test", "data", "research", "ops", "gate")


def workers_path(d: Path) -> Path:
    return d / "audits" / "workers.csv"


def read_workers(d: Path, _locked: bool = False) -> list[dict]:
    p = workers_path(d)
    if not p.exists():
        return []
    if not _locked:
        with worker_lock(d):
            return read_workers(d, _locked=True)
    return [dict(r, backend=r.get("backend") or "") for r in read_csv(p, encoding="utf-8-sig")]


def write_workers(d: Path, rows: list[dict], _locked: bool = False) -> None:
    if not _locked:
        with worker_lock(d):
            return write_workers(d, rows, _locked=True)
    p = workers_path(d)
    p.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(WORKER_FIELDS + [k for row in rows for k in row]))
    write_csv(p, rows, fields, lineterminator="\n")


@contextmanager
def worker_lock(d: Path, timeout: float = 10, stale: float = 60):
    """Serialize the entire ledger transaction, with bounded recovery from a crashed writer."""
    with file_lock(workers_path(d).with_suffix(".csv.lock"), timeout, stale, "worker ledger"):
        yield


@contextmanager
def file_lock(p: Path, timeout: float = 10, stale: float = 60, label: str = "file"):
    p.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    deadline, delay = time.monotonic() + timeout, 0.01
    while True:
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            break
        except (FileExistsError, PermissionError):
            try:
                before = p.stat()
                if time.time() - before.st_mtime > stale and p.stat() == before:
                    p.unlink()
                    continue
            except OSError:
                pass
            left = deadline - time.monotonic()
            if left <= 0:
                raise SystemExit(f"{label} locked for {timeout:g}s: {p}")
            time.sleep(min(delay, left))
            delay = min(delay * 1.5, 0.25)
    written = False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(token)
            f.flush()
            written = True
            yield   # keep the Windows handle open: a live owner cannot be unlinked by a stale contender
    finally:
        for attempt in range(5):
            try:
                if not written or p.read_text(encoding="utf-8") == token:
                    p.unlink()
                break
            except FileNotFoundError:
                break
            except OSError:
                if attempt < 4:
                    time.sleep(0.05)


def update_worker_row(rows: list[dict], wid: str, fields: dict) -> dict:
    """Update rows held under worker_lock; the caller commits them together."""
    row = next((r for r in rows if r.get("id") == wid), None)
    if row is None:
        row = {k: "" for k in WORKER_FIELDS}
        row.update(id=wid, started=iso())
        rows.append(row)
    for k, v in fields.items():
        if k not in WORKER_FIELDS[1:]:
            raise SystemExit(f"unknown worker field '{k}'; allowed: {', '.join(WORKER_FIELDS[1:])}")
        v = str(v)
        if k == "class" and v and v not in WORKER_CLASSES:
            raise SystemExit(f"class must be one of {', '.join(WORKER_CLASSES)}")
        if v.startswith("+") and v[1:].replace(".", "", 1).isdigit():
            v = f"{hours(row.get(k)) + float(v[1:]):g}"
        row[k] = v
    if "status" in fields and (fields["status"] == "" or
                               fields["status"] not in TERMINAL_WORKER_STATUSES and "ended" not in fields):
        row["ended"] = ""
    elif row.get("status") in TERMINAL_WORKER_STATUSES and not row.get("ended"):
        row["ended"] = iso()
    return row


def upsert_worker(d: Path, wid: str, fields: dict) -> dict:
    """Create or update one worker atomically; numeric fields given as +N are added."""
    with worker_lock(d):
        rows = read_workers(d, _locked=True)
        row = update_worker_row(rows, wid, fields)
        write_workers(d, rows, _locked=True)
        return row


def model_family(r: dict) -> str:
    a, m = (r.get("agent") or "").lower(), (r.get("model") or "").lower()
    if a == "codex" or "gpt" in m:
        return "codex"
    return next((k for k in ("opus", "sonnet", "haiku", "fable") if k in m), m or a or "?")


def model_key(r: dict) -> str:
    """Canonical model and effort, retaining versioned model identities in old ledgers."""
    name, effort = (r.get("model") or "?").strip().lower(), (r.get("effort") or "").strip().lower()
    try:
        qualified = name.partition("-")[2] in ("low", "medium", "high", "xhigh", "max")
        _, name, default = resolve_model(name)
        effort = effort or (default if qualified else "")
    except SystemExit:
        pass
    return f"{name}/{effort or 'unspecified'}"


def assessed_worker(r: dict) -> bool:
    return r.get("first_pass") in ("y", "n") and all(re.fullmatch(r"[0-9]+", str(r.get(k, "")))
                                                        for k in ("critical", "major"))


def worker_stats(rows: list[dict]) -> dict:
    """(exact model/effort, class) -> usage and fully assessed quality samples."""
    out: dict = {}
    for r in rows:
        if (r.get("status") not in TERMINAL_WORKER_STATUSES - {"fallback"} or r.get("class") == "gate"
                or (r.get("note") or "").startswith("bake-off ")):
            continue
        s = out.setdefault((model_key(r), r.get("class") or "?"),
                           {"runs": 0, "fp_n": 0, "fp_y": 0, "unassessed": 0, "defects": 0.0,
                            "minutes": 0.0, "tokens": 0.0})
        s["runs"] += 1
        if assessed_worker(r):
            s["fp_n"] += 1
            s["fp_y"] += r["first_pass"] == "y"
            s["defects"] += int(r["critical"]) + int(r["major"])
        else:
            s["unassessed"] += 1
        s["minutes"] += hours(r.get("minutes"))
        s["tokens"] += hours(r.get("input")) + hours(r.get("output"))
    return out


def running_workers(d: Path) -> list[str]:
    return [r["id"] for r in read_workers(d) if r.get("started") and not r.get("ended")
            and r.get("status") not in TERMINAL_WORKER_STATUSES]


def cmd_worker(a) -> None:
    if not getattr(a, "id", None):
        return cmd_workers(a)
    d = Path(a.dir).resolve()
    fields = dict(p.split("=", 1) for p in a.pairs if "=" in p)
    row = upsert_worker(d, a.id, fields)
    print(f"{a.id}: " + ", ".join(f"{k}={row[k]}" for k in WORKER_FIELDS[1:] if row.get(k)))


def project_key(d: Path) -> str:
    return os.path.normcase(str(d.resolve()))


def pooled_workers(d: Path, pool: bool) -> list[dict]:
    projects = {project_key(d): d}
    if pool:
        override = os.environ.get("MARATHON_OVERVIEW_GLOBS")
        patterns = project_globs()
        if not override and os.environ.get("MARATHON_REPOS_ROOT"):
            root = os.environ["MARATHON_REPOS_ROOT"]
            patterns += [str(Path(root) / "*" / "STATE.md"), str(Path(root) / "*" / "*" / "STATE.md")]
        for g in patterns:
            for st in glob.glob(g):
                p = Path(st).parent.resolve()
                projects.setdefault(project_key(p), p)
    rows = {}
    for project, p in projects.items():
        for r in read_workers(p):
            rows[(project, r.get("id"))] = r
    return list(rows.values())


def cmd_workers(a) -> None:
    d = Path(a.dir).resolve()
    stats = worker_stats(pooled_workers(d, a.pool))
    if not stats:
        print("no finished workers in audits/workers.csv yet")
        return
    print(f"{'model/effort':<32}{'class':<10}{'runs':>5}{'assessed':>10}{'1st pass':>10}{'defects/run':>13}{'minutes':>10}{'tokens':>12}")
    for (model, cls), s in sorted(stats.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        fp = f"{s['fp_y'] / s['fp_n'] * 100:.0f}%" if s["fp_n"] else "-"
        defects = f"{s['defects'] / s['fp_n']:.2f}" if s["fp_n"] else "-"
        print(f"{model:<32}{cls:<10}{s['runs']:>5}{s['fp_n']:>10}{fp:>10}{defects:>13}"
              f"{s['minutes']:>10.1f}{s['tokens']:>12.0f}")


def lead_sessions(fm: dict, include_current: bool = True) -> list[str]:
    ids = list(dict.fromkeys(s.strip() for s in (fm.get("lead_sessions") or "").split(",") if s.strip()))
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID")
    return ids + ([sid] if include_current and sid and sid not in ids else [])


USAGE_KEYS = ("msgs", "input", "cache_write", "cache_read", "output", "w5", "w1h")
USAGE_TYPES = ("input", "cache_write", "cache_read", "output")
USAGE_PRICES = {"opus-5-5": (4, 20, .20), "sonnet-5-5": (2, 10, .20), "opus-5": (5, 25, .50),
                "sonnet-5": (2, 10, .20), "fable-5-1": (10, 50, .25), "haiku-5-5": (.10, .50, .01)}


def transcript_usage(path: Path, since_utc: dt.datetime | None) -> dict:
    tot = dict.fromkeys(USAGE_KEYS, 0)
    tot["models"] = {}
    seen = set()
    try:
        f = path.open(encoding="utf-8", errors="replace")
    except OSError:
        return tot
    with f:
        for line in f:
            if '"usage"' not in line:
                continue
            try:
                j = json.loads(line)
            except ValueError:
                continue
            if not isinstance(j, dict):
                continue
            msg = j.get("message") if isinstance(j.get("message"), dict) else {}
            u = msg.get("usage")
            if not isinstance(u, dict):
                continue
            ts = j.get("timestamp") or ""
            if since_utc and ts:
                try:
                    if dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(dt.timezone.utc) < since_utc:
                        continue
                except (ValueError, TypeError):
                    pass
            key = msg.get("id") or j.get("uuid")
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            cc = u.get("cache_creation") or {}
            w5, w1h = int(cc.get("ephemeral_5m_input_tokens") or 0), int(cc.get("ephemeral_1h_input_tokens") or 0)
            if not w5 + w1h:
                w5 = int(u.get("cache_creation_input_tokens") or 0)
            r = dict(msgs=1, input=int(u.get("input_tokens") or 0), cache_write=w5 + w1h,
                     cache_read=int(u.get("cache_read_input_tokens") or 0), output=int(u.get("output_tokens") or 0), w5=w5, w1h=w1h)
            model = str(msg.get("model") or "unknown")
            dest = tot["models"].setdefault(model, dict.fromkeys(USAGE_KEYS, 0))
            for k, v in r.items():
                tot[k] += v
                dest[k] += v
    return tot


def usage_cost(model: str, r: dict) -> dict:
    name = model.removeprefix("claude-")
    key = next((k for k in sorted(USAGE_PRICES, key=len, reverse=True) if name == k or name.startswith(k + "-")), None)
    if key is None:
        return dict.fromkeys(USAGE_TYPES)
    pin, pout, pread = USAGE_PRICES[key]
    return dict(input=r["input"] * pin / 1e6, cache_write=(r["w5"] * 1.25 + r["w1h"] * 2) * pin / 1e6,
                cache_read=r["cache_read"] * pread / 1e6, output=r["output"] * pout / 1e6)


def usage_role(path: Path) -> str:
    try:
        desc = json.loads(path.with_suffix(".meta.json").read_text(encoding="utf-8")).get("description", "")
    except (OSError, ValueError, AttributeError):
        desc = ""
    desc = str(desc or "").strip()
    if re.match(r"W\d+", desc): return "build workers"
    if "gate round" in desc.lower(): return "gate reviewers"
    if re.search(r"review|strategic", desc, re.I): return "reviews"
    if re.search(r"research|teardown|benchmark", desc, re.I): return "research"
    return "other"


def usage_ledger(d: Path, by_role: bool = False) -> list[dict]:
    """Deduplicated Claude transcripts at model/TTL list prices; Codex worker tokens are subscription usage."""
    fm, _ = read_state(d)
    try:
        since = dt.datetime.fromisoformat(fm.get("started", "")).astimezone(dt.timezone.utc)
    except ValueError:
        since = None
    cache_path = d / ".tmp" / "usage-cache.json"
    since_key = since.isoformat() if since else ""
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        if cache.get("version") != 1 or cache.get("since") != since_key:
            cache = {}
    except (OSError, ValueError, AttributeError):
        cache = {}
    entries = cache.get("transcripts", {})
    fresh = {}

    def scan(path):
        try:
            st = path.stat()
        except OSError:
            return transcript_usage(path, since)
        key = str(path.resolve())
        sig = [st.st_size, st.st_mtime_ns]
        old = entries.get(key, {})
        u = old["usage"] if old.get("stat") == sig and "usage" in old else transcript_usage(path, since)
        fresh[key] = {"stat": sig, "usage": u}
        return u

    def part(name, lower=False):
        return dict(dict.fromkeys(USAGE_KEYS, 0), part=name, runs=0, models={}, lower_bound=lower)

    def add(dest, u):
        dest["runs"] += 1
        for k in USAGE_KEYS:
            dest[k] += u[k]
        for model, r in u["models"].items():
            target = dest["models"].setdefault(model, dict(dict.fromkeys(USAGE_KEYS, 0), runs=0))
            target["runs"] += 1
            for k in USAGE_KEYS:
                target[k] += r[k]

    lead, subs = part("lead"), {}
    if not by_role:
        subs["Claude sub-agents"] = part("Claude sub-agents", True)
    # The calling session counts only when registered for this project; saved leads survive rotation.
    for sid in lead_sessions(fm, include_current=registry_info(d) is not None):
        for t in (HOME / "projects").glob(f"*/{sid}.jsonl"):
            add(lead, scan(t))
            for st in t.with_suffix("").glob("subagents/*.jsonl"):
                u = scan(st)
                if u["msgs"]:
                    role = usage_role(st) if by_role else "Claude sub-agents"
                    add(subs.setdefault(role, part(role, True)), u)
    if fresh or cache_path.exists():
        updated = {"version": 1, "since": since_key, "transcripts": fresh}
        if updated != cache:
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write(cache_path, json.dumps(updated))
            except OSError:
                pass   # accounting still works when the optional cache cannot be written
    out = [lead, *subs.values()]
    for dest in out:
        costs = dict.fromkeys(USAGE_TYPES, 0.0)
        for model, r in dest["models"].items():
            r["costs"] = usage_cost(model, r)
            r["usd"] = sum(r["costs"].values()) if all(v is not None for v in r["costs"].values()) else None
            r["total"] = sum(r[k] for k in USAGE_TYPES)
            r["lower_bound"] = dest["lower_bound"]
            for k in USAGE_TYPES:
                costs[k] = costs[k] + r["costs"][k] if costs[k] is not None and r["costs"][k] is not None else None
        dest["costs"] = costs
        dest["usd"] = sum(costs.values()) if all(v is not None for v in costs.values()) else None
        dest["total"] = sum(dest[k] for k in USAGE_TYPES)
    cx = part("Codex runs")
    for r in read_workers(d):
        if model_family(r) == "codex":
            u = dict.fromkeys(USAGE_KEYS, 0)
            u.update(input=int(hours(r.get("input")) - hours(r.get("cached"))),
                     cache_read=int(hours(r.get("cached"))), output=int(hours(r.get("output"))))
            u["models"] = {r.get("model") or "unknown": dict(u)}
            add(cx, u)
    for r in [cx, *cx["models"].values()]:
        r.update(total=sum(r[k] for k in USAGE_TYPES), usd=None, costs=dict.fromkeys(USAGE_TYPES), lower_bound=False)
    out.append(cx)
    return out


def usage_dollars(r: dict, key: str | None = None) -> str:
    usd = r["costs"][key] if key else r["usd"]
    lower = "≥" if r["lower_bound"] and (key is None or key == "output") else ""
    if usd is None:
        return "unknown"
    return lower + (f"${usd:,.0f}" if usd >= 10 else f"${usd:.2f}")


def cmd_usage(a) -> None:
    full = getattr(a, "full", False) or getattr(a, "by_role", False)
    rows = usage_ledger(Path(a.dir).resolve(), by_role=getattr(a, "by_role", False))
    claude = rows[:-1]
    total = sum(r["usd"] for r in claude) if all(r["usd"] is not None for r in claude) else None
    print("API-equivalent $ (list prices); tokens in millions; Codex runs are on the subscription")
    print(f"{'part / model':<30}{'runs':>5}{'tokens':>9}{'read':>6}{'$ input':>9}{'$ write':>9}{'$ read':>9}{'$ output':>10}{'$ total':>10}{'share':>7}")

    def show(label, r, codex):
        tok = r["total"] / 1e6
        read = f"{r['cache_read'] / r['total'] * 100:.0f}%" if r["total"] else "-"
        if codex:
            print(f"{label:<30}{r['runs']:>5}{tok:>8.1f}M{read:>6}{'subscription':>47}")
            return
        share = f"{r['usd'] / total * 100:.0f}%" if total and r["usd"] is not None else "-"
        print(f"{label:<30}{r['runs']:>5}{tok:>8.1f}M{read:>6}" + "".join(
            f"{usage_dollars(r, k):>{w}}" for k, w in zip(USAGE_TYPES, (9, 9, 9, 10))) + f"{usage_dollars(r):>10}{share:>7}")

    for r in rows:
        codex = r["part"] == "Codex runs"
        if not full or len(r["models"]) == 1 or codex:
            show(r["part"], r, codex)
        else:
            for model, values in sorted(r["models"].items()):
                show(r["part"] + " / " + model.removeprefix("claude-"), values, codex)
            show(r["part"] + " / total", r, codex)
    print("Claude total: " + usage_dollars(dict(usd=total, lower_bound=any(r["runs"] and r["lower_bound"] for r in claude))))
    if full and any(r["runs"] and r["lower_bound"] for r in claude):
        print("≥ lower bound: Claude sub-agent transcripts record output at response start, not final output; output tokens/$ and totals are undercounted.")
    if full and total is None:
        print("unknown: no supplied API price for one or more recorded models.")




def cmd_config(a) -> None:
    if getattr(a, "models", False) and a.name:
        print(" ".join(x for x in resolve_model(a.name) if x))
        return
    fm = read_state(Path(a.dir).resolve())[0] if a.dir else {"profile": DEFAULT_PROFILE}
    if getattr(a, "models", False):
        print("codex_backends " + run_value(fm, "codex_backends"))
        for i, n in enumerate(worker_chain(fm)):
            agent, model, eff = resolve_model(n)
            print(f"{'primary ' if i == 0 else 'fallback'} {n:<8} {agent:<7}{model}{' ' + eff if eff else ''}")
    elif a.profiles:
        for k, p in PROFILES.items():
            if k != LEGACY_PROFILE or run_value(fm, "profile") == LEGACY_PROFILE:
                print(f"{k:<11}{p['name']:<10}{p['about']}")
    else:
        print("\n".join(run_config(fm, short=a.short)))


def cmd_handoff(a) -> None:
    """Save checkpoint notes, or prepare a quiet-point transfer completed by successor claim."""
    d = Path(a.dir).resolve()
    fm, body = read_state(d)
    if getattr(a, "abort", False):
        fm.pop("handoff_pending", None)
        write_state(d, fm, body)
        print("handoff aborted; the old lead keeps running")
        return
    original_body = body
    running = [] if a.save_only else running_workers(d)
    if running and not a.force:
        raise SystemExit(f"workers still running ({', '.join(running)}): their notices come back to this session. "
                         "Rotate after they report (or --force if they are dead and marked)")
    n = int(hours(fm.get("rotations"))) + (0 if fm.get("handoff_pending") else 1)
    if not a.save_only:
        fm["rotations"] = str(n)
        fm["lead_sessions"] = ",".join(lead_sessions(fm))
        fm["handoff_pending"] = fm.get("handoff_pending") or iso()
    label = "checkpoint" if a.save_only else f"rotation {n}"
    lines = [f"- {iso()} {label}: {a.why}", f"- next: {fm.get('next', '?')}"] + [f"- {x}" for x in (a.note or [])]
    resume_prompt = (f"Resume marathon {d} (lead rotation {n}). Read STATE.md (Handoff section first) and CHARTER.md, "
                     f"run marathon.py claim {d}, then continue from next. Do not re-read old transcripts.")
    if not a.save_only:
        lines.append("- Resume prompt: " + resume_prompt)
    body = set_section(body, "Handoff", lines) if "## Handoff\n" in body else body.rstrip("\n") + "\n\n## Handoff\n" + "\n".join(lines) + "\n"
    if a.save_only:
        raw = (d / "STATE.md").read_text(encoding="utf-8-sig")
        state_transaction(d, raw.removesuffix(original_body) + body)
        print("Handoff notes saved (checkpoint)")
        return
    write_state(d, fm, body)
    print("handoff pending: start the successor; keep this lead running until the successor runs claim.")
    print(f"If the successor cannot start, run marathon.py handoff-abort {d}.")
    print("RESUME PROMPT (start the new lead session with exactly this):")
    print(f"Resume marathon {d} (lead rotation {n}). Read STATE.md (Handoff section first) and CHARTER.md, "
          f"run marathon.py claim {d}, then continue from next. Do not re-read old transcripts.")


# ---------- bounded state, questions and machine-wide resources ----------
def history_sections(text: str, title: str):
    return re.finditer(r"(?m)^## " + re.escape(title) + r"\n(?P<content>.*?)(?=^## |\Z)", text, re.S)


def state_transaction(d: Path, text: str | None = None) -> None:
    with file_lock(d / ".tmp" / "state-write.lock"):
        journal = d / ".tmp" / "state-write.json"
        def state_hash():
            return hashlib.sha256((d / "STATE.md").read_bytes()).hexdigest() if (d / "STATE.md").exists() else None
        def finish(data):
            if (d / "DECISIONS.md").exists() and not marathon_archive(d):
                raise SystemExit("DECISIONS.md is not marathon's archive; preserve it and move it before retrying")
            atomic_write(d / "DECISIONS.md", data["archive"])
            atomic_write(d / "STATE.md", data["state"])
            journal.unlink()
        if journal.exists():
            data = json.loads(journal.read_text(encoding="utf-8"))
            current = state_hash()
            # atomic_write uses UTF-8 with LF on every host.
            target = hashlib.sha256(data["state"].encode("utf-8")).hexdigest()
            if "before" in data and current in (data["before"], target):
                finish(data)
            else:
                stale = journal.with_suffix(".stale")
                if stale.exists():
                    stale = journal.with_name(journal.stem + "." + uuid.uuid4().hex + ".stale")
                journal.rename(stale)
                print(f"STATE changed after journal creation; kept newer file; lead must reconcile {stale}", file=sys.stderr)
                if text is not None:
                    raise SystemExit("STATE changed; reread before writing")
        if text is not None:
            text, archive = cap_state(d, text)
            if archive is None:
                atomic_write(d / "STATE.md", text)
            else:
                data = {"state": text, "archive": archive, "before": state_hash()}
                atomic_write(journal, json.dumps(data, ensure_ascii=False))
                finish(data)


def cap_state(d: Path, body: str) -> tuple[str, str | None]:
    pointer, moved = "Older decisions and log: DECISIONS.md", []
    def trim(m):
        content = m.group("content")
        entries = list(re.finditer(r"(?m)^(?:[-*+] |\d+[.)] )", content))
        if len(entries) <= 5:
            return m.group(0)
        start, end = entries[0].start(), entries[-5].start()
        moved.append(m.group(0)[:m.start("content") - m.start()] + content[start:end])
        return m.group(0)[:m.start("content") - m.start()] + content[:start] + content[end:]
    body = re.sub(r"(?m)^## (?:Decisions|Log)\n(?P<content>.*?)(?=^## |\Z)", trim, body, flags=re.S)
    archive, appended = d / "DECISIONS.md", None
    if moved:
        if archive.exists() and not marathon_archive(d):
            raise SystemExit("DECISIONS.md is not marathon's archive; preserve it and move it before retrying")
        previous = archive.read_text(encoding="utf-8") if archive.exists() else ARCHIVE_MARKER + "\n\n"
        appended = ARCHIVE_MARKER + "\n\n"
        for title in ("Decisions", "Log"):
            chunks = [m.group("content").strip("\n") for text in (previous, *moved) for m in history_sections(text, title)]
            if chunks:
                appended += "## " + title + "\n" + "\n".join(chunks) + "\n\n"
    if moved or marathon_archive(d):
        body = re.sub(r"(?m)^" + re.escape(pointer) + r"\n?", "", body).rstrip("\n") + "\n\n" + pointer + "\n"
    return body, appended


def history_lines(d: Path, body: str, title: str) -> list[str]:
    p = d / "DECISIONS.md"
    texts = ([p.read_text(encoding="utf-8")] if marathon_archive(d) else []) + [body]
    return [line for text in texts for m in history_sections(text, title)
            for line in m.group("content").splitlines() if line.strip()]


def ask_questions(path: str) -> list[dict]:
    try:
        qs = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise SystemExit(f"questions: {e}")
    if not isinstance(qs, list) or not 1 <= len(qs) <= 5:
        raise SystemExit("questions: supply 1–5 questions")
    ids = set()
    for q in qs:
        if not isinstance(q, dict) or not isinstance(q.get("id"), str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", q["id"]):
            raise SystemExit("questions: each id must be a simple unique name")
        opts = q.get("options")
        if q["id"] in ids or not isinstance(q.get("text"), str) or not q["text"].strip() or len(q["text"]) > 160:
            raise SystemExit("questions: duplicate id or text outside 1–160 characters")
        if (not isinstance(opts, list) or not 1 <= len(opts) <= 8 or
                any(not isinstance(x, str) or not x.strip() for x in opts) or len(set(opts)) != len(opts) or (not q.get("must_decide") or q.get("default") is not None) and q.get("default") not in opts):
            raise SystemExit("questions: unique options required; default must be in options")
        if "must_decide" in q and not isinstance(q["must_decide"], bool):
            raise SystemExit("questions: must_decide must be boolean")
        ids.add(q["id"])
    return qs


def ask_widget(data: dict) -> str:
    esc, fields = html.escape, []
    for q in data["questions"]:
        options = []
        compact = len(q["options"]) > 4
        for i, label in enumerate(q["options"]):
            code = chr(65 + i)
            chosen = not q.get("must_decide") and label == q["default"]
            options.append(f'<option value="{code}"{" selected" if chosen else ""}>{code} · {esc(label)}</option>' if compact else
                           f'<label><input type="radio" name="{q["id"]}" value="{code}"{" checked" if chosen else ""}><span>{code} · {esc(label)}</span></label>')
        choices = (f'<select name="{q["id"]}"><option value="" disabled{" selected" if q.get("must_decide") else ""}>Choose one</option>{"".join(options)}</select>'
                   if compact else '<div>' + "".join(options) + '</div>')
        fields.append(f'<fieldset><legend>{esc(q["text"])}{" (choose one)" if q.get("must_decide") else ""}</legend>{choices}</fieldset>')
    widget = '''<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Choose next steps</title>
<style>body{margin:0;background:var(--k-page,#fff);color:var(--k-ink,#222);font:16px/1.25 "Segoe UI",-apple-system,"Microsoft YaHei UI",sans-serif}form{padding:16px;max-width:640px;margin:auto}fieldset{border:0;padding:0;margin:0 0 10px;min-width:0}legend{font-weight:700;margin-bottom:4px;overflow-wrap:anywhere;max-height:2.5em;overflow:auto}fieldset div{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(0,1fr);gap:4px}label{display:flex;align-items:center;gap:4px;height:44px;border:1px solid #bbb;border-radius:5px;padding:0 6px;box-sizing:border-box;min-width:0;cursor:pointer}label:has(:checked){background:#eee;border-color:#333}input{margin:0;accent-color:#333;flex-shrink:0}span{overflow:auto;max-height:2.5em;overflow-wrap:anywhere}select{font:inherit;width:100%;height:44px;box-sizing:border-box}button{font:inherit;min-height:44px;width:100%;border:0;border-radius:5px;background:#222;color:#fff;cursor:pointer}button:disabled{opacity:.45;cursor:default}</style>
<form data-ask="SETID">FIELDS<button disabled>Confirm</button></form><script>(()=>{const f=document.querySelector('form[data-ask="SETID"]'),b=f.querySelector('button'),sets=[...f.querySelectorAll('fieldset')];const choice=s=>s.querySelector('select')||s.querySelector('input:checked');const ready=()=>b.disabled=sets.some(s=>!choice(s)?.value);f.onchange=ready;f.onsubmit=e=>{e.preventDefault();if(!b.disabled)sendPrompt('ASK SETID: '+sets.map(s=>{const x=choice(s);return x.name+'='+x.value}).join(' '))};ready()})();</script>'''
    widget = widget.replace("SETID", data["id"]).replace("FIELDS", "".join(fields))
    if len(widget.encode("utf-8")) > 6 * 1024:
        raise SystemExit("questions: widget exceeds 6 KB; shorten questions/options")
    return widget


def ask_answers(data: dict, text: str) -> dict:
    text = unicodedata.normalize("NFKC", text).strip()
    if text.startswith("ASK "):
        prefix, sep, text = text.partition(":")
        if not sep or prefix != "ASK " + data["id"]:
            raise SystemExit("answers: wrong question set")
    agree = re.match(r"^(同意|agree\b|ok\b)\s*", text.strip(), re.I)
    answers, explicit, qs = {}, set(), data["questions"]
    if agree:
        answers = {q["id"]: data["defaults"][q["id"]] for q in qs if not q.get("must_decide")}
        text = text.strip()[agree.end():]
    text = re.sub(r"\b(\d+)\s+([A-Za-z])\b", r"\1\2", text)
    text = re.sub(r"\s*=\s*", "=", text)
    for token in re.split(r"[\s,;；]+", text.strip()):
        if not token:
            continue
        key, sep, value = token.partition("=")
        if not sep:
            match = re.fullmatch(r"(\d+)([A-Za-z])", token)
            if not match:
                raise SystemExit(f"answers: invalid choice {token}")
            key, value = match[1], match[2]
        q = next((q for q in qs if q["id"] == key), None)
        if q is None and (match := re.fullmatch(r"q?(\d+)", key, re.I)) and 1 <= int(match[1]) <= len(qs):
            q = qs[int(match[1]) - 1]
        value = value.upper()
        if q is None or len(value) != 1 or not 0 <= ord(value) - 65 < len(q["options"]) or q["id"] in explicit:
            raise SystemExit(f"answers: invalid/duplicate choice {token}")
        answers[q["id"]] = value
        explicit.add(q["id"])
    return answers


def cmd_ask(a) -> None:
    timer = getattr(a, "at_deadline", False)
    if (a.answers is not None and not a.resolve) or (a.wait is not None and not a.file) or (timer and not a.resolve):
        raise SystemExit("ask: --answers needs --resolve; --wait needs --file; --at-deadline needs --resolve")
    d, target = Path(a.dir).resolve(), None
    while True:
        with file_lock(d / ".tmp" / "state-command.lock", label="state command"), file_lock(d / ".tmp" / "ask.lock"):
            pending = ask_step(a, d, target)
        if not timer or not pending:
            return
        target = pending["id"]
        a.answers = None
        time.sleep(min(15, max(0, (dt.datetime.fromisoformat(pending["deadline"]) - now()).total_seconds())))


def ask_step(a, d: Path, target: str | None = None):
    fm, body = read_state(d)
    data = json.loads(fm["asking"]) if fm.get("asking") else None
    if target and (not data or data["id"] != target):
        outcome = next((line for line in reversed(history_lines(d, body, "Decisions")) if f"ASK {target}:" in line), "answered or replaced")
        print(f"CLOSED {target}: {outcome}", flush=True)
        return
    if a.status:
        pending = [q["id"] for q in data["questions"] if q["id"] not in data.get("answers", {})] if data else []
        print(f"OPEN {data['id']} · {max(0, math.ceil((dt.datetime.fromisoformat(data['deadline']) - now()).total_seconds()))} seconds left; unanswered: {', '.join(pending)}" if data else "CLOSED: no open question set")
        return
    if a.file:
        if data:
            raise SystemExit("asking: a question set is already open; resolve it first")
        qs = ask_questions(a.file)
        wait = a.wait if a.wait is not None else float(fm.get("ask_wait") or 10)
        if not math.isfinite(wait) or wait < 0:
            raise SystemExit("ask_wait must be finite and nonnegative")
        data = {"id": uuid.uuid4().hex[:8], "deadline": (now() + dt.timedelta(minutes=wait)).isoformat(),
                "defaults": {q["id"]: chr(65 + q["options"].index(q["default"])) for q in qs if q.get("default") in q["options"]}, "questions": qs}
        widget = ask_widget(data)
        fm["asking"] = json.dumps(data, ensure_ascii=True, separators=(",", ":"))
        write_state(d, fm, body)
        if wait:
            print(widget + "\n\nPlain-text fallback:")
            for i, q in enumerate(qs, 1):
                opts = "; ".join(f"{chr(65+j)}={v}" for j, v in enumerate(q["options"]))
                print(f"{i}. {q['id']}: {q['text']} · {opts} · " + ("must decide (no default)" if q.get("must_decide") else f"default {data['defaults'][q['id']]}"))
            print(f"ASK {data['id']}: reply 同意 / agree / ok, or e.g. 1A / {qs[0]['id']}=A. Deadline {data['deadline']}")
            return data
    if not data:
        if a.answers and a.answers.strip():
            line = f"late answer {a.answers.strip()} (not applied; lead decides)"
            write_state(d, fm, add_to_section(body, "Decisions", f"{iso()} · {line}"))
            print(line)
        else:
            print("CLOSED: no open question set")
        return
    reply_id = re.match(r"ASK ([^:]+):", (a.answers or "").strip())
    if reply_id and reply_id[1] != data["id"] and any(f"ASK {reply_id[1]}:" in line for line in history_lines(d, body, "Decisions")):
        line = f"late answer {a.answers.strip()} (not applied; lead decides)"
        write_state(d, fm, add_to_section(body, "Decisions", f"{iso()} · {line}"))
        print(line)
        return data
    answers = dict(data.get("answers", {}))
    answers.update(ask_answers(data, a.answers or ""))
    expired = now() >= dt.datetime.fromisoformat(data["deadline"])
    pending = [q["id"] for q in data["questions"] if q["id"] not in answers]
    if not expired and pending:
        if answers:
            data["answers"] = answers
            fm["asking"] = json.dumps(data, ensure_ascii=True, separators=(",", ":"))
            write_state(d, fm, body)
        print(f"WAIT {data['id']}: deadline {data['deadline']}; unanswered: {', '.join(pending)}", flush=True)
        return data
    outcomes = []
    for q in data["questions"]:
        value = answers.get(q["id"])
        if value is None and q.get("must_decide"):
            body = add_to_section(body, "Parked for the user", f"ASK {data['id']} {q['id']}: {q['text']} (must decide)")
            outcomes.append(f"{q['id']}=parked")
        else:
            value = value or data["defaults"][q["id"]]
            outcomes.append(f"{q['id']}={value} ({q['options'][ord(value)-65]}; {'answer' if q['id'] in answers else 'default'})")
    outcome = f"ASK {data['id']}: " + "; ".join(outcomes)
    body = add_to_section(body, "Decisions", f"{iso()} · {outcome}")
    fm["asking"] = ""
    write_state(d, fm, body)
    print(outcome, flush=True)


def cmd_lock(a) -> None:
    if a.force and not a.release:
        raise SystemExit("lock: --force needs --release")
    if not math.isfinite(a.ttl) or a.ttl <= 0 or not a.owner.strip():
        raise SystemExit("lock: owner and positive finite ttl required")
    p = REGISTRY.parent / "browser.lock"
    with file_lock(p.with_suffix(".guard")):
        try:
            info = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
            if info is not None and (not isinstance(info, dict) or not all(k in info for k in ("owner", "dir", "time", "ttl"))):
                raise ValueError("incomplete lease")
        except ValueError:
            info = {"owner": "<incomplete>", "dir": "?", "time": p.stat().st_mtime, "ttl": 30}
        age = max(0, time.time() - info["time"]) if info else 0
        live = info and age < info["ttl"] * 60
        same = info and info["owner"] == a.owner and project_key(Path(info["dir"])) == project_key(Path(a.dir))
        if live and not same and not (a.release and a.force):
            print(f"HELD browser: {info['owner']} · {info['dir']} · age {age:.0f}s")
            raise SystemExit(2)
        if a.status:
            print(f"HELD browser: {info['owner']} · {info['dir']} · age {age:.0f}s" if live else "FREE browser")
            return
        if a.release:
            if info and not same and not a.force:
                print(f"HELD browser: {info['owner']} · {info['dir']} · age {age:.0f}s")
                raise SystemExit(2)
            p.unlink(missing_ok=True)
            print("RELEASED browser")
            return
        if info:
            p.unlink()
        with p.open("x", encoding="utf-8") as f:
            json.dump({"owner": a.owner, "dir": str(Path(a.dir).resolve()), "time": time.time(), "ttl": a.ttl}, f)
        print(f"ACQUIRED browser: {a.owner} · ttl {a.ttl:g} min")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    visible = "init claim status set note log wait score evidence preflight worker usage handoff config install-hook ask lock"
    sp = ap.add_subparsers(dest="cmd", required=True, metavar="{" + visible.replace(" ", ",") + "}")

    def parser(name, command, *aliases, directory=True, **kw):
        p = sp.add_parser(name, **kw)
        for alias in aliases:
            sp._name_parser_map[alias] = p
        if directory:
            p.add_argument("dir", **({"nargs": "?"} if directory == "?" else {}))
        p.set_defaults(f=command)
        return p
    p = parser("init", cmd_init); p.add_argument("--type", required=True, choices=["game", "site", "research"])
    p.add_argument("--title", required=True); p.add_argument("--budget", type=float, default=12)
    p.add_argument("--mode", default="balanced", choices=["fast", "balanced", "efficient"])
    p.add_argument("--anywhere", action="store_true", help="compatibility flag; init accepts any directory")
    p = parser("set-status", cmd_set); p.add_argument("status", choices=STATUSES)
    p.add_argument("--reason", required=True)
    p = parser("claim", cmd_claim)
    p = parser("wait", cmd_wait, "gate-wait"); p.add_argument("what", nargs="?"); p.add_argument("--clear", action="store_true")
    p.add_argument("--gate", action="store_true"); p.add_argument("--round", type=int); p.add_argument("--start", action="store_true")
    p = parser("log", cmd_log); p.add_argument("text", nargs="?"); p.add_argument("--lead", action="store_true")
    p.add_argument("--at")
    p = parser("note", cmd_note); p.add_argument("section", choices=["parked", "decision", "next", "now"])
    p.add_argument("text"); p.add_argument("--add", action="store_true", help="now: add a bullet instead of replacing the section")
    p = parser("set", cmd_set); p.add_argument("pairs", nargs="*")
    p.add_argument("--status", choices=STATUSES); p.add_argument("--reason")
    p = parser("status", cmd_status, "report", "overview", directory="?", description="Without dir: scan immediate child folders of MARATHON_REPOS_ROOT if set; otherwise ~/repos and the current folder\'s parent. MARATHON_OVERVIEW_GLOBS overrides these patterns (os.pathsep-separated). Include registered projects in either case.")
    p.add_argument("--full", action="store_true"); p.add_argument("--report", action="store_true")
    p.add_argument("--since", help="ISO time (default: last report, else project start)")
    p.add_argument("--mark", action="store_true", help="record that the report was sent")
    p.add_argument("--save", help="with --mark: file (or - for stdin) holding the answer, appended to REPORTS.md")
    p.add_argument("--forecast", help='with --mark: your forecast, e.g. "next=74 end=76 chance=40" (next gate, final score, %% chance of the pass mark)')
    p.add_argument("--no-live", action="store_true", help="skip the live-link check")
    p.add_argument("--days", type=float, default=14, help="include paused/done projects touched in the last N days (default 14)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--sessions", help='JSON file mapping a project folder (or name) to {"id": "local_…", "title": "…"}')
    p.add_argument("--widget", help="write the overview cards as an inline-widget HTML fragment to this file")
    p.add_argument("--markdown", action="store_true", help="print the phone-friendly overview table")
    p = parser("score", cmd_score); p.add_argument("--from", dest="src", action="append")
    p.add_argument("--final", action="store_true"); p.add_argument("--round", type=int)
    p.add_argument("--artifact"); p.add_argument("--reuse-round", type=int, help="final: reuse a passing dual round on the same clean SHA and rubric")
    p.add_argument("--carry-forward", action="store_true", help="focused re-gate: each reviewer's omitted keys carry the previous scored round; Astra stays full")
    p.add_argument("--adjudication", help="the lead's ruling file when Opus and GPT disagree (score prints ADJUDICATE)")
    p.add_argument("--astra-pending", action="store_true", help="Astra is past astra_wait: score with Opus now, merge Astra later")
    p.add_argument("--late", action="store_true", help="rescore an earlier round with the late Astra report added (replaces that row)")
    p.add_argument("--missing-reason", help="reason (at least 10 characters) for a missing reviewer model; final requires two configured Claude reviewers (Opus, or Sonnet under sonnet+astra)")
    p = parser("evidence", cmd_evidence, help="prepare changes and a pre-gate evidence index")
    p.add_argument("--round", type=int, required=True)
    p = parser("preflight", cmd_preflight, "logins", directory=False); p.add_argument("--type", default="site", choices=["game", "site", "research"])
    p.add_argument("--logins", nargs="+"); p.add_argument("urls", nargs="*", help=argparse.SUPPRESS)
    p = parser("install-hook", cmd_install_hook, directory=False); p.add_argument("--remove", action="store_true")
    p = parser("worker", cmd_worker, "workers", help="list quality, or update a worker row by id (key=value; +N adds)")
    p.add_argument("id", nargs="?"); p.add_argument("pairs", nargs="*")
    p.add_argument("--pool", action="store_true", help="include every marathon project on this PC")
    p = parser("usage", cmd_usage, help="token ledger: lead sessions, Claude sub-agents, Codex runs")
    p.add_argument("--by-role", action="store_true", help="group Claude sub-agents by metadata role")
    p.add_argument("--full", action="store_true")
    p = parser("handoff", cmd_handoff, "handoff-abort", help="prepare lead rotation; retain the old lead until the successor claims")
    p.add_argument("--why"); p.add_argument("--abort", action="store_true"); p.add_argument("--note", action="append")
    p.add_argument("--force", action="store_true"); p.add_argument("--save-only", action="store_true", help="write Handoff notes only; no transfer")
    p = parser("config", cmd_config, "models", directory="?", help="the run configuration (profile, lead, workers, gate) to show the user")
    p.add_argument("--short", action="store_true"); p.add_argument("--profiles", action="store_true")
    p.add_argument("--models", action="store_true"); p.add_argument("--name")
    p = parser("ask", cmd_ask, help="question widget, answers and deadline defaults")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--file"); g.add_argument("--resolve", action="store_true"); g.add_argument("--status", action="store_true")
    p.add_argument("--wait", type=float); p.add_argument("--answers"); p.add_argument("--at-deadline", action="store_true")
    p = parser("lock", cmd_lock, help="machine-wide browser lease"); p.add_argument("resource", choices=["browser"])
    p.add_argument("--owner", required=True); p.add_argument("--ttl", type=float, default=30); p.add_argument("--force", action="store_true")
    g = p.add_mutually_exclusive_group(); g.add_argument("--release", action="store_true"); g.add_argument("--status", action="store_true")
    argv = sys.argv[1:]
    if argv[:2] == ["worker", "list"]:
        argv = ["worker", *argv[2:]]
    a = ap.parse_args(argv)
    for alias, flag in (("report", "report"), ("gate-wait", "gate"), ("handoff-abort", "abort"), ("models", "models")):
        if a.cmd == alias:
            setattr(a, flag, True)
    if a.cmd in ("status", "report", "overview"):
        if a.report and not a.dir: ap.error("status --report requires dir")
    elif a.cmd == "set":
        if a.status and (a.reason is None or a.pairs): ap.error("--status requires --reason and no key=value pairs")
        if not a.status and (not a.pairs or a.reason): ap.error("set requires key=value pairs or --status with --reason")
    elif a.cmd in ("wait", "gate-wait"):
        if a.gate and a.round is None: ap.error("--gate requires --round")
    elif a.cmd in ("preflight", "logins"):
        if a.cmd == "logins":
            if not a.urls: ap.error("logins requires urls")
            a.logins = a.urls
    elif a.cmd in ("handoff", "handoff-abort"):
        if not a.abort and a.why is None: ap.error("handoff requires --why or --abort")
    elif a.cmd in ("config", "models"):
        if not (a.models or a.profiles) and not a.dir: ap.error("config requires dir or --models")
    if a.f == cmd_log and a.text == "-":
        a.piped_text = input_text()
    if a.f == cmd_status and a.report and a.mark and a.save == "-":
        a.saved_text = sys.stdin.buffer.read().decode("utf-8-sig")
    d = Path(a.dir).resolve() if getattr(a, "dir", None) else None
    writes = a.f in (cmd_claim, cmd_set, cmd_note, cmd_log, cmd_wait, cmd_score, cmd_handoff)
    writes = writes or (a.f == cmd_status and a.report and a.mark)
    if d and (d / "STATE.md").exists() and writes:
        with file_lock(d / ".tmp" / "state-command.lock", timeout=10, label="state command"):
            a.f(a)
    else:
        a.f(a)


if __name__ == "__main__":
    main()
