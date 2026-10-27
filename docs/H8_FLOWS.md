# H8 — learning what an action is worth

**Question.** H4 showed D.O. learning what its actions *do*. It did not show that learning
improving what *happens*. Can a learner whose target is the drive itself, rather than its
own byte estimates, improve outcomes, and if so, is it the learning or the looking ahead?

**Answer, on 300 held-out simulated worlds × 10 seeds** (every verdict rule was code
before the test worlds were touched):

- A TD learner trained on the organism's own drive error has **41% lower** frugality
  error than H4's calibrated planner, **53% lower** than the live planner, and **20% lower**
  than the strongest one-step planner I could build from the live code.
- The gain is temporal credit assignment. The same learner with γ = 0 is **25% worse**;
  only γ = 0.9 reliably finds the action whose payoff is entirely in the future (94% of
  runs, around cycle 2, against 27% for γ = 0, which is chance).
- **Remove that one action and the advantage of looking ahead disappears**
  (−0.0003, CI −0.0007 to +0.0001).
- **A hand-written term beats the learner.** The planner with a flow term I wrote has 33%
  lower error than the learner (0.0037 vs 0.0056). I could only write that term after
  diagnosing why H4 failed. The learner found 44% of the same improvement with no hint.

Code: `src/do/sim/` (habitat, agents), `src/do/experiments/h8_flows.py` (protocol,
pre-registration, verdict rules). Data and figures: `experiments/h8_flows/`. Reproduce:
`do experiment h8` (about 6 minutes, standard library only).

---

## 1. Where the question came from

H4 ended PARTIAL. Calibrating `rotate_ledger` from its own outcomes moved it from rank 2
to rank 1 in the learning arm. The goal was met in neither arm. (The README review later
found the learning arm started about 24.5 KB larger, so even the rank change is
confounded with starting state.)

The journal put the miss down to greedy selection converging on the same set. The data
says something sharper. In every H4 run the actions freed about 210 KB while the footprint
fell by about 100 KB. **Bookkeeping grew about 23 KB per cycle and ate the rest.** The
binding problem was a *flow*.

The planner can only see *stocks*. It scores the bytes an action frees this cycle, and
`planner.evaluate` rejects anything that predicts zero before scoring it:

```python
if c.predicted <= 0:
    c.rejected = "predicted gain is zero or negative"
```

Calibration cannot repair that, because its error signal (actual against promised bytes,
this cycle) is just as one-step as the score it corrects. An action that cuts future
growth "under-delivers" every time it runs, by definition.

So there are three things a learner could learn, and H4 tested only the first:

| learner | learns | target |
|---|---|---|
| calibration (H4) | what an action **does** | bytes freed vs promised, this cycle |
| TD, γ = 0 | what an action does to the **next** measurement | next cycle's drive error |
| TD, γ = 0.9 | what an action is **worth** | discounted future drive error |

## 2. Why a simulation

`DO_CONCEPT.md` §I ranks the learning signal as the problem most likely to kill the
project, and recommends a simulated world with dense feedback before anything ambitious
(`ROADMAP.md` phase 9). H4's ten episodes on the live host took 72 seconds. A learner of
values needs thousands of episodes.

`sim/habitat.py` simulates one drive (frugality), the footprint it measures, and the
actions that move it. The parameter ranges bracket what the live host measured: a 72 KB
experiment matrix, 6 KB of bytecode, about 23 KB of bookkeeping per cycle, and a
compression correction of k = 1.74 (about 7.7×) against the 2.0× prior.

- **Stocks**: experiment matrices, bytecode, stale snapshots, the sqlite freelist and the
  live ledger, with the live registry's applicability rules and promises.
- **Flows**: every cycle appends ledger and memory bytes, whatever was chosen. Growth is
  drawn log-uniformly from 2.5 to 36 KB per cycle, so slow and fast habitats are equally
  represented.
- **Regrowth**: `__pycache__` comes back within one to three cycles of being cleared.
- **The flow action** `consolidate_bookkeeping` records unchanged observations as deltas.
  It cuts ledger growth to 20–60% from the next cycle on, and frees nothing now. **It is not
  in the live registry.** It exists here to test whether a learner can find value that a
  one-step score cannot represent.

**The reward is not designed for the experiment.** It is minus the frugality drive's
weighted error, computed by the live `Drive` class with the live config (target 0.5,
deadband 0.2, weight 1.2).

## 3. The agents

All of them see only `Habitat.observe()`: totals, components, last cycle's growth, and
each applicable action's own promise. The true compression ratio, the consolidation cut,
the regrowth delay and the defragmentation bonus are never observable. A test walks the
agents module's AST and fails if it names any of them.

| agent | what it is |
|---|---|
| `planner` | `cognition/planner.py`'s `evaluate` and `select`, unmodified, on candidates built from the promises. Reactive like the live loop: no objective while the drive is in band. |
| `planner+cal` | plus H4's calibration update, k ← (1−α)k + α·actual/promised |
| `planner+cal always` | acting every cycle. This is the strongest one-step planner I could build from the live code. |
| `planner+cal+flow always` | plus a hand-written score for the flow action: last cycle's ledger growth × a guessed 50% cut × the 6-cycle objective deadline from config |
| `td(0)`, `td(0.9)` | linear Q-learning over 78 binary features of the observation (ten active per state), α = 0.05, ε 0.3 → 0.02 over 4,000 training runs of 16 cycles |
| `random` | uniform over applicable actions |

Two details matter for the reading:

- A time limit is not a terminal state, so the learner bootstraps through cycle 16
  (Pardo et al. 2018). It has no clock feature.
- An untrained TD agent breaks ties randomly, so **S0 is exactly the random agent**
  (identical to the last digit, same seeds). That is why S0 sits an order of magnitude
  above everything else.

## 4. Protocol and pre-registration

The protocol is `DO_CONCEPT.md` §C, unchanged.

- **Worlds.** Train 0–1999, validate 50000–50199, test 100000–100299. Disjointness is a
  gate, and so is a check that no test world was ever sampled in training.
- **Measures.** S0 is measured before any experience, S1 after it with learning frozen,
  and S0′ after the learned state is wiped with the code kept. S0′ must equal S0 exactly,
  and it does.
- **Noise.** Ten independent learner seeds. Comparisons use a paired bootstrap over test
  worlds (4,000 resamples), and the high- vs low-growth split uses a stratified one.
- **Gates.** Seven gates must all pass before any verdict is printed: pools disjoint,
  observation contract, reward is the live drive, baseline is the live planner,
  S0 == S0′, no test world in training, and a deterministic replay of seed 0.

**What a validation pilot decided, before test.** It ran on 200 validation worlds with
one to three seeds.

1. **A confound in my own habitat.** In the first version consolidation cut growth in the
   same cycle it was chosen, so a γ = 0 learner could see part of its value immediately.
   That would have blurred exactly the distinction H8 exists to make. Consolidation now
   takes effect from the next cycle. A unit test pins that its immediate reward equals
   WAIT's.
2. **Step size.** α was chosen from {0.05, 0.1, 0.2}.
3. **Training budget.** 12,000 training runs did worse than 4,000 (0.0068 vs 0.0055). This
   is consistent with the known instability of Q-learning with function approximation.
   The budget was fixed at 4,000 and the instability is reported, not tuned away.
4. **The comparators and predictions** were refined from what the pilot showed. Those
   pilot numbers are recorded in the harness docstring so the predictions can be checked
   against them.

**The test worlds were evaluated three times, with identical numbers.** After the first
run I corrected a background figure in the habitat's docstrings: a compression ratio I
had quoted from an inconsistent earlier note. I then made the recorded code hash ignore
line endings, so that it verifies on any OS. No hypothesis, rule or code path changed.
Every number reproduced exactly, down to the learners' weight fingerprints, and
`results.json` carries the hashes of the files that produced it.

## 5. Results

Mean frugality error per cycle on 300 unseen worlds (lower is better). The 95% CI is
across 10 seeds.

| agent | error / cycle | 95% CI | cycles in band | low growth | high growth | uses flow action |
|---|---|---|---|---|---|---|
| `td(0.9)` | **0.0056** | 0.0051–0.0060 | 91% | 0.0010 | 0.0106 | 94% |
| `td(0)` | 0.0074 | 0.0069–0.0080 | 87% | 0.0012 | 0.0144 | 27% |
| `planner+cal+flow always` | **0.0037** | 0.0036–0.0039 | 92% | 0.0015 | 0.0062 | 84% |
| `planner+cal always` | 0.0070 | 0.0068–0.0071 | 89% | 0.0015 | 0.0130 | 0% |
| `planner+cal` (H4) | 0.0094 | 0.0092–0.0095 | 76% | 0.0023 | 0.0172 | 0% |
| `planner` (live) | 0.0119 | — | 75% | 0.0045 | 0.0201 | 0% |
| `td(0.9)` before experience = `random` | 0.0652 | 0.0632–0.0672 | 63% | 0.0473 | 0.0852 | 97% |

| | hypothesis | verdict | evidence (paired difference, 95% CI) |
|---|---|---|---|
| H8a | learning happened | **SUPPORTED** | S0 − S1 = +0.0597 [+0.0563, +0.0630]; S0 == S0′ |
| H8b | learned values beat H4's mechanism on outcomes | **SUPPORTED** | vs planner+cal +0.0038 [+0.0030, +0.0046]; vs planner+cal always +0.0014 [+0.0007, +0.0022] |
| H8c | it is temporal credit assignment | **SUPPORTED** | td(0) − td(0.9) = +0.0019 [+0.0013, +0.0026]; flow action 94% vs 27% |
| H8d | the gain lives where flows dominate | **SUPPORTED** | gap high − low growth = +0.0036 [+0.0024, +0.0052] |
| H8e | without the flow action, the gain goes | **SUPPORTED** | gap +0.0019 with it, −0.0003 [−0.0007, +0.0001] without |
| H8f | hand-written term vs learner | **HAND-WRITTEN TERM BETTER** | −0.0018 [−0.0034, −0.0004] |

![learning curve](../experiments/h8_flows/learning_curve.svg)

![ablation](../experiments/h8_flows/ablation.svg)

Per 16-cycle run, td(0.9) waits 5.7 times, rotates the ledger 3.9 times, vacuums 3.1 times
and consolidates once, at cycle 2.2 on average. The calibrated planner that acts every
cycle clears bytecode 7.6 times a run. That is the regrowth trap: it always wins the
one-step score when nothing bigger is available, and it buys a cycle or two at most.

## 6. Reading it honestly

**What it shows.** In this habitat, learning from the organism's own drive signal changes
outcomes, which H4's calibration could not do. The ablation pins down where the gain
comes from. Learning per se buys little: γ = 0 is roughly the calibrated planner that acts
every cycle (0.0074 vs 0.0070). Propagating value through time is what pays, and only
because one action's payoff lies entirely in the future. Remove that action and γ = 0.9
is no better than γ = 0, and slightly worse than the one-step planner (0.0076 vs 0.0070).

**What it does not show.**

- **The world is mine.** I wrote the habitat after diagnosing H4, so it contains the
  structure I expected to matter. Its ranges are anchored to measurements, but the
  existence of a pure-flow action is my design. The honest claim is conditional: when such
  an action exists, a learner can find it and a one-step score cannot.
- **Hand-engineering won** (H8f). Knowing the missing term beats learning it, here. The
  argument for learning is not that it beats a designer who already knows the answer. It
  is that it needs no one to know. That is the argument the next experiments have to make
  on structure I did not anticipate.
- **The learner is small and unstable**: linear features I chose, constant step size, and
  worse results with more training. A decaying step size or a gradient-TD method is the
  obvious fix and has not been tried.
- **It is not the live organism.** `consolidate_bookkeeping` does not exist in the live
  registry, and nothing here has run on the real ledger.
- **One drive.** No trade-offs between drives were tested.

**What would falsify the reading.** If adding delta-encoded observations to the live
registry and training the same learner on the live organism's own stream does not reduce
its drive error relative to the calibrated planner, then the effect is a property of my
habitat, not of D.O.

## 7. Next

1. **Sim to live.** Implement delta-encoded observations as a real action, then run the
   learner on the live organism's stream with the same S0/S1/S0′ protocol.
2. **Acting through the model (brain milestone B4).** The brain already predicts its
   worlds in bits. Choosing actions by imagining their consequences with it would turn
   H8's model-free value learning into model-based learning. That is the comparison that
   matters for whether the brain is worth having.
3. **A habitat I did not write.** Procedurally generated actions whose stock and flow
   effects are drawn at random, so that neither I nor a hand-written term knows which
   ones matter. That is the test H8f says learning has to pass.
