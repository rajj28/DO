"""Capability registry with affordability checking.

Most agent frameworks treat a tool as available if it is installed. On this host that
is false in an instructive way: a 18 GiB model sits on disk while 2.8 GiB of RAM is
free. "Installed" and "usable" are different states, and conflating them makes an
agent confidently plan actions it cannot perform.

Hence `installed_unaffordable`, and hence every capability carrying resource
preconditions that are checked against live measurements rather than assumed.

Lifecycle (docs/ARCHITECTURE.md section 9):
    discover -> understand -> evaluate -> experiment -> integrate -> test
             -> deploy -> measure -> retain | rollback
v0.1 implements discover / evaluate / measure. The rest are scaffolded interfaces with
no autonomous path to code execution, deliberately (see docs/SAFETY.md).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Any, Callable

GIB = 1024 ** 3

UNKNOWN = "unknown"
DISCOVERED = "discovered"
INSTALLED_UNAFFORDABLE = "installed_unaffordable"
AVAILABLE = "available"
DEGRADED = "degraded"
QUARANTINED = "quarantined"
RETIRED = "retired"


@dataclass
class Capability:
    name: str
    description: str
    version: str = "0.1.0"
    requirements: dict = field(default_factory=dict)   # ram_bytes, disk_bytes, network, module
    permissions: list[str] = field(default_factory=list)
    risk: float = 0.1
    dependencies: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    status: str = UNKNOWN
    reason: str = ""
    performance: dict = field(default_factory=dict)
    discovered_ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


def _fmt(n: float) -> str:
    return f"{n / GIB:.1f} GiB"


class Registry:
    def __init__(self, ledger=None):
        self.caps: dict[str, Capability] = {}
        self.ledger = ledger

    def declare(self, cap: Capability) -> Capability:
        self.caps[cap.name] = cap
        return cap

    def evaluate(self, view) -> list[Capability]:
        """Set each capability's status from live measurements."""
        ram = view.val("resources.ram.available_bytes")
        disk = view.val("resources.disk.free_bytes")
        net = view.val("world.network.reachable")

        for cap in self.caps.values():
            prev = cap.status
            req = cap.requirements
            reasons: list[str] = []
            status = AVAILABLE

            if req.get("network") and net is not True:
                status = DEGRADED
                reasons.append(f"requires network; world.network.reachable={net}")

            need_ram = req.get("ram_bytes")
            if need_ram:
                if ram is None:
                    status = DEGRADED
                    reasons.append("cannot verify RAM requirement: measurement unavailable")
                elif need_ram > ram:
                    status = INSTALLED_UNAFFORDABLE
                    reasons.append(f"needs {_fmt(need_ram)} RAM, measured {_fmt(ram)} available")

            need_disk = req.get("disk_bytes")
            if need_disk and disk is not None and need_disk > disk:
                status = INSTALLED_UNAFFORDABLE
                reasons.append(f"needs {_fmt(need_disk)} free disk, measured {_fmt(disk)}")

            mod = req.get("module")
            if mod:
                try:
                    __import__(mod)
                except Exception as e:
                    status = DEGRADED
                    reasons.append(f"optional module {mod!r} unavailable: {type(e).__name__}")

            if req.get("present") is False:
                status = UNKNOWN
                reasons.append("not present on this host")

            cap.status = status
            cap.reason = "; ".join(reasons) or "all measured preconditions satisfied"

            if self.ledger and prev != cap.status:
                from ..ledger import EventType
                self.ledger.append(EventType.CAPABILITY_CHANGE, {
                    "capability": cap.name, "from": prev, "to": cap.status,
                    "reason": cap.reason})
        return list(self.caps.values())

    def as_list(self) -> list[dict]:
        return [c.to_dict() for c in self.caps.values()]

    def usable(self) -> list[Capability]:
        return [c for c in self.caps.values() if c.status == AVAILABLE]

    def blocked(self) -> list[Capability]:
        return [c for c in self.caps.values()
                if c.status in (INSTALLED_UNAFFORDABLE, DEGRADED)]


def seed_registry(view, ledger=None) -> Registry:
    """The capabilities the seed is born with, plus whatever it discovers on the host.

    Note that discovery is genuine: local models are found by reading manifests, and
    their RAM requirement is estimated from their actual on-disk weight rather than
    guessed.
    """
    r = Registry(ledger)

    r.declare(Capability("self_inspection",
                         "measure own process, runtime and host resources",
                         permissions=[], risk=0.0,
                         tests=["returns >=10 observations with epistemic status"]))
    r.declare(Capability("persistent_memory",
                         "write and recall memories across restarts (sqlite)",
                         requirements={"disk_bytes": 8 * 1024 ** 2},
                         permissions=["fs.write:sandbox"], risk=0.05))
    r.declare(Capability("event_ledger",
                         "append hash-chained events and verify the chain",
                         requirements={"disk_bytes": 4 * 1024 ** 2},
                         permissions=["fs.write:sandbox"], risk=0.05))
    r.declare(Capability("uncertainty_register",
                         "detect, score and persist its own knowledge gaps",
                         risk=0.0))
    r.declare(Capability("text_communication",
                         "emit and receive text through the console",
                         permissions=["human.ask"], risk=0.05))
    r.declare(Capability("network_probe",
                         "test reachability of a named host via DNS",
                         requirements={"network": True}, permissions=["net.dns"], risk=0.1))
    r.declare(Capability("web_retrieval",
                         "fetch and extract a web page, retaining provenance",
                         requirements={"network": True}, permissions=["net.http"],
                         risk=0.45,
                         reason="side effects leave the host; approval required"))
    r.declare(Capability("voice_output",
                         "speak through a text-to-speech provider",
                         requirements={"network": True, "module": "os"},
                         permissions=["tts.speak"], risk=0.3))

    # --- discovered on this host ------------------------------------------
    models = view.val("tools.local_models") or []
    for m in models:
        # Weights must be resident to run. Using on-disk size as the RAM floor is an
        # underestimate for most runtimes, which makes it a conservative test.
        r.declare(Capability(
            name=f"local_inference:{m['name']}",
            description=f"generate text with local model {m['name']} ({m['gib']} GiB)",
            requirements={"ram_bytes": int(m["bytes"]), "module": "urllib.request"},
            permissions=["llm.generate:localhost"],
            risk=0.15,
            dependencies=["ollama"],
            performance={"weight_gib": m["gib"]},
        ))

    if not models:
        r.declare(Capability("local_inference",
                             "generate text with a locally hosted model",
                             requirements={"present": False},
                             permissions=["llm.generate:localhost"], risk=0.15,
                             reason="no local model artefacts found"))

    r.evaluate(view)
    return r
