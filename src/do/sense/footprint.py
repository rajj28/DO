"""Footprint perception: how much storage D.O. itself is consuming, by component.

The genesis boot found a real constraint it could do nothing about — a host disk at
2.4% free. Freeing D.O.'s *entire* footprint changes that number in the fifth decimal
place. An organism that cannot tell those two facts apart will either despair or lie.

So storage is measured twice, in two namespaces that must not be confused:

    RESOURCES  resources.disk.*   the host substrate. Measurable, NOT actionable.
    SELF       resources.own.*    its own allocation. Measurable AND actionable.

`reclaimable_bytes` is deliberately *not* computed here. What can be reclaimed depends
on which actions are applicable right now, which is the planner's job, not perception's.
Perception that quietly answers "what could I do about it" has already made a decision.
"""
from __future__ import annotations

from pathlib import Path

from ..kernel.types import Epistemic, Namespace

# component -> (relative path or glob, whether it is a directory)
# Ordered most-to-least expendable, which is documentation, not policy: the planner
# decides, and it decides from action preconditions rather than from this order.
COMPONENTS: dict[str, str] = {
    "experiments": "experiments/*/matrix",   # regenerable by re-running the experiment
    "bytecode": "**/__pycache__",            # regenerable by the interpreter
    "archives": "var.archived.*",            # prior states kept by `do reset`
    "snapshots": "snapshots",                # derived state, rebuildable from the ledger
    "ledger": "ledger*.jsonl*",              # the source of truth: compressible, never deleted
    "memory": "memory.db",                   # sqlite; compactable, never deleted
    "sandbox": "sandbox",                    # its own scratch space
    "identity": "identity.json",             # never touched
}


def dir_bytes(p: Path) -> int:
    """Apparent size of a tree. Apparent, not on-disk: block rounding is one of the
    reasons a prediction of bytes-freed is never exactly right, and learning that error
    is part of the point."""
    if not p.exists():
        return 0
    if p.is_file():
        try:
            return p.stat().st_size
        except OSError:
            return 0
    total = 0
    for child in p.rglob("*"):
        try:
            if child.is_file():
                total += child.stat().st_size
        except OSError:
            continue
    return total


def measure(state_dir: Path, project_root: Path) -> dict[str, dict]:
    """Bytes per component, with the paths each figure came from."""
    out: dict[str, dict] = {}
    for name, pattern in COMPONENTS.items():
        base = project_root if ("/" in pattern or "*" in pattern.split("/")[0]) else state_dir
        if name == "experiments":
            paths = list(project_root.glob(pattern))
        elif name == "bytecode":
            paths = [p for p in project_root.rglob("__pycache__") if p.is_dir()]
        elif name == "archives":
            paths = list(state_dir.parent.glob(pattern))
        else:
            paths = list(state_dir.glob(pattern)) if "*" in pattern else [state_dir / pattern]
        size = sum(dir_bytes(p) for p in paths)
        out[name] = {"bytes": size, "paths": [str(p) for p in paths if p.exists()]}
    return out


def observe(sensors, state_dir: Path, project_root: Path, quota_bytes: int,
            detailed: bool = False) -> dict:
    """Add resources.own.* observations.

    `detailed` is False in normal sensing, and that is the point. An organism handed
    the per-component breakdown for free never has to decide to investigate - it would
    always already know why it is over budget. Sensing reports the total; establishing
    the composition is work, and work is an action (DiagnoseFootprint). Separating them
    is what makes the diagnose stage real rather than ceremonial.
    """
    comps = measure(Path(state_dir), Path(project_root))
    total = sum(c["bytes"] for c in comps.values())

    sensors._add("resources.own.total_bytes", total, Epistemic.OBSERVED,
                 "footprint.measure", Namespace.SELF, unit="bytes")
    sensors._add("resources.own.quota_bytes", quota_bytes, Epistemic.REPORTED,
                 "config:resources.state_quota_bytes", Namespace.SELF, unit="bytes",
                 note="an allocation, not a measurement: a number a human chose")
    # Recovery paths are a resource like any other: measurable, and something an
    # action can change in either direction. prune_snapshots destroys them;
    # write_recovery_snapshot creates them. That tension is real, not staged.
    snaps = list((Path(state_dir) / "snapshots").glob("*.json"))
    sensors._add("resources.own.snapshot_count", len(snaps), Epistemic.OBSERVED,
                 "filesystem:snapshots", Namespace.SELF, unit="paths")
    sensors._add("resources.own.recovery_paths", len(snaps), Epistemic.INFERRED,
                 "count of independent reconstructions available", Namespace.SELF,
                 note="no off-host copy exists; snapshots are the only path")
    sensors._add("resources.own.snapshot_target", 3, Epistemic.REPORTED,
                 "config:resources.recovery_paths_target", Namespace.SELF)
    sensors._add("resources.own.quota_used_ratio",
                 round(total / quota_bytes, 4) if quota_bytes else None,
                 Epistemic.INFERRED, "own.total/own.quota", Namespace.SELF)
    if detailed:
        for name, c in comps.items():
            sensors._add(f"resources.own.{name}_bytes", c["bytes"], Epistemic.OBSERVED,
                         "footprint.measure(detailed)", Namespace.SELF, unit="bytes")
    else:
        # Declared explicitly, so the composition is a KNOWN unknown rather than
        # something never considered.
        sensors._add("resources.own.composition", None, Epistemic.UNKNOWN,
                     "undeterminable:requires the diagnose_footprint action",
                     Namespace.SELF)

    if detailed and comps:
        biggest = max(comps.items(), key=lambda kv: kv[1]["bytes"])
        sensors._add("resources.own.largest_component", biggest[0], Epistemic.INFERRED,
                     "argmax over footprint components", Namespace.SELF,
                     note=f"{biggest[1]['bytes']} bytes")
    return comps
