"""Attention: what to focus on, and what kind of thing to say about it.

Two selections happen here, and both are scored rather than scripted.

1. **Focus** — the highest-priority open gap. Priority already carries live drive
   error, so the environment's actual condition decides what D.O. attends to.

2. **Speech act** — each act has a fitness function over state, and the winner is the
   argmax. This matters for honesty about the experiment: D.O. is not wired to ask a
   question. If it asks, ASK won a comparison; if the machine were in a different
   state, FLAG or REPORT would win instead, and it would say a different kind of
   thing. The alternatives and their scores are written to the ledger.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..kernel.types import Epistemic, Namespace, Observation
from .gaps import Gap

ASK = "ASK"                # pose a question to the creator
FLAG = "FLAG"              # surface a measurement outside its band
REPORT = "REPORT"          # state what has been established
REQUEST = "REQUEST"        # ask for authority or resource
DECLARE = "DECLARE"        # state the shape of its own ignorance


@dataclass
class UtterancePlan:
    speech_act: str
    focus: Gap
    supports: list[Observation]
    dominant_drive: Any
    unfilled: list[str]
    secondary: list[Gap]
    act_scores: dict[str, float] = field(default_factory=dict)
    notes: dict = field(default_factory=dict)


def select_focus(gaps: list[Gap]) -> Gap | None:
    return gaps[0] if gaps else None


def score_speech_acts(view, focus: Gap, drives: list) -> dict[str, float]:
    """Fitness of each communicative act given the current state."""
    from ..drives import dominant as dom_drive

    interactive = bool(view.val("self.process.interactive"))
    _, unfilled = view.filled_slots()
    unknown_ratio = len(unfilled) / max(1, len(unfilled) + len(view.filled_slots()[0]))
    dom = dom_drive(drives)
    dom_err = dom.weighted_error if dom else 0.0
    denials = view.memory_counts.get("_denials", 0)

    # A threshold breach is the sharpest signal available: a measured value sitting
    # outside a band it was compared against.
    breach = 1.0 if focus.kind == "RESOURCE_THRESHOLD" else 0.0
    for g in view.carried_gaps:
        if g.get("kind") == "RESOURCE_THRESHOLD":
            breach = max(breach, 0.6)

    return {
        # asking is only worth it if someone is listening and the gap is answerable
        ASK: round(0.9 * focus.tractability * (1.0 if interactive else 0.2)
                   + 0.5 * focus.info_gain + 0.4 * focus.instrumental, 4),
        # flagging wins when something measured is out of band
        FLAG: round(1.2 * breach + 0.8 * dom_err, 4),
        # reporting scales with how much has actually been established
        REPORT: round(0.55 * (1.0 - unknown_ratio) + 0.2, 4),
        # requesting authority becomes rational once actions have been refused
        REQUEST: round(0.7 * min(1.0, denials / 3.0)
                       + 0.6 * (1.0 if focus.kind == "AUTHORITY_UNDEFINED" else 0.0), 4),
        # declaring ignorance wins when ignorance dominates the state
        DECLARE: round(0.85 * unknown_ratio + 0.3 * focus.instrumental, 4),
    }


def plan(view, gaps: list[Gap], drives: list, ledger=None) -> UtterancePlan | None:
    from ..drives import dominant as dom_drive
    from ..ledger import EventType

    focus = select_focus(gaps)
    if focus is None:
        return None

    scores = score_speech_acts(view, focus, drives)
    act = max(scores, key=lambda k: scores[k])
    dom = dom_drive(drives)
    _, unfilled = view.filled_slots()

    if ledger is not None:
        ledger.decision(
            decision=f"focus:{focus.kind}:{focus.subject}",
            reason=f"priority {focus.priority} = info {focus.info_gain} + instrumental "
                   f"{focus.instrumental} (drive '{_drive_of(focus)}') + tractability "
                   f"{focus.tractability}; next candidate "
                   f"{gaps[1].priority if len(gaps) > 1 else 'none'}",
            confidence=_confidence(gaps),
            alternatives=len(gaps),
            namespace=focus.about)
        ledger.decision(
            decision=f"speech_act:{act}",
            reason=f"argmax over {len(scores)} acts; "
                   + ", ".join(f"{k}={v}" for k, v in sorted(scores.items(),
                                                             key=lambda kv: -kv[1])),
            confidence=round(_margin(scores), 3),
            alternatives=len(scores))
        ledger.append(EventType.QUESTION, {
            "gap_id": focus.id, "question": focus.question, "about": focus.about,
            "priority": focus.priority})

    return UtterancePlan(
        speech_act=act,
        focus=focus,
        supports=_supports(view, focus, dom),
        dominant_drive=dom,
        unfilled=unfilled,
        secondary=[g for g in gaps[1:4]],
        act_scores=scores,
        notes={"n_gaps": len(gaps), "n_new": sum(1 for g in gaps if g.is_new)},
    )


def _drive_of(focus: Gap) -> str:
    from .gaps import KIND_TO_DRIVE
    return KIND_TO_DRIVE.get(focus.kind, "none")


def _confidence(gaps: list[Gap]) -> float:
    """Confidence in the focus choice = how far the winner clears the runner-up."""
    if len(gaps) < 2:
        return 0.5
    top, second = gaps[0].priority, gaps[1].priority
    if top <= 0:
        return 0.3
    return round(min(0.99, 0.5 + 0.5 * (top - second) / abs(top)), 3)


def _margin(scores: dict[str, float]) -> float:
    vals = sorted(scores.values(), reverse=True)
    if len(vals) < 2 or vals[0] <= 0:
        return 0.5
    return min(0.99, 0.5 + 0.5 * (vals[0] - vals[1]) / abs(vals[0]))


def _supports(view, focus: Gap, dom) -> list[Observation]:
    """Evidence to accompany the utterance.

    Selection is by relevance to the focus subject and to the dominant drive, then by
    how far a ratio sits from 0.5 (extreme measurements carry more information than
    middling ones). Nothing here is a fixed list of "interesting facts".
    """
    head = focus.subject.split(".")[0]
    scored: list[tuple[float, Observation]] = []
    for key, o in view.observations.items():
        if not o.is_known or o.epistemic is Epistemic.UNKNOWN:
            continue
        if isinstance(o.value, (list, dict)) and len(str(o.value)) > 120:
            continue
        s = 0.0
        if key.startswith(head):
            s += 0.6
        if dom is not None and any(t in (dom.basis or "") for t in (key,)):
            s += 0.8
        if key.endswith("_ratio") and isinstance(o.value, (int, float)):
            s += 0.5 + abs(0.5 - float(o.value))       # extremes are informative
        if o.epistemic is Epistemic.OBSERVED:
            s += 0.15
        if s > 0:
            scored.append((s, o))
    scored.sort(key=lambda t: -t[0])
    return [o for _, o in scored[:6]]
