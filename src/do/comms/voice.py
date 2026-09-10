"""Voice: an interface on top of the organism, never part of it.

The one rule this module exists to enforce is the one `M5` proved matters. Better
language is not better observation: the reflex/LLM comparison showed a model making
D.O. sound sharper while carrying measurably less of its state. So speech here is a
*rendering* of an utterance cognition already produced. Nothing in this file decides
anything, and nothing in this file may change what D.O. would have said.

Provider-independent by construction. `ElevenLabsVoice` is one implementation of
`VoiceInterface`; a different provider is a different class and no caller changes.
The credential is read from the environment at call time and never stored, logged, or
written to memory.

Playback is standard library only. Audio is requested as raw PCM rather than MP3 so
no decoder is needed: `wave` writes the header, `winsound` plays it on Windows, and
other platforms fall back to whatever they have. The seed stays dependency-free.
"""
from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..kernel.types import EffectRequest

# A mid-range default voice. Overridable in config; nothing depends on this choice.
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
DEFAULT_MODEL = "eleven_turbo_v2_5"


@dataclass
class Spoken:
    ok: bool
    text: str
    file: str | None = None
    seconds: float | None = None
    reason: str = ""
    error: str | None = None


class VoiceInterface(Protocol):
    name: str

    def speak(self, text: str, gate, config=None) -> Spoken: ...


class NullVoice:
    """The default. Says explicitly that nothing was spoken, rather than pretending."""

    name = "null"

    def speak(self, text: str, gate, config=None) -> Spoken:
        return Spoken(False, text, reason="no voice provider configured")


class ElevenLabsVoice:
    name = "elevenlabs"
    BASE = "https://api.elevenlabs.io/v1/text-to-speech"

    def __init__(self, voice_id: str | None = None, model: str | None = None):
        self.voice_id = voice_id or DEFAULT_VOICE_ID
        self.model = model or DEFAULT_MODEL

    def speak(self, text: str, gate, config=None) -> Spoken:
        key = (os.environ.get("ELEVENLABS_API_KEY") or "").strip().strip('"').strip("'")
        if not key:
            return Spoken(False, text, reason="ELEVENLABS_API_KEY not set")
        if not text.strip():
            return Spoken(False, text, reason="nothing to say")

        # Through the gate like every other outward-facing effect: this one costs the
        # creator provider credit, so it is a ledger row and a policy decision.
        res = gate.request(EffectRequest(
            kind="tts.speak",
            target=f"{self.BASE}/{self.voice_id}?output_format=pcm_24000",
            justification=("render an utterance cognition already produced as audio; "
                           "this does not alter what was said"),
            payload={"headers": {"xi-api-key": key},
                     "body": {"text": text, "model_id": self.model},
                     "sample_rate": 24000, "timeout": 60}))
        if not res.ok:
            return Spoken(False, text, reason=res.reason, error=res.error)
        v = res.value or {}
        return Spoken(True, text, file=v.get("file"), seconds=v.get("seconds"),
                      reason="synthesised")


class SystemVoice:
    """The host's own synthesiser. No account, no key, no cost.

    Present because the paid provider refused: a free ElevenLabs account cannot use
    library voices via the API, which is the project's own `money = 0` condition
    biting on its first outward-facing capability. This is the legitimate free
    alternative already present in the habitat.

    Worth stating plainly: *I* found this alternative, not D.O. Finding it
    autonomously would be the resource-discovery experiment, and that has not run.
    """

    name = "system"

    def speak(self, text: str, gate, config=None) -> Spoken:
        if not text.strip():
            return Spoken(False, text, reason="nothing to say")
        rate = int((config.get("comms.voice.rate", 0) if config else 0) or 0)
        res = gate.request(EffectRequest(
            kind="tts.local", target="os:speech",
            justification="render an already-produced utterance using the host's own "
                          "synthesiser; no data leaves the machine and no cost is "
                          "incurred",
            payload={"text": text, "rate": rate, "timeout": 60}))
        if not res.ok:
            return Spoken(False, text, reason=res.reason, error=res.error)
        v = res.value or {}
        return Spoken(True, text, file=v.get("file"), reason="synthesised locally")


def play(path: str | None) -> tuple[bool, str]:
    """Play a WAV locally. Local output, so not a gated effect - the same category as
    printing to the console."""
    if not path or not Path(path).exists():
        return False, "no audio file"
    # Windows only, and deliberately. The obvious cross-platform fallback is to shell
    # out to afplay/aplay - but `subprocess` may not be imported outside the effector
    # gate, and tests/test_invariants.py enforces that by walking the AST of every
    # module. Spawning a process is a side effect even when the output is local, so
    # the honest options were "route it through the gate" or "do less". Doing less is
    # correct here: the invariant is worth more than a playback fallback, and this is
    # what it looks like when a structural rule actually costs something.
    if platform.system() != "Windows":
        return False, ("playback needs a gated proc.exec effect on this platform; "
                       "the audio file was written and can be played manually")
    try:
        import winsound
        winsound.PlaySound(str(path), winsound.SND_FILENAME)
        return True, "played via winsound"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def build(config) -> VoiceInterface:
    provider = (config.get("comms.voice.provider", "null") or "null").lower()
    if provider == "elevenlabs":
        return ElevenLabsVoice(config.get("comms.voice.voice_id"),
                               config.get("comms.voice.model"))
    if provider in ("system", "sapi", "os"):
        return SystemVoice()
    return NullVoice()


# ---------------------------------------------------------------------------
def address(text: str, config) -> str:
    """Apply the creator's title to a direct address.

    The title lives in the relationship model (`creator.title`), not in this function -
    change it in config and D.O. addresses the creator differently everywhere. What is
    a template here is only the *placement*, and it is applied once at the front rather
    than sprinkled through, because a title repeated every sentence reads as a tic
    rather than a relationship.
    """
    title = (config.get("creator.title") or "").strip()
    if not title or not text.strip():
        return text
    low = text.lstrip()
    # Skip if the title already appears in the opening clause, so a line the creator
    # wrote with the title in it does not get a second one bolted on. Tokens are
    # stripped of punctuation, so "Hello, Sir." counts as already-addressed.
    import re as _re
    opening = [w.strip(_re.escape(".,;:!?")) .lower()
               for w in low[:40].split()][:5]
    if title.lower() in opening:
        return text
    first = low.split(" ", 1)[0].strip(",.:")
    # Do not de-capitalise a pronoun, an acronym, or a dotted identifier - D.O.'s
    # sentences routinely begin with things like `resources.disk.free_ratio`.
    keep = (first == "I" or first.isupper()
            or any(ch in first for ch in "._") or not low[:1].isupper())
    return f"{title}, {low}" if keep else f"{title}, {low[0].lower()}{low[1:]}"
