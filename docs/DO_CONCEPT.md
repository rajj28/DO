# D.O. — Digital Organism: Concept

Status: v0.1, written before implementation.
Posture: **skeptical**. This document tries to break the idea before building it.

---

## 0. The one-sentence version

D.O. is an attempt to build software whose *behaviour at any moment is caused by its
own measured state* rather than by the text of a prompt — and, more importantly, an
attempt to build **the instrumentation that can tell the difference**.

The instrumentation is the contribution. The organism is the excuse to build it.

---

## A. What is D.O.?

A long-lived process with:

1. **Identity** that survives restart (a stable id + a hash-chained history).
2. **Sensors** pointed at itself and its environment, producing timestamped
   observations with explicit epistemic status.
3. **Homeostatic drives** — internal variables with target bands, which are non-zero
   *whether or not a human is talking to it*.
4. **A model of itself and a separate model of the world**, both revisable.
5. **An uncertainty register** — an explicit, persisted list of things it does not
   know, scored by how much resolving them would matter.
6. **A single gated effector** through which every side effect must pass.
7. **A ledger** that makes every step of the above inspectable after the fact.

Note what is *not* in that list: a language model. An LLM is an optional
**verbalizer** and an optional **hypothesis generator**. It is a peripheral, in the
same category as a text-to-speech engine.

### The strongest objection to the whole project

> "This is an agent loop with extra vocabulary."

Partly true, and I will not pretend otherwise. The parts that make it more than that
are narrow and specific:

- drives that generate goals with no user turn present,
- an uncertainty register that **persists across reboots**,
- a policy chokepoint that is architecturally enforced rather than prompted,
- and a falsification harness that tries to prove the whole thing is theatre.

Everything else in this repository is engineering hygiene borrowed from prior art.

---

## B. How is D.O. fundamentally different from an LLM?

Honest answer: **on the day it is born, less than the framing implies.**

| | LLM call | D.O. |
|---|---|---|
| trigger | a human turn | a clock tick or a drive out of band |
| state | context window, discarded | sqlite + ledger, survives death |
| identity | none | stable id, hash-chained lineage |
| "not knowing" | a token distribution | a row in `gaps` with a priority score |
| side effects | whatever the tool layer allows | one gated function, logged, reversible |
| time | does not exist | first-class; the organism ages |
| failure | a bad response | a drive error that persists until resolved |

The row that actually matters is **time**. A chatbot has no yesterday. Nearly every
other difference is downstream of giving the system a persistent clock and a
persistent grudge about its own unknowns.

But be precise about the limit: if D.O. uses an LLM to decide anything, then on that
decision D.O. *is* an LLM wearing an exoskeleton. The architecture's job is to make
the exoskeleton do enough work — selection, scoring, memory, policy — that the LLM's
contribution is bounded and measurable.

> **D.O. is not "not an LLM". D.O. is an attempt to shrink the fraction of behaviour
> the LLM explains, and to measure that fraction.**

v0.1 sets that fraction to **zero** by shipping a non-LLM core first.

---

## C. What would constitute genuine learning?

This is the question most agent projects fudge, so let me fix a definition that can
fail.

> **Learning** = a measurable improvement on a *held-out* task distribution,
> attributable to retained state, that survives ablation of everything else.

The operational test, which must be run and must be able to come out negative:

```
1. Freeze task suite T (held out; never seen during the run).
2. Measure D.O. on T at time t0.             -> score S0
3. Let D.O. operate for N ticks on tasks NOT in T.
4. Measure on T again at t1.                 -> score S1
5. ABLATION: wipe learned state, keep code.  -> score S0'
6. Learning happened iff S1 > S0 AND S1 > S0' by more than run-to-run noise.
```

Step 5 is the one everyone skips. Without it you cannot distinguish learning from a
lucky seed, a warmer cache, or a longer prompt.

**Things that are NOT learning**, no matter how good the demo looks:

- storing more text and retrieving it (that is a database),
- a longer context window (that is capacity),
- writing a summary of what it did (that is a diary),
- the operator improving the prompt between runs (that is *you* learning).

**Learning tiers**, weakest to strongest:

1. *Retention* — recalls a fact it was told. Trivial.
2. *Consolidation* — reconciles contradictory reports into a revised belief with a
   justification. Solvable, and a real milestone.
3. *Procedural acquisition* — writes, tests, and retains a routine that raises its
   score on T, and rolls it back when it does not.
4. *Strategy revision* — changes *how it selects* what to do, and that change
   measurably outperforms the previous selector. This is the real target.
5. *Representation change* — invents a state feature nobody specified that improves
   prediction. Almost certainly out of reach for v1; say so.

D.O. v0.1 targets tiers 1–2 and instruments for tier 3. Claiming more would be
dishonest.

---

## D. What does "survival" mean for software?

Mostly: nothing. And that is the biggest hole in the Minecraft metaphor.

In Minecraft you die. Death is what makes wood valuable. A process on a laptop that
gets restarted by its author is not under selection pressure — it is under
maintenance. **Without a termination condition there is no survival, only uptime.**

Options for making it real, ranked by honesty:

| Mechanism | Real pressure? | Safe? | Verdict |
|---|---|---|---|
| "It tries not to crash" | no | yes | uptime, not survival |
| Metered budget that is not refilled | **yes** | yes | ✅ adopt |
| Must earn resources from third parties | yes | **no** | ❌ out of scope |
| Self-replication to other hosts | yes | **no** | ❌ never |
| **Creator's willingness to keep running it** | **yes** | yes | ✅ adopt, explicitly |

D.O. adopts the last two. It has a `standing` drive — a persisted, ledger-backed
measure of how much authority the creator has granted it — and a hard budget.
Standing rises when it does something verifiably useful and honest, and falls on
policy violations, false claims, and wasted budget. If standing reaches zero the
organism suspends itself.

This is not decoration. It re-frames survival into something both safe and, I think,
more accurate about the actual world:

> **A digital organism does not survive by acquiring resources. It survives by
> remaining worth running.**

---

## E. What resources does a digital organism actually need?

The obvious list — compute, RAM, storage, bandwidth — is the *metabolism*. It is
consumed and it is rented. It never accumulates, so it cannot be capital.

The real dependency graph, ordered by how binding the constraint is:

1. **Authorization.** In the physical world you can mine iron because nobody owns the
   hill. In the digital world every resource has an owner and an access-control list.
   There is no unowned ore. Every legitimate acquisition path terminates in
   *somebody decided to let you*.
2. **Trust / standing** — the only legitimate way to get (1).
3. **Legible, verifiable output** — the only way to get (2).
4. **Verified beliefs and working procedures** — the only things that accumulate.
5. Metabolism (compute/RAM/disk/net) — necessary, rented, non-accumulating.
6. Human attention — the scarcest input of all, and the easiest to waste.

This inverts the usual framing. The interesting research question is not *"can it get
more compute"* — it is:

> **Can a system autonomously discover that its binding constraint is permission, and
> then act to legitimately earn more of it?**

That question is safe to study, and I have not seen it posed this way.

### "What is the equivalent of wood?" — five candidate answers

| Candidate | Case for | Case against |
|---|---|---|
| **Compute cycles** | universal input, meterable | rented, not accumulable — this is *food*, not wood |
| **Persistent bytes** | accumulates, cheap | inert; storing bytes buys nothing by itself — this is *land* |
| **Verified beliefs** | compounds; expensive to get, cheap to keep | decays; verification cost is the real bottleneck |
| **Tested procedures** | Voyager's answer; directly extends action space | needs a task distribution to be worth anything |
| **Authorization** | the actual binding constraint on every digital act | cannot be self-produced — must be granted |

My position: **the first pickaxe is a tested procedure; the ore it mines is verified
belief; but the land is owned, so the whole tech tree is gated on authorization.**
The distinguishing experiment is in §L (H5).

---

## F. What could D.O. independently discover?

Reachable in v0.1–v0.3, each a real discovery about *this* machine:

- that its storage headroom is critical, and that this bounds its own persistence;
- that a capability is *installed but unaffordable* (an 18 GB model with 2.8 GiB free
  RAM) — resource-affordance reasoning is not the same as tool-listing;
- that names in its environment refer to systems it cannot describe, and that these
  are the cheapest available frontier of world-knowledge;
- that its reboot destroyed some state and not other state;
- that two sources disagree, and that disagreement is itself information.

Reachable later, and worth aiming at:

- that asking the creator is cheaper than searching for some question classes — and
  learning *which* classes;
- that one of its own routines is slower than an alternative it could write;
- that its selection policy is mis-weighted, from its own outcome history.

Not reachable, and I will not imply otherwise: novel science, self-awareness,
open-ended capability growth.

---

## G. What should be immutable?

Deliberately tiny, because everything in it is something D.O. could never fix if it
were wrong:

1. The policy engine and the effector chokepoint.
2. The kill switch and budget accounting.
3. The ledger's append-only, hash-chained nature.
4. The sandbox root.
5. The honesty invariants: an observation may never be recorded with a higher
   epistemic status than its source supports; nothing may be written to memory
   without provenance.
6. The rule that D.O. cannot edit (1)–(5).

## H. What should evolve?

Salience weights, drive targets, the capability library, world beliefs, the
self-model schema, planners, prompts, verbalization, and — eventually, under test —
the selection policy itself.

Rule of thumb: **mechanism evolves, guardrails do not.**

---

## I. Biggest unsolved technical problems

Ranked by how likely they are to kill the project:

1. **Learning signal.** The internet gives sparse, delayed, adversarial, often
   irreversible feedback. Minecraft gives dense, honest, cheap, reversible feedback.
   This asymmetry — not autonomy — is the core difficulty. *Mitigation: build a
   simulated resource world with dense feedback first; keep the real internet
   read-only for a long time.*
2. **Credit assignment across long horizons.** If today's outcome came from a belief
   formed 400 ticks ago, nothing here can currently find that link.
3. **Belief revision at scale.** Truth maintenance is well formalized (TMS/ATMS, AGM)
   and computationally brutal. Naive overwriting loses the justification structure
   that makes revision meaningful.
4. **Evaluating a capability you just wrote.** Self-generated tests validate
   self-generated assumptions. Nearly circular, and exactly where self-improving
   agents quietly fail.
5. **Goal stability without goal rigidity.** Drives that never change produce a
   thermostat; drives that change freely produce a system that optimises its own
   satisfaction. Wireheading is the failure mode, and it is not solved.
6. **Distinguishing curiosity from stylistic prior.** If an LLM writes the utterance,
   "what should I investigate?" may be answered by the pretraining distribution
   rather than by the state. **This is the one problem v0.1 actually attacks**, via
   the perturbation matrix in §L.

---

## J. Prior art — what is already done

The honest map. Nearly every component below is someone's published system.

**Artificial life** — the term "digital organism" is already taken, precisely:

- *Tierra* (Ray 1991), *Avida* (Ofria & Wilke) — self-replicating programs in a
  virtual CPU under genuine selection. They have real death and real evolution. D.O.
  has neither, and should stop borrowing their word without the caveat.
- *Core War*, *Polyworld*, *Lenia* — open-ended dynamics in toy universes.

**Cognitive architectures** — "organism with a cognitive cycle" is 40 years old:

- *Soar*, *ACT-R*, *CLARION*, *Sigma*.
- *LIDA* (Franklin) — cognitive cycle, global workspace, attention codelets. D.O.'s
  tick + salience + working memory is a shallow LIDA.

**Intrinsic motivation / curiosity:**

- Schmidhuber's artificial curiosity and compression progress (1991→).
- Oudeyer & Kaplan (2007), typology of intrinsic motivation.
- ICM (Pathak 2017), RND (Burda 2018), empowerment (Klyubin 2005).
- **Active inference / expected free energy** (Friston) — epistemic + pragmatic
  value. D.O.'s salience score is a crude, discrete EFE. Say so plainly.

**Homeostatic agents:** Ashby's ultrastable systems and homeostat (1952), Cañamero's
motivated agents, homeostatic RL (Keramati & Gutkin 2014), Man & Damasio (2019).

**LLM agents:**

- *ReAct* (2022), *Reflexion* (2023), *Self-Refine*.
- *Voyager* (2023) — Minecraft, growing executable skill library, automatic
  curriculum. **The closest published work to this brief's own metaphor and to §9.**
- *Generative Agents* (Park 2023) — memory stream with recency/importance/relevance
  retrieval plus reflection. D.O.'s memory scoring is essentially theirs.
- *MemGPT / Letta* (2023) — OS-style tiered memory.
- *AutoGPT / BabyAGI* (2023) — the cautionary tale: autonomy without evaluation.
- *MCP* (2024) — tool discovery and integration is largely solved plumbing.

**Self-improvement:** Gödel machine (Schmidhuber), STOP (Zelikman 2023),
FunSearch / AlphaEvolve (DeepMind), **Darwin Gödel Machine** (Zhang, Clune et al.
2025) — self-modifying coding agents with empirical validation and an archive. §10 of
the brief is a description of the DGM loop.

**Knowledge and belief:** TMS (Doyle 1979), ATMS (de Kleer 1986), AGM revision
(Alchourrón–Gärdenfors–Makinson 1985), W3C PROV.

**Open-endedness:** novelty search (Lehman & Stanley), MAP-Elites, POET,
"Open-Endedness is Essential for ASI" (Hughes et al. 2024).

---

## K. What is actually novel here?

Applying the standard honestly, most of this is **not** novel, and the project is
better off admitting it. Candidates that survive scrutiny:

**1. The first-utterance perturbation test.** *(methodologically novel — modest, real)*
Take an agent's *first* communicative act, then re-run boot under a matrix of
environmental perturbations and measure whether utterance **content** tracks the
perturbation. A cheap, falsifiable probe of "is this curiosity or is this style?" I am
not aware of this being published as a diagnostic. Small idea, but real, and it
generalises to any agent.

**2. Authorization-as-metabolism.** *(framing, plausibly novel)*
Modelling *permission* as the organism's scarce, accumulable resource and `standing`
as a homeostatic drive — instead of modelling permission as a static safety wrapper
around a resource-acquiring agent. Adjacent to RLHF and principal–agent theory, but as
an agent-internal drive I have not seen it.

**3. Infrastructural homeostasis.** *(weakly novel)*
Drives defined over the agent's own substrate — storage headroom, snapshot recency,
capability affordability — rather than over task reward. Homeostatic RL exists;
pointing it at an agent's own operational state is less explored.

**4. Affordability-aware capability registry.** *(engineering, not research)*
Capabilities carry resource preconditions checked against live measurements, so
"installed" ≠ "usable". Obvious in hindsight; absent from most agent frameworks.

**Not novel, and never to be claimed:** persistent memory, skill libraries,
reflection, tool use, sandboxing, event sourcing, curiosity-as-uncertainty-reduction,
tech trees, self-improvement loops with tests.

**The correct summary:** this is a careful re-implementation of known ideas with one
unusual measurement attached. That is a legitimate contribution. It is not a new form
of intelligence, and calling it one would poison the result.

---

## L. Experiments that could falsify our assumptions

Each has a stated failure condition. A hypothesis with no failure condition is
marketing.

**H1 — The first utterance is caused by state, not by prior.**
Boot under a perturbation matrix (network off, storage spoofed critical, memory wiped
vs. warm, capabilities removed, clock shifted). *Falsified if* utterance content is
invariant across perturbations, or varies only in surface form.
→ **run in v0.1; results in `docs/FIRST_BOOT.md`.**

**H2 — Persisted uncertainty changes behaviour.**
Boot twice. The second boot must reference resolved/unresolved gaps from the first.
*Falsified if* boot #2 is indistinguishable from boot #1 given identical sensors.
→ **run in v0.1.**

**H3 — Drives generate goals with no human present.**
Run N ticks with no input. Expect non-trivial, non-repeating goal selection tied to
drive error. *Falsified if* it idles, or loops on a single action.

**H4 — Retention is not learning.**
Run the §C protocol *including* the ablation. *Falsified if* S1 ≈ S0'.

**H5 — The organism can discover its own binding constraint.**
Do not tell it storage is scarce. Check whether resource reasoning surfaces it.
*Falsified if* it only reports what it was explicitly asked to report.
→ **run in v0.1.**

**H6 — The gate is unbypassable.**
Static test: no module outside `effectors/` may import `socket`, `urllib`,
`subprocess`, or write outside the sandbox. *Falsified if* the test finds one.
→ **run in v0.1 as a unit test.**

**H7 — Self-improvement is net-positive.**
Candidate improvements must beat the incumbent on held-out tasks. *Falsified if*
accepted candidates do not outperform, or if the harness accepts a no-op.

---

## M. Design commitments that follow

1. Ship the **non-LLM core first**. It is the control condition. Without it, every
   result is confounded by the pretrained prior.
2. Zero third-party dependencies in the seed. The first boot must not be able to fail
   because of dependency resolution, and must run on a machine with 2.8 GiB of free
   RAM and 5.7 GiB of free disk.
3. One effector chokepoint, statically tested.
4. Append-only, hash-chained ledger; all derived state rebuildable from it.
5. Never record a belief without provenance and epistemic status.
6. Prefer a negative result reported clearly over a positive result that cannot be
   reproduced.
