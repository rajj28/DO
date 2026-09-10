"""Self-model and world-model: derived views, not stores.

The brief proposed these as writable components. They are projections instead, built
from observations plus memory. Two writable copies of the same fact desynchronise, and
when they do, the one that is wrong is the one you consult.

The six namespaces are kept strictly apart. Mixing SELF with WORLD is how an agent
comes to treat its own configuration as a fact about reality.

`REQUIRED_SLOTS` is the self-model schema. An unfilled slot is not an error — it is a
*known unknown*, and it is the primary source of the orientation drive and of gaps.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from ..kernel.types import Epistemic, Namespace, Observation

# What a self-model must contain to count as oriented. Chosen because each is either
# measurable or clearly not, so "unfilled" is unambiguous.
REQUIRED_SLOTS: dict[str, str] = {
    "self.process.pid":              "which process am I",
    "self.runtime.version":          "what executes me",
    "self.clock.epoch":              "when is now",
    "self.memory.db_exists":         "do I have a past",
    "self.purpose":                  "what am I for",
    "self.expected_lifetime":        "how long do I persist",
    "resources.cpu.logical":         "how much compute",
    "resources.ram.available_bytes": "how much working room",
    "resources.disk.free_bytes":     "how much room to persist",
    "world.host.system":             "what kind of place is this",
    "world.network.reachable":       "is anything outside reachable",
    "user.identity":                 "who started me",
    "user.intent":                   "what is wanted of me",
}


@dataclass
class StateView:
    """Everything cognition is allowed to see, in one immutable-ish bundle."""

    observations: dict[str, Observation] = field(default_factory=dict)
    referents: list[dict] = field(default_factory=list)
    capabilities: list[dict] = field(default_factory=list)
    drives: list[Any] = field(default_factory=list)
    memory_counts: dict = field(default_factory=dict)
    identity: dict = field(default_factory=dict)
    prior_boot: dict | None = None
    carried_gaps: list[dict] = field(default_factory=list)
    boot_ts: float = field(default_factory=time.time)
    config: Any = None

    # ---- access -----------------------------------------------------------
    def val(self, key: str, default: Any = None) -> Any:
        o = self.observations.get(key)
        return default if o is None or not o.is_known else o.value

    def obs(self, key: str) -> Observation | None:
        return self.observations.get(key)

    def known(self, key: str) -> bool:
        o = self.observations.get(key)
        return bool(o and o.is_known)

    def by_namespace(self, ns: Namespace) -> dict[str, Observation]:
        return {k: o for k, o in self.observations.items() if o.namespace is ns}

    def config_floor(self, dotted: str) -> Any:
        """Comparison thresholds live in config, not in cognition. D.O. measures a
        value and compares it to a floor; it is never told 'disk is low'."""
        return self.config.get(dotted) if self.config is not None else None

    # ---- derived ----------------------------------------------------------
    def filled_slots(self) -> tuple[list[str], list[str]]:
        filled = [s for s in REQUIRED_SLOTS if self.known(s)]
        unfilled = [s for s in REQUIRED_SLOTS if not self.known(s)]
        return filled, unfilled

    def orientation(self) -> float:
        filled, _ = self.filled_slots()
        return len(filled) / max(1, len(REQUIRED_SLOTS))

    def described_ratio(self) -> float:
        """Fraction of visible referents this organism can say anything about.

        In the seed this is 0.0 by construction, and that is the honest value: it has
        collected names and possesses no descriptions. The number is not decoration,
        it is the comprehension drive's input."""
        if not self.referents:
            return 1.0
        described = sum(1 for r in self.referents if r.get("described"))
        return described / len(self.referents)


def build_self_model(view: StateView) -> dict:
    filled, unfilled = view.filled_slots()
    ns = view.by_namespace(Namespace.SELF)
    return {
        "identity": view.identity,
        "namespace": "SELF",
        "slots_filled": {s: view.val(s) for s in filled if s.startswith("self.")},
        "slots_unfilled": [s for s in unfilled if s.startswith("self.")],
        "orientation": round(view.orientation(), 3),
        "observations": {k: o.to_dict() for k, o in ns.items()},
        "limitations": _limitations(view),
        "age_seconds": round(time.time() - view.identity.get("born_at", time.time()), 1),
        "boot_index": view.identity.get("boot_index"),
        "has_past": bool(view.prior_boot),
    }


def build_world_model(view: StateView) -> dict:
    return {
        "namespace": "WORLD",
        "host": {k: view.val(k) for k in view.observations if k.startswith("world.host.")},
        "network": {
            "reachable": view.val("world.network.reachable"),
            "epistemic": (view.obs("world.network.reachable").epistemic.value
                          if view.obs("world.network.reachable") else "unknown"),
        },
        "referents_seen": len(view.referents),
        "referents_described": sum(1 for r in view.referents if r.get("described")),
        "comprehension": round(view.described_ratio(), 3),
        "referents": [{k: r[k] for k in ("name", "kind", "evidence", "weight")}
                      for r in sorted(view.referents, key=lambda r: -r["weight"])[:40]],
        "user": {
            "identity": view.val("user.identity"),
            "intent": view.val("user.intent"),
            "status": "unknown_but_presumed_present" if view.val("self.process.interactive")
                      else "unknown",
        },
        "resources": {k: view.val(k) for k in view.observations
                      if k.startswith("resources.")},
        "tools": {
            "on_path": view.val("tools.on_path", []),
            "local_models": view.val("tools.local_models", []),
        },
    }


def _limitations(view: StateView) -> list[str]:
    """Limitations the organism can establish by measurement, not by being told."""
    out: list[str] = []
    if view.val("world.network.reachable") is False:
        out.append("world.network.reachable=false: cannot obtain information beyond this host")
    fr = view.val("resources.disk.free_ratio")
    if fr is not None and fr < 0.10:
        out.append(f"resources.disk.free_ratio={fr}: persistence headroom is constrained")
    rr = view.val("resources.ram.free_ratio")
    if rr is not None and rr < 0.15:
        out.append(f"resources.ram.free_ratio={rr}: working room is constrained")
    for c in view.capabilities:
        if c.get("status") == "installed_unaffordable":
            out.append(f"capability {c['name']}: present but exceeds measured resources")
    _, unfilled = view.filled_slots()
    if unfilled:
        out.append(f"{len(unfilled)}/{len(REQUIRED_SLOTS)} self-model slots unfilled")
    return out


def snapshot(view: StateView, path) -> dict:
    from pathlib import Path
    snap = {
        "ts": time.time(),
        "self": build_self_model(view),
        "world": build_world_model(view),
        "drives": [d.to_dict() for d in view.drives],
        "memory": view.memory_counts,
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(snap, indent=2, default=str), encoding="utf-8")
    return snap
