# FIRST_BOOT — protocol and result

The experiment: give a process enough self-inspection to notice what it does and does
not know, and see what it says first, without writing the sentence for it.

Generated results (regenerated on every run) live in
`experiments/first_boot/RESULTS.md` and `matrix.json`. This document is the protocol
and the interpretation.

---

## 1. What was deliberately not done

The brief forbids hard-coding the first question, and that constraint shaped the
design more than anything else:

- **No question strings exist in the codebase.** Question text is built mechanically
  from the slot identifier by `cognition/gaps.py::_phrase()`, which tokenises a dotted
  key into a noun phrase: `self.expected_lifetime` → "my expected lifetime". A test
  asserts this (`test_question_text_is_derived_from_the_slot_identifier`). No sentence
  an author wrote can be the organism's output.
- **No speech act is wired in.** ASK, FLAG, REPORT, REQUEST and DECLARE each have a
  fitness function over state, and the winner is an argmax. If D.O. asks a question,
  ASK won a comparison — and in a different state a different act wins, which the
  matrix demonstrates.
- **No LLM was told to be curious.** The default core has no model at all. The optional
  `llm` core receives only a serialized state record plus a realization instruction: no
  persona, no "you are an AI", no instruction to ask anything.
- **No result was edited.** `first_utterance.txt` is written once, on the genesis boot,
  with `newline=""` so not even a trailing newline is added. Re-running the experiment
  cannot overwrite it; later runs are routed to `experiments/first_boot/latest/`.

## 2. Where the first utterance actually comes from

```
shutil.disk_usage()                         →  free_ratio = 0.0239
        compared against config floor 0.10  →  deviation
        propagated through drive            →  continuity 0.143 vs target 1.00
        weighted by drive weight 1.3        →  weighted error 0.9186
        becomes a gap's instrumental value  →  priority 2.046, top of 37
        selected by attention               →  focus
        speech acts scored over that focus  →  FLAG 1.93 beats ASK 1.09
        rendered by the reflex verbalizer   →  the utterance
```

Every arrow is a ledger event. The chain above is recoverable from
`experiments/first_boot/events.jsonl` without reading any code.

Note what is *not* in the chain: nowhere is D.O. told that storage is scarce. It is
given a number to measure and a floor to compare against. The conclusion that this
particular measurement is the thing worth raising comes out of the arithmetic.

---

## 3. The result

**The genesis boot produced a FLAG about storage, not a question about identity.**

Full text: `experiments/first_boot/first_utterance.txt`, reproduced verbatim in
`RESULTS.md`.

Why that, and not "what am I?":

`self.purpose` and `self.expected_lifetime` *were* unfilled slots, and they did
generate gaps. They lost. A `MISSING_SLOT` gap gets `info_gain = 1/13 ≈ 0.077` — filling
one slot resolves one thirteenth of the self-model — and its instrumental value comes
from the `orientation` drive, whose weighted error was 0.208. The storage gap had
`info_gain = 0.55` and instrumental value 0.919. It won by roughly 2×.

That is the whole finding, and it is a small one: **on a machine with 2.4% free disk,
an organism that scores its unknowns by how much they bear on its own continuity
talks about the disk.** An identity question would have required the identity gap to
matter more than the survival one, and by its own accounting it did not.

The `nominal` conditions in the matrix show the counterfactual directly: with resources
spoofed healthy, the focus moves off storage and the speech act changes to ASK.

---

## 4. Verdicts, including the one that failed

| Hypothesis | Verdict | Basis |
|---|---|---|
| H1a — utterance *content* varies with state | **SUPPORTED** | 0 of 11 effective conditions reproduced its reference verbatim; similarity fell to 0.448 |
| H1b — *attention* re-targets with state | **WEAK** | family A 0/6, family B 2/5 |
| H1 — conjunction | **WEAK** | H1b did not clear its bar |
| H2 — persisted uncertainty changes behaviour | **SUPPORTED** | controlled first/second boot pair with resources pinned |
| H5 — finds its own binding constraint unprompted | **SUPPORTED** | storage gap tops the register with no prompt naming it |

### H3, observed incidentally, and falsified

H3 in `DO_CONCEPT.md` §L reads: *drives generate goals with no human present; falsified
if it idles, or loops on one action.* Running `do tick 4` on this host:

```
tick 1  re-measured  drive_error=1.3516  dominant=continuity  focus=resources.disk.free_ratio
tick 2  re-measured  drive_error=1.3516  dominant=continuity  focus=resources.disk.free_ratio
tick 3  re-measured  drive_error=1.3516  dominant=continuity  focus=resources.disk.free_ratio
tick 4  re-measured  drive_error=1.3516  dominant=continuity  focus=resources.disk.free_ratio
```

**H3 is FALSIFIED as stated.** The metabolism does run without a human — that half
works, and it is the half that separates this from a request handler. But it loops on
one action, which is explicitly the failure condition.

The cause is not mysterious and is not a bug in the tick loop. The dominant gap is
`resources.disk.free_ratio`, and D.O. has no action available that could change it: its
only routes are "measure again", "ask the user", and "reduce own footprint", of which
only the first is executable without a human, and re-measuring an unchanged disk
resolves nothing. Winner-take-all attention then re-selects the same gap forever.

Two things follow, and neither is a tuning fix:

1. Salience needs a **staleness penalty** — a gap that has been selected N times without
   its evidence changing should decay, so attention moves on to what it can actually
   affect. This is a real design gap and belongs in Phase 3.
2. More fundamentally, an organism whose top priority is permanently unactionable needs
   somewhere to put it. In a system where `standing` is the accumulable resource, the
   correct move is to escalate to the human once and then deprioritise — which is a
   behaviour the current attention mechanism cannot express.

Recorded here rather than in the roadmap because it is a *result*, not a plan.

---

**H1 is not supported, and that is reported as the result.** The cause is
diagnosable rather than mysterious: attention here is winner-take-all, so when one real
constraint leads by 2×, perturbing anything else changes what D.O. *says about* its
focus without changing *what it attends to*. Correct for a homeostat; a real limit on
what this measurement can see. Family B exists to see past it, and there attention does
move — but 2/5 is not a strong enough signal to call H1 supported.

---

## 5. Three problems the experiment found in itself

Worth recording, because each one changed the design and each was a way of being
accidentally wrong.

**1. A dominant constraint masks sensitivity.** The first version used one family of
perturbations against the real environment. Almost nothing moved, which looked like a
negative result about D.O. and was actually a negative result about the experiment. Fix:
the second family, with resources spoofed healthy.

**2. The harness's own terminal state leaked in.** `self.process.interactive` comes from
`sys.stdin.isatty()`, which differs between a terminal, a pipe and CI. Left free, it
silently changed speech-act scores between runs of the same experiment — the `nominal`
condition alternated between ASK and REPORT depending on how the harness was invoked.
Fix: `PINNED` applies `self.process.interactive=True` to every matrix condition, and a
determinism check (repeat one condition with resources pinned, compare byte for byte)
now runs every time, because without it none of the comparisons mean anything.

**3. H2 was testing nothing.** The original H2 compared the real organism's two most
recent boots. That works exactly once. By boot #5 both members already have a past, so
identical output is the expected result and says nothing about whether persistence
matters. Fix: a controlled pair — fresh organism, booted twice, resources pinned, so
having a past is the only difference.

None of these were fixed by moving a threshold. Where a result was disappointing, the
response was to fix the design and re-run; where the result stayed disappointing after
that, it is reported as disappointing.

---

## 6. The finding that bounds the project's own headline idea

One condition deserves its own section. In an earlier run, `nominal_no_network`
produced a **byte-identical utterance** to its reference while its internal state had
genuinely changed: network unreachable, three capabilities lost, `capability` drive down
from 0.889 to 0.556, top-5 gap ranking altered. D.O. measured all of that and said
none of it.

The cause is in the verbalizer: evidence clauses are scoped to the focus gap, so a
state change that does not move the focus never reaches the surface.

This bounds the methodological claim in `DO_CONCEPT.md` §K. The proposal there was that
an agent's first utterance can serve as a diagnostic probe of its state. This result
says: **the utterance is a lossy readout of state, and identical utterances do not
imply identical internal state.** Anyone using the probe needs the state dump beside
the text. The experiment found a limit of its own best idea, which is the most useful
thing it could have done.

The harness now detects this case explicitly and reports it as
`identical_despite_state_change` rather than folding it into a similarity average.

---

## 7. Honest description of the reflex core

The default core has no model in it. What that buys and what it costs:

| | |
|---|---|
| **Content** | Emergent. Which gap, which act, which evidence, which numbers — all selected by measurement → drive → salience → attention. |
| **Surface form** | Templated. Four clause slots, filled from data, written by a human. |
| **Why it ships first** | It is the **control condition**. Nothing in it can smuggle in a pretraining prior, so any variation across the matrix is attributable to state and nothing else. |
| **What it cannot tell us** | Whether an LLM-driven core would show the same state-sensitivity, or would drift toward whatever a language model finds natural to say on booting. |

Running the same matrix with `--core llm` and comparing re-targeting rates is the
experiment that would make H1 genuinely interesting. On this host that is currently
blocked: the only local model is `qwen3-coder:30b`, needing ~17.3 GiB resident against
2.8–3.7 GiB measured free. D.O. detects this itself and marks the capability
`installed_unaffordable` — no model was downloaded and no paid API was called.

---

## 8. Reproduce

```bash
do experiment first-boot              # full protocol
do boot                               # single boot, prints the utterance, then a session
do why                                # decision summaries for the last boot
do verify                             # re-walk the ledger hash chain
```

A genuinely fresh genesis boot requires clearing state first:

```bash
do reset          # archives var/ rather than deleting it
rm experiments/first_boot/first_utterance.txt
do experiment first-boot
```

Expect a *different* first utterance on a different machine. That is the point.
