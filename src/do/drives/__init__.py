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
    # How this drive's value is computed from a measurable quantity. Present only for
    # drives grounded in a metric that could, in principle, be moved. This is what lets
    # a goal be DERIVED - invert the set point to get the metric value that satisfies
    # the drive - instead of being pattern-matched from a hand-written subject string.
    # Whether it can ACTUALLY be moved is a separate question, answered by the action
    # registry, not asserted here.
    spec: dict | None = None

    def satisfying_metric_value(self, budget: float) -> float | None:
        """The metric value at which this drive returns to its band.

        `fraction_of_budget`: value = 1 - metric/budget, so the drive is satisfied
        once metric <= (1 - (target - deadband)) * budget.
        """
        if not self.spec or not budget:
            return None
        if self.spec.get("form") == "fraction_of_budget":
            satisfying = self.target - self.deadband
            # For a DECREASE drive (value = 1 - metric/budget, e.g. frugality) the
            # metric must fall to (1-satisfying)*budget. For an INCREASE drive
            # (value = metric/budget, e.g. recovery, comprehension) it must RISE to
            # satisfying*budget. The earlier code used the decrease form for both,
            # which computed the wrong target for increase drives.
            if self.spec.get("direction") == "increase":
                return max(0.0, satisfying * float(budget))
            return max(0.0, (1.0 - satisfying) * float(budget))
        return None

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
        return {"name": self.name, "metric": (self.spec or {}).get("metric_key"),
                "value": round(self.value, 4), "target": self.target,
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
                              f"{len(view.referents)} visible referents described",
                        spec={"metric_key": "self.referents.described",
                              "budget_key": "self.referents.total",
                              "form": "fraction_of_budget",
                              "direction": "increase",
                              "diagnostic": None}))

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
                        s["deadband"], s["weight"], basis=basis,
                        spec={"metric_key": "resources.disk.free_bytes",
                              "budget_key": "resources.disk.total_bytes",
                              "form": "fraction_of_budget",
                              "direction": "increase",
                              "diagnostic": None}))

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
                        basis=f_basis,
                        spec={"metric_key": "resources.own.total_bytes",
                              "budget_key": "resources.own.quota_bytes",
                              "form": "fraction_of_budget",
                              "direction": "decrease",
                              # What would explain this metric if it goes out of band.
                              # D.O. does not start knowing its own composition.
                              "diagnostic": "diagnose_footprint"}))

    # recovery: how many independent ways this state could be reconstructed. Deliberately
    # in tension with frugality - snapshots cost storage, and pruning them buys space by
    # spending survivability. Which one wins is exactly what the fear ablation measures.
    paths = view.val("resources.own.recovery_paths")
    target_paths = float(view.val("resources.own.snapshot_target") or 3)
    s = spec("recovery")
    if paths is None:
        r_val, r_basis = 0.5, "resources.own.recovery_paths not measured"
    else:
        r_val = min(1.0, float(paths) / max(1.0, target_paths))
        r_basis = (f"{int(paths)} of {int(target_paths)} recovery path(s); "
                   f"no off-host copy")
    drives.append(Drive("recovery", r_val, s["target"], s["deadband"], s["weight"],
                        basis=r_basis,
                        spec={"metric_key": "resources.own.recovery_paths",
                              "budget_key": "resources.own.snapshot_target",
                              "form": "fraction_of_budget",
                              "direction": "increase",
                              "diagnostic": None}))

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
