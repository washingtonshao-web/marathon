"""Example load gate for Marathon (optional). To use it, copy or rename this file to load_limits.py next to marathon.py.

New Codex workers then wait while the whole PC is over MARATHON_LOAD_CAP percent CPU or RAM (default 80), and
`marathon.py status` shows the load line. Nothing that is already running is stopped. Standard library only:
Windows and Linux measure CPU and RAM; macOS measures CPU from the load average (RAM is not measured there).

    python load_limits.example.py        # print the readings and whether a new worker may start now
"""
import os
import sys
import time

CAP = float(os.environ.get("MARATHON_LOAD_CAP", "80"))  # percent, for CPU and RAM


def _cpu_windows(sample: float) -> float | None:
    import ctypes
    from ctypes import wintypes

    def times():
        idle, kernel, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
        if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
            return None
        return [(f.dwHighDateTime << 32) | f.dwLowDateTime for f in (idle, kernel, user)]

    a = times()
    time.sleep(sample)
    b = times()
    if not a or not b:
        return None
    idle, busy = b[0] - a[0], (b[1] - a[1]) + (b[2] - a[2])  # kernel time includes idle time
    return 100.0 * (busy - idle) / busy if busy > 0 else None


def _cpu_linux(sample: float) -> float | None:
    def times():
        with open("/proc/stat", encoding="ascii") as f:
            v = [int(x) for x in f.readline().split()[1:]]
        return v[3] + (v[4] if len(v) > 4 else 0), sum(v)  # idle + iowait, total

    i0, t0 = times()
    time.sleep(sample)
    i1, t1 = times()
    return 100.0 * (1 - (i1 - i0) / (t1 - t0)) if t1 > t0 else None


def cpu_percent(sample: float = 0.5) -> float | None:
    """Whole-PC CPU use in percent over `sample` seconds, or None when it cannot be measured."""
    try:
        if os.name == "nt":
            return _cpu_windows(sample)
        if os.path.exists("/proc/stat"):
            return _cpu_linux(sample)
        return min(100.0, 100.0 * os.getloadavg()[0] / (os.cpu_count() or 1))
    except Exception:  # a reading is a courtesy, never a failure
        return None


def ram_percent() -> float | None:
    """Whole-PC RAM use in percent, or None when it cannot be measured."""
    try:
        if os.name == "nt":
            import ctypes

            class MEMSTAT(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + \
                           [(n, ctypes.c_ulonglong) for n in ("total", "avail", "tpage", "apage", "tvirt", "avirt", "aext")]
            m = MEMSTAT()
            m.dwLength = ctypes.sizeof(MEMSTAT)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)) and m.total:
                return 100.0 * (m.total - m.avail) / m.total
            return None
        if os.path.exists("/proc/meminfo"):
            info = {}
            with open("/proc/meminfo", encoding="ascii") as f:
                for line in f:
                    k, v = line.split(":", 1)
                    info[k] = int(v.split()[0])
            return 100.0 * (1 - info["MemAvailable"] / info["MemTotal"])
    except Exception:
        return None
    return None


def readings() -> dict:
    return {"cpu": cpu_percent(), "ram": ram_percent()}


def check(kind: str = "cpu", values: dict | None = None) -> tuple[bool, str, dict]:
    """May new work of `kind` start now? (ok, why, readings). Every kind uses the same CPU and RAM cap here."""
    r = readings() if values is None else values
    over = [f"{k.upper()} {v:.0f}% > {CAP:.0f}%" for k, v in r.items() if v is not None and v > CAP]
    return not over, "; ".join(over) or "under limits", r


def describe(values: dict | None = None) -> str:
    r = readings() if values is None else values
    parts = [f"{k.upper()} {v:.0f}%" for k, v in r.items() if v is not None]
    return f"PC load {', '.join(parts) or 'not measured'} (cap {CAP:.0f}%)"


if __name__ == "__main__":
    values = readings()
    ok, why, _ = check("cpu", values)
    print(describe(values))
    print("new worker now: " + ("yes" if ok else "no, " + why))
    sys.exit(0)
