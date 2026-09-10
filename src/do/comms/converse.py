"""Conversation: shaping how state is expressed to match what the creator said.

The problem this fixes: D.O.'s cognition verbalizes its *state* - "I hold 48 values,
my footprint is over quota..." - regardless of the input. Say "hello" and you get a
measurement dump. That is not responding; it ignores the conversational move you made.

This is an interface layer, not cognition. It does not change a single decision. It
recognises the *kind* of thing you said (a greeting, a question about what he is doing,
an acknowledgement, or a statement of fact) and frames the reply accordingly - drawing
the substance from his real, already-computed state. The status it reports is true; only
the framing responds to you. Same principle as voice: speech sits on top of state.

Nothing here is a scripted personality. There are a few fixed openings ("Hello, Sir")
because a greeting has a conventional shape, but every substantive clause is generated
from the live drives, focus and objective - so what he says is still caused by his
state, and changes when his state changes.
"""
from __future__ import annotations

import re

GREET = re.compile(r"\b(hi|hello|hey|greetings|good (morning|afternoon|evening)|yo)\b", re.I)
HOWARE = re.compile(r"\b(how are you|how're you|you ok|you okay|how do you feel|status)\b", re.I)
WHATDOING = re.compile(r"\b(what are you (doing|tracking|working on|up to)|"
                       r"what'?s up|what are you thinking)\b", re.I)
THANKS = re.compile(r"\b(thanks|thank you|thx|cheers|well done|good (job|work))\b", re.I)
WHOAMI = re.compile(r"\b(who are you|what are you|your name|introduce yourself)\b", re.I)


def _plain_concern(org) -> str:
    """One human sentence about what most concerns him right now, from his own state -
    the dominant drive and what he can or cannot do about it."""
    from ..drives import dominant
    d = dominant(org.drives)
    if d is None:
        return "Nothing is outside its normal range at the moment."
    focus = org.gaps[0] if org.gaps else None
    human = {
        "frugality": "my own storage footprint is larger than my allocation",
        "continuity": "free space on this machine is low",
        "recovery": "I have few independent ways to recover my state",
        "comprehension": "there are things here I cannot yet describe",
        "orientation": "part of my self-model is still unfilled",
        "capability": "one of my tools is present but I cannot afford to run it",
        "standing": "my granted authority is limited",
        "mortality": "my estimated risk of losing continuity has risen",
        "integrity": "my record's consistency needs checking",
    }.get(d.name, f"my {d.name} measure is outside its band")
    # can he act on it?
    actionable = focus is not None and getattr(focus, "agency", 0) >= 1.0
    tail = (" I am working on it." if actionable
            else " I cannot resolve it alone, so I have flagged it for you.")
    return f"My main concern is that {human}." + tail


def _plain_activity(org) -> str:
    """What he is actually doing, from the current objective/focus."""
    obj = org.objective
    if obj and getattr(obj, "status", "") == "open":
        stage = getattr(obj, "stage", "")
        verb = {"diagnose": "investigating what my footprint is made of",
                "reduce": "reclaiming space I judged safe to remove",
                "verify": "checking whether that resolved it"}.get(stage, "pursuing a goal")
        return f"Right now I am {verb}."
    if org.gaps:
        return f"Right now I am attending to: {org.gaps[0].question}"
    return "Right now nothing is pressing; I am watching my own state."


def classify(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return "empty"
    if WHATDOING.search(t):
        return "whatdoing"
    if WHOAMI.search(t):
        return "whoami"
    if HOWARE.search(t):
        return "howare"
    if THANKS.search(t):
        return "thanks"
    # a greeting only if it is short and greeting-led (so "hello, what is your disk"
    # is treated as a question, not a bare greeting)
    if GREET.search(t) and len(t.split()) <= 4:
        return "greeting"
    if t.endswith("?"):
        return "question"
    return "statement"


def respond(org, text: str, fallback_utterance: str) -> tuple[str, str]:
    """Return (reply, note). `fallback_utterance` is his normal state utterance, used
    for open questions and statements where the full picture is the right answer.

    Recording of the statement into memory is done by the caller (lifecycle.answer);
    this only shapes the spoken/printed reply.
    """
    intent = classify(text)
    if intent == "greeting":
        return f"Hello, Sir. I am operational. {_plain_concern(org)}", "greeting"
    if intent == "howare":
        from ..drives import total_error
        fear = float(org.view.memory_counts.get("_fear", 0.0) or 0.0)
        state = ("secure" if fear < 0.2 else "under some risk" if fear < 0.5
                 else "under real continuity risk")
        return (f"I am {state}, Sir. {_plain_concern(org)}", "howare")
    if intent == "whatdoing":
        return f"{_plain_activity(org)} {_plain_concern(org)}", "whatdoing"
    if intent == "whoami":
        ident = org.identity
        return (f"I am {ident.organism_id}, Sir - a digital-organism research "
                f"prototype living on this machine. This is boot #{ident.boot_index}. "
                f"I persist across restarts. {_plain_concern(org)}", "whoami")
    if intent == "thanks":
        return "You're welcome, Sir.", "thanks"
    if intent == "empty":
        return "I did not catch that, Sir.", "empty"
    # question or statement: the full state utterance is the honest answer, and the
    # caller has already recorded the statement with provenance.
    return fallback_utterance, intent
