"""Objectives: goals derived from state, then decomposed into stages.

**The thing this module is not allowed to do.** An earlier version contained:

    if gap.subject == "resources.own.quota_used_ratio":
        ...build the footprint objective...

That is the experimenter supplying the goal and the organism appearing to form it. It
passes every test while proving nothing, because the interesting claim - *the goal
emerged from the state* - is exactly the part that was hand-written.

Nothing here names a subject. A goal is derived, generically:

    1. the gap bears on a drive (cognition.gaps.KIND_TO_DRIVE)
    2. that drive is outside its band
    3. the drive declares the metric its value is computed from (drives.Drive.spec)
    4. some registered action declares it moves that metric
    5. invert the drive's set point to get the metric value that satisfies it

If (4) fails there is no goal - there is an escalation. A constraint you cannot move is
not something to pursue; it is something to report. That distinction is what the tick
loop lacked when H3 was falsified.

**Decomposition.** A goal is not an action. Between "my footprint is over budget" and
"delete something" sits a question the organism cannot skip: *what is my footprint made
of?* Sensing gives it a total. Only a diagnostic gives it a composition. So an
objective moves through stages, and the planner is restricted to the actions
appropriate to the current one.

    DIAGNOSE -> REDUCE -> VERIFY -> done
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

DIAGNOSE = "diagnose"
REDUCE = "reduce"
VERIFY = "verify"
DONE = "done"


@dataclass
class Objective:
    id: str
    gap_id: str
    drive: str
    statement: str
    metric_key: str
    direction: str
    start_value: float
    current_value: float
    target_value: float
    deadline_cycles: int
    opened_cycle: int
    status: str = OPEN
    stage: str = DIAGNOSE
    subgoals: list = field(default_factory=list)
    diagnosis: dict | None = None
    attempts: int = 0
    actions_taken: list = field(default_factory=list)
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
        span = abs(self.start_value - self.target_value)
        if span <= 0:
            return 1.0
        moved = abs(self.start_value - self.current_value)
        wrong = ((self.direction == "decrease" and self.current_value > self.start_value)
                 or (self.direction == "increase" and self.current_value < self.start_value))
        return 0.0 if wrong else min(1.0, moved / span)

    def advance(self, value: float, cycle: int) -> "Objective":
        """Move the metric, then move the stage. Order matters: the stage a goal is in
        is a fact about what it still needs, not a counter."""
        self.current_value = value
        if self.satisfied:
            self.stage, self.status, self.closed_cycle = DONE, MET, cycle
        elif cycle - self.opened_cycle >= self.deadline_cycles:
            self.stage, self.status, self.closed_cycle = DONE, ABANDONED, cycle
            self.note = (f"deadline of {self.deadline_cycles} cycles reached at "
                         f"{self.progress:.0%} of the required movement")
        elif self.stage == DIAGNOSE and self.diagnosis is not None:
            self.stage = REDUCE
        self._sync_subgoals()
        return self

    def _sync_subgoals(self) -> None:
        order = [DIAGNOSE, REDUCE, VERIFY]
        here = order.index(self.stage) if self.stage in order else len(order)
        for sg in self.subgoals:
            i = order.index(sg["stage"]) if sg["stage"] in order else len(order)
            sg["status"] = ("done" if (i < here or self.status == MET)
                            else "active" if i == here else "pending")


def _oid(gap_id: str, metric: str) -> str:
    return hashlib.sha1(f"{gap_id}|{metric}".encode()).hexdigest()[:16]


def namespace_of(key: str) -> str:
    """The observation family a key belongs to: `resources.own.total_bytes` -> `resources.own`."""
    return ".".join((key or "").split(".")[:2])


def drive_for(gap, drives):
    """Bind a gap to the drive that actually governs it.

    Binding by gap KIND was wrong the moment a second resource drive existed: every
    RESOURCE_THRESHOLD gap mapped to `continuity`, so the own-footprint gap was tested
    for actionability against the host disk - and correctly found unactionable, which
    made an actionable goal look impossible.

    Bind by observation namespace instead. `resources.own.quota_used_ratio` and
    frugality's `resources.own.total_bytes` share `resources.own`; the disk gap and
    continuity share `resources.disk`. That is a structural fact about the observation
    tree, not a hand-written pairing, so it keeps working as drives are added.
    """
    # Exact metric first. Two drives can share a namespace - frugality and recovery
    # both live in `resources.own` - so namespace alone is ambiguous once more than
    # one drive measures the same family.
    for d in drives:
        if (d.spec or {}).get("metric_key") == gap.subject:
            return d
    ns = namespace_of(gap.subject)
    for d in drives:
        mk = (d.spec or {}).get("metric_key")
        if mk and namespace_of(mk) == ns:
            return d
    from .gaps import KIND_TO_DRIVE
    name = KIND_TO_DRIVE.get(gap.kind)
    return next((d for d in drives if d.name == name), None)


def generate(gap, view, drives, cycle: int, config) -> Objective | None:
    """Derive a goal, or None if this gap is not something to pursue."""
    from ..capabilities.actions import actions_moving

    drive = drive_for(gap, drives)
    if drive is None or drive.satisfied or not drive.spec:
        return None

    metric = drive.spec.get("metric_key")
    # Agency is read from the action registry, never asserted. If nothing moves this
    # metric, the constraint is real and D.O. is not the one who can act on it.
    if not actions_moving(metric):
        return None

    budget = view.val(drive.spec.get("budget_key"))
    current = view.val(metric)
    target = drive.satisfying_metric_value(budget)
    if current is None or target is None:
        return None

    direction = drive.spec.get("direction", "decrease")
    needs_diagnosis = bool(drive.spec.get("diagnostic"))

    obj = Objective(
        id=_oid(gap.id, metric), gap_id=gap.id, drive=drive.name,
        statement=(f"bring {metric} from {int(current)} to "
                   f"{'at most' if direction == 'decrease' else 'at least'} "
                   f"{int(target)}, the value at which drive '{drive.name}' "
                   f"({drive.value:.3f} against target {drive.target:.2f}) "
                   f"returns to its band"),
        metric_key=metric, direction=direction,
        start_value=float(current), current_value=float(current),
        target_value=float(target),
        deadline_cycles=int(config.get("objectives.deadline_cycles", 6)),
        opened_cycle=cycle,
        stage=DIAGNOSE if needs_diagnosis else REDUCE,
    )
    obj.subgoals = decompose(obj, drive, needs_diagnosis)
    obj._sync_subgoals()
    return obj


def decompose(obj: Objective, drive, needs_diagnosis: bool) -> list[dict]:
    """Break a goal into the stages it actually requires.

    The diagnose stage is included only when the drive says its metric has a
    composition worth investigating. Not every goal needs investigating, and inserting
    a ceremonial step that always succeeds would make the decomposition decorative.
    """
    subs = []
    if needs_diagnosis:
        subs.append({
            "stage": DIAGNOSE,
            "goal": f"determine what constitutes {obj.metric_key}",
            "why": ("I measured a total that is out of band. I cannot choose what to "
                    "reduce without knowing what the total is made of, and sensing "
                    "does not tell me - measuring the composition is itself work."),
            "status": "pending"})
    subs.append({
        "stage": REDUCE,
        "goal": (f"move {obj.metric_key} to "
                 f"{'<=' if obj.direction == 'decrease' else '>='} "
                 f"{int(obj.target_value)}"),
        "why": "acting on the constituents I judged safe should relieve the drive",
        "status": "pending"})
    subs.append({
        "stage": VERIFY,
        "goal": f"confirm drive '{obj.drive}' returned to its band",
        "why": ("the metric moving is not the same as the drive being satisfied; "
                "only re-measuring settles it"),
        "status": "pending"})
    return subs


def record_diagnosis(obj: Objective, detail: dict) -> dict:
    """Fold an investigation's findings into the goal, and classify what was found.

    The classification is not a judgement written here - each component is labelled by
    whether any registered action declares it can move it. 'Safe to act on' means
    'something I have is designed to act on this', which is the only sense of safe D.O.
    can establish for itself.
    """
    comps = detail.get("components", [])
    obj.diagnosis = {
        "total_bytes": detail.get("total_bytes"),
        "largest": detail.get("largest"),
        "reducible_bytes": detail.get("reducible_bytes"),
        "components": comps,
        "actionable": [c["component"] for c in comps
                       if c.get("recoverable_now", 0) > 0],
        "in_scope_but_empty": [c["component"] for c in comps
                               if c.get("reducible_by") and not c.get("recoverable_now")],
        "not_actionable": [c["component"] for c in comps if not c.get("reducible_by")],
    }
    reducible = detail.get("reducible_bytes") or 0
    need = max(0.0, obj.current_value - obj.target_value)
    obj.diagnosis["sufficient"] = reducible >= need
    obj.diagnosis["shortfall"] = max(0, int(need - reducible))
    return obj.diagnosis


def escalation_for(gap, view, drives=None) -> dict:
    """What to tell the creator about a constraint D.O. cannot act on.

    Naming the limit precisely is the value. "I am low on disk" is a complaint. "No
    action I have moves this metric, here is the measurement, here is the share of it
    I could affect even by erasing myself entirely" is something a person can act on.
    """
    own = view.val("resources.own.total_bytes") or 0
    free = view.val("resources.disk.free_bytes") or 0
    share = (own / free) if free else 0.0
    d = drive_for(gap, drives or [])
    metric = (d.spec or {}).get("metric_key") if d and d.spec else gap.subject
    return {
        "gap_id": gap.id,
        "subject": gap.subject,
        "metric": metric,
        "statement": gap.statement,
        "why_i_cannot_act": (
            f"no action in my registry declares that it moves {metric}. Everything I "
            f"can do operates inside my own footprint, which is {own} bytes against "
            f"{free} bytes free on this volume ({share:.4%}). Erasing myself entirely "
            f"would not return this measure to its band."),
        "what_would_help": "a decision by you about what on this volume is expendable",
        "measured": {"own_total_bytes": own, "disk_free_bytes": free,
                     "own_share_of_free": round(share, 6)},
    }
