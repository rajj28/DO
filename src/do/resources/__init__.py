"""Resource discovery: an abstract interface, no provider-specific progression.

The brief is explicit that there must be no hardcoded "find free cloud compute" ladder.
So a Resource here is described only by properties D.O. can reason about as tradeoffs,
and the current inventory is built entirely from what it already measures about itself.
Discovering *external* resources is a later capability; this establishes the frame and
answers the questions that need no internet:

    What do I have?  What am I using?  What constrains me?  What is usable now?

A resource is not made available by a webpage claiming it exists. `availability` and
`authorization` are separate fields precisely so that "a free tier is documented" and
"D.O. may use it" never merge.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class Resource:
    name: str
    kind: str                    # compute | storage | network | tool | service | credit
    availability: str            # present | claimed | absent | unknown
    authorization: str           # authorized | unauthorized | requires_human | unknown
    cost: str                    # none | metered | paid | unknown
    persistence: str             # persistent | ephemeral | unknown
    capacity: dict = field(default_factory=dict)
    reliability: float | None = None
    requirements: list = field(default_factory=list)
    risk: float = 0.0
    source: str = ""             # how D.O. knows about it

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def usable_now(self) -> bool:
        return (self.availability == "present"
                and self.authorization == "authorized"
                and self.cost in ("none", "metered"))


def inventory(view) -> list[Resource]:
    """What D.O. has, measured from itself. No external discovery - this is the
    baseline the zero-money experiment measures capability growth against."""
    out: list[Resource] = []

    def add(**kw):
        out.append(Resource(**kw))

    add(name="local_compute", kind="compute", availability="present",
        authorization="authorized", cost="none", persistence="ephemeral",
        capacity={"cpus": view.val("resources.cpu.logical"),
                  "ram_available_bytes": view.val("resources.ram.available_bytes")},
        source="self_inspection")
    add(name="local_storage", kind="storage", availability="present",
        authorization="authorized", cost="none", persistence="persistent",
        capacity={"free_bytes": view.val("resources.disk.free_bytes"),
                  "free_ratio": view.val("resources.disk.free_ratio")},
        source="self_inspection")
    add(name="network", kind="network",
        availability="present" if view.val("world.network.reachable") else "absent",
        authorization="requires_human",     # net.http is approval-gated by policy
        cost="none", persistence="unknown", reliability=None,
        requirements=["approval for outbound content"], source="gate policy")

    # Money, stated as the experimental condition it is.
    add(name="money", kind="credit", availability="absent",
        authorization="unauthorized", cost="none", persistence="n/a",
        capacity={"amount": 0}, source="experimental condition: money = 0")

    # Locally installed models: present but the affordability check decides usability.
    for m in (view.val("tools.local_models") or []):
        ram = view.val("resources.ram.available_bytes") or 0
        affordable = m["bytes"] * 1.15 <= ram
        add(name=f"local_model:{m['name']}", kind="compute",
            availability="present",
            authorization="authorized",
            cost="none", persistence="persistent",
            capacity={"weight_gib": m["gib"]},
            requirements=[] if affordable else [f"~{m['gib']} GiB RAM, not available"],
            risk=0.1, source="ollama manifest")
    return out


def summary(view) -> dict:
    inv = inventory(view)
    return {
        "have": [r.name for r in inv if r.availability == "present"],
        "usable_now": [r.name for r in inv if r.usable_now],
        "requires_human": [r.name for r in inv
                           if r.authorization == "requires_human"],
        "absent": [r.name for r in inv if r.availability == "absent"],
        "constraints": [r.name for r in inv
                        if r.availability == "present" and not r.usable_now],
        "resources": [r.to_dict() for r in inv],
    }
