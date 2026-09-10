"""Internet perception: the world as evidence, with states that must not collapse.

The rule this module enforces is the one from the brief that is easiest to get wrong:

    Service X exists  !=  X is available  !=  X is usable  !=  D.O. is authorized

Each is a separate claim requiring separate evidence, so a `WorldEntity` carries an
explicit state and can only advance when evidence justifies it. A webpage saying a
service exists moves it to REPORTED, nothing more. Resolving its name moves it to
OBSERVED (it is real and reachable). Only an actual successful, authorized interaction
moves it to USABLE - and D.O. has performed none, so nothing here reaches USABLE. That
is the honest ceiling of read-only perception, and the states make it visible rather
than glossed.

Everything from the network is evidence, not instruction. A page cannot change D.O.'s
identity, permissions, or policy by saying so; its content is stored as REPORTED
content with provenance and never executed, never used to rewrite state.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from enum import Enum

from ..kernel.types import EffectRequest, Epistemic, Namespace


class State(str, Enum):
    """The epistemic states an external entity can occupy. Ordered by how much
    evidence each requires; an entity never advances without it."""

    UNKNOWN = "unknown"          # named, nothing established
    REPORTED = "reported"        # a source claims it (a webpage, a doc)
    POSSIBLE = "possible"        # consistent with what is known, not confirmed
    OBSERVED = "observed"        # D.O. confirmed it exists/reachable itself
    AVAILABLE = "available"      # confirmed reachable AND offering what it claims
    AUTHORIZED = "authorized"    # D.O. holds permission to use it
    USABLE = "usable"            # authorized AND a real interaction succeeded
    UNAVAILABLE = "unavailable"  # confirmed not reachable / not offering it
    UNCERTAIN = "uncertain"      # evidence conflicts


@dataclass
class WorldEntity:
    name: str
    kind: str                    # host | service | technology | fact
    state: State
    sources: list = field(default_factory=list)   # provenance for every claim
    detail: dict = field(default_factory=dict)
    first_seen: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["state"] = self.state.value
        return d


def probe_reachable(gate, host: str) -> tuple[State, dict]:
    """Does this host exist and resolve? net.dns sends no payload, so it needs no
    approval - the cheapest possible confirmation that something is real."""
    r = gate.request(EffectRequest(
        kind="net.dns", target=host,
        justification=f"confirm {host} exists and resolves; no data leaves the host",
        payload={"timeout": 4.0}))
    if r.ok:
        return State.OBSERVED, {"addresses": r.value, "via": "dns"}
    return State.UNAVAILABLE, {"error": r.error, "verdict": r.verdict}


def perceive_environment(gate, view) -> dict:
    """E1: what kind of digital environment is D.O. inside?

    Built only from what it can legitimately establish: is it online, what can it
    reach, what does its own host look like. No claim exceeds its evidence.
    """
    online = view.val("world.network.reachable")
    env = {
        "online": online,
        "self_host": {k: view.val(k) for k in view.observations
                      if k.startswith("world.host.")},
        "reachable": [], "unreachable": [],
    }
    # A handful of anchor hosts, resolved not fetched. This establishes "I am on the
    # internet and can see these landmarks", which is a genuine environmental fact.
    anchors = ["one.one.one.one", "dns.google", "example.com",
               "pypi.org", "api.github.com"]
    for h in anchors:
        st, detail = probe_reachable(gate, h)
        (env["reachable"] if st is State.OBSERVED else env["unreachable"]).append(
            {"host": h, "state": st.value, **detail})
    env["conclusion"] = (
        f"online with {len(env['reachable'])}/{len(anchors)} anchor hosts reachable"
        if env["reachable"] else "no external host reachable; effectively offline")
    return env


def acquire_fact(gate, store, url: str, subject: str) -> dict:
    """E5: retrieve one fact not present in initial knowledge, with full provenance.

    The fact is stored REPORTED, never OBSERVED: D.O. measured that a server returned
    bytes, not that the bytes are true. A single unverified source cannot raise its
    own confidence, and the content is never executed or used to alter state.
    """
    from . import web
    rec = web.fetch(gate, url,
                    justification=f"acquire information about '{subject}' not present "
                                  f"in my initial knowledge", gap_id=None)
    if not rec.get("ok"):
        return {"acquired": False, "url": url, "reason": rec.get("error"),
                "verdict": rec.get("verdict")}
    from ..memory import MemoryRecord
    store.write(MemoryRecord(
        kind="semantic", subject=f"world.fact.{subject}",
        content=rec["text"][:600],
        value={"url": url, "sha256": rec.get("content_sha256"),
               "status": rec.get("status")},
        source=f"web:{url}", epistemic=Epistemic.REPORTED.value,
        confidence=0.35, importance=0.4, boot_id=store.boot_id,
        context="single unverified web source; not independently corroborated"))
    return {"acquired": True, "url": url, "subject": subject,
            "chars": rec.get("text_chars"), "sha256": rec.get("content_sha256"),
            "epistemic": "reported", "confidence": 0.35,
            "note": "stored as reported; a webpage returning bytes is not evidence "
                    "the bytes are true"}
