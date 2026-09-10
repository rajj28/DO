"""Append-only, hash-chained event log. The source of truth.

Everything else in D.O. is derived state and may be rebuilt or thrown away. This file
may not. Chaining each record's hash to its predecessor makes retroactive edits
detectable, which is what turns "we log things" into "the log is evidence".

Deliberately JSONL and not a database: a corrupt sqlite page can cost the whole
history; a corrupt JSONL line costs one line, and the chain tells you which.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Iterator

from ..kernel.types import canonical_json

GENESIS_HASH = "0" * 64


class EventType:
    BOOT = "BOOT"
    OBSERVATION = "OBSERVATION"
    DECISION = "DECISION"
    QUESTION = "QUESTION"
    TOOL_CALL = "TOOL_CALL"
    RESULT = "RESULT"
    MEMORY_WRITE = "MEMORY_WRITE"
    BELIEF_UPDATE = "BELIEF_UPDATE"
    CAPABILITY_CHANGE = "CAPABILITY_CHANGE"
    RESOURCE_CHANGE = "RESOURCE_CHANGE"
    DRIVE_UPDATE = "DRIVE_UPDATE"
    GAP_OPEN = "GAP_OPEN"
    GAP_RESOLVE = "GAP_RESOLVE"
    UTTERANCE = "UTTERANCE"
    INPUT = "INPUT"
    POLICY_DENY = "POLICY_DENY"
    POLICY_APPROVAL_REQUIRED = "POLICY_APPROVAL_REQUIRED"
    ERROR = "ERROR"
    RECOVERY = "RECOVERY"
    SHUTDOWN = "SHUTDOWN"


class Ledger:
    def __init__(self, path: Path, boot_id: str, echo: bool = False):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.boot_id = boot_id
        self.echo = echo
        self._seq, self._prev = self._tail()

    def _tail(self) -> tuple[int, str]:
        """Resume the chain. Reads only the last valid record, not the whole history.

        Falls back to the newest sealed segment when the live file is empty, which is
        the state immediately after a rotation that moved every record out.
        """
        last = None
        if self.path.exists() and self.path.stat().st_size > 0:
            with self.path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        last = line.strip()
        if last is None:
            segs = segments(self.path)
            if segs:
                try:
                    with gzip.open(segs[-1], "rt", encoding="utf-8") as fh:
                        for line in fh:
                            if line.strip():
                                last = line.strip()
                except Exception:
                    last = None
        if not last:
            return 0, GENESIS_HASH
        try:
            rec = json.loads(last)
            return int(rec["seq"]), str(rec["hash"])
        except Exception:
            return 0, GENESIS_HASH

    def append(self, type_: str, payload: dict[str, Any] | None = None,
               actor: str = "organism") -> dict:
        self._seq += 1
        rec = {
            "seq": self._seq,
            "ts": time.time(),
            "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
            "boot_id": self.boot_id,
            "type": type_,
            "actor": actor,
            "payload": payload or {},
            "prev_hash": self._prev,
        }
        rec["hash"] = hashlib.sha256(canonical_json(rec).encode("utf-8")).hexdigest()
        self._prev = rec["hash"]
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
            fh.flush()
            os.fsync(fh.fileno())      # a ledger that loses its tail on crash is not a ledger
        if self.echo:
            print(f"  [{type_}] {json.dumps(rec['payload'], default=str)[:160]}")
        return rec

    def decision(self, decision: str, reason: str, confidence: float,
                 alternatives: int = 0, **extra) -> dict:
        """A structured decision summary.

        Explicitly NOT a reasoning trace. What is recorded is the selection: what was
        chosen, out of how many candidates, on what measured grounds. That is enough
        to audit behaviour without exposing private deliberation.
        """
        return self.append(EventType.DECISION, {
            "decision": decision,
            "reason": reason,
            "confidence": round(float(confidence), 3),
            "alternatives_considered": alternatives,
            **extra,
        })

    # ---- reading ----------------------------------------------------------
    def read(self, limit: int | None = None, types: set[str] | None = None,
             boot_id: str | None = None) -> list[dict]:
        out = [r for r in iter_events(self.path)
               if (types is None or r.get("type") in types)
               and (boot_id is None or r.get("boot_id") == boot_id)]
        return out[-limit:] if limit else out

    def verify(self) -> tuple[bool, str]:
        return verify_chain(self.path)


def segments(path: Path) -> list[Path]:
    """Sealed, gzipped segments of this ledger, oldest first.

    Rotation (see `capabilities/actions.py::RotateLedger`) moves old records out of the
    live file to save space. The chain must still read as one continuous history, so
    every reader here walks segments before the live file. Zero-padded indices make
    lexicographic order the right order.
    """
    p = Path(path)
    return sorted(p.parent.glob(f"{p.stem}.seg*.jsonl.gz"))


def _parse_lines(lines: Iterator[str]) -> Iterator[dict]:
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except Exception:
            continue


def iter_events(path: Path, include_segments: bool = True) -> Iterator[dict]:
    p = Path(path)
    if include_segments:
        for seg in segments(p):
            try:
                with gzip.open(seg, "rt", encoding="utf-8") as fh:
                    yield from _parse_lines(fh)
            except Exception:
                continue
    if not p.exists():
        return
    with p.open("r", encoding="utf-8") as fh:
        yield from _parse_lines(fh)


def verify_chain(path: Path) -> tuple[bool, str]:
    """Re-walk the hash chain across sealed segments and the live file."""
    prev = GENESIS_HASH
    n = 0
    for rec in iter_events(path):
        n += 1
        if rec.get("prev_hash") != prev:
            return False, f"chain break at seq={rec.get('seq')}: prev_hash mismatch"
        body = {k: v for k, v in rec.items() if k != "hash"}
        h = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
        if h != rec.get("hash"):
            return False, f"content altered at seq={rec.get('seq')}: hash mismatch"
        prev = rec["hash"]
    nseg = len(segments(path))
    return True, (f"chain intact over {n} events"
                  + (f" across {nseg} sealed segment(s) + live" if nseg else ""))
