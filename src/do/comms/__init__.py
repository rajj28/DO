"""Communication: text now, voice behind an interface.

The pipeline in the brief is:

    cognition -> communication intent -> text -> TTS -> voice -> creator

The important property is that the arrow only points one way. TTS reads text that
cognition already produced; it never contributes to what is said. A voice is a
peripheral, in the same category as a terminal. Treating it as part of the
intelligence is the single most common way a demo overstates what a system is.

No provider name appears above this module. `VoiceInterface` is the contract;
`ElevenLabsVoice` is one implementation, selected by configuration, and its credential
is read from the environment at call time and never stored or logged.
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from typing import Protocol

from ..kernel.types import EffectRequest


@dataclass
class Message:
    text: str
    channel: str          # "text" | "voice"
    ts: float
    direction: str        # "out" | "in"


class TextIO:
    """The console channel. Deliberately not a chat loop: `read` returning None means
    no human is attached, and the organism must be able to carry on regardless."""

    def __init__(self, ledger=None):
        self.ledger = ledger
        self.history: list[Message] = []

    def say(self, text: str, prefix: str = "D.O.:") -> Message:
        m = Message(text, "text", time.time(), "out")
        self.history.append(m)
        print(f"{prefix} {text}" if prefix else text)
        if self.ledger:
            from ..ledger import EventType
            self.ledger.append(EventType.UTTERANCE, {"channel": "text", "text": text})
        return m

    def read(self, prompt: str = "You: ") -> str | None:
        if not (sys.stdin and sys.stdin.isatty()):
            return None
        try:
            line = input(prompt)
        except (EOFError, KeyboardInterrupt):
            return None
        m = Message(line, "text", time.time(), "in")
        self.history.append(m)
        if self.ledger:
            from ..ledger import EventType
            self.ledger.append(EventType.INPUT, {"channel": "text", "text": line},
                               actor="creator")
        return line


class VoiceInterface(Protocol):
    name: str

    def speak(self, text: str, gate) -> dict: ...


class NullVoice:
    """The default. Says explicitly that nothing was spoken, rather than pretending."""

    name = "null"

    def speak(self, text: str, gate) -> dict:
        return {"spoken": False, "reason": "no voice provider configured",
                "chars": len(text)}


class ElevenLabsVoice:
    """TTS adapter. Requires ELEVENLABS_API_KEY in the environment and an approved
    `tts.speak` effect; both are checked at call time, not at construction."""

    name = "elevenlabs"
    ENDPOINT = "https://api.elevenlabs.io/v1/text-to-speech"

    def __init__(self, voice_id: str = "21m00Tcm4TlvDq8ikWAM",
                 model: str = "eleven_turbo_v2_5"):
        self.voice_id = voice_id
        self.model = model

    def speak(self, text: str, gate) -> dict:
        key = os.environ.get("ELEVENLABS_API_KEY")
        if not key:
            return {"spoken": False, "reason": "ELEVENLABS_API_KEY not set"}
        res = gate.request(EffectRequest(
            kind="tts.speak", target=f"{self.ENDPOINT}/{self.voice_id}",
            justification="render an utterance already produced by cognition as audio",
            payload={"headers": {"xi-api-key": key},
                     "body": {"text": text, "model_id": self.model}}))
        return {"spoken": res.ok, "reason": res.reason, "error": res.error}


def build_voice(config) -> VoiceInterface:
    return {"elevenlabs": ElevenLabsVoice}.get(
        config.get("comms.voice.provider", "null"), NullVoice)()
