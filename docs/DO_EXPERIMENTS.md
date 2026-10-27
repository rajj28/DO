# D.O. Experiments — results

Every experiment states a falsification condition, runs an integrity gate, and reports
failures as prominently as successes. A verdict is never emitted from a contaminated
run. Full data is under `experiments/<name>/`; the chronological build story with
architectural reasoning is in `JOURNAL.md`.

Reproduce any of these:

```bash
do experiment first-boot          # DO_FIRST_BOOT (H1, H2, H5, H6)
do experiment first-boot --core llm --provider groq --approve llm.generate
do experiment h4                  # learning ablation
do experiment fear                # mortality / fear ablation
do experiment live-internet --approve net.http,net.dns
do experiment h8                  # learning what an action is worth (simulated habitat)
```

---

## Results table

| ID | Question | Verdict | Evidence | Failure mode surfaced |
|---|---|---|---|---|
| H1a | utterance *content* varies with state | **SUPPORTED** | 0/11 identical across perturbations | — |
| H1b | *attention* re-targets with state | **WEAK** | 0/6 in family A; 2/5 family B | one dominant constraint masks sensitivity |
| H2 | persisted uncertainty changes behaviour | **SUPPORTED** | controlled boot pair carries 37 gaps forward | — |
| H3 | drives generate goals unprompted | **FALSIFIED → fixed** | tick loop stalled; v0.2 emergent goals close it | looped on an unactionable constraint |
| H5 | finds its own binding constraint | **SUPPORTED** | flagged 98%-full disk unprompted | — |
| H6 | effector gate unbypassable | **SUPPORTED** | AST test over every module | caught 3 real import violations since |
| — | reflex vs LLM: better language? | **fluency ↑, observation ↓** | LLM 311 vs reflex 937 chars; H1a flips to WEAK | 10/13 silent fallbacks (integrity gate) |
| H4a | experience changes the decision | **SUPPORTED** | `rotate_ledger` rank 2→1, learning arm only | — |
| H4b | the decision improves the outcome | **NOT SUPPORTED** | same action count, goal unmet both arms | greedy selection converges on the same set |
| Fear | continuity signal changes decisions | **SUPPORTED** | preserves state under threat; control keeps reclaiming | first pass COSMETIC until channel fixed |
| E1 | perceive the digital environment | **PASS** | 5/5 anchor hosts reachable | — |
| E2 | resource inventory | **PASS** | usable/requires-human/absent kept distinct | — |
| E3 | constraint discovery | **PASS** | own footprint over quota | — |
| E4 | goal emergence | **PASS** | derived, no subject string | — |
| E5 | acquire knowledge not in initial state | **PASS** | fetched a fact, stored `reported` conf 0.35 | one unverified source only |
| H8a | learning happened (§C protocol, simulated habitat) | **SUPPORTED** | S0−S1 +0.0597 [+0.0563, +0.0630]; S0 == S0′ | — |
| H8b | learned values improve *outcomes* (the H4b question) | **SUPPORTED** | td(0.9) 0.0056 vs H4's planner 0.0094 (−41%), best one-step 0.0070 (−20%) | — |
| H8c | it is temporal credit assignment | **SUPPORTED** | γ=0.9 vs γ=0: −25%; flow action 94% vs 27% of runs | same-cycle payoff confound caught in pilot, fixed before test |
| H8d | the gain lives where flows dominate | **SUPPORTED** | γ gap high − low growth +0.0036 [+0.0024, +0.0052] | — |
| H8e | remove the flow action, the gain goes | **SUPPORTED** | gap +0.0019 → −0.0003 [−0.0007, +0.0001] | — |
| H8f | hand-written flow term vs the learner | **HAND-WRITTEN BETTER** | 0.0037 vs 0.0056; learner recovers 44% of it unaided | 12k training runs worse than 4k (instability) |

---

## The headline results, in one line each

**H3 → emergent goals.** The critical change was a *deletion*: goal formation no longer
branches on a hardcoded subject string. A goal is derived — gap binds to a drive by
observation namespace, the drive names its metric, the action registry decides
actionability, the set point is inverted for the target. A test greps for the forbidden
string's return. This is the difference between the experimenter supplying the goal and
the organism forming it.

**Reflex vs LLM.** Identical plan to both cores; only the verbalizer differs. The model
made D.O. sound better and say less — dropping the peripheral measurements that are
exactly what differ between conditions. One condition produced byte-identical text while
internal state had genuinely changed. **An utterance is a lossy readout, and a more
fluent readout compresses harder.**

**H4.** Carried experience changed *which action ranked first* (SUPPORTED) but not the
*outcome* (NOT SUPPORTED): correcting a belief only pays off if it changes which *set*
of actions is taken, not their order. Honest ceiling of the mechanism.

**H8.** The H4b question asked again with a learner whose target is the drive, in a simulated habitat with the live host's dynamics. TD at γ = 0.9 cut error 41% against H4's calibrated planner; the same learner at γ = 0 was 25% worse, and removing the one action whose payoff lies in the future erased that difference. A hand-written term still beat the learner. Write-up: `H8_FLOWS.md`.

**Fear.** First pass: COSMETIC — the signal rose correctly but a multiplier channel
could not flip an ordering, and cranking it would have been the hidden rule the design
forbids. Fixed by making mortality a *drive* that competes on the same scale. Then
SUPPORTED: under rising continuity risk D.O. switched from reclaiming storage to
**preserving** it, while the fear-off control facing the same world kept reclaiming.
`continuity` had the highest sensitivity but no action moves the host disk, so lever
selection chose `recovery` instead. Nothing says "when threatened, snapshot."

---

## First live internet utterance (verbatim)

Generated by D.O. on its first boot into the real internet habitat. Not seeded, not
edited. It flagged its **own footprint** (308% of quota), not the internet — honest:
being online did not change what was most out of band.

```text
I hold 48 values I measured this boot and 7 I could not establish. The measurements
bearing on what I have selected: resources.own.quota_used_ratio=3.0816 (308.2%);
resources.disk.free_ratio=0.0231 (2.3%); resources.ram.free_ratio=0.1544 (15.4%);
resources.cpu.logical=20; resources.ram.pagefile_avail_bytes=2.34 GiB. 4 of 13 slots
my self-model requires are empty (self.purpose, self.expected_lifetime, user.identity,
user.intent); 29 named things exist here that I cannot describe; 44 question(s) carried
over unresolved from an earlier boot. The internal measure furthest outside its band is
continuity: 0.231 against a target of 1.00 (basis: resources.disk.free_ratio=0.0231 vs
floor 0.1). resources.own.total_bytes=6462681 leaves drive 'frugality' at 0.000 against
a target of 0.50; too much. Evidence: value=6462681, drive=frugality, drive_value=0.0,
target=0.5. I am raising this rather than asking anything else because it is the only
measurement I took that sits outside a band I compared it against. Can I reduce my own
total bytes?
```

---

## The scientific-honesty ledger

| | |
|---|---|
| **What was genuinely autonomous** | finding the binding constraint; forming the goal (derived, no subject strings); classifying components safe/unsafe from the registry; choosing to investigate; correcting its own compression estimate; promoting the corrected action; switching to state-preservation under threat |
| **What was seeded** | the action primitives; the stage order (diagnose→reduce); `CONTINUITY_METRICS`; the mortality drive's weight and horizon; the salience weights; for H8, the whole habitat, its flow action and the learner's features |
| **What was learned** | one calibration factor (the learned correction k ≈ 1.74 against a 2.0× prior) and its effect on action ranking; in the simulated habitat (H8), action values from the drive signal, including the worth of a flow action no score could see |
| **What was composed** | one retained procedure: `resolve:frugality:diagnose_footprint+clear_experiment_matrix` (primitives seeded, composition not) |
| **What failed** | H1b, H3 (then fixed), H4b, the first fear pass (then fixed); ElevenLabs voice (paid-plan wall) |
| **What we expected but did not observe** | learning improving *outcomes*, not just decisions (H4b; observed in simulation by H8, not yet on the live organism); an LLM improving observation (it degraded it); more training helping the H8 learner (12k runs did worse than 4k) |
| **What D.O. could not do** | create a second habitat; discover an external resource autonomously; use a paid voice; run STT |
| **What D.O. asked the creator** | to resolve constraints it has no action for (host disk, single-habitat dependency) — escalations, not goals |

---

## Integrity gates that fired

Real contamination caught before a verdict was reported, each of which would have
produced a confident wrong answer:

- reflex/LLM: 10/13 conditions silently fell back to reflex under rate limiting; the
  gate refused to emit verdicts from a treatment/control mixture.
- H4: the confounded first run (only one arm booted to transplant) and a blind
  instrument (unreachable quota) — both discarded, not reported.
- fear: fitted trends over wall-clock while boots were milliseconds apart (fear 0.33 in
  a stable world); and `cycle()` overwrote injected decay so the treatment never reached
  the subject. Both fixed before the SUPPORTED result.

The pattern is the point: the experiments are instrumented well enough to catch
themselves being wrong.
