"""The reflex verbalizer: turn an UtterancePlan into text, with no language model.

**Be precise about what this is.** The *content* of the utterance is fully determined
by state: which gap, which speech act, which supporting observations, which numbers.
The *surface form* is a clause grammar written by a human — me. So:

    content   = emergent (selected by measurement -> drive -> salience -> attention)
    surface   = templated (four clause slots, filled from data)

That is the honest description, and it is stated in the results rather than glossed
over. Its virtue is being the **control condition**: nothing in this module can
smuggle in a pretraining prior, so any variation across the perturbation matrix is
attributable to state and to nothing else.

No clause slot contains a question. Questions arrive from `Gap.question`, which
`gaps._phrase()` builds mechanically from the slot identifier.
"""
from __future__ import annotations

from ..kernel.types import Epistemic, Observation
from .attention import ASK, DECLARE, FLAG, REPORT, REQUEST, UtterancePlan

GIB = 1024 ** 3


def _fmt(o: Observation) -> str:
    v = o.value
    if isinstance(v, bool):
        return f"{o.key}={str(v).lower()}"
    if isinstance(v, float):
        if o.key.endswith("_ratio"):
            return f"{o.key}={v:.4f} ({v * 100:.1f}%)"
        return f"{o.key}={v:.4g}"
    if isinstance(v, int) and (o.unit == "bytes"):
        return f"{o.key}={v / GIB:.2f} GiB"
    if isinstance(v, (list, dict)):
        return f"{o.key}[{len(v)}]"
    return f"{o.key}={v}"


def _clause_grounding(plan: UtterancePlan, view) -> str:
    n_obs = sum(1 for o in view.observations.values() if o.is_known)
    n_unk = len(view.observations) - n_obs
    facts = "; ".join(_fmt(o) for o in plan.supports[:5])
    return (f"I hold {n_obs} values I measured this boot and {n_unk} I could not "
            f"establish. The measurements bearing on what I have selected: {facts}.")


def _clause_boundary(plan: UtterancePlan, view) -> str:
    filled, unfilled = view.filled_slots()
    undesc = sum(1 for r in view.referents if not r.get("described"))
    carried = len(view.carried_gaps)
    parts = [f"{len(unfilled)} of {len(filled) + len(unfilled)} slots my self-model "
             f"requires are empty ({', '.join(unfilled[:4])}"
             f"{', ...' if len(unfilled) > 4 else ''})"]
    if undesc:
        parts.append(f"{undesc} named things exist here that I cannot describe")
    if carried:
        parts.append(f"{carried} question(s) carried over unresolved from an earlier boot")
    return "; ".join(parts) + "."


def _clause_salience(plan: UtterancePlan) -> str:
    d = plan.dominant_drive
    if d is None:
        return ("No internal measure is outside its band, so nothing is pulling my "
                "attention more than anything else.")
    return (f"The internal measure furthest outside its band is {d.name}: "
            f"{d.value:.3f} against a target of {d.target:.2f} "
            f"(basis: {d.basis}).")


def _clause_act(plan: UtterancePlan, view) -> str:
    g = plan.focus
    act = plan.speech_act

    if act == ASK:
        route = g.reducible_by[0] if g.reducible_by else "no route known"
        return (f"{g.statement}. Of the {plan.notes.get('n_gaps', 0)} open gaps this "
                f"scored highest ({g.priority}), and the cheapest route I have to "
                f"closing it is: {route}. {g.question}")

    if act == FLAG:
        ev = ", ".join(f"{k}={v}" for k, v in (g.evidence or {}).items())
        return (f"{g.statement}. Evidence: {ev}. I am raising this rather than asking "
                f"anything else because it is the only measurement I took that sits "
                f"outside a band I compared it against. {g.question}")

    if act == REQUEST:
        return (f"{g.statement}. {g.why_it_matters}. {g.question}")

    if act == DECLARE:
        subs = "; ".join(s.subject for s in plan.secondary[:3])
        return (f"{g.statement}. Behind it: {subs}. I can state the shape of what I do "
                f"not know more precisely than I can state what I do know.")

    # REPORT
    return (f"{g.statement}. I have not acted on it. {g.question}")


def render(plan: UtterancePlan, view) -> str:
    """Assemble the utterance. Order is fixed; every value is measured."""
    return " ".join([
        _clause_grounding(plan, view),
        _clause_boundary(plan, view),
        _clause_salience(plan),
        _clause_act(plan, view),
    ])
