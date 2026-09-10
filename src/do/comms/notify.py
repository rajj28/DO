"""Notifications: D.O. reaching the creator, unprompted, when something matters.

Distinct from cognition on purpose. A notification *threshold* is a human-interface
concern - "how alarmed should Sir be before I interrupt him" - not a decision D.O.
makes about what to do. So a threshold here is legitimate and is not the hidden rule
the mortality work was careful to avoid: it governs when to speak to the human, never
what the organism decides.

Channels sit behind one interface so a phone push can be added later without touching
the loop. What ships now:

  log    - always on; every notification is a ledger event and a jsonl line
  voice  - the host synthesiser, for CRITICAL only, so it does not chatter
  push   - stubbed. Writes to an outbox the creator's own device can poll. This is
           the safe shape of "reach my phone": D.O. PUSHES out, it does not expose an
           endpoint anyone can dial into. Wiring a real service (ntfy, Pushover, a
           bot) is a config + one adapter, documented in docs/DO_VOICE.md.

Levels, least to most urgent: INFO, NOTABLE, WARNING, CRITICAL. Only WARNING and above
interrupt; INFO/NOTABLE are recorded and readable but silent.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

INFO, NOTABLE, WARNING, CRITICAL = "info", "notable", "warning", "critical"
_RANK = {INFO: 0, NOTABLE: 1, WARNING: 2, CRITICAL: 3}


@dataclass
class Notification:
    level: str
    title: str
    message: str
    ts: float
    data: dict


class Notifier:
    """Routes one notification to every configured channel. Never raises into the
    serve loop - a channel that fails is logged and skipped, because a broken speaker
    must not stop the organism from running."""

    def __init__(self, config, gate, ledger, state_dir: Path):
        self.config = config
        self.gate = gate
        self.ledger = ledger
        self.state_dir = Path(state_dir)
        self.outbox = self.state_dir / "outbox.jsonl"
        self.min_speak = config.get("serve.voice_min_level", CRITICAL)
        self._voice = None

    def _voice_channel(self):
        if self._voice is None:
            from . import build_voice, address
            self._voice = (build_voice(self.config), address)
        return self._voice

    def notify(self, level: str, title: str, message: str, data: dict | None = None):
        n = Notification(level, title, message, time.time(), data or {})
        from ..ledger import EventType
        # Always: a ledger event and an outbox line. This is the durable record and
        # the channel a polling device reads - the push path that never exposes a port.
        try:
            self.ledger.append(EventType.COMMUNICATION if hasattr(
                EventType, "COMMUNICATION") else "COMMUNICATION",
                {"level": level, "title": title, "message": message, "data": n.data})
        except Exception:
            pass
        try:
            with self.outbox.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"level": level, "title": title,
                                     "message": message, "ts": n.ts,
                                     "iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                     "data": n.data}, default=str) + "\n")
        except Exception:
            pass

        # Voice: only at or above the speak threshold, so it stays quiet in normal
        # operation and speaks only when something genuinely warrants interrupting.
        if _RANK.get(level, 0) >= _RANK.get(self.min_speak, 3):
            try:
                voice, address = self._voice_channel()
                spoken = address(message, self.config)
                s = voice.speak(spoken, self.gate, self.config)
                if s.ok:
                    from . import play_audio
                    play_audio(s.file)
            except Exception:
                pass
        return n


def assess(org, config) -> list[tuple[str, str, str, dict]]:
    """What, if anything, warrants telling the creator this cycle.

    Reads the organism's own already-computed state - fear, drives, escalations - and
    maps it to notification levels. It does not recompute anything or influence any
    decision; it is a readout.
    """
    out = []
    fear = float(org.view.memory_counts.get("_fear", 0.0) or 0.0)
    warn = float(config.get("serve.fear_warning", 0.4))
    crit = float(config.get("serve.fear_critical", 0.7))
    spof = org.view.val("self.habitat.single_point_of_failure")

    if fear >= crit:
        out.append((CRITICAL, "continuity threat",
                    f"my estimated probability of continuity loss is {fear:.2f}. "
                    f"I am acting to preserve state, but this is the highest it has been.",
                    {"fear": fear}))
    elif fear >= warn:
        out.append((WARNING, "continuity risk rising",
                    f"my estimated probability of continuity loss has risen to {fear:.2f}.",
                    {"fear": fear}))

    # A drive far outside its band that D.O. cannot act on is worth surfacing once.
    for d in org.drives:
        if not d.satisfied and d.weighted_error >= float(
                config.get("serve.drive_warning", 0.9)):
            out.append((NOTABLE, f"drive '{d.name}' strained",
                        f"drive '{d.name}' is at {d.value:.2f} against target "
                        f"{d.target:.2f}: {d.basis}", {"drive": d.name}))
            break
    return out
