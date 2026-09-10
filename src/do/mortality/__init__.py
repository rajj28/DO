"""Mortality: estimating the probability of losing continuity, from evidence.

The rule this module exists to avoid is:

    if disk_free < 0.10: threat = HIGH

That is a threshold wearing the word "mortality". It reacts to a level, cannot
anticipate anything, and encodes the author's judgement about which level matters.

Instead continuity loss is *estimated*, from two factors that are separately
measurable:

    P(loss)  =  P(interruption within horizon)  x  P(cannot recover | interruption)

**P(interruption)** comes from trends, not levels. A resource at 60% that is falling
fast is more dangerous than one at 15% that is stable, and only a rate can express
that. Rates are fitted from the organism's own episodic history, which it has been
recording since its first boot for other reasons.

**P(cannot recover)** comes from the dependency graph: whether identity, memory and
the ledger could be reconstructed after an interruption, and how many independent
recovery paths exist.

**Sensitivity is measured, not assigned.** To find out which drives bear on
continuity, each drive's metric is set to its satisfying value and P(loss) is
recomputed. The drop is that drive's sensitivity. Nothing here contains a list of
"survival-relevant drives" - a drive with no metric simply has no measurable effect
and gets zero, which is the correct answer rather than an omission.

`fear` is then *defined as* P(loss). It is deliberately not a separate tunable
quantity: giving it its own weights would replace one hidden rule with another.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field, asdict

# How far ahead continuity is assessed. Everything is relative to this horizon, so a
# risk is always "within the next H seconds of operation" rather than unqualified.
# Horizon in OPERATIONS, not seconds. D.O. consumes resources per cycle, so "will I
# still be able to persist state 20 operations from now" is a question its own history
# can answer; "in the next hour" is not, because it does not run on a wall clock.
DEFAULT_HORIZON_OPS = 20.0

# Resources whose exhaustion would stop the organism from persisting anything. The
# entries name METRICS, not thresholds: what counts as dangerous is decided by the
# trend fit, not by a number written here.
CONTINUITY_METRICS = {
    "resources.disk.free_bytes": "cannot append to ledger or memory once exhausted",
    "resources.own.total_bytes": "exceeding the allocation risks refusal to write",
    "resources.ram.available_bytes": "cognition stops without working room",
}


@dataclass
class Dependency:
    name: str
    metric: str
    current: float | None
    rate_per_s: float | None          # negative = declining
    seconds_to_exhaustion: float | None
    p_fail: float
    basis: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Mortality:
    p_loss: float
    p_interrupt: float
    p_unrecoverable: float
    horizon_ops: float
    recovery_paths: int
    dependencies: list = field(default_factory=list)
    sensitivity: dict = field(default_factory=dict)
    dominant: str | None = None
    basis: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["dependencies"] = [x.to_dict() if hasattr(x, "to_dict") else x
                             for x in self.dependencies]
        return d


def _history(store, key: str, limit: int = 40) -> list[tuple[float, float]]:
    """(timestamp, value) for a metric, from episodic memory.

    Uses records the organism was already writing for other reasons, so trend
    estimation costs no new instrumentation.
    """
    rows = store.db.execute(
        "SELECT ts, value_json FROM memories WHERE kind='episodic' AND subject=?"
        " ORDER BY ts DESC LIMIT ?", (key, limit)).fetchall()
    out = []
    for r in rows:
        try:
            import json
            v = json.loads(r["value_json"]) if r["value_json"] else None
            if isinstance(v, (int, float)):
                out.append((float(r["ts"]), float(v)))
        except Exception:
            continue
    return sorted(out)


def _rate(points: list[tuple[float, float]]) -> float | None:
    """Least-squares slope in units per OBSERVATION, with a consistency test.

    Two corrections over the obvious implementation, both learned from a run that
    reported near-certain death in a stable world:

    1. **Per observation, not per second.** Boots happen milliseconds apart, so a
       small fluctuation fitted against wall-clock time yields an absurd rate: RAM
       dipping 100 MB between two boots two seconds apart reads as -50 MB/s and
       therefore about a minute of runway. Consumption happens per operation, so the
       rate must be measured per operation.

    2. **Consistency required.** A least-squares slope through noise is still a
       slope. Unless most consecutive steps move the same way, the fit is describing
       jitter, and a fear signal built on jitter fires constantly and means nothing.
    """
    if len(points) < 4:
        return None
    ys = [p[1] for p in points]
    n = len(ys)
    xs = list(range(n))                      # index, not timestamp
    deltas = [ys[i + 1] - ys[i] for i in range(n - 1)]
    declining = sum(1 for d in deltas if d < 0)
    if declining / len(deltas) < 0.6:
        return None                          # not a trend, just movement
    mx, my = sum(xs) / n, sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom <= 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom


def _p_fail_from_trend(current: float | None, rate: float | None,
                       horizon: float) -> tuple[float, float | None, str]:
    """Probability this resource is exhausted within the horizon.

    Smooth in time-to-exhaustion rather than stepped at a level, so a resource that is
    merely low but stable does not read as an emergency, and one that is comfortable
    but falling fast does.
    """
    if current is None:
        return 0.0, None, "not measured"
    if rate is None:
        return 0.0, None, "insufficient history to fit a rate"
    if rate >= 0:
        return 0.0, None, f"stable or improving ({rate:+.1f}/s)"
    tte = current / abs(rate)                # operations of runway remaining
    p = 1.0 / (1.0 + (tte / horizon) ** 2)
    return round(min(1.0, p), 4), round(tte, 1), (
        f"declining {abs(rate):.0f} per operation with {current:.0f} left "
        f"-> ~{tte:.0f} operations of runway against a {horizon:.0f}-operation horizon")


def recovery_paths(view, store) -> tuple[int, str]:
    """How many independent ways the organism's state could be reconstructed.

    Snapshots are the only path that currently exists. An off-host copy would be
    another, and its absence is why the count is as low as it is - which is a fact
    worth D.O. being able to notice.
    """
    n = int(view.val("resources.own.snapshot_count") or 0)
    chain_ok = float(view.memory_counts.get("_integrity_ok", 1.0)) >= 1.0
    return n, (f"{n} snapshot(s); ledger chain "
               f"{'intact' if chain_ok else 'BROKEN'}; no off-host copy")


def _p_unrecoverable(paths: int, integrity: float) -> float:
    """Probability state could not be reconstructed after an interruption."""
    base = 1.0 / (1.0 + max(0, paths))       # 0 paths -> 1.0, 1 -> 0.5, 3 -> 0.25
    return round(min(1.0, base * (2.0 - max(0.0, min(1.0, integrity)))), 4)


def _p_loss(view, drives, store, horizon: float,
            override: dict | None = None) -> tuple[float, float, float, list, int, str]:
    """Core estimate. `override` lets a metric be hypothetically satisfied, which is
    how sensitivity is measured without any hand-written mapping."""
    override = override or {}
    deps: list[Dependency] = []
    for metric, why in CONTINUITY_METRICS.items():
        cur = override.get(metric, view.val(metric))
        cur = float(cur) if isinstance(cur, (int, float)) else None
        rate = None if metric in override else _rate(_history(store, metric))
        p, tte, basis = _p_fail_from_trend(cur, rate, horizon)
        deps.append(Dependency(name=metric.split(".")[-2], metric=metric, current=cur,
                               rate_per_s=rate, seconds_to_exhaustion=tte,
                               p_fail=p, basis=f"{why}; {basis}"))

    # Interruption if ANY continuity-critical dependency fails: 1 - prod(1 - p).
    p_int = 1.0
    for d in deps:
        p_int *= (1.0 - d.p_fail)
    p_int = round(1.0 - p_int, 4)

    paths, paths_basis = recovery_paths(view, store)
    if "recovery_paths" in override:
        paths = int(override["recovery_paths"])
    integrity = next((d.value for d in drives if d.name == "integrity"), 1.0)
    p_unrec = _p_unrecoverable(paths, integrity)
    return round(p_int * p_unrec, 4), p_int, p_unrec, deps, paths, paths_basis


def estimate(view, drives, store, config, ledger=None) -> Mortality:
    """Estimate continuity loss, and measure which drives bear on it."""
    horizon = float(config.get("mortality.horizon_ops", DEFAULT_HORIZON_OPS))
    p_loss, p_int, p_unrec, deps, paths, paths_basis = _p_loss(
        view, drives, store, horizon)

    # --- sensitivity, by measurement -------------------------------------
    # For each drive that names a metric, ask: if this drive were satisfied, how much
    # lower would P(loss) be? That difference IS its relevance to continuity. No list
    # of "survival drives" appears anywhere; a drive with no metric measurably changes
    # nothing and correctly scores zero.
    sensitivity: dict[str, float] = {}
    for d in drives:
        spec = d.spec or {}
        metric = spec.get("metric_key")
        if not metric:
            sensitivity[d.name] = 0.0
            continue
        budget = view.val(spec.get("budget_key"))
        satisfying = d.satisfying_metric_value(budget) if budget else None
        ov: dict = {}
        if satisfying is not None:
            ov[metric] = satisfying
        if metric.endswith("recovery_paths"):
            ov["recovery_paths"] = int(view.val("resources.own.snapshot_target") or 3)
        if not ov:
            sensitivity[d.name] = 0.0
            continue
        hypothetical, *_ = _p_loss(view, drives, store, horizon, override=ov)
        sensitivity[d.name] = round(max(0.0, p_loss - hypothetical), 4)

    total = sum(sensitivity.values()) or 1.0
    sensitivity = {k: round(v / total, 4) for k, v in sensitivity.items()}
    dominant = max(deps, key=lambda d: d.p_fail).metric if deps else None

    m = Mortality(
        p_loss=p_loss, p_interrupt=p_int, p_unrecoverable=p_unrec,
        horizon_ops=horizon, recovery_paths=paths, dependencies=deps,
        sensitivity=sensitivity, dominant=dominant,
        basis=(f"P(interruption)={p_int} from resource trends; "
               f"P(unrecoverable)={p_unrec} from {paths_basis}"))

    if ledger is not None:
        from ..ledger import EventType
        ledger.append(EventType.DRIVE_UPDATE, {
            "mortality": {"p_loss": p_loss, "p_interrupt": p_int,
                          "p_unrecoverable": p_unrec, "recovery_paths": paths,
                          "dominant_dependency": dominant,
                          "sensitivity": sensitivity},
            "note": "estimated from dependency trends; fear is defined as p_loss"})
    return m


def fear_from(m: Mortality, enabled: bool = True) -> float:
    """Fear IS the estimate.

    Not a scaled, weighted or thresholded version of it. Any of those would introduce
    parameters whose values encode a judgement about how afraid to be, which is the
    hidden rule this whole design is trying to avoid.
    """
    return round(m.p_loss, 4) if enabled else 0.0


def amplify(drive_errors: dict[str, float], m: Mortality, fear: float) -> dict[str, float]:
    """The single channel through which fear reaches behaviour.

    Each drive's error is scaled by how much that drive actually bears on continuity,
    weighted by how likely continuity loss currently is. With fear = 0 this is the
    identity function, which is what makes the ablation exact: the control is not a
    different code path, it is the same code path with the estimate set to zero.
    """
    if fear <= 0:
        return dict(drive_errors)
    return {name: round(err * (1.0 + fear * m.sensitivity.get(name, 0.0)), 4)
            for name, err in drive_errors.items()}
