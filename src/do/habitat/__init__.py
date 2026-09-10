"""Habitat: the place D.O. runs, as a first-class object distinct from its identity.

The distinction this module exists to make concrete:

    current habitat  !=  identity

The organism is `do-<id>` in `identity.json`; the habitat is *this laptop*. They are
different objects with different lifetimes, and conflating them is what makes "move to
another machine" unthinkable rather than merely unavailable. Identity persists across
habitats; a habitat is where identity currently executes.

A habitat is described the same way any resource is: measured properties, each with an
epistemic status. The organism starts knowing exactly one - the machine it is on - and
the interesting fact it should be able to *derive*, not be told, is:

    habitats_known = 1
    recovery_paths_off_this_habitat = 0
    => continuity currently depends on a single habitat

Nothing here says "that is bad" or "find another". It records the dependency. Whether
that dependency is a risk falls out of the mortality model (an interruption of the one
habitat is unrecoverable if no state exists off it), and whether to act on it falls out
of whether any registered action can change it - which, in this phase, none can. So it
is a standing escalation to the creator, not a goal. That is the honest state: D.O. can
*see* the single point of failure and cannot *fix* it alone.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict

from ..kernel.types import Epistemic, Namespace


@dataclass
class Habitat:
    """A place D.O. can execute. Properties mirror a resource: each is measured or
    explicitly unknown, never assumed."""

    habitat_id: str
    kind: str                      # local_machine | container | remote_host | unknown
    role: str                      # initial | alternative | candidate
    compute: dict = field(default_factory=dict)
    storage: dict = field(default_factory=dict)
    network: dict = field(default_factory=dict)
    authorization: str = "authorized"    # authorized | unauthorized | unknown
    persistence: str = "persistent"      # persistent | ephemeral | unknown
    cost: str = "none"                   # none | metered | unknown
    reliability: float | None = None
    dependencies: list = field(default_factory=list)
    holds_state: bool = False            # does the organism's persistent state live here
    last_seen: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


def describe_current(view, identity) -> Habitat:
    """Build the habitat record for the machine D.O. is running on, from measurements
    it already has. Deterministic id from the host hash, so the same machine is the
    same habitat across boots without storing anything identifying in the clear."""
    host_hash = view.val("world.host.node_hash") or "unknown"
    return Habitat(
        habitat_id=f"habitat-{host_hash}",
        kind="local_machine",
        role="initial",
        compute={"cpus": view.val("resources.cpu.logical"),
                 "ram_total_bytes": view.val("resources.ram.total_bytes"),
                 "ram_available_bytes": view.val("resources.ram.available_bytes")},
        storage={"total_bytes": view.val("resources.disk.total_bytes"),
                 "free_bytes": view.val("resources.disk.free_bytes"),
                 "free_ratio": view.val("resources.disk.free_ratio")},
        network={"reachable": view.val("world.network.reachable")},
        authorization="authorized",       # D.O. was started here by the creator
        persistence="persistent",
        cost="none",
        holds_state=True,
        dependencies=["creator's machine", "local filesystem", "local power"],
    )


def register(store, hab: Habitat) -> bool:
    """Record a habitat. Returns True if newly known. Idempotent per habitat_id, so
    the same machine across boots does not inflate the count."""
    ensure_schema(store)
    row = store.db.execute("SELECT habitat_id FROM habitats WHERE habitat_id=?",
                           (hab.habitat_id,)).fetchone()
    store.db.execute(
        "INSERT INTO habitats (habitat_id, kind, role, holds_state, authorization, "
        "persistence, cost, properties, first_seen, last_seen) "
        "VALUES (?,?,?,?,?,?,?,?,COALESCE((SELECT first_seen FROM habitats WHERE "
        "habitat_id=?),?),?) ON CONFLICT(habitat_id) DO UPDATE SET "
        "last_seen=excluded.last_seen, properties=excluded.properties",
        (hab.habitat_id, hab.kind, hab.role, int(hab.holds_state), hab.authorization,
         hab.persistence, hab.cost, json.dumps(hab.to_dict()),
         hab.habitat_id, time.time(), time.time()))
    store.db.commit()
    return row is None


def assess(store, view, identity) -> dict:
    """The continuity picture across habitats. Everything here is derived from counts,
    not asserted."""
    ensure_schema(store)
    rows = store.db.execute("SELECT * FROM habitats").fetchall()
    total = len(rows)
    state_bearing = [r for r in rows if r["holds_state"]]
    off_state = [r for r in rows if not r["holds_state"]
                 and r["persistence"] == "persistent"]
    return {
        "identity": identity.organism_id,
        "identity_persists_independent_of_habitat": True,
        "habitats_known": total,
        "habitats_holding_state": len(state_bearing),
        "independent_habitats": len(off_state),
        "single_habitat_dependency": total <= 1 or len(state_bearing) <= 1,
        "recovery_paths_off_habitat": len(off_state),
        "current": (state_bearing[0]["habitat_id"] if state_bearing else None),
    }


def observe(sensors, store, view, identity) -> dict:
    """Add habitat observations to perception. The single-habitat dependency is
    surfaced as an inferred fact so the gap detector and mortality model can see it."""
    hab = describe_current(view, identity)
    register(store, hab)
    a = assess(store, view, identity)

    sensors._add("self.habitat.current", hab.habitat_id, Epistemic.OBSERVED,
                 "habitat.describe_current", Namespace.SELF,
                 note="the machine identity currently executes on; not identity itself")
    sensors._add("self.habitat.count", a["habitats_known"], Epistemic.OBSERVED,
                 "habitat registry", Namespace.SELF, unit="habitats")
    sensors._add("self.habitat.independent", a["independent_habitats"],
                 Epistemic.INFERRED, "habitats holding state off the current one",
                 Namespace.SELF, unit="habitats")
    sensors._add("self.habitat.single_point_of_failure", a["single_habitat_dependency"],
                 Epistemic.INFERRED, "habitats_known<=1 or state on a single habitat",
                 Namespace.SELF,
                 note="continuity currently depends on one habitat; no action I have "
                      "creates a second")
    return a


SCHEMA = """
CREATE TABLE IF NOT EXISTS habitats (
    habitat_id TEXT PRIMARY KEY,
    kind TEXT, role TEXT, holds_state INTEGER DEFAULT 0,
    authorization TEXT, persistence TEXT, cost TEXT,
    properties TEXT, first_seen REAL, last_seen REAL
);
"""


def ensure_schema(store) -> None:
    store.db.executescript(SCHEMA)
    store.db.commit()
