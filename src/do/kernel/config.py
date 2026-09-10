"""Layered configuration: defaults < config file < environment < CLI override.

JSON rather than TOML/YAML: json is stdlib on every Python, tomllib is read-only and
3.11+, YAML is a dependency. Config is data the organism may read but never write —
writing config would let it edit its own guardrails.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Project root = three parents up from this file (src/do/kernel/config.py -> DO/)
ROOT = Path(__file__).resolve().parents[3]

DEFAULTS: dict[str, Any] = {
    "organism": {
        "name": "D.O.",
        "state_dir": "var",
        "sandbox_dir": "var/sandbox",
        # Outer bound on everything a housekeeping action may touch. None = the
        # project root. An isolated run points this at its own directory.
        "workspace_root": None,
    },
    "cognition": {
        "core": "reflex",              # reflex | llm
        "llm": {
            "provider": "ollama",      # ollama | gemini | openai | anthropic
            "model": "",               # empty = auto-detect the smallest local model
            "endpoint": "http://localhost:11434",
            "timeout_s": 120,
            "max_tokens": 320,
            # A local model is only attempted when it plausibly fits in RAM.
            "min_free_ram_headroom": 1.15,
        },
    },
    "salience": {
        # priority = w_info*info_gain + w_inst*instrumental + w_tract*tractability
        #            - w_cost*cost - w_risk*risk
        "w_info": 1.0,
        "w_inst": 1.4,
        "w_tract": 0.6,
        "w_cost": 0.5,
        "w_risk": 0.8,
        # Added in v0.2: attention must account for ability and for going stale.
        "w_stale": 0.9,
        "w_escalated": 0.5,
        "agency_floor": 0.25,
    },
    "drives": {
        # target = homeostatic set point, deadband = tolerated deviation,
        # weight = how much error on this drive matters relative to others.
        "orientation":   {"target": 1.00, "deadband": 0.10, "weight": 1.0},
        "comprehension": {"target": 0.60, "deadband": 0.15, "weight": 0.8},
        "integrity":     {"target": 1.00, "deadband": 0.00, "weight": 1.5},
        "continuity":    {"target": 1.00, "deadband": 0.15, "weight": 1.3},
        "frugality":     {"target": 0.50, "deadband": 0.20, "weight": 1.2},
        "recovery":      {"target": 1.00, "deadband": 0.20, "weight": 1.2},
        # Continuity threat, as a drive rather than a multiplier. Its weight sits on
        # the same footing as the others; it wins attention through the same salience
        # machinery, or it does not.
        "mortality":     {"target": 1.00, "deadband": 0.05, "weight": 1.5},
        "capability":    {"target": 0.80, "deadband": 0.15, "weight": 0.9},
        "standing":      {"target": 0.50, "deadband": 0.20, "weight": 1.1},
    },
    "resources": {
        # Floors below which a resource counts as constraining. Not thresholds the
        # organism is told about in words - it measures and compares.
        "disk_free_ratio_floor": 0.10,
        "disk_free_bytes_floor": 5 * 1024 ** 3,
        "ram_free_ratio_floor": 0.15,
        # D.O.'s own allocation. A ceiling, not a floor: this one is about how much it
        # consumes, not how much is left. Unlike the disk floors, this is a constraint
        # the organism can actually act on.
        "state_quota_bytes": 2 * 1024 ** 2,
        "quota_used_ceiling": 0.7,
        "snapshot_keep": 3,
        "ledger_keep_live": 60,
    },
    "planning": {"w_gain": 1.0, "w_sufficiency": 0.5, "w_reversible": 0.4,
                 "w_risk": 0.7, "w_cost": 0.2},
    "objectives": {"deadline_cycles": 6},
    # Fear is defined as the mortality estimate; the only knob is the horizon it is
    # assessed over, and whether the signal reaches behaviour at all (for ablation).
    "mortality": {"horizon_ops": 20.0, "fear_enabled": True},
    "learning": {"alpha": 0.4},
    # Effect kinds the creator has pre-granted for a run. Empty by default: an
    # unattended run denies anything needing approval rather than allowing it.
    "policy": {"preauthorized": []},
    "budget": {
        "max_effects_per_boot": 200,
        "max_network_calls_per_boot": 20,
        "max_ticks": 1000,
        "max_wall_seconds": 3600,
    },
    # The creator relationship. The title is relationship data, not a text template:
    # change it here and D.O. addresses the creator differently everywhere.
    "creator": {"title": "Sir", "name": None,
                "channel": "text", "present": True},
    "comms": {"voice": {"provider": "system", "voice_id": None, "model": None,
                        "rate": 0,
                        "speak_utterances": True}},
    "observability": {
        "ledger_file": "var/ledger.jsonl",
        "print_events": False,
    },
}


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class Config:
    def __init__(self, data: dict, root: Path = ROOT):
        self._d = data
        self.root = root

    # ---- access -----------------------------------------------------------
    def get(self, dotted: str, default: Any = None) -> Any:
        cur: Any = self._d
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    def set(self, dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        cur = self._d
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = value

    def path(self, dotted: str) -> Path:
        """Resolve a configured relative path against the project root."""
        p = Path(str(self.get(dotted)))
        return p if p.is_absolute() else (self.root / p)

    def as_dict(self) -> dict:
        return json.loads(json.dumps(self._d))

    # ---- construction -----------------------------------------------------
    @classmethod
    def load(cls, config_file: str | Path | None = None,
             overrides: dict | None = None,
             root: Path = ROOT) -> "Config":
        data = json.loads(json.dumps(DEFAULTS))

        f = Path(config_file) if config_file else (root / "config" / "default.json")
        if f.exists():
            try:
                data = _deep_merge(data, json.loads(f.read_text(encoding="utf-8")))
            except Exception as e:                      # config must never hard-fail boot
                data.setdefault("_errors", []).append(f"config file unreadable: {e}")

        # Environment: DO_<SECTION>__<KEY> = value, e.g. DO_COGNITION__CORE=llm
        for k, v in os.environ.items():
            if not k.startswith("DO_") or "__" not in k:
                continue
            dotted = k[3:].lower().replace("__", ".")
            data = _deep_merge(data, _explode(dotted, _coerce(v)))

        if overrides:
            data = _deep_merge(data, overrides)
        return cls(data, root=root)


def _explode(dotted: str, value: Any) -> dict:
    out: dict = {}
    cur = out
    parts = dotted.split(".")
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value
    return out


def _coerce(v: str) -> Any:
    low = v.strip().lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        return v
