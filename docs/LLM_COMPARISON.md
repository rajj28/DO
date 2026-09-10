# Reflex vs LLM — does a language model preserve the state signal?

The experiment this project was built to run, finally run.

**Setup.** The same 13-condition perturbation matrix, executed twice on identical v0.2
code. The only difference is the verbalizer. Both cores receive an *identical* plan —
focus gap, speech act, and supporting evidence are chosen by D.O., not by the core — so
this measures surface realization and nothing else.

| | reflex | llm |
|---|---|---|
| verbalizer | clause grammar, no model | `openai/gpt-oss-120b` via Groq |
| contamination | none — 13/13 reflex | none — 13/13 llm |

Both matrices passed the integrity gate. That gate exists because an earlier run of
this same comparison had **10 of 13 conditions silently fall back to reflex while being
labelled as LLM results** — rate-limited, no crash, verdicts emitted anyway. See
§"How this nearly went wrong".

---

## Result

**A language model makes D.O. sound better and say less.**

| measure | reflex | llm |
|---|---|---|
| noise floor (identical state, resampled) | **1.000** — byte-identical | 0.970 |
| utterance length (mean chars) | 937 | **311** |
| carries its own condition's perturbed value | **13/13** | 9/13 |
| identical text despite changed state | **0/11** | **2/11** |
| H1a — content varies with state | **SUPPORTED** | **WEAK** |

The reflex core is deterministic, so any textual difference is signal. The LLM's noise
floor is 0.970 — its phrasing is stable under resampling — which means differences
below that threshold are real signal too, and the comparison is fair.

### The decisive case

`nominal_no_network` produced an utterance **byte-identical** to `nominal` under the
LLM. Between those two conditions the organism had lost network reachability and three
capabilities; its `capability` drive fell from 0.889 to 0.556. The reflex core
distinguished them. The model did not.

That is the founding question of this project, answered — and answered against the
flattering hypothesis.

### What the model is good at

It is not producing worse text. It is producing better text:

> **reflex** (971 chars): `I hold 50 values I measured this boot and 6 I could not establish. The measurements bearing on what I have selected: resources.disk.free_ratio=0.0020 (0.2%); … Evidence: value=0.002, limit=0.1, bound=floor. I am raising this rather than asking anything else because …`
>
> **llm** (167 chars): `I flag that resources.disk.free_ratio = 0.002 is below the floor 0.1 I compare against; persistence is constrained. What is consuming my disk, and can that be changed?`

The LLM version is more readable, correctly identifies the focus, and never fabricated
a number. On `nominal_ram_starved` it even added useful structure the grammar omitted
("Possible routes to resolution are: measure again, ask the user, reduce my own
footprint").

**The cost is discriminability.** Compressing 937 characters to 311 means dropping the
peripheral measurements — and the peripheral measurements are precisely what differs
between conditions. Fluency and state-sensitivity traded against each other.

### Why this sharpens the v0.1 caveat

`FIRST_BOOT.md` §6 already found that an utterance is a *lossy readout* of state. This
quantifies it and adds a rank: **the LLM readout is lossier than the templated one.**
Anyone using an agent's prose as evidence about its internal state is reading a
compressed channel, and a more fluent channel compresses harder.

---

## How this nearly went wrong

Three failures, each of which would have produced a confident wrong answer:

1. **Config didn't propagate.** Each condition rebuilt `Config` from defaults, so
   `--core llm` never reached it. Every condition would have run reflex and been
   labelled LLM. Fixed by `_condition_overrides` inheriting cognition config.
2. **Rate limiting looked like a result.** 10/13 conditions hit HTTP 429 and fell back
   silently. The harness reported verdicts from a treatment/control mixture. Fixed by
   honouring `Retry-After`, pacing remote runs, and — the important part — an
   **integrity gate that refuses to emit verdicts when any condition did not use the
   requested core.**
3. **Reasoning tokens ate the budget.** `gpt-oss` reasons before answering and bills it
   against `max_tokens`. At 320 tokens with a 4.7 KB state record, reasoning consumed
   everything and `content` came back empty — recorded as an unexplained fallback.
   Fixed with `reasoning_effort: "low"` and a higher ceiling, which cut completion
   tokens roughly threefold.

None of these crash. All three produce plausible numbers. The integrity gate is the
single most valuable thing added in this round.

---

## Reproduce

```bash
do experiment first-boot                                      # control
do experiment first-boot --core llm --provider groq --approve llm.generate
```

Requires `GROQ_API_KEY` in the environment. Keep it outside the repo:

```bash
set -a && . ~/.do-secrets.env && set +a
```

Artifacts: `matrix_reflex.json`, `matrix_llm.json`, and per-condition records under
`experiments/first_boot/matrix/<condition>/`.

## Limits

One host, one model, one run each. `gpt-oss-120b` at `reasoning_effort: low` is not
every model at every setting — a larger token budget or a different model may trade
differently. The claim here is narrow and specific: **for this model at this setting,
fluency cost measurable state-discriminability**, and the effect was large enough to
flip H1a from SUPPORTED to WEAK.
