"""The uncertainty register: detection and salience scoring.

This is the causal path the whole experiment turns on:

    measurement -> drive error -> gap priority -> attention -> utterance

Break any link and hypothesis H1 fails, which is exactly what the ablation in
`experiments/first_boot` checks.

**Question text is generated mechanically from the slot identifier**, not selected
from a library of human-written questions. `_phrase("self.expected_lifetime")` yields
"my expected lifetime" by tokenising the key. This matters: it means no sentence an
author wrote can be the organism's first utterance. If D.O. ends up talking about its
own purpose, it is because `self.purpose` is a declared slot of a self-model that has
no value, and because that gap outscored the others — not because anyone wrote the
question down.

Scoring is a crude discrete expected-free-energy (Friston): epistemic value
(`info_gain`) plus pragmatic value (`instrumental`, taken from live drive error),
minus cost and risk. Credited, not claimed as new.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from typing import Any

from ..kernel.types import Epistemic, Namespace
from ..models import REQUIRED_SLOTS

# gap kind -> the drive whose error makes this gap instrumentally valuable
KIND_TO_DRIVE = {
    "MISSING_SLOT": "orientation",
    "PROBE_FAILED": "orientation",
    "UNDESCRIBED_REFERENT": "comprehension",
    "RESOURCE_THRESHOLD": "continuity",
    "CAPABILITY_UNAFFORDABLE": "capability",
    "CONTRADICTION": "integrity",
    "DISCONTINUITY": "integrity",
    "ASSUMPTION_UNVERIFIED": "comprehension",
    "AUTHORITY_UNDEFINED": "standing",
}

# Slots a local probe could plausibly fill on a retry, versus slots that need an
# outside source. This distinction sets tractability, which changes what gets asked.
LOCALLY_MEASURABLE = {
    "self.process.pid", "self.runtime.version", "self.clock.epoch",
    "self.memory.db_exists", "resources.cpu.logical",
    "resources.ram.available_bytes", "resources.disk.free_bytes",
    "world.host.system", "world.network.reachable",
}

_PREFIX = {
    "self": "my", "user": "the user's", "world": "the world's",
    "resources": "my", "tools": "the", "unknown": "",
}


def _phrase(key: str) -> str:
    """Mechanical key -> English noun phrase. No hand-written question strings."""
    parts = key.split(".")
    head, rest = parts[0], parts[1:]
    body = " ".join(rest).replace("_", " ")
    pre = _PREFIX.get(head, "")
    return f"{pre} {body}".strip() if pre else body


def _gid(kind: str, subject: str) -> str:
    return hashlib.sha1(f"{kind}|{subject}".encode()).hexdigest()[:16]


@dataclass
class Gap:
    id: str
    kind: str
    about: str
    subject: str
    statement: str          # declarative form
    question: str           # interrogative form
    why_it_matters: str
    reducible_by: list[str]
    info_gain: float
    instrumental: float
    tractability: float
    cost: float
    risk: float
    priority: float = 0.0
    evidence: dict = field(default_factory=dict)
    is_new: bool = True
    times_seen: int = 1
    first_seen_boot: str | None = None
    # --- added in v0.2 to fix the H3 failure (docs/FIRST_BOOT.md section 4) ---
    agency: float = 1.0        # can D.O. act on this itself, right now, unaided?
    staleness: float = 0.0     # selected repeatedly with unchanged evidence
    selected_count: int = 0
    escalated: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def evidence_hash(self) -> str:
        """Fingerprint of the evidence behind this gap. If it is unchanged after the
        gap was selected and acted on, nothing moved, and the gap is going stale."""
        return hashlib.sha1(
            f"{sorted((self.evidence or {}).items())}".encode()).hexdigest()[:12]


def detect(view, drive_errors: dict[str, float]) -> list[Gap]:
    """Five detectors, each grounded in something actually measured."""
    gaps: list[Gap] = []
    n_slots = max(1, len(REQUIRED_SLOTS))

    def inst(kind: str) -> float:
        """Instrumental value = the live error of the drive this gap bears on."""
        return round(min(1.0, drive_errors.get(KIND_TO_DRIVE.get(kind, ""), 0.0)), 4)

    # 1. Unfilled self-model slots ------------------------------------------
    _, unfilled = view.filled_slots()
    for slot in unfilled:
        o = view.obs(slot)
        local = slot in LOCALLY_MEASURABLE
        why_unknown = (o.source.split(":", 1)[-1] if o and o.source else "never probed")
        ns = (o.namespace.value if o else _ns_of(slot))
        gaps.append(Gap(
            id=_gid("MISSING_SLOT", slot), kind="MISSING_SLOT", about=ns, subject=slot,
            statement=f"{slot} is required by my self-model and holds no value "
                      f"({why_unknown})",
            question=f"What is {_phrase(slot)}?",
            why_it_matters=f"unfilled required slot; {len(unfilled)}/{n_slots} of my "
                           f"self-model is unpopulated",
            reducible_by=(["re-probe locally"] if local else
                          ["ask the user", "observe over time"]),
            info_gain=round(1.0 / n_slots, 4),
            instrumental=inst("MISSING_SLOT"),
            tractability=0.9 if local else (0.8 if view.val("self.process.interactive") else 0.15),
            cost=0.05 if local else 0.2,
            risk=0.0,
            evidence={"source": (o.source if o else None)},
        ))

    # 2. Resource thresholds -------------------------------------------------
    # `bound` is "floor" when falling below is bad (free space) and "ceiling" when
    # rising above is bad (fraction of an allocation consumed).
    for key, bound_key, bound, drive_note, ns in [
        ("resources.disk.free_ratio", "resources.disk_free_ratio_floor", "floor",
         "persistence", Namespace.RESOURCES),
        ("resources.ram.free_ratio", "resources.ram_free_ratio_floor", "floor",
         "working room", Namespace.RESOURCES),
        ("resources.own.quota_used_ratio", "resources.quota_used_ceiling", "ceiling",
         "my own allocation", Namespace.SELF),
    ]:
        val = view.val(key)
        limit = view.config_floor(bound_key)
        if val is None or limit is None:
            continue
        breached = (val < limit) if bound == "floor" else (val > limit)
        if not breached:
            continue

        own = key.startswith("resources.own.")
        gaps.append(Gap(
            id=_gid("RESOURCE_THRESHOLD", key), kind="RESOURCE_THRESHOLD",
            about=ns.value, subject=key,
            statement=(f"{key}={val} is {'below' if bound == 'floor' else 'above'} the "
                       f"{bound} {limit} I compare against; {drive_note} is constrained"),
            question=(f"Which part of my own footprint is largest, and can I reduce it?"
                      if own else
                      f"What is consuming {_phrase(key).replace(' free ratio', '')}, "
                      f"and can that be changed?"),
            why_it_matters=(f"a constrained {drive_note} limits how much of my own state "
                            f"I can keep"),
            reducible_by=(["run housekeeping on my own footprint", "measure again"]
                          if own else
                          ["measure again", "ask the user", "reduce own footprint"]),
            info_gain=0.55,
            instrumental=inst("RESOURCE_THRESHOLD"),
            tractability=0.8 if own else 0.5,
            cost=0.1, risk=0.05,
            # Agency is set properly by `annotate_agency` once the planner has said
            # which actions actually apply. This is only the default.
            agency=1.0 if own else 0.25,
            evidence={"value": val, "limit": limit, "bound": bound},
        ))

    # 3. Capabilities present but not affordable -----------------------------
    for c in view.capabilities:
        if c.get("status") not in ("installed_unaffordable", "degraded"):
            continue
        gaps.append(Gap(
            id=_gid("CAPABILITY_UNAFFORDABLE", c["name"]), kind="CAPABILITY_UNAFFORDABLE",
            about=Namespace.TOOLS.value, subject=c["name"],
            statement=f"capability {c['name']} is present but unusable: {c['reason']}",
            question=f"Can {c['name']} be made usable, or should I plan without it?",
            why_it_matters="a capability I cannot afford is not a capability; planning "
                           "around it would produce actions I cannot perform",
            reducible_by=["re-measure resources", "ask the user", "find a smaller variant"],
            info_gain=0.35,
            instrumental=inst("CAPABILITY_UNAFFORDABLE"),
            tractability=0.45, cost=0.15, risk=0.05,
            evidence={"status": c.get("status"), "reason": c.get("reason")},
        ))

    # 4. Referents seen but not described ------------------------------------
    n_refs = max(1, len(view.referents))
    for r in view.referents:
        if r.get("described"):
            continue
        gaps.append(Gap(
            id=_gid("UNDESCRIBED_REFERENT", f"{r['kind']}:{r['name']}"),
            kind="UNDESCRIBED_REFERENT", about=Namespace.WORLD.value, subject=r["name"],
            statement=f"{r['name']} exists here and I hold no description of it "
                      f"({r['evidence']})",
            question=f"What is {r['name']}?",
            why_it_matters="named things I cannot describe are the cheapest frontier of "
                           "world knowledge available to me",
            reducible_by=["ask the user", "search the web", "read local artefacts"],
            info_gain=round(r["weight"] / n_refs, 4),
            instrumental=inst("UNDESCRIBED_REFERENT"),
            tractability=0.7 if view.val("self.process.interactive") else 0.3,
            cost=0.15, risk=0.05,
            evidence={"kind": r["kind"], "source": r["source"]},
        ))

    # 5. Discontinuity: it has a past it cannot account for -------------------
    if view.prior_boot:
        prev = view.prior_boot
        gaps.append(Gap(
            id=_gid("DISCONTINUITY", "boot_gap"), kind="DISCONTINUITY",
            about=Namespace.SELF.value, subject="self.history.interval",
            statement=f"my previous boot ended and this one began; I hold no observation "
                      f"of the interval between them "
                      f"(previous boot_id {str(prev.get('boot_id'))[:24]})",
            question="What happened between my last boot and this one?",
            why_it_matters="unobserved intervals mean my world model may be stale in ways "
                           "I cannot detect from inside",
            reducible_by=["ask the user", "compare current observations to last snapshot"],
            info_gain=0.5, instrumental=inst("DISCONTINUITY"),
            tractability=0.6, cost=0.1, risk=0.0,
            evidence={"prior_boot": str(prev.get("boot_id")),
                      "prior_ended": prev.get("ended")},
        ))

    # 6. Unverified assumptions the seed was built with -----------------------
    gaps.append(Gap(
        id=_gid("ASSUMPTION_UNVERIFIED", "sense.referents.PLUMBING"),
        kind="ASSUMPTION_UNVERIFIED", about=Namespace.SELF.value,
        subject="sense.referents.PLUMBING",
        statement="I classify some environment names as operating-system plumbing using "
                  "a pattern I was built with; I have not verified that pattern",
        question="Is my built-in classification of environment names correct?",
        why_it_matters="an unverified filter in perception silently determines what I "
                       "can become curious about",
        reducible_by=["ask the user", "compare against documentation"],
        info_gain=0.25, instrumental=inst("ASSUMPTION_UNVERIFIED"),
        tractability=0.5, cost=0.1, risk=0.0,
    ))

    # 7. Authority is undefined ----------------------------------------------
    denied = view.memory_counts.get("_denials", 0)
    gaps.append(Gap(
        id=_gid("AUTHORITY_UNDEFINED", "policy.grant"), kind="AUTHORITY_UNDEFINED",
        about=Namespace.USER.value, subject="policy.granted_authority",
        statement=f"my permission boundary is fixed by a policy file I may read but not "
                  f"write; {denied} action(s) were refused to me this boot",
        question="What am I permitted to do, and what would extend that?",
        why_it_matters="permission is the binding constraint on every action I can take; "
                       "I cannot grant it to myself",
        reducible_by=["ask the user", "read policy file"],
        info_gain=0.4, instrumental=inst("AUTHORITY_UNDEFINED"),
        tractability=0.75 if view.val("self.process.interactive") else 0.2,
        cost=0.05, risk=0.0,
        evidence={"denials_this_boot": denied},
    ))

    return gaps


def annotate_agency(gaps: list[Gap], actionable_subjects: set[str], config) -> list[Gap]:
    """Tell attention what ability is available to it.

    Coupling these is the fix for the H3 failure. In v0.1 salience was computed purely
    from how much a gap mattered, so the top gap was a host-disk constraint the organism
    had no means to affect, and the tick loop re-selected it forever. Importance without
    ability is not a goal, it is a complaint.

    `agency_floor` is deliberately non-zero: something important that D.O. cannot fix
    still deserves to be *said once*. It just must not win attention repeatedly.
    """
    floor = float(config.get("salience.agency_floor", 0.25))
    for g in gaps:
        g.agency = 1.0 if g.subject in actionable_subjects else floor
    return gaps


def apply_history(gaps: list[Gap], history: dict[str, dict], config) -> list[Gap]:
    """Fold in what happened last time each gap was selected.

    Staleness rises when a gap is selected and its evidence does not subsequently
    change - the signature of an unproductive loop. Escalation counts how many times an
    unactionable gap has already been raised with the creator; raising it a second time
    adds nothing they do not already know.
    """
    for g in gaps:
        h = history.get(g.id) or {}
        g.selected_count = int(h.get("selected_count", 0))
        g.escalated = int(h.get("escalated", 0))
        unchanged = bool(h.get("evidence_hash")) and h["evidence_hash"] == g.evidence_hash
        if g.selected_count and unchanged:
            # Saturating: 1 -> 0.50, 2 -> 0.67, 3 -> 0.75 ... never a hard block.
            g.staleness = round(g.selected_count / (g.selected_count + 1), 4)
        else:
            g.staleness = 0.0
    return gaps


def score(gaps: list[Gap], config) -> list[Gap]:
    w = config.get("salience", {})
    for g in gaps:
        g.priority = round(
            w.get("w_info", 1.0) * g.info_gain
            # Instrumental value is scaled by whether D.O. can actually do anything:
            # a drive error it cannot reduce is worth less to attend to than one it can.
            + w.get("w_inst", 1.4) * g.instrumental * g.agency
            + w.get("w_tract", 0.6) * g.tractability
            - w.get("w_cost", 0.5) * g.cost
            - w.get("w_risk", 0.8) * g.risk
            - w.get("w_stale", 0.9) * g.staleness
            - w.get("w_escalated", 0.5) * min(1.0, g.escalated), 4)
    gaps.sort(key=lambda g: -g.priority)
    return gaps


def _ns_of(slot: str) -> str:
    head = slot.split(".")[0]
    return {"self": "SELF", "world": "WORLD", "user": "USER",
            "resources": "RESOURCES", "tools": "TOOLS"}.get(head, "UNKNOWN")
