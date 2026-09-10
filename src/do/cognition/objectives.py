"""Objectives: turn a prioritised gap into something that can succeed or fail.

A gap says *"I do not know X"* or *"X is outside its band"*. That is not yet a goal,
because it has no finish line. An Objective adds three things a gap lacks:

    a metric      the observable that must move
    a target      the value at which the drive is satisfied
    a deadline    after which persisting is evidence the approach is wrong

The target is derived from the drive's own set point rather than picked, so "what would
count as done" is answerable from the same numbers that made the gap urgent in the first
place. Nothing here invents a threshold.

**Objectives are only generated for gaps D.O. can act on.** A gap with no applicable
action does not become a goal; it becomes an escalation. Conflating the two is how an
agent ends up "working on" something it has no means to affect, which is exactly the
loop the first tick experiment fell into (`docs/FIRST_BOOT.md` §4, H3).
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field, asdict
from typing import Any

OPEN = "open"
MET = "met"
BLOCKED = "blocked"
ABANDONED = "abandoned"


@dataclass
class Objective:
    id: str
    gap_id: str
    statement: str
    metric_key: str
    direction: str            # "decrease" | "increase"
    start_value: float
    current_value: float
    target_value: float
    deadline_cycles: int
    opened_cycle: int
    status: str = OPEN
    attempts: int = 0
    actions_taken: list[str] = field(default_factory=list)
    closed_cycle: int | None = None
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def satisfied(self) -> bool:
        if self.direction == "decrease":
            return self.current_value <= self.target_value
        return self.current_value >= self.target_value

    @property
    def progress(self) -> float:
        """Fraction of the required movement achieved, in [0, 1]."""
        span = abs(self.start_value - self.target_value)
        if span <= 0:
            return 1.0
        moved = abs(self.start_value - self.current_value)
        # Movement in the wrong direction counts as zero progress, not negative, so a
        # single bad cycle does not make the number unreadable.
        wrong = ((self.direction == "decrease" and self.current_value > self.start_value)
                 or (self.direction == "increase" and self.current_value < self.start_value))
        return 0.0 if wrong else min(1.0, moved / span)

    def refresh(self, value: float, cycle: int) -> "Objective":
        self.current_value = value
        if self.satisfied:
            self.status = MET
            self.closed_cycle = cycle
        elif cycle - self.opened_cycle >= self.deadline_cycles:
            self.status = ABANDONED
            self.closed_cycle = cycle
            self.note = (f"deadline of {self.deadline_cycles} cycles reached with "
                         f"{self.progress:.0%} of the required movement achieved")
        return self


def _oid(gap_id: str, metric: str) -> str:
    return hashlib.sha1(f"{gap_id}|{metric}".encode()).hexdigest()[:16]


def generate(gap, view, drives, cycle: int, config) -> Objective | None:
    """Derive an objective from a gap, or None if the gap is not something to pursue."""
    if gap.kind != "RESOURCE_THRESHOLD":
        return None

    # Which drive does this gap bear on, and what value would satisfy it?
    if gap.subject == "resources.own.quota_used_ratio":
        drive = next((d for d in drives if d.name == "frugality"), None)
        if drive is None:
            return None
        quota = view.val("resources.own.quota_bytes")
        used = view.val("resources.own.total_bytes")
        if not quota or used is None:
            return None
        # frugality value = 1 - used/quota, satisfied when value >= target - deadband
        satisfying_value = drive.target - drive.deadband
        target_bytes = int(max(0.0, 1.0 - satisfying_value) * quota)
        return Objective(
            id=_oid(gap.id, "resources.own.total_bytes"),
            gap_id=gap.id,
            statement=(f"reduce my own storage footprint from {used} to at most "
                       f"{target_bytes} bytes, which is where the frugality drive "
                       f"({drive.value:.3f} against target {drive.target:.2f}) returns "
                       f"to its band"),
            metric_key="resources.own.total_bytes",
            direction="decrease",
            start_value=float(used),
            current_value=float(used),
            target_value=float(target_bytes),
            deadline_cycles=int(config.get("objectives.deadline_cycles", 6)),
            opened_cycle=cycle,
        )

    # Host storage. Deliberately returns None: see the module docstring. The caller
    # turns an unactionable resource gap into an escalation instead.
    return None


def escalation_for(gap, view) -> dict:
    """What to tell the creator about a constraint D.O. cannot act on.

    Naming the limit precisely is the whole value here. "I am low on disk" is a
    complaint; "this is outside what I can affect, here is the measurement, here is why
    my own housekeeping would not move it" is a request someone can act on.
    """
    own = view.val("resources.own.total_bytes") or 0
    free = view.val("resources.disk.free_bytes") or 0
    share = (own / free) if free else 0.0
    return {
        "gap_id": gap.id,
        "subject": gap.subject,
        "statement": gap.statement,
        "why_i_cannot_act": (
            "every action available to me operates inside my own footprint, and my "
            f"entire footprint is {own} bytes against {free} bytes free on this volume "
            f"({share:.4%}). Removing all of it would not move "
            f"resources.disk.free_ratio at the precision I can measure."),
        "what_would_help": "a decision by you about what on this volume is expendable",
        "measured": {"own_total_bytes": own, "disk_free_bytes": free,
                     "own_share_of_free": round(share, 6)},
    }
