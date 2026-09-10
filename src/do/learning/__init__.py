"""Outcome learning: the only place in D.O. where experience changes future behaviour.

Every action predicts bytes freed before it runs and reports bytes freed after. The
ratio between them is a correction factor the organism has no way to know a priori and
every way to learn:

    k <- (1 - alpha) * k + alpha * (actual / predicted_raw)

`predicted_raw` is the action's own uncalibrated estimate, so `k` means exactly one
thing - "how wrong is this action's model of itself" - and the calibrated prediction is
`predicted_raw * k`.

Why this is a real learning target and not a decorative one: two of the five actions
have estimates that cannot be correct in principle.

* `rotate_ledger` assumes a 2.0x compression ratio because nothing can know in advance
  how well its own history compresses. On this host the true figure is near 7x, so the
  first prediction is wrong by a factor of three and the correction is large, specific,
  and verifiable.
* `vacuum_memory` estimates from the sqlite freelist, which ignores defragmentation.

The other three are close to exactly predictable, which matters: a learning result that
improves *only* the hard cases and leaves the easy ones alone is far more credible than
one that improves everything uniformly.

This satisfies the tier-3 definition in `docs/DO_CONCEPT.md` §C only if the ablation is
run. `experiments/survival_loop.py` runs it.
"""
from __future__ import annotations

import time
from typing import Any

from ..kernel.types import Epistemic
from ..ledger import EventType
from ..memory import MemoryRecord

CALIBRATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS calibration (
    action TEXT PRIMARY KEY,
    k REAL NOT NULL DEFAULT 1.0,
    samples INTEGER NOT NULL DEFAULT 0,
    last_predicted_raw REAL,
    last_predicted REAL,
    last_actual REAL,
    sum_ape REAL NOT NULL DEFAULT 0.0,
    updated_ts REAL
);
"""


def ensure_schema(store) -> None:
    store.db.executescript(CALIBRATION_SCHEMA)
    store.db.commit()


def load_calibration(store) -> dict[str, float]:
    ensure_schema(store)
    return {r["action"]: float(r["k"]) for r in
            store.db.execute("SELECT action, k FROM calibration").fetchall()}


def ape(predicted: float, actual: float) -> float:
    """Absolute percentage error, floored so a zero actual does not divide by zero."""
    denom = max(abs(actual), 1.0)
    return abs(actual - predicted) / denom


def record_outcome(store, ledger, action_name: str, predicted_raw: int,
                   predicted: int, actual: int, detail: dict, config) -> dict:
    """Compare prediction to observation, update the model, remember the lesson."""
    ensure_schema(store)
    alpha = float(config.get("learning.alpha", 0.4))

    row = store.db.execute("SELECT * FROM calibration WHERE action=?",
                           (action_name,)).fetchone()
    k_before = float(row["k"]) if row else 1.0
    samples = int(row["samples"]) if row else 0
    sum_ape = float(row["sum_ape"]) if row else 0.0

    err_before = ape(predicted, actual)

    if predicted_raw > 0:
        observed_k = actual / predicted_raw
        # First observation carries full weight: a prior of 1.0 held with no evidence
        # should not be defended against the first real measurement.
        k_after = observed_k if samples == 0 else (1 - alpha) * k_before + alpha * observed_k
    else:
        observed_k, k_after = None, k_before

    store.db.execute(
        "INSERT INTO calibration (action,k,samples,last_predicted_raw,last_predicted,"
        "last_actual,sum_ape,updated_ts) VALUES (?,?,?,?,?,?,?,?) "
        "ON CONFLICT(action) DO UPDATE SET k=excluded.k, samples=calibration.samples+1,"
        " last_predicted_raw=excluded.last_predicted_raw,"
        " last_predicted=excluded.last_predicted, last_actual=excluded.last_actual,"
        " sum_ape=calibration.sum_ape+?, updated_ts=excluded.updated_ts",
        (action_name, k_after, 1, predicted_raw, predicted, actual,
         err_before, time.time(), err_before))
    store.db.commit()

    ledger.append(EventType.BELIEF_UPDATE, {
        "subject": f"capability.{action_name}.calibration",
        "predicted_raw": predicted_raw, "predicted": predicted, "actual": actual,
        "absolute_percentage_error": round(err_before, 4),
        "k_before": round(k_before, 4), "k_after": round(k_after, 4),
        "samples": samples + 1,
        "note": "prediction error folded into the action's own model of itself",
    })

    # Procedural memory: how to do it, and how well it actually works.
    store.write(MemoryRecord(
        kind="procedural", subject=f"capability.{action_name}.performance",
        content=(f"{action_name}: raw estimate x{k_after:.3f} matches observed outcome "
                 f"(n={samples + 1}); last run predicted {predicted}B, freed {actual}B"),
        value={"k": k_after, "samples": samples + 1, "last_ape": round(err_before, 4)},
        source=f"outcome:{action_name}", epistemic=Epistemic.OBSERVED.value,
        confidence=min(0.95, 0.5 + 0.1 * (samples + 1)), importance=0.7,
        boot_id=store.boot_id, context="learned from acting, not from being told"))

    # Facts about itself that only acting could reveal.
    ratio = detail.get("observed_compression_ratio")
    if ratio:
        store.believe(
            subject="self.ledger.compression_ratio",
            content=f"my own event history compresses {ratio}x with gzip -9",
            source=f"outcome:{action_name}", epistemic=Epistemic.OBSERVED.value,
            confidence=0.9, importance=0.6, value=ratio)

    return {"action": action_name, "predicted_raw": predicted_raw,
            "predicted": predicted, "actual": actual,
            "ape": round(err_before, 4), "k_before": round(k_before, 4),
            "k_after": round(k_after, 4), "observed_k": observed_k,
            "samples": samples + 1}


def calibration_report(store) -> list[dict]:
    ensure_schema(store)
    out = []
    for r in store.db.execute("SELECT * FROM calibration ORDER BY action").fetchall():
        n = max(1, int(r["samples"]))
        out.append({"action": r["action"], "k": round(float(r["k"]), 4),
                    "samples": int(r["samples"]),
                    "mean_ape": round(float(r["sum_ape"]) / n, 4),
                    "last_predicted": r["last_predicted"], "last_actual": r["last_actual"]})
    return out


def wipe_calibration(store) -> int:
    """Ablation support. Removes learned state, leaves code and beliefs untouched -
    which is what makes the comparison in `docs/DO_CONCEPT.md` §C step 5 meaningful."""
    ensure_schema(store)
    n = store.db.execute("SELECT COUNT(*) c FROM calibration").fetchone()["c"]
    store.db.execute("DELETE FROM calibration")
    store.db.execute("DELETE FROM memories WHERE kind='procedural' AND subject LIKE "
                     "'capability.%.performance'")
    store.db.commit()
    return int(n)
