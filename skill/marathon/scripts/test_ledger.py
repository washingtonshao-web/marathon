"""Production quality, ledger and handoff regressions. Standard library only; no live model or network calls."""
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SCRIPT = HERE / "marathon.py"


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix=".ledger-test-", dir=REPO)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repos = self.root / "repos"
        self.home = self.root / "home"
        self.env = dict(os.environ, MARATHON_CLAUDE_HOME=str(self.home), MARATHON_REPOS_ROOT=str(self.repos),
                        MARATHON_OVERVIEW_GLOBS=str(self.repos / "*" / "STATE.md"),
                        CLAUDE_CODE_SESSION_ID="old-lead", GIT_CEILING_DIRECTORIES=str(self.root), PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
        self.project = self.repos / "project"
        self.cli("init", self.project, "--type", "site", "--title", "Ledger test")

    def cli(self, *args, code=0, session=None):
        env = self.env if session is None else dict(self.env, CLAUDE_CODE_SESSION_ID=session)
        r = subprocess.run([sys.executable, "-B", str(SCRIPT), *map(str, args)], capture_output=True,
                           encoding="utf-8", env=env, timeout=30, stdin=subprocess.DEVNULL)
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, code, out)
        return out

    def probe(self, code):
        prefix = f"import sys; sys.path.insert(0, {str(HERE)!r}); import marathon as m; from pathlib import Path; import json; "
        r = subprocess.run([sys.executable, "-B", "-c", prefix + code], capture_output=True, encoding="utf-8",
                           env=self.env, timeout=30, stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout.strip()

    def rows(self):
        p = self.project / "audits" / "workers.csv"
        if not p.exists():
            return []
        with p.open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))

    def state(self, **fields):
        p = self.project / "STATE.md"
        s = p.read_text(encoding="utf-8")
        for k, v in fields.items():
            s = re.sub(rf"^{k}:.*\n", "", s, flags=re.M)
            if v is not None:
                s = s.replace("---\n", f"---\n{k}: {v}\n", 1)
        p.write_text(s, encoding="utf-8")

    def read_state(self):
        return (self.project / "STATE.md").read_text(encoding="utf-8")

    def parallel(self, pairs):
        jobs = [subprocess.Popen([sys.executable, "-B", str(SCRIPT), "worker", str(self.project), *args],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env, stdin=subprocess.DEVNULL) for args in pairs]
        for job in jobs:
            out, err = job.communicate(timeout=30)
            self.assertEqual(job.returncode, 0, (out + err).decode("utf-8", "replace"))

    def usage_fixture(self):
        self.state(started="2026-01-01T00:00:00+00:00", lead_sessions="old-lead")
        folder = self.home / "projects" / "fixture"
        folder.mkdir(parents=True, exist_ok=True)
        lead = folder / "old-lead.jsonl"
        def message(mid, model, input, write, read, output, ttl=None, timestamp="2026-10-01T00:00:00Z"):
            usage = dict(input_tokens=input, cache_creation_input_tokens=write, cache_read_input_tokens=read, output_tokens=output)
            if ttl is not None: usage["cache_creation"] = ttl
            return dict(timestamp=timestamp, message=dict(id=mid, model=model, usage=usage))
        opus = message("opus", "claude-opus-5-5", 1000000, 5000000, 4000000, 5000000,
                       dict(ephemeral_5m_input_tokens=2000000, ephemeral_1h_input_tokens=3000000))
        sonnet = message("sonnet", "claude-sonnet-5-5", 2000000, 1000000, 3000000, 4000000)
        old = message("before", "claude-opus-5-5", 9999999, 0, 0, 0, timestamp="2025-12-31T23:59:59Z")
        lead.write_text("\n".join(json.dumps(r) for r in [old, opus, opus, sonnet, sonnet]) + "\n", encoding="utf-8")
        sub = lead.with_suffix("") / "subagents" / "agent-build.jsonl"
        sub.parent.mkdir(parents=True)
        worker = message("worker", "claude-sonnet-5-5", 1000000, 2000000, 3000000, 8)
        sub.write_text((json.dumps(worker) + "\n") * 3, encoding="utf-8")
        sub.with_suffix(".meta.json").write_text(json.dumps(dict(description="W12 build the candidate")), encoding="utf-8")
        # This inflated CSV must never influence costs or status.
        (self.home / "usage.csv").write_text("session_id,total_tokens,est_api_cost_usd\nold-lead,900000000,999999\n", encoding="utf-8")
        self.cli("worker", self.project, "C1", "agent=codex", "model=gpt-6-astra", "input=200", "cached=50", "output=30")
        self.cli("worker", self.project, "C2", "agent=codex", "model=gpt-6.1-sol", "input=100", "cached=25", "output=10")
        return lead, sub

    def ledger(self, by_role=False):
        return json.loads(self.probe(f"print(json.dumps(m.usage_ledger(Path({str(self.project)!r}), by_role={by_role!r})))"))

    def test_u1_dedup_model_prices_ttls_and_lower_bound(self):
        lead_path, sub_path = self.usage_fixture()
        lead, sub, codex = self.ledger()
        self.assertEqual(lead["msgs"], 2)
        self.assertEqual(lead["input"], 3000000)
        self.assertEqual(lead["cache_write"], 6000000)
        self.assertEqual((lead["w5"], lead["w1h"]), (3000000, 3000000))
        self.assertEqual(lead["output"], 9000000)
        opus = lead["models"]["claude-opus-5-5"]
        sonnet = lead["models"]["claude-sonnet-5-5"]
        for key, value in dict(input=4, cache_write=34, cache_read=.8, output=100).items():
            self.assertAlmostEqual(opus["costs"][key], value)
        for key, value in dict(input=4, cache_write=2.5, cache_read=.6, output=40).items():
            self.assertAlmostEqual(sonnet["costs"][key], value)
        self.assertAlmostEqual(lead["usd"], 185.9)
        self.assertFalse(lead["lower_bound"])
        self.assertEqual((sub["msgs"], sub["output"]), (1, 8))
        self.assertTrue(sub["lower_bound"])
        self.assertAlmostEqual(sub["usd"], 7.60008)
        self.assertEqual((codex["input"], codex["cache_read"], codex["output"], codex["total"]), (225, 75, 40, 340))
        self.assertIsNone(codex["usd"])
        self.assertEqual(set(codex["models"]), {"gpt-6-astra", "gpt-6.1-sol"})
        out = self.cli("usage", self.project, "--full")
        for text in ["$ input", "$ write", "$ read", "$ output", "$ total", "lead / opus-5-5", "lead / sonnet-5-5",
                     "$34", "≥$7.60", "subscription", "Claude total: ≥$194", "response start, not final output"]:
            self.assertIn(text, out)
        self.assertNotIn("999999", out)
        self.assertNotIn("tokens", self.cli("status", self.project))

    def test_u1_by_role_metadata_and_prices(self):
        lead, sub = self.usage_fixture()
        for desc, role in [("W12 build", "build workers"), ("Gate round 3", "gate reviewers"),
                           ("Strategic direction", "reviews"), ("Review changes", "reviews"),
                           ("Research sources", "research"), ("Teardown", "research"),
                           ("Benchmark", "research"), ("Translate text", "other")]:
            sub.with_suffix(".meta.json").write_text(json.dumps(dict(description=desc)), encoding="utf-8")
            rows = self.ledger(True)
            self.assertEqual(rows[1]["part"], role)
            self.assertTrue(rows[1]["lower_bound"])
            self.assertRegex(self.cli("usage", self.project, "--by-role"), r"(?m)^" + role + r"\s+1\s")
        sub.with_suffix(".meta.json").write_text("broken", encoding="utf-8")
        self.assertEqual(self.ledger(True)[1]["part"], "other")
        sub.with_suffix(".meta.json").unlink()
        self.assertEqual(self.ledger(True)[1]["part"], "other")
        out = self.probe("""
r = dict(input=1000000, output=1000000, cache_read=1000000, w5=1000000, w1h=1000000)
for model, pin, pout, pread in [('opus-5-5',4,20,.2), ('sonnet-5-5',2,10,.2), ('opus-5',5,25,.5),
                                ('sonnet-5',2,10,.2), ('fable-5-1',10,50,.25), ('haiku-5-5',.1,.5,.01)]:
    c = m.usage_cost('claude-' + model, r)
    assert c == dict(input=pin, output=pout, cache_read=pread, cache_write=3.25*pin), c
assert all(v is None for v in m.usage_cost('unpriced-model', r).values())
print('price checks passed')
""")
        self.assertIn("price checks passed", out)

    def test_u1_cache_reuse_and_invalidation(self):
        lead, sub = self.usage_fixture()
        original = self.ledger()
        cache = self.project / ".tmp" / "usage-cache.json"
        self.assertTrue(cache.exists())
        self.assertEqual(len(json.loads(cache.read_text(encoding="utf-8"))["transcripts"]), 2)
        before = cache.stat().st_mtime_ns
        code = f"""
from unittest.mock import patch
d = Path({str(self.project)!r})
with patch.object(m, 'transcript_usage', side_effect=AssertionError('warm cache must not rescan')):
    assert m.usage_ledger(d)[0]['msgs'] == 2
    assert m.usage_row(d)['lead']['usd'] == 185.9
print('cache reused')
"""
        self.assertIn("cache reused", self.probe(code))
        self.assertEqual(cache.stat().st_mtime_ns, before)
        # Same byte size with changed mtime must invalidate just this transcript.
        lead.write_text(lead.read_text(encoding="utf-8").replace('"input_tokens": 1000000', '"input_tokens": 2000000'), encoding="utf-8")
        os.utime(lead, ns=(lead.stat().st_atime_ns, lead.stat().st_mtime_ns + 1000000000))
        self.assertEqual(self.ledger()[0]["input"], 4000000)
        # Different size with the old mtime also invalidates.
        old_time = lead.stat().st_mtime_ns
        line = json.loads(lead.read_text(encoding="utf-8").splitlines()[1]); line["message"]["id"] = "extra"
        with lead.open("a", encoding="utf-8") as f: f.write(json.dumps(line) + "\n")
        os.utime(lead, ns=(lead.stat().st_atime_ns, old_time))
        self.assertEqual(self.ledger()[0]["msgs"], 3)
        self.state(started="2027-01-01T00:00:00+00:00")
        self.assertEqual(self.ledger()[0]["msgs"], 0)
        cache.write_text("broken", encoding="utf-8")
        self.assertEqual(self.ledger()[0]["msgs"], 0)
        lead.unlink(); sub.unlink()
        self.assertEqual(self.ledger()[0]["runs"], 0)
        self.assertEqual(json.loads(cache.read_text(encoding="utf-8"))["transcripts"], {})

    def test_u1_report_transcripts_only_and_session_scope(self):
        out = self.cli("report", self.project)
        self.assertNotIn("API-equivalent:", out)
        self.assertFalse((self.project / ".tmp" / "usage-cache.json").exists())
        lead, sub = self.usage_fixture()
        self.state(tokens_at_start="100|1")
        out = self.cli("report", self.project)
        self.assertEqual(out.count("API-equivalent:"), 1)
        self.assertIn("lead $186 · Claude sub-agents ≥$7.60", out)
        self.assertIn("Codex 340 tokens (subscription)", out)
        self.assertNotIn("lead tokens", out)
        self.assertNotIn("999999", out)
        # Mere invocation cannot attach the calling session, even when its transcripts exist.
        self.state(lead_sessions=None)
        self.assertEqual(self.ledger()[0]["runs"], 0)
        self.assertNotIn("API-equivalent:", self.cli("report", self.project))
        registry = self.home / "marathon" / "active" / "old-lead.json"
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(json.dumps(dict(project=str(self.project))), encoding="utf-8")
        self.assertEqual(self.ledger()[0]["runs"], 1)
        registry.write_text(json.dumps(dict(project=str(self.repos / "elsewhere"))), encoding="utf-8")
        self.assertEqual(self.ledger()[0]["runs"], 0)
        self.state(lead_sessions="old-lead,old-lead")
        self.assertEqual(self.ledger()[0]["runs"], 1)
        self.assertIn("lead $186", self.cli("report", self.project, session="unregistered"))

    def test_a3_concurrent_upserts_and_increments(self):
        self.parallel([[f"W{i}", "agent=codex", "model=gpt-6-astra", "status=done"] for i in range(24)])
        self.assertEqual({r["id"] for r in self.rows()}, {f"W{i}" for i in range(24)})
        self.parallel([["shared", "input=+1"] for _ in range(16)])
        self.assertEqual(next(r for r in self.rows() if r["id"] == "shared")["input"], "16")
        self.assertFalse((self.project / "audits" / "workers.csv.lock").exists())

    def test_a3_lock_stale_timeout_and_finally(self):
        lock = self.project / "audits" / "workers.csv.lock"
        lock.write_text("dead-writer", encoding="ascii")
        os.utime(lock, (time.time() - 61, time.time() - 61))
        self.cli("worker", self.project, "recovered", "status=done")
        self.assertFalse(lock.exists())
        self.cli("worker", self.project, "invalid", "class=bad", code=1)
        self.assertFalse(lock.exists())
        lock.write_text("live-writer", encoding="ascii")
        start = time.monotonic()
        out = self.cli("worker", self.project, "blocked", code=1)
        self.assertIn("worker ledger locked for 10s", out)
        self.assertGreaterEqual(time.monotonic() - start, 9.5)
        self.assertEqual(lock.read_text(encoding="utf-8"), "live-writer")
        self.assertEqual(len(self.rows()), 1)

    def start_probe(self, code):
        prefix = f"import sys; sys.path.insert(0, {str(HERE)!r}); import marathon as m; from pathlib import Path; import os, time; "
        job = subprocess.Popen([sys.executable, "-B", "-c", prefix + code], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", env=self.env)
        self.addCleanup(lambda: job.kill() if job.poll() is None else None)
        return job

    def test_a3_stale_contenders_and_live_windows_handle(self):
        lock = self.project / "audits" / "workers.csv.lock"
        lock.write_text("dead-writer", encoding="ascii")
        os.utime(lock, (time.time() - 61, time.time() - 61))
        self.parallel([[f"S{i}", "status=done"] for i in range(16)])
        self.assertEqual(len(self.rows()), 16)
        if os.name != "nt":
            return
        holder = self.start_probe(f"d = Path({str(self.project)!r})\nwith m.worker_lock(d):\n p=m.workers_path(d).with_suffix('.csv.lock'); os.utime(p, (time.time()-61, time.time()-61)); print('ready', flush=True); sys.stdin.readline()")
        self.assertEqual(holder.stdout.readline().strip(), "ready")
        writer = self.start_probe(f"print('trying', flush=True); m.upsert_worker(Path({str(self.project)!r}), 'after-live-owner', {{'status':'done'}})")
        self.assertEqual(writer.stdout.readline().strip(), "trying")
        time.sleep(0.2)
        self.assertIsNone(writer.poll(), "a stale timestamp must not permit deleting a live Windows lock")
        self.assertNotIn("after-live-owner", {r["id"] for r in self.rows()})
        holder.communicate("release\n", timeout=10)
        out, err = writer.communicate(timeout=10)
        self.assertEqual(writer.returncode, 0, out + err)
        self.assertEqual(len(self.rows()), 17)

    def test_a3_readers_share_lock_and_bom_columns(self):
        self.cli("worker", self.project, "original", "status=done")
        code = f"""
d = Path({str(self.project)!r})
original = m.csv.DictReader
def held_reader(f):
    print('ready', flush=True)
    sys.stdin.readline()
    return original(f)
m.csv.DictReader = held_reader
m.read_workers(d)
"""
        reader = self.start_probe(code)
        self.assertEqual(reader.stdout.readline().strip(), "ready")
        writer = self.start_probe(f"print('trying', flush=True); m.upsert_worker(Path({str(self.project)!r}), 'after-reader', {{'status':'done'}})")
        self.assertEqual(writer.stdout.readline().strip(), "trying")
        time.sleep(0.2)
        self.assertIsNone(writer.poll(), "reader must serialize with atomic replacement")
        self.assertNotIn("after-reader", {r["id"] for r in self.rows()})
        reader.communicate("release\n", timeout=10)
        out, err = writer.communicate(timeout=10)
        self.assertEqual(writer.returncode, 0, out + err)
        self.assertEqual(len(self.rows()), 2)
        self.assertFalse(list((self.project / "audits").glob(".workers.csv.*.tmp")))
        p = self.project / "audits" / "workers.csv"
        rows = self.rows()
        rows[0]['provider_request'] = 'preserved'
        with p.open('w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
        self.cli("worker", self.project, "original", "input=1")
        self.assertEqual(len(self.rows()), 2)
        self.assertEqual(self.rows()[0]['provider_request'], 'preserved')
        self.assertEqual(self.rows()[0]['id'], 'original')

    def test_a3_transient_permission_and_release_retries(self):
        code = f"""
from unittest.mock import patch
d = Path({str(self.project)!r})
real_open, real_unlink = m.os.open, Path.unlink
calls = {{'open':0, 'unlink':0}}
def busy_open(path, flags, *args, **kwargs):
    if str(path).endswith('.csv.lock'):
        calls['open'] += 1
        if calls['open'] == 1: raise PermissionError('delete pending')
    return real_open(path, flags, *args, **kwargs)
def busy_unlink(path, *args, **kwargs):
    if str(path).endswith('.csv.lock'):
        calls['unlink'] += 1
        if calls['unlink'] < 3: raise PermissionError('sharing violation')
    return real_unlink(path, *args, **kwargs)
with patch.object(m.os, 'open', busy_open), patch.object(Path, 'unlink', busy_unlink):
    m.upsert_worker(d, 'retries', {{'status':'done'}})
assert calls['open'] >= 2 and calls['unlink'] == 3, calls
assert not m.workers_path(d).with_suffix('.csv.lock').exists()
with patch.object(m.os, 'open', side_effect=PermissionError('not writable')):
    try:
        with m.worker_lock(d, timeout=0.05): pass
    except SystemExit as e:
        assert 'locked for 0.05s' in str(e)
    else:
        raise AssertionError('permission denial must exhaust the bounded retry')
print('permission retries passed')
"""
        self.assertIn('permission retries passed', self.probe(code))

    def test_a14_terminal_and_rerun(self):
        for status in ("done", "partial", "failed", "timeout", "fallback"):
            self.cli("worker", self.project, status, "status=" + status)
            self.assertRegex(next(r for r in self.rows() if r["id"] == status)["ended"], r"^\d{4}-")
        self.cli("worker", self.project, "done", "ended=2000-01-01T00:00", "status=done")
        self.cli("worker", self.project, "done", "first_pass=y")
        self.assertEqual(self.rows()[0]["ended"], "2000-01-01T00:00")
        self.cli("worker", self.project, "done", "status=")
        self.assertEqual(self.rows()[0]["ended"], "")
        self.assertIn("workers still running (done)", self.cli("handoff", self.project, "--why", "test", code=1))
        self.cli("worker", self.project, "done", "status=done")
        self.cli("worker", self.project, "done", "status=running")
        self.assertEqual(self.rows()[0]["ended"], "")
        self.assertIn("workers still running (done)", self.cli("handoff", self.project, "--why", "test", code=1))
        self.cli("worker", self.project, "done", "status=done")
        # Old ledgers may contain terminal rows without ended, and rows which never started.
        p = self.project / "audits" / "workers.csv"
        rows = self.rows()
        for r in rows:
            r["ended"] = ""
        rows.append(dict(rows[0], id="not-started", started="", status=""))
        with p.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
        self.assertIn("RESUME PROMPT", self.cli("handoff", self.project, "--why", "quiet"))

    def test_a18_empty_and_absent_fallback(self):
        self.state(worker_fallback=None)
        self.assertIn("fallback astra", self.cli("models", self.project))
        for value in ("", "none", "NONE"):
            out = self.cli("set", self.project, "worker_fallback=" + value)
            self.assertNotIn("→ fallback", out)
            models = self.cli("models", self.project)
            self.assertEqual(len([line for line in models.splitlines() if line.startswith(("primary ", "fallback"))]), 1)
            self.assertIn("primary  sol61", models)
        self.assertEqual(json.loads(self.probe("print(json.dumps(m.chain_from({'profile':'codex'}, 'sol61')))")), ["sol61", "astra", "sonnet"])
        self.assertEqual(json.loads(self.probe("print(json.dumps(m.chain_from({'profile':'codex'}, 'gpt-6.1-sol')))")), ["gpt-6.1-sol", "astra", "sonnet"])
        self.assertEqual(json.loads(self.probe("print(json.dumps(m.chain_from({'profile':'codex'}, 'luna')))")), ["luna", "sonnet"])
        self.assertEqual(json.loads(self.probe("print(json.dumps(m.chain_from({'profile':'codex'}, 'sonnet')))")), ["sonnet"])
        self.assertEqual(json.loads(self.probe("print(json.dumps(m.chain_from({'profile':'codex','worker_fallback':''}, 'luna')))")), ["luna"])
        self.assertEqual(json.loads(self.probe("print(json.dumps(m.chain_from({'profile':'codex'})))")), ["sol61", "astra", "sonnet"])

    def test_s10_new_chain_astra_override_and_existing_state(self):
        self.assertIn("workers: sol61", self.read_state())
        self.assertIn("worker_fallback: astra,sonnet", self.read_state())
        chain = lambda: json.loads(self.probe(f"print(json.dumps(m.chain_from(m.read_state(Path({str(self.project)!r}))[0])))"))
        self.assertEqual(chain(), ["sol61", "astra", "sonnet"])
        config = self.cli("config", self.project)
        self.assertIn("GPT-6.1-Sol high → fallback GPT-6-Astra high → Claude Sonnet 5.5", config)
        self.assertIn("Opus 5.5 xhigh + Astra high", config)
        self.cli("set", self.project, "workers=astra")
        self.assertEqual(chain(), ["astra", "sonnet"])
        self.state(workers="astra", worker_fallback="sol61,sonnet")
        original = (self.project / "STATE.md").read_bytes()
        self.assertEqual(chain(), ["astra", "sol61", "sonnet"])
        for command in (("config", self.project), ("models", self.project), ("status", self.project)):
            self.cli(*command)
            self.assertEqual((self.project / "STATE.md").read_bytes(), original)
        self.cli("set", self.project, "next=unrelated update")
        self.assertEqual(chain(), ["astra", "sol61", "sonnet"])
        self.assertIn("workers: astra", self.read_state())
        self.assertIn("worker_fallback: sol61,sonnet", self.read_state())
        self.cli("set", self.project, "profile=claude")
        self.assertEqual(chain(), ["sonnet", "opus"])

    def test_b2_legacy_and_new_profile(self):
        self.assertIn("profile: codex", self.read_state())
        self.assertIn("primary  sol61", self.cli("models"))
        self.state(profile=None, workers=None, worker_fallback=None)
        text = "No profile chosen yet (older project): running as Classic. Use profile=codex to switch."
        self.assertIn(text, self.cli("config", self.project))
        self.assertIn(text, self.cli("config", self.project, "--short"))
        self.assertEqual(self.probe("print(m.run_value({}, 'profile'))"), "classic")
        self.assertIn("primary  opus", self.cli("models", self.project))
        self.assertIn("fallback sonnet", self.cli("models", self.project))
        self.cli("set", self.project, "profile=codex")
        self.assertNotIn(text, self.cli("config", self.project))
        self.assertIn("primary  sol61", self.cli("models", self.project))

    def test_a13_two_phase_and_abort(self):
        self.cli("set-status", self.project, "running", "--reason", "test")
        registry = self.home / "marathon" / "active"
        old = registry / "old-lead.json"
        (registry / "historical.json").write_text(json.dumps({"project": str(self.project).upper()}), encoding="utf-8")
        other = registry / "other-project.json"
        other.write_text(json.dumps({"project": str(self.repos / "other")}), encoding="utf-8")
        unrelated = registry / "unlisted.json"
        unrelated.write_text(json.dumps({"project": str(self.project)}), encoding="utf-8")
        self.state(lead_sessions="old-lead,historical,other-project")
        out = self.cli("handoff", self.project, "--why", "context full", "--note", "next wave")
        self.assertIn("RESUME PROMPT", out)
        self.assertTrue(old.exists())
        self.assertIn("handoff_pending=", self.cli("config", self.project))
        self.assertIn("handoff_pending=", self.cli("status", self.project))
        self.assertIn("next wave", self.read_state())
        self.assertNotIn("handoff complete", self.cli("claim", self.project))
        self.assertIn("handoff_pending:", self.read_state())
        out = self.cli("claim", self.project, session="new-lead")
        self.assertIn("handoff complete", out)
        self.assertFalse(old.exists())
        if os.name == "nt":
            self.assertFalse((registry / "historical.json").exists())
        self.assertTrue((registry / "new-lead.json").exists())
        self.assertTrue(other.exists())
        self.assertTrue(unrelated.exists())
        self.assertNotIn("handoff_pending:", self.read_state())
        self.assertIn("old-lead,historical,other-project,new-lead", self.read_state())
        self.cli("handoff", self.project, "--why", "next rotation", session="new-lead")
        self.cli("handoff-abort", self.project, session="new-lead")
        self.assertNotIn("handoff_pending:", self.read_state())
        self.assertTrue((registry / "new-lead.json").exists())
        self.assertIn("Stop", json.loads((self.home / "settings.json").read_text(encoding="utf-8"))["hooks"])

    def test_a20_model_effort_and_assessments(self):
        code = """
rows = []
for model, effort in [('gpt-6.1-sol', 'high'), ('gpt-6-astra', 'xhigh'), ('opus', 'high')]:
    rows += [dict(id=str(i), model=model, effort=effort, status='done', first_pass='y', critical='0', major='0', **{'class':'build'}) for i in range(8)]
rows += [dict(id='u'+str(i), model='gpt-6-astra', effort='high', status='done', first_pass='y', **{'class':'build'}) for i in range(8)]
s = m.worker_stats(rows)
assert s[('gpt-6-astra/high','build')]['unassessed'] == 8
assert s[('gpt-6-astra/high','build')]['fp_n'] == 0
assert len(s) == 4
for r in rows[-8:]:
    r.update(critical='0', major='1', first_pass='n')
s = m.worker_stats(rows)
for missing in ['first_pass', 'critical', 'major']:
    row = dict(rows[-1]); row.pop(missing)
    stats = m.worker_stats([row])[('gpt-6-astra/high','build')]
    assert stats['unassessed'] == 1 and stats['fp_n'] == 0 and stats['defects'] == 0
# An assessed population's denominator must not include unassessed runs.
clean = dict(rows[-1], first_pass='y', major='0')
unknown = dict(clean, first_pass='', major='99')
s = m.worker_stats([clean, unknown])[('gpt-6-astra/high','build')]
assert s['fp_n'] == 1 and s['defects'] == 0 and s['unassessed'] == 1
print('quality checks passed')
"""
        self.assertIn("quality checks passed", self.probe(code))

    def test_a21_pool_deduplicates_projects_and_ids(self):
        code = f"""
d = Path({str(self.project)!r})
p = d.parent / 'other'; p.mkdir(); (p / 'STATE.md').write_text('x', encoding='utf-8')
rows = [dict(id='W'+str(i), model='gpt-6-astra', effort='high', status='done', first_pass='y', critical='0', major='0', **{{'class':'build'}}) for i in range(4)]
m.write_workers(p, rows + [rows[0]])
m.write_workers(d, [rows[0]])
import os
os.environ.pop('MARATHON_REPOS_ROOT')
os.environ.pop('MARATHON_OVERVIEW_GLOBS')
m.OVERVIEW_GLOBS = [str(p / 'STATE.md'), str(p / '..' / 'other' / 'STATE.md'), str(d / 'STATE.md')]
if os.name == 'nt': m.OVERVIEW_GLOBS.append(str(p / 'STATE.md').upper())
pooled = m.pooled_workers(d, True)
assert len(pooled) == 5, pooled
assert m.worker_stats(pooled)[('gpt-6-astra/high','build')]['fp_n'] == 5
import argparse
m.cmd_workers(argparse.Namespace(dir=str(d), pool=True))
"""
        out = self.probe(code)
        self.assertIn("gpt-6-astra/high", out)
        self.assertIn("assessed", self.cli("workers", self.project, "--pool"))

    def test_r2_production_quality(self):
        code = f"""
import argparse, io
from contextlib import redirect_stdout
d = Path({str(self.project)!r})
def output(rows):
    m.write_workers(d, rows)
    out = io.StringIO()
    with redirect_stdout(out): m.cmd_workers(argparse.Namespace(dir=str(d), pool=False))
    return out.getvalue()
def rows(n, passed, defects=0, model='gpt-6-astra', effort='high', cls='build'):
    return [dict(id=str(i), model=model, effort=effort, status='done', first_pass='y' if i < passed else 'n',
                 critical='0', major=str(defects), minutes='2', input='100', output='20', **{{'class':cls}}) for i in range(n)]
for n, passed, defects in [(7,0,9), (8,5,0), (10,7,1), (10,6,0), (8,8,2)]:
    text = output(rows(n,passed,defects))
    assert all(h in text for h in ['runs','assessed','1st pass','defects/run','minutes','tokens']), text
    assert all(h not in text for h in ['KEEP CODEX','BEHIND','routing check','vs Opus']), text
assert m.model_key({{'model':'astra-xhigh'}}) == 'gpt-6-astra/xhigh'
assert m.model_key({{'model':'gpt-6-astra'}}) == 'gpt-6-astra/unspecified'
unknown = [dict(r, major='') for r in rows(8,0)]
synthetic = [dict(r, note='bake-off case: result.json') for r in rows(8,0,9)]
assert not m.worker_stats(synthetic)
assert 'no finished workers' in output(synthetic)
text = output(rows(8,8,2,cls='test'))
text = output(rows(8,8,0))
assert '16.0' in text and '960' in text, text
print('production checks passed')
"""
        self.assertIn('production checks passed', self.probe(code))
        self.assertIn("invalid choice: 'baseline'", self.cli('baseline', self.project, code=2))
        self.assertEqual('True', self.probe("print('Choosing the model' not in m.__doc__ and not hasattr(m, 'routing_verdicts') and not hasattr(m, 'cmd_baseline'))"))

    def test_r2_save_only_changes_handoff_only(self):
        self.cli('set', self.project, 'profile=codex-lead')
        self.cli('worker', self.project, 'live', 'status=running')
        for pending in (None, 'existing-transfer'):
            self.state(rotations='3', handoff_pending=pending)
            p = self.project / 'STATE.md'
            p.write_text(self.read_state().replace('rotations: 3', 'rotations: \"3\"'), encoding='utf-8')
            before = self.read_state()
            out = self.cli('handoff', self.project, '--save-only', '--why', 'checkpoint', '--note', 'next task', session='')
            after = self.read_state()
            self.assertEqual(before.split('---', 2)[1], after.split('---', 2)[1])
            self.assertEqual(before.split('## Handoff')[0].rstrip(), after.split('## Handoff')[0].rstrip())
            self.assertIn('checkpoint: checkpoint', after)
            self.assertIn('next task', after)
            self.assertNotIn('RESUME PROMPT', out)
            self.assertNotIn('handoff pending', out)
        self.assertFalse((self.home / 'marathon' / 'active').exists())

    def test_r2_requested_configuration_and_verified_claim(self):
        for profile in ('codex', 'codex-lead', 'claude', 'classic'):
            self.env.pop('CODEX_THREAD_ID', None)
            if profile == 'codex-lead':  # a Codex host, detected from its thread id, not from the profile
                self.env['CODEX_THREAD_ID'] = 'test-thread'
            self.cli('set', self.project, 'profile=' + profile)
            out = self.cli('config', self.project)
            self.assertIn('Lead: requested', out)
            self.assertIn('Workers requested:', out)
            self.assertIn('Gate requested:', out)
            self.assertNotIn('250k', out)
            self.assertNotIn('80k', out)
            if profile != 'classic':
                self.assertIn('first quiet point past 150k', out)
            if profile == 'codex-lead':
                self.assertIn('Codex checkpoint: handoff --save-only', out)
            self.assertIn('lead requested', self.cli('config', self.project, '--short'))
        self.cli('set', self.project, 'profile=codex')
        self.env.pop('CLAUDE_MODEL', None)
        self.cli('set-status', self.project, 'running', '--reason', 'test')
        self.assertNotIn('lead_verified:', self.read_state())
        self.env['CLAUDE_MODEL'] = 'claude-opus-5-5'
        self.cli('claim', self.project)
        self.assertIn('lead_verified: claude-opus-5-5', self.read_state())
        self.assertIn('Lead: verified claude-opus-5-5', self.cli('config', self.project))
        self.assertIn('lead verified claude-opus-5-5', self.cli('config', self.project, '--short'))
        self.env.pop('CLAUDE_MODEL')
        self.cli('claim', self.project)
        self.assertNotIn('lead_verified:', self.read_state())
        self.env['CLAUDE_MODEL'] = 'claude-opus-5-5'
        self.cli('claim', self.project)
        self.assertIn('lead_verified:', self.read_state())
        self.cli('claim', self.project, session='')
        self.assertNotIn('lead_verified:', self.read_state())



    # ---------- S1: alias side effects and compact usage ----------
    def test_s1_status_transition_alias_side_effects(self):
        code = f'''
import datetime as dt, io
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch
d = Path({str(self.project)!r})
initial = (d / 'STATE.md').read_bytes()
reg = m.reg_path()
settings = m.HOME / 'settings.json'
results = []
for legacy in (True, False):
    (d / 'STATE.md').write_bytes(initial)
    for p in (reg, settings, d / 'DECISIONS.md'): p.unlink(missing_ok=True)
    stages = []
    for i, status in enumerate(('running', 'running', 'paused', 'running', 'blocked', 'done')):
        fm, body = m.read_state(d)
        fm['waiting_on'] = 'background worker'
        m.write_state(d, fm, body)
        argv = ['set-status', str(d), status] if legacy else ['set', str(d), '--status', status]
        out = io.StringIO()
        with patch.object(sys, 'argv', ['marathon.py', *argv, '--reason', 'test reason']), \
                patch.object(m, 'now', return_value=dt.datetime(2026, 10, 1, i, tzinfo=dt.timezone.utc)), \
                patch.object(m.uuid, 'uuid4', return_value=SimpleNamespace(hex='12345678')), \
                patch.object(m, 'usage_row', return_value=dict(total_tokens=123, est_api_cost_usd=4)), redirect_stdout(out):
            m.main()
        fm, _ = m.read_state(d)
        assert fm['status'] == status and not fm['waiting_on'], fm
        assert fm['tokens_at_start'] == '123|4', fm
        assert bool(fm['running_since']) == (status == 'running'), fm
        assert reg.exists() == (status == 'running')
        stages.append((out.getvalue(), (d / 'STATE.md').read_bytes(),
                       reg.read_bytes() if reg.exists() else None, settings.read_bytes(),
                       (d / 'DECISIONS.md').read_bytes() if (d / 'DECISIONS.md').exists() else None))
    assert fm['work_hours'] == '3.00', fm
    results.append(stages)
assert results[0] == results[1], results
print('transition parity passed')
'''
        self.assertIn('transition parity passed', self.probe(code))

    def test_s1_gate_wait_and_abort_alias_side_effects(self):
        self.state(waiting_on='existing background job', waiting_since='original', handoff_pending='pending')
        code = f'''
import datetime as dt, io
from contextlib import redirect_stdout
from unittest.mock import patch
d = Path({str(self.project)!r})
initial = (d / 'STATE.md').read_bytes()
def invoke(argv):
    out = io.StringIO()
    with patch.object(sys, 'argv', ['marathon.py', *argv]), redirect_stdout(out):
        try: m.main()
        except SystemExit as e: return e.code, out.getvalue()
    return 0, out.getvalue()
with patch.object(m, 'now', return_value=dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc)):
    for old, new in ((['gate-wait', str(d)], ['wait', str(d), '--gate']),
                     (['handoff-abort', str(d)], ['handoff', str(d), '--abort'])):
        results = []
        for argv in (old, new):
            (d / 'STATE.md').write_bytes(initial)
            if old[0] == 'gate-wait':
                missing = invoke([*argv, '--round', '1'])
                start = invoke([*argv, '--round', '1', '--start'])
                query = invoke([*argv, '--round', '1'])
                wrong = invoke([*argv, '--round', '2'])
                assert missing[0] != 0 and wrong[0] != 0
                assert start[0] == query[0] == 0 and 'WAIT' in query[1]
                result = (missing, start, query, wrong)
            else:
                result = invoke(argv)
                assert result[0] == 0 and 'handoff_pending' not in m.read_state(d)[0]
            fm, _ = m.read_state(d)
            assert fm['waiting_on'] == 'existing background job' and fm['waiting_since'] == 'original', fm
            results.append((result, (d / 'STATE.md').read_bytes()))
        assert results[0] == results[1], results
print('wait and abort parity passed')
'''
        self.assertIn('wait and abort parity passed', self.probe(code))

    def test_s1_report_and_overview_alias_results(self):
        answer = self.root / 'answer.md'
        answer.write_text('Saved progress answer', encoding='utf-8')
        sessions = self.root / 'sessions.json'
        sessions.write_text('{}', encoding='utf-8')
        code = f'''
import datetime as dt, io
from contextlib import redirect_stdout
from unittest.mock import patch
d = Path({str(self.project)!r})
paths = [d / 'STATE.md', d / 'REPORTS.md', d / 'audits/forecasts.csv']
originals = {{p: p.read_bytes() if p.exists() else None for p in paths}}
widget = d / 'overview.html'
mark = ['--mark', '--save', {str(answer)!r}, '--forecast', 'next=80 end=90 chance=70']
sessions = ['--days', '3', '--sessions', {str(sessions)!r}]
for old, new in ((['report', str(d), '--no-live', '--since', '2026-01-01T00:00:00+00:00'], ['status', str(d), '--report', '--no-live', '--since', '2026-01-01T00:00:00+00:00']),
                 (['report', str(d), *mark], ['status', str(d), '--report', *mark]),
                 (['overview'], ['status']), (['overview', '--json', *sessions], ['status', '--json', *sessions]),
                 (['overview', '--markdown', '--widget', str(widget), *sessions], ['status', '--markdown', '--widget', str(widget), *sessions])):
    results = []
    for argv in (old, new):
        for p, data in originals.items():
            if data is None: p.unlink(missing_ok=True)
            else: p.write_bytes(data)
        out = io.StringIO()
        with patch.object(sys, 'argv', ['marathon.py', *argv]), \
                patch.object(m, 'now', return_value=dt.datetime(2026, 10, 20)), \
                patch.object(m, 'live_check', side_effect=AssertionError('no network')), redirect_stdout(out):
            m.main()
        results.append((out.getvalue(), [p.read_bytes() if p.exists() else None for p in paths + [widget]]))
    assert results[0] == results[1], (old, results)
print('report and overview parity passed')
'''
        self.assertIn('report and overview parity passed', self.probe(code))

    def test_s1_worker_and_models_alias_results(self):
        self.cli('worker', self.project, 'W1', 'model=astra', 'status=done', 'first_pass=n', 'major=2')
        for flags in ([], ['--pool']):
            self.assertEqual(self.cli('workers', self.project, *flags), self.cli('worker', self.project, *flags))
        for args in ([], [self.project], ['--name', 'astra'], ['--name', 'opus']):
            self.assertEqual(self.cli('models', *args), self.cli('config', '--models', *args))
        self.assertEqual(self.cli('models', '--name', 'bogus', code=1), self.cli('config', '--models', '--name', 'bogus', code=1))
        self.assertNotIn('bake-off', self.cli('worker', self.project))

    def test_s6_ask_defaults_are_lazy(self):
        self.assertNotIn('ask_wait:', self.read_state())
        self.assertNotIn('asking:', self.read_state())
        questions = self.root / 'questions.json'
        questions.write_text(json.dumps([dict(id='q1', text='Choose', options=['A', 'B'], default='A')]), encoding='utf-8')
        self.cli('ask', self.project, '--file', questions)
        data = json.loads(re.search(r'^asking: (.+)$', self.read_state(), re.M)[1])
        from datetime import datetime
        self.assertAlmostEqual((datetime.fromisoformat(data['deadline']) - datetime.now()).total_seconds(), 600, delta=3)
        self.cli('ask', self.project, '--resolve', '--answers', 'ok')
        self.assertIn('q1=A', self.read_state())

    def test_s6_state_lock_is_bounded_and_independent(self):
        self.cli('set-status', self.project, 'running', '--reason', 'isolated test')
        lock = self.project / '.tmp' / 'state-command.lock'
        before = (self.project / 'STATE.md').read_bytes()
        holder = self.start_probe(f"\nwith m.file_lock(Path({str(lock)!r})):\n print('ready', flush=True); sys.stdin.readline()")
        self.assertEqual(holder.stdout.readline().strip(), 'ready')
        for args in (('wait', 'worker'), ('gate-wait', '--round', '1', '--start'),
                     ('ask', '--status'), ('handoff', '--why', 'test'), ('handoff-abort',)):
            start = time.monotonic()
            out = self.cli(args[0], self.project, *args[1:], code=1)
            self.assertIn('state command locked for 10s', out)
            self.assertGreaterEqual(time.monotonic() - start, 9.5)
            self.assertLess(time.monotonic() - start, 15)
        self.assertEqual((self.project / 'STATE.md').read_bytes(), before)
        for args in (('status',), ('config',), ('usage',), ('worker', 'direct', 'input=1')):
            start = time.monotonic()
            self.cli(args[0], self.project, *args[1:])
            self.assertLess(time.monotonic() - start, 3)
        probe = f"""
import codex_worker as worker
d = Path({str(self.project)!r})
assert worker.m is m
fm, body = worker.m.read_state(d)
assert worker.m.chain_from(fm)
worker.m.upsert_worker(d, 'imported', {{'status': 'done'}})
print('direct worker calls passed')
"""
        self.assertIn('direct worker calls passed', self.probe(probe))
        start = time.monotonic()
        hook = subprocess.run([sys.executable, '-B', str(HERE / 'stop_hook.py')],
                              input=json.dumps(dict(session_id='old-lead', cwd=str(self.project))),
                              capture_output=True, encoding='utf-8', env=self.env, timeout=3)
        self.assertEqual(hook.returncode, 0, hook.stdout + hook.stderr)
        self.assertLess(time.monotonic() - start, 3)
        holder.communicate('release\n', timeout=3)
        self.assertEqual(holder.returncode, 0)
        self.cli('wait', self.project, 'worker')
        self.assertIn('waiting_on: worker', self.read_state())
        self.assertFalse(lock.exists())

    def test_s6_stdin_does_not_hold_state_lock(self):
        for args in (('log', '-'), ('report', '--mark', '--save', '-')):
            proc = subprocess.Popen([sys.executable, '-B', str(SCRIPT), args[0], str(self.project), *args[1:]],
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    encoding='utf-8', env=self.env)
            self.addCleanup(lambda p=proc: p.kill() if p.poll() is None else None)
            time.sleep(0.2)
            self.assertIsNone(proc.poll())
            self.assertFalse((self.project / '.tmp' / 'state-command.lock').exists())
            self.cli('note', self.project, 'decision', 'concurrent with pipe')
            out, err = proc.communicate('piped text', timeout=3)
            self.assertEqual(proc.returncode, 0, out + err)
        self.assertIn('piped text', (self.project / 'PROMPTS.md').read_text(encoding='utf-8'))
        self.assertIn('piped text', (self.project / 'REPORTS.md').read_text(encoding='utf-8'))
        dash = subprocess.run([sys.executable, '-B', str(SCRIPT), 'log', str(self.project), '-'],
                              input='-', capture_output=True, encoding='utf-8', env=self.env, timeout=3)
        self.assertEqual(dash.returncode, 0, dash.stdout + dash.stderr)
        self.assertIn('(user, 1 chars)', dash.stdout)
        self.assertTrue((self.project / 'PROMPTS.md').read_text(encoding='utf-8').endswith('\n-\n'))


    def test_s1_usage_totals_full_and_by_role(self):
        self.usage_fixture()
        short = self.cli('usage', self.project)
        full = self.cli('usage', self.project, '--full')
        self.assertEqual(len(short.splitlines()), 6)
        self.assertNotIn('lead / opus', short)
        self.assertNotIn('response start', short)
        self.assertIn('lead / opus-5-5', full)
        self.assertIn('lead / sonnet-5-5', full)
        self.assertIn('response start, not final output', full)
        for label in ('lead', 'Claude sub-agents', 'Codex runs'):
            self.assertRegex(short, r'(?m)^' + label + r'\s+')
        self.assertIn('Claude total: ≥$194', short)
        self.assertEqual(self.cli('usage', self.project, '--by-role'), self.cli('usage', self.project, '--by-role', '--full'))


if __name__ == "__main__":
    unittest.main(verbosity=2)
