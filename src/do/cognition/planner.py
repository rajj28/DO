"""Candidate generation and evaluation: the two steps between an objective and an act.

Separated from `objectives.py` on purpose. Deciding *what to achieve* and deciding
*how* are different failures when they go wrong, and collapsing them is how an agent
ends up choosing goals it happens to have tools for rather than tools that serve its
goals.

Evaluation scores every applicable action on five terms:

    expected_gain   predicted movement toward the target, CALIBRATED by past outcomes
    sufficiency     whether this one action closes the objective on its own
    reversibility   regenerable > derived > compressed > irreversible
    risk            declared by the action
    cost            wall-clock, as a fraction of a budget

Exactly one action is selected per cycle. That is a deliberate constraint: with two
actions in flight, an outcome cannot be attributed to either, and the learning signal -
the whole reason for predicting before acting - is destroyed.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

REVERSIBILITY_WEIGHT = {
    "regenerable": 1.0,     # re-runnable from scratch
    "derived": 0.85,        # rebuildable from the ledger
    "compressed": 0.7,      # content preserved in another form
    "irreversible": 0.0,    # none exist in v0.1
}


@dataclass
class Candidate:
    action: str
    description: str
    component: str
    predicted_raw: int
    calibration_k: float
    predicted: int
    basis: str
    precondition: str
    risk: float
    reversible: str
    cost_s: float
    diagnostic: bool = False
    reliability: float = 0.7
    reliability_basis: str = ""
    sufficiency: float = 0.0
    score: float = 0.0
    rejected: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def generate(ctx, objective, calibration: dict[str, float],
             stage: str | None = None, store=None, view=None) -> list[Candidate]:
    """Enumerate applicable actions, restricted to the goal's current stage.

    Stage filtering is what stops the loop short-circuiting its own decomposition. In
    DIAGNOSE only diagnostics are offered, so D.O. cannot start deleting things before
    it knows what they are. In REDUCE only actions moving this objective's metric are
    offered, so a diagnostic cannot be mistaken for progress.
    """
    from ..capabilities.actions import applicable_actions

    out: list[Candidate] = []
    for action, why in applicable_actions(ctx):
        if stage == "diagnose" and not action.diagnostic:
            continue
        if stage == "reduce" and (action.diagnostic
                                  or action.metric != objective.metric_key):
            continue
        try:
            raw, basis = action.estimate(ctx)
        except Exception as e:
            raw, basis = 0, f"estimate failed: {type(e).__name__}: {e}"
        k = float(calibration.get(action.name, 1.0))
        # Conditional reliability, learned from this action's own history in
        # situations like this one. Prior 0.7 until there is evidence.
        rel, rel_why = 0.7, "no experience yet"
        if store is not None and view is not None:
            from ..learning import outcomes as _out
            feats = _out.context_features(view, objective, stage or "")
            rel, rel_why = _out.reliability(store, action.name, feats)
        out.append(Candidate(
            reliability=rel, reliability_basis=rel_why,
            diagnostic=action.diagnostic,
            action=action.name, description=action.description,
            component=action.component, predicted_raw=int(raw),
            calibration_k=round(k, 4), predicted=int(raw * k), basis=basis,
            precondition=why, risk=action.risk, reversible=action.reversible,
            cost_s=0.5,
        ))
    return out


def w_rev(c: "Candidate") -> float:
    return REVERSIBILITY_WEIGHT.get(c.reversible, 0.0)


def evaluate(candidates: list[Candidate], objective, config) -> list[Candidate]:
    """Score and rank. Returns the list sorted best-first, with rejections marked."""
    needed = max(1.0, objective.start_value - objective.target_value
                 if objective.direction == "decrease" else 1.0)
    remaining = max(0.0, objective.current_value - objective.target_value)

    for c in candidates:
        # A diagnostic frees nothing by design. Scoring it on predicted gain would
        # reject it every time, so knowledge is scored on being what this stage needs.
        if c.diagnostic:
            c.predicted = max(c.predicted, 1)
            c.sufficiency = 0.0
            c.score = round(1.0 + w_rev(c) - 0.7 * c.risk, 4)
            continue
        if c.predicted <= 0:
            c.rejected = "predicted gain is zero or negative"
            c.score = -1.0
            continue
        if REVERSIBILITY_WEIGHT.get(c.reversible, 0.0) <= 0.0:
            c.rejected = f"reversibility class {c.reversible!r} is not permitted in v0.1"
            c.score = -1.0
            continue

        # Expected gain, not promised gain. An action that has historically
        # under-delivered in situations like this one is discounted by exactly how
        # often it under-delivered - which is the point at which outcome -> belief ->
        # policy -> future decision is actually closed, rather than merely recorded.
        gain = min(1.0, c.predicted / needed) * c.reliability
        c.sufficiency = round(
            (min(1.0, c.predicted / remaining) if remaining > 0 else 1.0)
            * c.reliability, 4)
        rev = REVERSIBILITY_WEIGHT.get(c.reversible, 0.0)
        w = config.get("planning", {}) or {}
        c.score = round(
            w.get("w_gain", 1.0) * gain
            + w.get("w_sufficiency", 0.5) * c.sufficiency
            + w.get("w_reversible", 0.4) * rev
            - w.get("w_risk", 0.7) * c.risk
            - w.get("w_cost", 0.2) * min(1.0, c.cost_s / 10.0), 4)

    candidates.sort(key=lambda c: -c.score)
    return candidates


def select(candidates: list[Candidate]) -> Candidate | None:
    live = [c for c in candidates if c.rejected is None and c.score > 0]
    return live[0] if live else None


def summarize(candidates: list[Candidate], chosen: Candidate | None) -> str:
    """One line per candidate, for the decision record. Rejections included, because a
    decision is only auditable if you can see what was passed over."""
    parts = []
    for c in candidates:
        mark = "*" if chosen and c.action == chosen.action else " "
        if c.rejected:
            parts.append(f"{mark}{c.action}=rejected({c.rejected})")
        else:
            parts.append(f"{mark}{c.action}=score {c.score} "
                         f"predict {c.predicted}B (raw {c.predicted_raw} "
                         f"x k{c.calibration_k}) x rel{c.reliability}")
    return "; ".join(parts)
