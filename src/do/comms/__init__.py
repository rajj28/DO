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


from .voice import (VoiceInterface, NullVoice, ElevenLabsVoice, SystemVoice, Spoken,  # noqa: E402
                    address, build as build_voice, play as play_audio)

from .converse import respond as converse_respond, classify as classify_intent  # noqa: E402
