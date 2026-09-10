"""Identity and lineage.

Two identifiers, and the difference between them is load-bearing:

  organism_id  persists forever, across every restart. It is the thing that has a
               history. Created once, on the first boot, and never regenerated.
  boot_id      is unique per process. It is how the ledger attributes an event to a
               particular life.

`boot_index` is how the organism knows whether it has a past. It is the only reason
boot #2 can differ from boot #1 (hypothesis H2).
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class Identity:
    organism_id: str
    born_at: float
    boot_id: str
    boot_index: int          # 1 on the very first boot
    prior_boots: list[str]
    genesis: bool            # True only when this process created the identity

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def age_seconds(self) -> float:
        return max(0.0, time.time() - self.born_at)


def load_or_create(state_dir: Path) -> Identity:
    state_dir.mkdir(parents=True, exist_ok=True)
    f = state_dir / "identity.json"
    boot_id = f"boot-{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"

    if f.exists():
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            prior = list(d.get("boots", []))
            ident = Identity(
                organism_id=d["organism_id"],
                born_at=float(d["born_at"]),
                boot_id=boot_id,
                boot_index=len(prior) + 1,
                prior_boots=prior,
                genesis=False,
            )
        except Exception:
            # A corrupt identity file is itself information; do not silently
            # overwrite a possibly-recoverable one.
            corrupt = state_dir / f"identity.corrupt.{int(time.time())}.json"
            f.rename(corrupt)
            return load_or_create(state_dir)
    else:
        ident = Identity(
            organism_id=f"do-{uuid.uuid4().hex[:12]}",
            born_at=time.time(),
            boot_id=boot_id,
            boot_index=1,
            prior_boots=[],
            genesis=True,
        )

    f.write_text(json.dumps({
        "organism_id": ident.organism_id,
        "born_at": ident.born_at,
        "boots": ident.prior_boots + [boot_id],
        "last_boot_at": time.time(),
        "last_pid": os.getpid(),
    }, indent=2), encoding="utf-8")
    return ident
