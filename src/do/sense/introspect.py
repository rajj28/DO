"""Phase A: self-observation.

Reads only what a process is entitled to read about itself and its host. Two rules
this module obeys strictly:

* **No credential values ever leave this function.** Environment variables are read
  as *names only*. A name is world-knowledge ("something called ELEVENLABS exists
  here"); a value is a secret.
* **No side effects.** Nothing here imports socket/subprocess/urllib. The network
  probe lives in `probe_network`, which takes a Gate and therefore appears in the
  ledger like any other action — the first thing D.O. learns about the world is that
  its actions are mediated.

`perturb` exists for the falsification harness (docs/DO_CONCEPT.md H1). A perturbed
observation carries `perturbed:` in its source, so the ledger never claims a spoofed
value was measured.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from ..kernel.types import Epistemic, Namespace, Observation

# Binaries worth knowing about. Presence is a fact about the environment; what they
# are for is mostly not known to the seed, which is exactly where curiosity starts.
KNOWN_TOOLS = [
    "python", "node", "npm", "git", "docker", "ollama", "gcloud", "aws", "az",
    "curl", "ffmpeg", "sqlite3", "uv", "pip", "go", "rustc", "java", "kubectl",
]

GIB = 1024 ** 3


class Sensors:
    def __init__(self, perturb: dict[str, Any] | None = None):
        self.perturb = perturb or {}
        self.obs: list[Observation] = []
        self.failures: list[tuple[str, str]] = []

    # ---- helpers ----------------------------------------------------------
    def _add(self, key: str, value: Any, epistemic: Epistemic, source: str,
             ns: Namespace = Namespace.SELF, unit: str | None = None,
             confidence: float = 1.0, note: str | None = None) -> Observation:
        if key in self.perturb:
            value = self.perturb[key]
            source = f"perturbed:{source}"
            if value is None:
                epistemic = Epistemic.UNKNOWN
        o = Observation(key=key, value=value, epistemic=epistemic, source=source,
                        namespace=ns, unit=unit, confidence=confidence, note=note)
        self.obs.append(o)
        return o

    def _unknown(self, key: str, why: str, ns: Namespace = Namespace.SELF) -> Observation:
        self.failures.append((key, why))
        return self._add(key, None, Epistemic.UNKNOWN, f"probe_failed:{why}", ns)

    # ---- probes -----------------------------------------------------------
    def process(self) -> None:
        self._add("self.process.pid", os.getpid(), Epistemic.OBSERVED, "os.getpid")
        try:
            self._add("self.process.ppid", os.getppid(), Epistemic.OBSERVED, "os.getppid")
        except Exception as e:
            self._unknown("self.process.ppid", str(e))
        self._add("self.process.executable", sys.executable, Epistemic.OBSERVED, "sys.executable")
        self._add("self.process.argv", list(sys.argv), Epistemic.OBSERVED, "sys.argv")
        self._add("self.process.cwd", os.getcwd(), Epistemic.OBSERVED, "os.getcwd")
        self._add("self.process.interactive", bool(sys.stdin and sys.stdin.isatty()),
                  Epistemic.OBSERVED, "sys.stdin.isatty")

    def runtime(self) -> None:
        self._add("self.runtime.language", "python", Epistemic.OBSERVED, "platform")
        self._add("self.runtime.implementation", platform.python_implementation(),
                  Epistemic.OBSERVED, "platform.python_implementation")
        self._add("self.runtime.version", platform.python_version(),
                  Epistemic.OBSERVED, "platform.python_version")
        self._add("self.runtime.max_recursion", sys.getrecursionlimit(),
                  Epistemic.OBSERVED, "sys.getrecursionlimit")

    def host(self) -> None:
        u = platform.uname()
        self._add("world.host.system", u.system, Epistemic.OBSERVED, "platform.uname",
                  Namespace.WORLD)
        self._add("world.host.release", u.release, Epistemic.OBSERVED, "platform.uname",
                  Namespace.WORLD)
        self._add("world.host.machine", u.machine, Epistemic.OBSERVED, "platform.uname",
                  Namespace.WORLD)
        self._add("world.host.node_hash", _stable_hash(u.node), Epistemic.OBSERVED,
                  "platform.uname+sha256", Namespace.WORLD,
                  note="hostname hashed, not stored in the clear")

    def compute(self) -> None:
        n = os.cpu_count()
        if n:
            self._add("resources.cpu.logical", n, Epistemic.OBSERVED, "os.cpu_count",
                      Namespace.RESOURCES, unit="cores")
        else:
            self._unknown("resources.cpu.logical", "os.cpu_count returned None",
                          Namespace.RESOURCES)
        try:
            self._add("resources.cpu.affinity", len(os.sched_getaffinity(0)),
                      Epistemic.OBSERVED, "os.sched_getaffinity", Namespace.RESOURCES,
                      unit="cores")
        except AttributeError:
            self._unknown("resources.cpu.affinity", "not available on this platform",
                          Namespace.RESOURCES)
        try:
            la = os.getloadavg()
            self._add("resources.cpu.load1", round(la[0], 2), Epistemic.OBSERVED,
                      "os.getloadavg", Namespace.RESOURCES)
        except (AttributeError, OSError):
            self._unknown("resources.cpu.load1", "no load average on this platform",
                          Namespace.RESOURCES)

    def memory(self) -> None:
        total = avail = None
        src = ""
        if platform.system() == "Windows":
            try:
                import ctypes

                class _MS(ctypes.Structure):
                    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                                ("ullTotalPhys", ctypes.c_ulonglong),
                                ("ullAvailPhys", ctypes.c_ulonglong),
                                ("ullTotalPageFile", ctypes.c_ulonglong),
                                ("ullAvailPageFile", ctypes.c_ulonglong),
                                ("ullTotalVirtual", ctypes.c_ulonglong),
                                ("ullAvailVirtual", ctypes.c_ulonglong),
                                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

                m = _MS()
                m.dwLength = ctypes.sizeof(_MS)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
                total, avail = m.ullTotalPhys, m.ullAvailPhys
                src = "kernel32.GlobalMemoryStatusEx"
                self._add("resources.ram.pagefile_avail_bytes", m.ullAvailPageFile,
                          Epistemic.OBSERVED, src, Namespace.RESOURCES, unit="bytes")
            except Exception as e:
                self._unknown("resources.ram.total_bytes", f"ctypes probe failed: {e}",
                              Namespace.RESOURCES)
        else:
            try:
                total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
                src = "os.sysconf"
                mi = Path("/proc/meminfo")
                if mi.exists():
                    for line in mi.read_text().splitlines():
                        if line.startswith("MemAvailable:"):
                            avail = int(line.split()[1]) * 1024
                            src = "os.sysconf + /proc/meminfo"
            except Exception as e:
                self._unknown("resources.ram.total_bytes", f"sysconf failed: {e}",
                              Namespace.RESOURCES)

        if total:
            self._add("resources.ram.total_bytes", total, Epistemic.OBSERVED, src,
                      Namespace.RESOURCES, unit="bytes")
        if avail is not None:
            self._add("resources.ram.available_bytes", avail, Epistemic.OBSERVED, src,
                      Namespace.RESOURCES, unit="bytes")
            if total:
                self._add("resources.ram.free_ratio", round(avail / total, 4),
                          Epistemic.INFERRED, "available/total", Namespace.RESOURCES)
        else:
            self._unknown("resources.ram.available_bytes", "no available-memory probe",
                          Namespace.RESOURCES)

    def storage(self) -> None:
        root = Path(os.getcwd()).anchor or "/"
        try:
            du = shutil.disk_usage(root)
            self._add("resources.disk.root", str(root), Epistemic.OBSERVED, "os.getcwd",
                      Namespace.RESOURCES)
            self._add("resources.disk.total_bytes", du.total, Epistemic.OBSERVED,
                      "shutil.disk_usage", Namespace.RESOURCES, unit="bytes")
            self._add("resources.disk.free_bytes", du.free, Epistemic.OBSERVED,
                      "shutil.disk_usage", Namespace.RESOURCES, unit="bytes")
            self._add("resources.disk.free_ratio", round(du.free / du.total, 4),
                      Epistemic.INFERRED, "free/total", Namespace.RESOURCES)
        except Exception as e:
            self._unknown("resources.disk.free_bytes", str(e), Namespace.RESOURCES)

    def clock(self) -> None:
        now = time.time()
        self._add("self.clock.epoch", now, Epistemic.OBSERVED, "time.time", unit="s")
        self._add("self.clock.local_iso", time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now)),
                  Epistemic.OBSERVED, "time.strftime")
        self._add("self.clock.timezone", time.strftime("%Z"), Epistemic.OBSERVED, "time.strftime")
        self._add("self.clock.monotonic", round(time.monotonic(), 3), Epistemic.OBSERVED,
                  "time.monotonic", unit="s")

    def tools(self) -> None:
        found, missing = {}, []
        for t in KNOWN_TOOLS:
            p = shutil.which(t)
            (found.__setitem__(t, p) if p else missing.append(t))
        self._add("tools.on_path", sorted(found), Epistemic.OBSERVED, "shutil.which",
                  Namespace.TOOLS)
        self._add("tools.absent", sorted(missing), Epistemic.OBSERVED, "shutil.which",
                  Namespace.TOOLS)
        self._add("tools.paths", found, Epistemic.OBSERVED, "shutil.which", Namespace.TOOLS)
        self._add("tools.local_models", _local_models(), Epistemic.OBSERVED,
                  "filesystem:ollama manifests", Namespace.TOOLS,
                  note="read from manifest files; no process was executed")

    def environment_names(self) -> None:
        """Names only. Never values."""
        names = sorted(os.environ.keys())
        self._add("world.env.count", len(names), Epistemic.OBSERVED, "os.environ",
                  Namespace.WORLD)
        self._add("world.env.names", names, Epistemic.OBSERVED, "os.environ",
                  Namespace.WORLD, note="names only; values never read")

    def memory_state(self, db_path: Path, ledger_path: Path) -> None:
        self._add("self.memory.db_exists", db_path.exists(), Epistemic.OBSERVED,
                  "pathlib.exists")
        self._add("self.memory.db_bytes", db_path.stat().st_size if db_path.exists() else 0,
                  Epistemic.OBSERVED, "pathlib.stat", unit="bytes")
        self._add("self.memory.ledger_exists", ledger_path.exists(), Epistemic.OBSERVED,
                  "pathlib.exists")

    # ---- unknowns the seed cannot resolve alone ---------------------------
    def declare_structural_unknowns(self) -> None:
        """Slots that matter and that no local probe can fill. Declaring them is not
        the same as fabricating them: each is recorded as UNKNOWN with a reason."""
        for key, why, ns in [
            ("user.identity", "no probe can establish who started this process", Namespace.USER),
            ("user.intent", "purpose is not inspectable from the environment", Namespace.USER),
            ("self.purpose", "no goal was supplied at construction", Namespace.SELF),
            ("self.expected_lifetime", "no termination policy is visible", Namespace.SELF),
            ("world.network.reachable", "not yet probed", Namespace.WORLD),
        ]:
            self._add(key, None, Epistemic.UNKNOWN, f"undeterminable:{why}", ns)

    def run_all(self, db_path: Path, ledger_path: Path) -> list[Observation]:
        for probe in (self.process, self.runtime, self.host, self.compute,
                      self.memory, self.storage, self.clock, self.tools,
                      self.environment_names):
            t0 = time.perf_counter()
            try:
                probe()
            except Exception as e:                 # a failed probe is data, not a crash
                self._unknown(f"probe.{probe.__name__}", f"{type(e).__name__}: {e}")
            dt = (time.perf_counter() - t0) * 1000
            if self.obs:
                self.obs[-1].cost_ms = round(dt, 2)
        self.memory_state(db_path, ledger_path)
        self.declare_structural_unknowns()
        return self.obs


def probe_network(gate, sensors: Sensors, hosts: list[str] | None = None) -> None:
    """Network reachability, through the gate. Deliberately not part of run_all():
    perception that touches the outside world is an action."""
    from ..kernel.types import EffectRequest

    hosts = hosts or ["one.one.one.one", "example.com"]
    reachable, detail = False, {}
    for h in hosts:
        r = gate.request(EffectRequest(
            kind="net.dns", target=h,
            justification="determine whether the world outside this host is reachable; "
                          "world.network.reachable is currently unknown",
            payload={"timeout": 3.0}))
        detail[h] = {"ok": r.ok, "verdict": r.verdict, "error": r.error}
        if r.ok:
            reachable = True
            break

    if reachable:
        sensors._add("world.network.reachable", True, Epistemic.OBSERVED,
                     "gate:net.dns", Namespace.WORLD)
    else:
        first = next(iter(detail.values()), {})
        sensors._add("world.network.reachable", False, Epistemic.OBSERVED,
                     f"gate:net.dns({first.get('verdict', 'error')})", Namespace.WORLD,
                     note=str(first.get("error"))[:120])
    sensors._add("world.network.probe_detail", detail, Epistemic.OBSERVED, "gate:net.dns",
                 Namespace.WORLD)


# ---- module helpers -------------------------------------------------------
def _stable_hash(s: str) -> str:
    import hashlib
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _local_models() -> list[dict]:
    """Discover locally installed models by reading manifests. Filesystem read only —
    running `ollama list` would be a subprocess, which policy forbids in v1."""
    out: list[dict] = []
    base = Path.home() / ".ollama" / "models" / "manifests"
    if not base.exists():
        return out
    for mf in base.rglob("*"):
        if not mf.is_file():
            continue
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
            size = sum(int(l.get("size", 0)) for l in data.get("layers", []))
            rel = mf.relative_to(base).as_posix().split("/")
            name = f"{rel[-2]}:{rel[-1]}" if len(rel) >= 2 else mf.name
            out.append({"name": name, "bytes": size, "gib": round(size / GIB, 2),
                        "runtime": "ollama"})
        except Exception:
            continue
    return sorted(out, key=lambda m: m["bytes"])
