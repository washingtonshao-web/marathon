"""load_limits.example.py: the readings, the cap, and the hook shapes codex_worker.py and marathon.py expect."""
import importlib.util
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
FAILED = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" -- {detail}"))
    if not cond:
        FAILED.append(name)


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    L = load("load_limits_example", "load_limits.example.py")
    r = L.readings()
    check("readings: CPU and RAM are percentages or None",
          all(v is None or 0 <= v <= 100 for v in (r["cpu"], r["ram"])) and set(r) == {"cpu", "ram"}, r)
    if sys.platform in ("win32", "linux"):
        check("readings: CPU and RAM are measured on Windows and Linux", r["cpu"] is not None and r["ram"] is not None, r)
    ok, why, details = L.check("cpu", {"cpu": 79.0, "ram": 40.0})
    check("check: under the cap", ok and why == "under limits" and details["cpu"] == 79.0, (ok, why))
    ok, why, _ = L.check("cpu", {"cpu": 91.0, "ram": 85.0})
    check("check: over the cap names both readings", not ok and "CPU 91% > 80%" in why and "RAM 85% > 80%" in why, why)
    ok, why, _ = L.check("cpu", {"cpu": None, "ram": None})
    check("check: nothing measured never blocks", ok, why)
    check("describe: one line with the cap", L.describe({"cpu": 50.0, "ram": None}) == "PC load CPU 50% (cap 80%)",
          L.describe({"cpu": 50.0, "ram": None}))

    # the hook as codex_worker.py uses it once the file is renamed to load_limits.py
    CW = load("cw_load_test", "codex_worker.py")
    calls = iter([{"cpu": 95.0, "ram": 50.0}, {"cpu": 30.0, "ram": 50.0}])
    hook = SimpleNamespace(check=lambda kind: L.check(kind, next(calls)))
    buf = io.StringIO()
    with patch.dict(sys.modules, {"load_limits": hook}), patch.object(CW.time, "sleep", lambda s: None), redirect_stdout(buf):
        CW.wait_for_room("W1")
    check("hook: a new Codex worker waits while CPU is over the cap, then starts", "W1 WAIT" in buf.getvalue()
          and "CPU 95% > 80%" in buf.getvalue(), buf.getvalue())

    print(f"\n{len(FAILED)} failure(s)" if FAILED else "\nall passed")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
