# D.O.'s Brain — design, critique, and first results

Status: **B1 and B2 run; one open problem stated plainly (hidden causes).**
Code: `src/do/brain/`. Experiments: `do experiment brain`, `do experiment brain-memory`.
Tests: `tests/test_brain.py`.

The request was a brain with no vector index and no retrieval step, one that is actually
powerful and avoids traditional methods unless they are necessary. This document records
what was built, what my own first design got wrong, what the experiments say, and where
the design is still weak.

---

## 1. What was wrong with the first proposal

The first proposal was an "organs" design: ACT-R activation over a graph, Rescorla–Wagner
prediction edges, a K=7 global workspace, TD(λ) for actions, episodic nodes, a sleep
phase that chunks co-firing nodes, and four named neuromodulators. Taken apart:

| # | Drawback | Why it matters | What replaced it |
|---|---|---|---|
| 1 | Seven mechanisms, seven learning rules, **no shared objective** | Results cannot be attributed and nothing says whether a change helped. Tuning becomes a hyperparameter soup. | **One objective: bits.** Every mechanism is paid for in the code length of D.O.'s own life. |
| 2 | **Hebbian association edges** learn co-occurrence | With many variables almost all co-occurrence is coincidence, and edges grow O(n²). | **Rent.** Structure exists only while it saves more bits than it costs to remember (MDL, per unit, online). |
| 3 | **Pairwise edges** | They cannot represent "A matters only when B is true" (AND, XOR, conditional effects). Measured below: v1 is *worse than counting frequencies* in the XOR world. | **Conjunctive units**, grown on demand. |
| 4 | Structure grows by **co-firing** | It finds correlations, not the causes of surprise. | **Born from surprise**, recruited by **contrastive episodic recall**. |
| 5 | **TD value learning** | It needs thousands of rewards, and D.O. gets very few. | Learn from **dense prediction error** on every variable at every tick. Action selection will plan through the predictive model (B4, not built yet). |
| 6 | K=7 workspace with **hand-weighted competition** | It brings back the hand-set salience weights the brain was meant to remove. | Deferred. Attention should be "spend compute where code length is high", in the same currency. |
| 7 | **Four neuromodulators** = four knobs | Each knob has its own knobs. | Replaced by statistics derived per unit: **rupture detection**, where a unit compares its own recent and long-run loss. |
| 8 | Logging every percept for replay | The ledger grows, and D.O.'s binding constraint is disk. | **Memory as residual.** The life is stored as the arithmetic code of what the brain failed to predict, and replayed by re-running the brain. |
| 9 | Tested only on the real machine | Little data, slow, and no ground truth. | **Synthetic worlds with known hidden structure** and an oracle bound first, then the real machine. |

---

## 2. The architecture

```
             frame(t), action(t)             history: 3 ticks of symbols "var=value@lag"
                    │
        ┌───────────▼────────────┐
        │   active units         │   unit = (target, conjunctive context, counts, weight)
        │   for each target      │   root unit (empty context) = base rate, never dies
        └───────────┬────────────┘
                    │  p(x) ∝ exp( Σ_u w_u · log p_u(x) )        log-linear pooling
                    ▼
            prediction of frame(t+1)  ──►  code length  −log2 p(actual)   ◄── THE objective
                    │
     ┌──────────────┼──────────────────────────────────────────────────┐
     │ learn        │ every active unit: counts += outcome; w += η·∂(code length)
     │ pay          │ every active unit: earns its exact leave-one-out bits
     │ rent         │ unpaid units: charged their MDL cost per activation and per tick
     │ rupture      │ a unit whose recent loss jumps above its long-run loss forgets
     │ grow         │ surprise > 0.3 bits → contrastive recall → new conjunctive unit
     │ generalize   │ paid-off unit tries itself with one condition dropped
     │ die          │ unpaid with negative balance, or paid off but recently harmful
     └─────────────────────────────────────────────────────────────────┘
                    │
            residual memory: arithmetic-code each value with p → the life, in bytes
```

### 2.1 One objective

Prediction is compression. A unit, a weight or a whole mechanism is good exactly when
D.O.'s life costs fewer bits to describe with it than without it. That currency is what
lets every mechanism below be ablated and measured.

### 2.2 Units

A unit is a context of 1 to 3 symbols, e.g. `("disk=0@0", "snap_age=3@0")`. It is
attached to one target variable and holds KT-style counts of what that target did next
whenever the context was true. There are no embeddings and no similarity search. A unit
is either active (its context holds now) or it is not.

### 2.3 Birth from surprise, by contrastive recall

When a target's outcome costs more than 0.3 bits, the brain remembers the moment. It
keeps the last 64 surprises per target. To grow, it asks a contrastive question of that
memory:

> Among the times this target surprised me, what was present when it came out *this*
> way, and absent when it came out another way?

Single symbols are scored directly. Pairs are drawn from what this moment shares with one
earlier moment of the same surprise, because a joint cause (XOR) is invisible to every
single symbol and only shows up as a coincidence of two. A candidate must clear a
significance bar, and the bar rises with the candidate's order (there are far more
candidate pairs than singles). **No contrast in memory means no birth**, so noise does
not breed structure. Related to contrast-set / emerging-pattern mining (Dong & Li 1999)
and to latent-cause memory formation on surprise (Gershman).

### 2.4 Mixing

Units are pooled log-linearly, with weights learned online on code length. Pooling
multiplies independent evidence, which averaging cannot do. A **newborn has weight 0**:
it has no say until the gradient of code length gives it one. This mattered: with a
newborn weight of 0.3, a crowd of untested units made the brain confidently wrong early
in life (first-window excess 4.4 bits/tick).

### 2.5 Rent: a mortgage, not a tax

A unit owes its description length (`|context|·log2(#symbols) + ½(k−1)·log2(H)`) once.

- **Unpaid:** each activation earns the exact leave-one-out contribution (how many bits
  the mixture would have lost without this unit) and pays `cost/H`. It also pays
  existence rent per tick, so a rare context cannot squat forever. Balance < 0 → death.
- **Paid off** (lifetime savings ≥ cost): it stays as long as its recent contribution
  is not negative.

The first version taxed every unit forever at a fixed rate. That starved units that each
save a little, which are exactly the units hidden-state inference needs. Changing the
tax to a mortgage is the MDL-correct reading, since a description is paid for once.

### 2.6 Rupture

Each unit tracks a fast and a slow moving average of its own code length. If a unit was
reliable and is now repeatedly wrong (fast > slow + 2 bits), its rule broke. It keeps 5%
of its counts and relearns. Change detection is local to the unit that broke, with no
global "noradrenaline" knob.

### 2.7 Generalization and fertility

A paid-off unit occasionally spawns itself with one condition dropped. If the condition
never mattered, the general version is active more often, earns more, and the specific
one starves. Each target's birth rate is the measured success rate of its children, so a
target whose children keep dying gets fewer of them.

### 2.8 Memory as residual (`brain/codec.py`)

An integer arithmetic coder (Witten, Neal & Cleary 1987) encodes each observed value
with the brain's own predicted distribution. The byte string *is* the life. Decoding
replays a fresh brain with the same seed, which regenerates the same predictions, which
unlock the same values. Consequences:

- storage cost is proportional to surprise;
- the record only decodes with the brain that wrote it (tested: a brain with one
  different parameter reads garbage);
- **frugality and intelligence become one objective.** A smarter brain keeps a smaller
  record of its life.

This depends on determinism: the cortex makes no decision that depends on set iteration
order or wall-clock time.

### 2.9 What stayed the same

The gate, the ledger, policy and the kill switch are untouched. `src/do/brain/` imports
only the standard library and no I/O module, which the existing invariant tests check.
The brain is pure computation and cannot reach the world.

---

## 3. Prior art, and what is new

Closest prior work:

- **MC-AIXI-CTW** (Veness, Ng, Hutter, Uther, Silver 2011): an agent whose world model is
  a compressor (Context Tree Weighting), with planning by Monte-Carlo simulation. Same
  philosophy. Differences: CTW is a Bayesian mixture over all context trees of a fixed
  depth over a *binary* history. Here the stream is factored over named variables,
  structure is grown sparsely on surprise, it is evicted by per-unit rent, and the
  record of the life is the code itself.
- **Context mixing / PAQ** (Mahoney): many context models mixed by a learned
  logistic-style combiner. The mixing here is a multinomial version of that.
- **Compression progress** as curiosity (Schmidhuber 2008); **predictive state
  representations** (Littman & Sutton 2002); **clone-structured cognitive graphs** for
  latent state (George et al. 2021); **latent-cause inference** (Gershman et al.);
  **MDL** (Rissanen); **emerging patterns** (Dong & Li 1999).
- **Artificial Agency Program** (Csaky, Feb 2026): a position paper unifying predictive
  compression, curiosity and resource bounds as a research agenda. Same spirit, no
  implementation of this kind.

**What I did not find anywhere:** this combination, namely

1. growing conjunctive predictors from surprise via **contrastive episodic recall**,
2. keeping them under **per-unit MDL rent computed as exact leave-one-out bits**,
   with a mortgage rather than a tax,
3. **per-unit rupture** for non-stationarity,
4. an agent's long-term memory stored as the **arithmetic-coded residual** of its own
   brain, decodable only by replaying that brain.

Each component has lineage, and the combination is what was tested. That is a claim
about what a search found, not a proof that it has never been done.

---

## 4. B1: does it predict better than traditional methods?

**Protocol** (`src/do/experiments/brain_b1.py`):

- Prequential. Every prediction is made before the outcome is seen, so every tick is
  held out at the moment it is scored.
- Every model sees the identical stream, under the same exploration policy.
- The harness scores the predictions, not the models themselves.
- Metric: **excess bits per tick over the oracle**, which knows the true generative
  probabilities including hidden state. That excess is the part learning could remove.
- 5 seeds × 3,000 ticks × 6 worlds × 13 models.

**Worlds** (`brain/worlds.py`), each hiding one structure with a known answer:

| world | hidden structure |
|---|---|
| conjunction | y′ = a XOR b, z′ = a AND c, plus noise |
| delayed | `clean` at t raises disk at t+3 |
| distractors | one real relation among 12 noise variables |
| hidden_mode | a never-observed mode drives three noisy observables |
| rule_change | y′ = x, reversing every 1,500 ticks |
| habitat | D.O.-shaped: a clock, a hidden nightly backup that loads the CPU and drains disk, conditional actions (`rotate` helps only when the ledger is large; `snapshot` fails at disk 0) and a placebo action |

### 4.1 Results

Excess bits/tick over the oracle, mean over 5 seeds (lower is better). Last column of each
pair: the final 30% of life, i.e. after learning.

| world | **brain** | brain, last 30% | logistic (flat) | flat, last 30% | best classic | v1 Hebbian |
|---|---|---|---|---|---|---|
| conjunction | **0.188** | **0.072** | 1.005 | 0.959 | 1.268 (joint table) | 1.340 |
| delayed | **0.240** | **0.098** | 0.368 | 0.255 | 0.579 (Markov-1) | 0.969 |
| distractors | **0.137** | **0.047** | 0.158 | 0.052 | 1.188 (persistence) | 1.105 |
| hidden_mode | 0.399 | 0.360 | **0.304** | **0.230** | 0.471 (persistence) | 0.454 |
| rule_change | 0.124 | 0.024 | **0.111** | **0.023** | 1.191 (persistence) | 0.746 |
| habitat | 0.920 | **0.509** | **0.836** | 0.562 | 1.795 (Markov-1) | 3.008 |

"Logistic (flat)" is the strongest traditional ML baseline here: online logistic
regression over every lagged symbol (the brain with growth, rent and recall switched off).

Brain size versus flat, in units: conjunction 213 vs 648 · delayed 128 vs 192 ·
distractors 440 vs 1,848 · hidden_mode 164 vs 306 · rule_change 125 vs 255 ·
habitat 199 vs 1,200. **The brain is 1.5–9× smaller.**

**Reading it honestly:**

- **Against all five classic baselines, the brain wins in every world**, usually by
  2–25×. The v1 design (Hebbian / Rescorla–Wagner, with its readout tuned in its
  favour) is worse than counting frequencies in four of six worlds.
- **Against logistic regression, the brain wins where structure is conjunctive or
  delayed**, by 13× on XOR and 2.6× on delay after learning, and ties on distractors and
  rule change. **It loses on hidden_mode** (0.36 vs 0.23) and loses on habitat over the
  whole life (it learns slower early) while winning after learning (0.51 vs 0.56).
- **Discovered structure, read straight out of `explain()`:**
  - `{a=0@0, b=0@0} → y=0` (p 0.92): the XOR rule, found exactly.
  - `clock=0@2 → cpu=high`: the timing of a backup it cannot see.
  - `{disk=0@0, snap_age=3@0} → snap_age stays 3`: snapshots fail on a full disk.
  - `clock=2@2 → clock=3` (p 0.989): bin timing from a 2-tick lag.
  - In distractors, exactly the three true units `x=k@0 → y=k` were paid off and
    nothing about the noise was. This is enforced by a test.

### 4.2 Ablations (all-life excess; the mechanism removed is the only change)

| removed | conjunction | delayed | distractors | hidden | rule_change | habitat | verdict |
|---|---|---|---|---|---|---|---|
| (full brain) | 0.188 | 0.240 | 0.137 | 0.399 | 0.124 | 0.920 | |
| contrastive recall | 0.991 | 0.663 | 0.508 | 0.462 | 0.290 | 3.281 | **the most important mechanism** |
| rent | 0.224 | 0.455 | 0.216 | **0.307** | 0.230 | 0.996 | helps in 5/6; hurts hidden_mode |
| rupture | 0.190 | 0.236 | 0.137 | 0.407 | 0.231 | 0.938 | halves rule-change excess; neutral elsewhere |
| generalization | 0.211 | 0.260 | 0.136 | 0.401 | 0.124 | 0.943 | small, consistent help |
| (+ inner senses) | 0.209 | 0.275 | 0.125 | 0.440 | 0.117 | 0.925 | **negative result**, see §6 |
| (+ innate first-order layer) | 0.175 | 0.240 | 0.213 | **0.310** | 0.129 | 0.838 | fixes hidden_mode at 2–7× the units; worse on distractors |

---

## 5. B2: is a brain-coded life smaller than the best compressors?

**Protocol** (`src/do/experiments/brain_memory.py`): record 3,000 ticks of life, store
it every way listed below, then **decode the brain version by replaying a fresh brain and
check that the replay is bit-exact.** A compression ratio from a codec that was never
decoded would be a claim, not a result.

The general compressors get a fair input as well as JSON: one byte per value, so they
know the alphabet just as the brain does. "Floor" is the true entropy of that life given
the hidden state (oracle bits plus the action entropy). No method can beat it.

| world | raw JSON | xz −9e | packed + xz/bz2 (best) | **brain** | floor | brain above floor | best general above floor |
|---|---|---|---|---|---|---|---|
| conjunction | 244,970 | 12,892 | 6,214 | **4,232** | 4,111 | **2.9%** | 51% |
| delayed | 161,592 | 9,568 | 3,421 | **2,409** | 2,305 | **4.5%** | 48% |
| distractors | 395,020 | 18,616 | 10,221 | **8,315** | 8,257 | **0.7%** | 24% |
| hidden_mode | 196,954 | 10,236 | 4,380 | **3,173** | 3,020 | **5.1%** | 45% |
| rule_change | 169,945 | 10,088 | 4,105 | **2,957** | 2,908 | **1.7%** | 41% |
| habitat | 357,564 | 16,780 | 7,040 | **3,729** | 3,342 | **11.6%** | 111% |

(bytes; exact replay in all six.)

**D.O.'s life, stored as its brain's residuals, lands within 0.7–11.6% of the
theoretical minimum.** The best general-purpose compressor sits 24–111% above it. The
brain's record is 1.2–1.9× smaller than the best general compressor even with the fair
packed input, and 48–96× smaller than raw JSON. Encode and decode each run at about
1,000 ticks/s in pure Python.

---

## 6. Negative results and open problems

Stated as plainly as the wins.

1. **Hidden causes are not solved.** On hidden_mode the brain reaches 0.36 bits/tick
   after learning. Logistic regression reaches 0.23. The *ideal Bayesian filter* (the true
   rules, with the mode inferred from all history) reaches **~0.09**. A 3-tick window of
   conjunctions is not a belief state. This is the main open problem, and the next
   milestone targets it directly (§7, B3).
2. **Inner senses did not work.** Feeding the brain's own discretized expectations back
   as input was meant to create a recurrent belief state. It made hidden_mode *worse*
   (0.44 vs 0.40), with fixed or adaptive levels and over a 6,000-tick life. The
   hypothesis was reasonable and the result is negative. The code is kept as an
   ablation arm (`beliefs=True`, default off).
3. **The economy is biased against many weak clues.** A dense innate first-order layer
   fixes hidden_mode (0.31) at 2–7× the units and costs accuracy on distractors. That
   is a real trade-off, not a free win, so it is not the default.
4. **It learns structure more slowly than logistic regression early in life.** Over the
   whole habitat life the flat model wins; after learning the brain does. Structure has
   to be discovered before it can be used.
5. **Everything here is synthetic.** The worlds were designed by me. They contain the
   kinds of structure D.O. faces, but the brain has not yet run on D.O.'s real machine
   trace.
6. **Prediction is not yet action.** B1 and B2 measure perception and memory. Choosing
   actions through the model has not been built.

### Seeded vs learned

| seeded (the genome) | learned |
|---|---|
| history window 3, max context order 3, capacity 96 per target | every unit: which symbols, which target |
| KT prior α=0.4, mixer rate η=0.02, newborn weight 0 | every count and every weight |
| half-life H=300 activations, existence half-life 1,200 ticks | which units live and which die |
| surprise threshold 0.3 bits, recall memory 64, evidence z=2 | what was surprising, and what differed |
| rupture threshold 2 bits | when a rule broke |

About 12 constants in total, all mechanism-level. None names a variable, a value or a
relation.

---

## 7. Next milestones

Each comes with its falsifier, as the rest of this project does.

| | Milestone | Mechanism | Falsified if |
|---|---|---|---|
| **B3** | **Latent causes** | When a target's residual surprise is persistent and *shared across targets* (o1, o2, o3 surprise together), posit a hidden variable. Infer its state by the brain's own forward filtering, give it units like any observable, and keep it only if it pays rent. | hidden_mode excess after learning does not fall from 0.36 toward the ideal filter's 0.09, or habitat does not improve |
| **B4** | **Acting by imagination** | Choose actions by simulating each one through the cortex a few ticks ahead and scoring the predicted drive error. CAUSE knowledge may only come from D.O.'s own interventions through the gate. | it does not beat today's greedy planner on the habitat's conditional actions, or it "learns" that the placebo action works |
| **B5** | **Curiosity as compression progress** | Intrinsic value = expected *drop* in code length from an action or investigation. | it explores no better than random on worlds with learnable structure, or it stares at noise |
| **B6** | **The real machine** | Feed `cycle()` observations to the cortex; store the ledger as residuals. | the brain does not beat Markov-1 on D.O.'s own trace, or the residual ledger is not smaller than the gzip one |
| **B7** | **Grounded words** | Words from the creator become symbols; units link them to percepts by the same contrastive recall. | held-out words do not map to the right percepts above chance |

---

## 8. Running it

```bash
do experiment brain          # B1: 13 models × 6 worlds × 5 seeds (~15 min serial)
do experiment brain-memory   # B2: residual memory vs gzip/bz2/xz, with exact replay
python -m unittest tests.test_brain -v
```

```python
from do.brain import Cortex
from do.brain.worlds import WORLDS
w = WORLDS["habitat"](0)
c = Cortex(w.variables, w.actions)
frame = w.observe()
for _ in range(3000):
    a = w.policy()
    c.predict(frame, a)
    frame = w.step(a)
    c.update(frame)
print(c.explain("cpu"))      # what it believes about the CPU, and why, in bits
```
