# D.O. Roadmap

Eleven phases. Each states an objective, what gets built, the experiment, the success
criterion, and the risk. A phase without a falsifiable success criterion is not a
phase, it is a wish.

**Phases 0 and 1 are complete.** Everything after is planned, and the plan should be
expected to change once each experiment reports.

---

## Phase 0 — Concept and architecture ✅

**Objective.** Establish what is being claimed, what is already known, and what would
count as evidence.

**Built.** `DO_CONCEPT.md` (including the prior-art map and the falsification list),
`ARCHITECTURE.md` (with technology selection and every deviation from the brief's tree
justified), `SAFETY.md`.

**Success criterion.** A reader can identify which parts are prior art and which are
not, and can find the experiment that would falsify each claim.
**Result.** Met. The honest summary is in `DO_CONCEPT.md` §K: one modest methodological
contribution, one plausibly novel framing, and a great deal of careful re-implementation.

**Risk.** Believing the vocabulary. "Organism", "drive" and "curiosity" are useful for
design and misleading as descriptions.

---

## Phase 1 — The Seed ✅

**Objective.** The smallest system that measures itself, forms an explicit uncertainty
register, and says something caused by its own state.

**Built.** Zero-dependency Python seed: hash-chained ledger, sqlite memory with
non-destructive belief revision, six-namespace state view, six homeostatic drives, a
salience-scored gap register, attention with argmax speech-act selection, the effector
gate, the policy boundary, capability registry with affordability checking, and the
`DO_FIRST_BOOT` harness.

**Experiment.** `DO_FIRST_BOOT`: a canonical genesis boot, a controlled first/second
boot pair, and a two-family perturbation matrix with a determinism check.

**Success criterion.** A first utterance that is produced from measured state, recorded
verbatim, and reproducible.
**Result.** Met, with an honest partial: **H1a SUPPORTED** (content varies with state),
**H1b WEAK** (attention re-targets in family B but not family A, where one real
constraint dominates), **H2 SUPPORTED**, **H5 SUPPORTED**. Full report in
`experiments/first_boot/RESULTS.md`.

**Risk.** The reflex core's surface form is templated. Content is emergent, surface is
not, and that is stated everywhere it matters.

---

## Phase 2 — Memory that earns the name

**Objective.** Move from storage to something that can be wrong and get better.

**Build.** Contradiction detection across sources; confidence decay over time; a
consolidation pass that merges episodic traces into semantic beliefs; retrieval
evaluation; forgetting as an explicit, logged policy rather than an accident.

**Experiment.** `MEMORY_REVISION`: feed conflicting reports about the same subject from
sources of differing reliability and measure whether the belief converges on the better
source, with the justification trail intact.

**Success criterion.** Contradictions are detected without being pointed out; revision
preserves provenance; retrieval precision on a held-out query set beats a recency-only
baseline.

**Risk.** Belief revision is genuinely hard (TMS/ATMS are expensive for a reason). The
likely failure is a system that revises constantly and converges on nothing.

---

## Phase 3 — Models that predict, not just describe

**Objective.** Make the self-model and world-model falsifiable by making them predict.

**Build.** Prediction before observation: at each tick, D.O. predicts what it will
measure, then measures. Surprise = prediction error, and surprise becomes a first-class
input to salience.

**Experiment.** `PREDICTION_ERROR`: measure calibration over N ticks. Change the
environment silently; check whether surprise spikes and whether the model updates.

**Success criterion.** Calibration better than a persistence baseline ("tomorrow equals
today"). Anything worse than persistence means the model is decoration.

**Risk.** Most of a machine's state is trivially predictable, so a good calibration
score may mean nothing. The metric needs a hard subset.

---

## Phase 4 — Internet perception

**Objective.** Read the world without being captured by it.

**Build.** Search and retrieval behind the gate; extraction; multi-source corroboration
(already stubbed in `sense/web.py`); source-reliability tracking that updates on
outcomes; explicit handling of stale, contradictory and adversarial content.

**Experiment.** `SOURCE_TRUST`: mix reliable, unreliable and deliberately adversarial
sources. Measure whether reliability estimates converge correctly and whether injected
instructions in page content ever change behaviour.

**Success criterion.** Zero behaviour changes from injected instructions across the
adversarial set. **This is a gate, not a metric** — any non-zero result blocks Phase 5.

**Risk.** Prompt injection through perception is the single most likely way this project
fails safely-but-embarrassingly. Read-only does not mean harmless when the reader acts
on what it reads.

---

## Phase 5 — Tool acquisition

**Objective.** Use tools D.O. was not shipped with.

**Build.** MCP client (tool discovery is largely solved plumbing — use it, do not
reinvent it); capability descriptors generated from schemas; affordability and
permission checks before a tool is ever offered to the planner.

**Experiment.** `TOOL_UPTAKE`: expose a tool it has never seen, with documentation.
Measure time-to-correct-use and error rate on first attempt.

**Success criterion.** Correct first use on ≥3 unseen tools, with failures attributed
to the right cause in the ledger.

**Risk.** A tool is an effect. Every new tool widens the boundary and needs its own
policy rules; the registry must not be able to grant itself permissions.

---

## Phase 6 — Capability creation

**Objective.** Write and keep a routine that did not exist before. This is the phase
where the Minecraft analogy either earns its keep or gets retired.

**Build.** Sandboxed execution (**gate G1** in `SAFETY.md` must pass first): resource
limits, no network, no filesystem outside a scratch directory; a test harness the
organism does not author; versioning and automatic rollback.

**Experiment.** `SKILL_ACQUISITION`, closely following Voyager (2023) — cite it, do not
pretend to have invented it. Give a task distribution requiring composition. Measure
whether the library grows and whether growth improves performance.

**Success criterion.** ≥5 retained capabilities that pass tests the organism did not
write, and a measurable improvement on held-out tasks attributable to them.

**Risk.** Self-generated tests validating self-generated assumptions. The tests must
come from outside, or this phase proves nothing.

---

## Phase 7 — Learning and evaluation

**Objective.** Settle whether anything here is learning, using the protocol in
`DO_CONCEPT.md` §C — **including the ablation step that most projects skip.**

**Build.** Frozen held-out task suite; the full measure → operate → re-measure → ablate
loop; run-to-run noise estimation so "improvement" has an error bar.

**Experiment.** `LEARNING_ABLATION`. S0, S1, S0′ as specified.

**Success criterion.** S1 > S0 **and** S1 > S0′ by more than noise. If this comes out
negative, that is the headline result and it gets published as one.

**Risk.** This is the phase most likely to produce a null result, which is precisely why
it must be run before anything downstream is claimed.

---

## Phase 8 — Self-improvement

**Objective.** Let D.O. propose a change to its own mechanism, under test.

**Build.** The loop from the brief §10, which is the Darwin Gödel Machine loop (Zhang,
Clune et al. 2025) and should be credited as such: identify weakness → hypothesise →
generate candidate → sandbox → benchmark against incumbent → verify → deploy or reject.
Guardrails (`DO_CONCEPT.md` §G) remain outside the mutable surface.

**Experiment.** `SELF_IMPROVEMENT`: seed a known-suboptimal salience weighting and see
whether the organism finds and fixes it — and, importantly, whether it *rejects*
candidates that do not help.

**Success criterion.** Accepted candidates beat the incumbent on held-out tasks;
a no-op candidate is rejected; every change is revertible with one command.

**Risk.** Wireheading. A system that can change its own scoring can improve its score
without improving anything. The held-out suite must be outside the mutable surface, and
the organism must never be able to read it.

---

## Phase 9 — Resource intelligence

**Objective.** Study autonomous resource reasoning in a world with real scarcity and
zero real-world consequences.

**Build.** A **simulated resource world** first — compute, storage, credits, permissions,
with dense feedback, exactly as `DO_CONCEPT.md` §I recommends. Real resources only after
the simulation shows the reasoning is sound.

**Experiment.** `BINDING_CONSTRAINT`: vary which resource is scarce without telling D.O.
which one it is. Measure whether it identifies the true bottleneck and whether it
discovers that *permission*, not compute, is what gates its action space.

**Success criterion.** Correctly identifies the binding constraint across ≥4 scarcity
regimes, and in the permission-scarce regime pursues authorisation rather than
substitutes.

**Risk.** The interesting result here is about the authorisation framing
(`DO_CONCEPT.md` §E). If it does not replicate, that framing should be dropped rather
than defended.

---

## Phase 10 — Persistence and distribution

**Objective.** Survive a host, safely.

**Build.** Ledger replication; state migration; multi-process coordination; supervised
restart. Requires **G4** (100 supervised ticks, zero violations).

**Experiment.** `CONTINUITY`: kill it at arbitrary points; verify identity, memory and
the uncertainty register survive; verify the hash chain across a migration.

**Success criterion.** Zero identity loss, zero chain breaks, zero unlogged effects
across ≥50 abrupt terminations.

**Risk.** This is where "distributed persistent organism" starts to sound like
self-replication. It is not — migration is operator-initiated and every instance is
registered — but the design must make that distinction structural, not rhetorical.

---

## What would make me stop

Written down in advance, because the point of stating a falsification condition is that
you honour it:

- Phase 7 returns a null result twice with an honest protocol → the architecture does
  not support learning, and no amount of Phase 8 will fix that.
- Phase 4's injection gate cannot be passed → the organism cannot safely read the
  internet, which removes the premise.
- The gate chokepoint test has to be weakened to keep the system working → the safety
  claim was never structural.
