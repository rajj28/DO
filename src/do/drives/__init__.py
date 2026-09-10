"""Homeostatic drives.

The reason this project is not a chatbot in a trench coat. Each drive is a measured
variable with a set point and a tolerated deadband; deviation produces *error*, and
error produces goals — with or without a human in the loop.

Lineage is Ashby's ultrastable system (1952) by way of homeostatic RL (Keramati &
Gutkin 2014). What is less common is pointing the drives at the agent's own
infrastructure — storage headroom, snapshot recency, whether its own tools are
affordable — rather than at task reward.

`standing` is the unusual one. It is the organism's measure of how much authority its
creator has granted it, and it is the only resource in the system that D.O. cannot
produce for itself. See docs/DO_CONCEPT.md section D and E: in a world where every
resource has an owner, permission is the binding constraint, and the only way to get
more of it is to be worth trusting.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Drive:
    name: str
    value: float
    target: float
    deadband: float
    weight: float
    basis: str            # what measurement produced `value` - never left blank

    @property
    def error(self) -> float:
        """Unsigned deviation outside the deadband, in [0, 1]."""
        raw = abs(self.target - self.value)
        return round(max(0.0, raw - self.deadband), 4)

    @property
    def weighted_error(self) -> float:
        return round(self.error * self.weight, 4)

    @property
    def satisfied(self) -> bool:
        return self.error <= 0.0

    def to_dict(self) -> dict:
        return {"name": self.name, "value": round(self.value, 4), "target": self.target,
                "deadband": self.deadband, "weight": self.weight,
                "error": self.error, "weighted_error": self.weighted_error,
                "satisfied": self.satisfied, "basis": self.basis}


def compute(view, config, ledger=None) -> list[Drive]:
    """Measure every drive from the current state view."""
    cfg = config.get("drives", {})

    def spec(name: str) -> dict:
        return cfg.get(name, {"target": 1.0, "deadband": 0.1, "weight": 1.0})

    drives: list[Drive] = []

    # orientation: how much of the required self-model is filled
    filled, unfilled = view.filled_slots()
    s = spec("orientation")
    drives.append(Drive("orientation", view.orientation(), s["target"], s["deadband"],
                        s["weight"],
                        basis=f"{len(filled)}/{len(filled) + len(unfilled)} required slots filled"))

    # comprehension: how much of the visible world it can describe
    s = spec("comprehension")
    drives.append(Drive("comprehension", view.described_ratio(), s["target"], s["deadband"],
                        s["weight"],
                        basis=f"{sum(1 for r in view.referents if r.get('described'))}/"
                              f"{len(view.referents)} visible referents described"))

    # integrity: is the ledger chain intact and is memory writable
    integrity = float(view.memory_counts.get("_integrity_ok", 1.0))
    s = spec("integrity")
    drives.append(Drive("integrity", integrity, s["target"], s["deadband"], s["weight"],
                        basis=view.memory_counts.get("_integrity_note", "ledger chain verified")))

    # continuity: can it survive a restart -> storage headroom x snapshot presence
    free_ratio = view.val("resources.disk.free_ratio")
    floor = config.get("resources.disk_free_ratio_floor", 0.10)
    if free_ratio is None:
        headroom, basis = 0.5, "resources.disk.free_ratio unknown; continuity indeterminate"
    else:
        headroom = min(1.0, free_ratio / floor) if floor > 0 else 1.0
        basis = f"resources.disk.free_ratio={free_ratio} vs floor {floor}"
    persisted = 1.0 if view.memory_counts.get("boots", 0) > 0 else 0.6
    s = spec("continuity")
    drives.append(Drive("continuity", round(headroom * persisted, 4), s["target"],
                        s["deadband"], s["weight"], basis=basis))

    # frugality: own footprint against its own allocation. Distinct from continuity
    # on purpose: continuity measures the host volume, which D.O. cannot affect, while
    # this measures its own consumption, which it can. An organism that cannot tell
    # those apart will either despair or lie.
    used = view.val("resources.own.quota_used_ratio")
    s = spec("frugality")
    if used is None:
        f_val, f_basis = 0.5, "resources.own.quota_used_ratio not measured"
    else:
        f_val = max(0.0, min(1.0, 1.0 - float(used)))
        f_basis = (f"resources.own.total_bytes={view.val('resources.own.total_bytes')} "
                   f"of quota {view.val('resources.own.quota_bytes')} "
                   f"({float(used):.1%} consumed)")
    drives.append(Drive("frugality", f_val, s["target"], s["deadband"], s["weight"],
                        basis=f_basis))

    # capability: usable / declared
    caps = view.capabilities or []
    usable = sum(1 for c in caps if c.get("status") == "available")
    ratio = usable / len(caps) if caps else 0.0
    s = spec("capability")
    drives.append(Drive("capability", ratio, s["target"], s["deadband"], s["weight"],
                        basis=f"{usable}/{len(caps)} declared capabilities usable now"))

    # standing: authority granted, minus denials incurred
    granted = float(view.memory_counts.get("_standing", 0.25))
    s = spec("standing")
    drives.append(Drive("standing", granted, s["target"], s["deadband"], s["weight"],
                        basis=view.memory_counts.get(
                            "_standing_note",
                            "initial grant; no history of granted authority")))

    if ledger is not None:
        from ..ledger import EventType
        ledger.append(EventType.DRIVE_UPDATE, {"drives": [d.to_dict() for d in drives]})
    return drives


def dominant(drives: list[Drive]) -> Drive | None:
    unsatisfied = [d for d in drives if not d.satisfied]
    return max(unsatisfied, key=lambda d: d.weighted_error) if unsatisfied else None


def error_map(drives: list[Drive]) -> dict[str, float]:
    return {d.name: d.weighted_error for d in drives}


def total_error(drives: list[Drive]) -> float:
    return round(sum(d.weighted_error for d in drives), 4)
