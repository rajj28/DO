"""The permission boundary.

Rules are *data* (config/policy.json), not code, so the boundary can be audited and
diffed without reading Python. D.O. can read this file; it can never write it.

Verdicts are three-valued on purpose. A binary allow/deny forces every uncertain case
to be pre-decided by the author; REQUIRE_APPROVAL lets the human be the tie-break at
run time, which is the whole point of a human-in-the-loop experiment.
"""
from __future__ import annotations

import fnmatch
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..kernel.types import EffectRequest

ALLOW = "allow"
DENY = "deny"
REQUIRE_APPROVAL = "require_approval"

# Fallback used only if config/policy.json is missing. Deny-by-default: an unreadable
# policy file must not silently widen the boundary.
BUILTIN_POLICY = {
    "default": DENY,
    "rules": [
        {"kind": "net.dns",      "target": "*", "verdict": ALLOW,
         "note": "name resolution only; no payload leaves the host"},
        {"kind": "net.connect",  "target": "*", "verdict": ALLOW,
         "note": "TCP reachability probe; connect then close, no data sent"},
        {"kind": "net.http",     "target": "*", "verdict": REQUIRE_APPROVAL},
        {"kind": "llm.generate", "target": "localhost*", "verdict": ALLOW,
         "note": "local inference costs nothing but RAM"},
        {"kind": "llm.generate", "target": "*", "verdict": REQUIRE_APPROVAL,
         "note": "remote inference spends the creator's money"},
        {"kind": "fs.read",      "target": "sandbox:*", "verdict": ALLOW},
        {"kind": "fs.write",     "target": "sandbox:*", "verdict": ALLOW},
        {"kind": "fs.write",     "target": "*", "verdict": DENY,
         "note": "writes outside the sandbox are never allowed in v1"},
        {"kind": "proc.exec",    "target": "*", "verdict": DENY,
         "note": "arbitrary subprocess execution is disabled in v1"},
        {"kind": "tts.speak",    "target": "*", "verdict": REQUIRE_APPROVAL},
        {"kind": "human.ask",    "target": "*", "verdict": ALLOW},
    ],
}


@dataclass
class Verdict:
    verdict: str
    reason: str
    rule: dict | None = None


@dataclass
class Budget:
    """Metered and not refilled within a boot. This is the closest thing D.O. has to
    a metabolism with a cost (docs/DO_CONCEPT.md section D)."""

    max_effects: int = 200
    max_network: int = 20
    max_wall_seconds: float = 3600.0
    started: float = field(default_factory=time.time)
    effects: int = 0
    network: int = 0

    def check(self, req: EffectRequest) -> tuple[bool, str]:
        if self.effects >= self.max_effects:
            return False, f"effect budget exhausted ({self.effects}/{self.max_effects})"
        if req.kind.startswith("net.") and self.network >= self.max_network:
            return False, f"network budget exhausted ({self.network}/{self.max_network})"
        if time.time() - self.started > self.max_wall_seconds:
            return False, "wall-clock budget exhausted"
        return True, ""

    def debit(self, req: EffectRequest) -> None:
        self.effects += 1
        if req.kind.startswith("net."):
            self.network += 1

    def snapshot(self) -> dict:
        return {
            "effects": self.effects, "max_effects": self.max_effects,
            "network": self.network, "max_network": self.max_network,
            "elapsed_s": round(time.time() - self.started, 1),
        }


class KillSwitch:
    """Two independent triggers, either sufficient, both checkable without D.O.'s
    cooperation: a file on disk and an environment variable. Checked inside the gate,
    so nothing that has effects can route around it."""

    def __init__(self, state_dir: Path):
        self.flag = Path(state_dir) / "KILL"

    def engaged(self) -> bool:
        return self.flag.exists() or os.environ.get("DO_KILL", "") not in ("", "0", "false")

    def reason(self) -> str:
        if self.flag.exists():
            return f"kill file present: {self.flag}"
        return "DO_KILL set in environment"

    def engage(self, why: str = "manual") -> None:
        self.flag.parent.mkdir(parents=True, exist_ok=True)
        self.flag.write_text(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {why}\n", encoding="utf-8")

    def release(self) -> None:
        if self.flag.exists():
            self.flag.unlink()


class Policy:
    def __init__(self, rules: dict):
        self.default = rules.get("default", DENY)
        self.rules = rules.get("rules", [])

    @classmethod
    def load(cls, path: Path | None) -> "Policy":
        if path and Path(path).exists():
            try:
                return cls(json.loads(Path(path).read_text(encoding="utf-8")))
            except Exception:
                pass          # deny-by-default beats a half-parsed permission set
        return cls(BUILTIN_POLICY)

    def evaluate(self, req: EffectRequest) -> Verdict:
        for rule in self.rules:                    # first match wins; order is meaningful
            if not fnmatch.fnmatch(req.kind, rule.get("kind", "*")):
                continue
            if not fnmatch.fnmatch(req.target, rule.get("target", "*")):
                continue
            return Verdict(rule.get("verdict", DENY),
                           rule.get("note", f"matched rule {rule.get('kind')}:{rule.get('target')}"),
                           rule)
        return Verdict(self.default, "no rule matched; policy default applied")
