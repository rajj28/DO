"""Shared value types.

These are the atoms every other package speaks in. Kept in one module so that no
package needs to import a sibling just to name a type (which is how import cycles
start).

Standard library only. See docs/ARCHITECTURE.md section 1.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class Epistemic(str, Enum):
    """How strongly a value is held.

    The honesty invariant (docs/DO_CONCEPT.md section G) forbids recording a value at
    a stronger status than its source supports.
    """

    OBSERVED = "observed"    # measured directly by this process, this boot
    INFERRED = "inferred"    # computed from other values held by this process
    REPORTED = "reported"    # asserted by a human, a file, or the network
    ASSUMED = "assumed"      # a default with no evidence behind it
    UNKNOWN = "unknown"      # explicitly not known; the value is absent


class Namespace(str, Enum):
    """The six referent classes. Kept apart on purpose: mixing SELF and WORLD is how
    an agent ends up believing its own configuration is a fact about reality."""

    SELF = "SELF"
    WORLD = "WORLD"
    USER = "USER"
    TOOLS = "TOOLS"
    RESOURCES = "RESOURCES"
    UNKNOWN = "UNKNOWN"


@dataclass
class Observation:
    """The atom of perception. Never a bare value."""

    key: str
    value: Any
    epistemic: Epistemic
    source: str
    namespace: Namespace = Namespace.SELF
    unit: str | None = None
    ts: float = field(default_factory=time.time)
    confidence: float = 1.0
    cost_ms: float = 0.0
    note: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["epistemic"] = self.epistemic.value
        d["namespace"] = self.namespace.value
        return d

    @property
    def is_known(self) -> bool:
        return self.epistemic is not Epistemic.UNKNOWN and self.value is not None


@dataclass
class EffectRequest:
    """A request to change something outside this process, or to read something the
    process is not automatically entitled to read."""

    kind: str               # net.dns, net.http, proc.exec, fs.write, llm.generate, tts.speak, human.ask
    target: str
    payload: dict = field(default_factory=dict)
    justification: str = ""
    gap_id: str | None = None
    estimated_cost: float = 0.0


@dataclass
class EffectResult:
    ok: bool
    verdict: str            # allow | deny | require_approval | halted | error
    value: Any = None
    error: str | None = None
    reason: str = ""
    duration_ms: float = 0.0


def canonical_json(obj: Any) -> str:
    """Stable serialization, so hashes over the same content always match."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
