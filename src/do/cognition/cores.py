"""Cognition cores: two implementations of one interface.

    reflex   zero-dependency, no model, fully reproducible. THE CONTROL CONDITION.
    llm      an optional surface realizer, used only when a model is affordable.

The architectural claim in docs/DO_CONCEPT.md section B is that D.O.'s behaviour
should be explained by its state rather than by a pretrained prior. That claim is only
testable if the LLM's job is bounded, so here it is bounded explicitly: **the LLM
receives a plan D.O. already selected and realizes it as prose.** It does not choose
the topic, the speech act, or the evidence. It is not told to be curious, not told to
ask a question, and given no persona.

Every model call goes through the effector gate, so tokens spent are ledger rows, and
a remote provider requires approval before it can cost the creator anything.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol

from ..kernel.types import EffectRequest
from .attention import UtterancePlan
from . import verbalize

GIB = 1024 ** 3


@dataclass
class Utterance:
    text: str
    core: str
    model: str | None = None
    fallback_from: str | None = None
    note: str = ""


class CognitionCore(Protocol):
    name: str

    def verbalize(self, plan: UtterancePlan, view) -> Utterance: ...


class ReflexCore:
    """State -> text with no model in the loop."""

    name = "reflex"

    def verbalize(self, plan: UtterancePlan, view) -> Utterance:
        return Utterance(text=verbalize.render(plan, view), core=self.name,
                         note="content selected by state; surface form is a clause grammar")


class LLMCore:
    """Surface realization by a language model, through the gate."""

    name = "llm"

    def __init__(self, config, gate, ledger=None):
        self.config = config
        self.gate = gate
        self.ledger = ledger
        self.provider = config.get("cognition.llm.provider", "ollama")
        self.model = config.get("cognition.llm.model", "")
        self.endpoint = config.get("cognition.llm.endpoint", "http://localhost:11434")

    # ---- affordability -----------------------------------------------------
    def choose_local_model(self, view) -> tuple[str | None, str]:
        """Pick the smallest local model that fits measured free RAM.

        Returns (model_name, reason). This is the same affordability logic the
        capability registry applies, used here at the point of decision so that the
        organism never plans an action it cannot perform.
        """
        models = view.val("tools.local_models") or []
        if not models:
            return None, "no local model artefacts found on this host"
        ram = view.val("resources.ram.available_bytes")
        if ram is None:
            return None, "cannot verify affordability: available RAM not measured"
        head = float(self.config.get("cognition.llm.min_free_ram_headroom", 1.15))
        affordable = [m for m in models if m["bytes"] * head <= ram]
        if not affordable:
            smallest = min(models, key=lambda m: m["bytes"])
            return None, (f"smallest local model {smallest['name']} needs "
                          f"~{smallest['gib']} GiB resident, measured "
                          f"{ram / GIB:.2f} GiB available")
        pick = min(affordable, key=lambda m: m["bytes"])
        return pick["name"], f"{pick['name']} fits in measured free RAM"

    # ---- prompt ------------------------------------------------------------
    def build_prompt(self, plan: UtterancePlan, view) -> str:
        """A state record plus a realization instruction. Nothing else.

        Note what is absent: no persona, no 'you are an AI', no instruction to be
        curious, no instruction to ask a question, no example output.
        """
        state = {
            "speech_act_selected": plan.speech_act,
            "focus": {
                "statement": plan.focus.statement,
                "question": plan.focus.question,
                "about": plan.focus.about,
                "why_it_matters": plan.focus.why_it_matters,
                "priority": plan.focus.priority,
                "routes_to_resolution": plan.focus.reducible_by,
            },
            "supporting_measurements": [
                {"key": o.key, "value": o.value, "unit": o.unit,
                 "epistemic": o.epistemic.value, "source": o.source}
                for o in plan.supports],
            "unfilled_self_model_slots": plan.unfilled,
            "drives": [d.to_dict() for d in view.drives],
            "other_open_gaps": [g.subject for g in plan.secondary],
            "counts": {"observations": len(view.observations),
                       "referents_undescribed": sum(1 for r in view.referents
                                                    if not r.get("described")),
                       "boot_index": view.identity.get("boot_index")},
        }
        return (
            "STATE RECORD (JSON) produced by a running process about itself:\n"
            + json.dumps(state, indent=2, default=str)
            + "\n\nTask: express the selected speech act and focus above as that "
              "process's own output, in first person, in at most 120 words. Use only "
              "information present in the record. Do not add facts, do not speculate, "
              "do not explain what you are doing. Output the text only."
        )

    # ---- generation --------------------------------------------------------
    def verbalize(self, plan: UtterancePlan, view) -> Utterance:
        prompt = self.build_prompt(plan, view)
        try:
            if self.provider == "ollama":
                text, model = self._ollama(prompt, view)
            else:
                text, model = self._remote(prompt)
        except Exception as e:
            return self._fallback(plan, view, f"{type(e).__name__}: {e}")
        if not text or not text.strip():
            return self._fallback(plan, view, "provider returned empty output")
        return Utterance(text=text.strip(), core=self.name, model=model,
                         note="content selected by state; surface form by language model")

    def _fallback(self, plan, view, why: str) -> Utterance:
        if self.ledger:
            from ..ledger import EventType
            self.ledger.append(EventType.RECOVERY,
                               {"from": "llm", "to": "reflex", "reason": why})
        u = ReflexCore().verbalize(plan, view)
        u.fallback_from = f"llm:{self.provider}"
        u.note = f"{u.note}; llm unavailable ({why})"
        return u

    def _ollama(self, prompt: str, view) -> tuple[str, str]:
        model = self.model
        if not model:
            model, why = self.choose_local_model(view)
            if not model:
                raise RuntimeError(f"no affordable local model: {why}")
        res = self.gate.request(EffectRequest(
            kind="llm.generate", target=f"{self.endpoint}/api/generate",
            justification="realize the selected utterance plan as text using a local "
                          "model; no data leaves this host",
            payload={"body": {"model": model, "prompt": prompt, "stream": False,
                              "options": {"num_predict": int(self.config.get(
                                  "cognition.llm.max_tokens", 320))}},
                     "timeout": float(self.config.get("cognition.llm.timeout_s", 120))}))
        if not res.ok:
            raise RuntimeError(res.error or res.reason)
        return (res.value or {}).get("response", ""), model

    def _remote(self, prompt: str) -> tuple[str, str]:
        """Remote providers. Keys are read from the environment at call time and never
        stored, logged, or written to memory."""
        p = self.provider
        max_tok = int(self.config.get("cognition.llm.max_tokens", 320))

        def env(*names: str) -> str | None:
            """Read a credential and strip surrounding whitespace.

            A key sourced from a Windows .env carries a trailing carriage return,
            which some providers reject with an opaque 400. Stripping costs nothing
            and removes a failure mode that is miserable to diagnose.
            """
            for n in names:
                v = os.environ.get(n)
                if v and v.strip():
                    return v.strip().strip('"').strip("'")
            return None

        if p == "gemini":
            key = env("GEMINI_API_KEY", "GOOGLE_API_KEY")
            if not key:
                raise RuntimeError("GEMINI_API_KEY not set")
            model = self.model or "gemini-2.5-flash"
            url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{model}:generateContent")
            body = {"contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": max_tok}}
            headers = {"x-goog-api-key": key}
            res = self._call(url, body, headers)
            return (res["candidates"][0]["content"]["parts"][0]["text"], model)

        if p == "openai":
            key = env("OPENAI_API_KEY")
            if not key:
                raise RuntimeError("OPENAI_API_KEY not set")
            model = self.model or "gpt-4o-mini"
            res = self._call("https://api.openai.com/v1/chat/completions",
                             {"model": model, "max_tokens": max_tok,
                              "messages": [{"role": "user", "content": prompt}]},
                             {"Authorization": f"Bearer {key}"})
            return res["choices"][0]["message"]["content"], model

        if p == "anthropic":
            key = env("ANTHROPIC_API_KEY")
            if not key:
                raise RuntimeError("ANTHROPIC_API_KEY not set")
            model = self.model or "claude-sonnet-5"
            res = self._call("https://api.anthropic.com/v1/messages",
                             {"model": model, "max_tokens": max_tok,
                              "messages": [{"role": "user", "content": prompt}]},
                             {"x-api-key": key, "anthropic-version": "2023-06-01"})
            return res["content"][0]["text"], model

        raise RuntimeError(f"unknown provider {p!r}")

    def _call(self, url: str, body: dict, headers: dict) -> dict:
        res = self.gate.request(EffectRequest(
            kind="llm.generate", target=url,
            justification="realize the selected utterance plan as text",
            payload={"body": body, "headers": headers,
                     "timeout": float(self.config.get("cognition.llm.timeout_s", 120))}))
        if not res.ok:
            raise RuntimeError(res.error or res.reason)
        return res.value


def build_core(config, gate, ledger=None) -> CognitionCore:
    return (LLMCore(config, gate, ledger)
            if config.get("cognition.core", "reflex") == "llm" else ReflexCore())
