# D.O. — build journal

Chronological record: what was built, what changed architecturally and **why**, and
what the experiments actually returned. Failures are recorded with the same prominence
as successes; several entries exist only because something went wrong.

All work to date occurred in a single session on **2026-09-10**. Entries are numbered
by milestone rather than by day, because dating them all "day 1" would be less useful
than showing the order of reasoning.

Repository: `https://github.com/rajj28/DO` (private) · commits `5381eb2`, `47aae59`,
`44835ef`

---

## M0 — Environment survey, before any code

**What.** Measured the host before choosing anything: Python 3.11.9, Node 25, uv,
gcloud, docker, ollama with one 18 GB model. RAM 15.7 GiB total / **2.8 GiB free**.
Disk 240 GB at **98% full**. No LLM key in the environment.

**Why it mattered.** Two decisions fell straight out of the measurements. The seed
would be **zero-dependency** (a `pip install` is a real failure mode with 5.7 GiB free,
and a first-boot experiment that can fail for infrastructural reasons produces
uninterpretable nulls). And `qwen3-coder:30b` was marked *installed but unaffordable* —
17.3 GiB resident against 2.8 GiB free — rather than pretended into a capability.

**Result.** The 98%-full disk later became the constraint D.O. discovered by itself.
It was never planted; it was just true.

---

## M1 — The seed, and the first utterance

**Architecture.** Deviated from the brief's proposed tree in four places, each for a
reason recorded in `ARCHITECTURE.md` §2. The load-bearing one: `security/` as a sibling
package became **`effectors/gate.py` as the only path to any side effect**, enforced by
an AST test that fails if any module outside it imports `socket`/`subprocess`/`urllib`.
A safety package other code *chooses* to call is advice; a boundary that is the only
implementation is an invariant.

Also added, absent from the brief: a **hash-chained ledger** (event sourcing gives
observable/versioned/reversible/auditable in one mechanism), **drives** (goals need a
source that is not the user), and a **tick loop** (without a clock this is a request
handler with a database).

**Result — the genesis utterance, verbatim, preserved write-once:**

> `I hold 38 values I measured this boot and 6 I could not establish. … resources.disk.free_ratio=0.0239 is below the floor 0.1 I compare against; persistence is constrained. … What is consuming my disk, and can that be changed?`

It flagged storage rather than asking what it was. Not because anyone wrote that
question, but because `self.purpose` scores `info_gain 0.077 × instrumental 0.208`
while the disk gap scores `0.55 × 0.919`. It won by roughly 2×.

---

## M2 — DO_FIRST_BOOT, and three flaws the experiment found in itself

| hypothesis | verdict |
|---|---|
| H1a content varies with state | SUPPORTED |
| H1b attention re-targets | **WEAK** |
| H2 persisted uncertainty changes behaviour | SUPPORTED |
| H3 drives generate goals unprompted | **FALSIFIED** |
| H5 finds its own binding constraint | SUPPORTED |
| H6 gate unbypassable | SUPPORTED |

**Three defects the harness found in itself**, each of which would have produced a
confident wrong answer:

1. *A dominant constraint masks sensitivity.* One family of perturbations against the
   real machine showed almost no movement — a negative result about the experiment,
   not the organism. Fix: a second condition family with resources spoofed healthy.
2. *The harness's own terminal state leaked in.* `sys.stdin.isatty()` differs between
   a terminal and a pipe, silently changing speech-act scores between runs. Fix:
   `PINNED`, plus a determinism check that reruns one condition and compares byte-for-byte.
3. *H2 was testing nothing.* It compared the two most recent boots — but by boot #5
   both already have a past. Fix: a controlled fresh pair.

**None were fixed by moving a threshold.** Where a result stayed disappointing after
the design was corrected, it is reported as disappointing.

**The finding that bounds the project's own headline idea:** one condition produced a
byte-identical utterance while its internal state had genuinely changed. *An utterance
is a lossy readout; identical text does not imply identical state.*

---

## M3 — H3 falsified: the loop that stalled

`do tick 4` re-selected `resources.disk.free_ratio` four times running. The metabolism
ran without a human — the half that matters — but looped on one action, which is
explicitly H3's failure condition.

**Diagnosis, not mystery.** The dominant gap was one D.O. had no action for. Its only
routes were "measure again", "ask the user", "reduce own footprint"; only the first was
executable unaided, and re-measuring an unchanged disk resolves nothing. Winner-take-all
attention then re-selected it forever.

---

## M4 — The survival loop (v0.2)

**Architecture.** `OBSERVE → CONSTRAIN → PRIORITIZE → OBJECTIVE → CANDIDATES →
EVALUATE → ACT → OBSERVE → LEARN → UPDATE → NEXT`, plus:

- **`frugality` drive** separate from `continuity`. Two storage facts exist — the host
  volume and D.O.'s own allocation — and only one is D.O.'s to fix. An organism that
  cannot tell them apart will either despair or lie.
- **agency** scales a gap's instrumental value by whether any registered action moves
  its metric. Importance without ability is not a goal, it is a complaint.
- **escalation damping**: an unactionable constraint is raised with the creator once,
  then stops competing for attention.
- Actions **predict before acting**; the gap between predicted and actual is the
  learning signal.

**Result.** Boot #13 showed the fix on the real organism for the first time: attention
moved off the host disk and onto `resources.own.quota_used_ratio` at 211% of quota.

---

## M5 — Reflex vs LLM: better language, worse observation

The experiment the project was built to run. Same 13-condition matrix twice on
identical code, differing only in the verbalizer. Both cores receive an identical plan.

| | reflex | llm (`gpt-oss-120b`) |
|---|---|---|
| noise floor (same state, resampled) | **1.000** | 0.970 |
| length (mean chars) | 937 | **311** |
| carries its own condition's value | **13/13** | 9/13 |
| identical text despite changed state | **0/11** | **2/11** |
| H1a | **SUPPORTED** | **WEAK** |

**Decisive case:** `nominal_no_network` produced text byte-identical to `nominal` under
the LLM, while the organism had lost network reachability and three capabilities and
its `capability` drive fell 0.889 → 0.556. The reflex core distinguished them.

**A language model makes D.O. sound better and say less.** Fluency and
state-discriminability traded against each other. Full write-up: `LLM_COMPARISON.md`.

**Three near-misses, none of which crash:**
1. Config didn't propagate — every condition would have run reflex under an LLM label.
2. Rate limiting looked like a result — 10/13 fell back silently and verdicts were
   emitted from a treatment/control mixture.
3. Reasoning tokens ate the budget — `gpt-oss` bills reasoning against `max_tokens`.

The most valuable thing built in this round is the **integrity gate**: the harness
refuses to emit any verdict if a single condition did not use the requested core.

---

## M6 — Emergent goals (the H3 closure)

**The critical change was a deletion.** `objectives.generate()` contained:

```python
if gap.subject == "resources.own.quota_used_ratio":
    ...build the footprint objective...
```

That is the experimenter supplying the goal while the organism appears to form it.
Goals are now derived: gap binds to a drive **by observation namespace**, the drive
declares the metric its value is computed from, the **action registry** decides whether
anything moves that metric, and the drive's set point is inverted for the target. A
test greps for the return of subject strings.

**Decomposition made real.** The per-component footprint breakdown was *removed from
default sensing*. D.O. boots knowing its total and not its composition; establishing
the composition is an action it must choose. The planner is stage-filtered so it cannot
delete before it knows what things are.

**Result, controlled workspace, no network, no model:**

```
GOAL       bring resources.own.total_bytes from 384512 to at most 182000
DIAGNOSED  largest=experiments  recoverable_now=212464B  sufficient=True
           safe: experiments, memory, ledger, bytecode, snapshots
           cannot act on: identity, archives, sandbox
EXECUTED   clear_experiment_matrix freed 182464B
MET in 2 cycles; frugality 0.421 vs target 0.5 → satisfied
host disk escalated throughout — never became a goal
```

**Bug found en route:** the diagnosis counted whole components as reducible whenever
any action targeted them, so it reported ample headroom while the planner found nothing
to do. It now asks each action what it can free *right now*. A diagnosis that
over-claims is worse than none.

---

## M7 — H4: learning from one's own outcomes

**Question:** does experience of its own outcomes make later decisions better, without
anyone adding a rule between runs?

**Design.** Identical environment rebuilt from a fixed seed every run. Two arms; the
only difference is whether the organism starts with what it learned last time.

**Two harness defects found before any result was trusted** — the reason the first
verdict was thrown away rather than reported:

1. *Confound.* Only the learning arm booted to receive its transplant, leaving it with
   a larger ledger and more to reclaim. The extra bytes it freed looked like skill and
   were volume. Both arms now boot identically.
2. *Blind instrument.* The quota was unreachable, so "cycles to solve" measured
   "cycles to exhaust" and the arms were identical by construction. A null result from
   a blind instrument means nothing. Also, diagnostics were being scored as failed
   actions — they free nothing by definition.

**Result:**

| | ablated | learning |
|---|---|---|
| `rotate_ledger` rank | `[2,2,2,2,2]` | `[2,1,1,1,1]` |
| actions to solve | 3,3,3,3,3 | 3,3,3,3,3 |
| bytes freed | ~215,000 | ~209,000 |
| goal met | never | never |

**H4a — experience changes the DECISION: SUPPORTED.** The learning arm promoted the
under-promising action from rank 2 to rank 1 beginning at run 2 — exactly when
transplanted calibration first existed — and held it. The ablated arm is flat. No rule
was added between runs.

**H4b — the changed decision improves the OUTCOME: NOT SUPPORTED.** Same action count,
goal unmet in both arms, and the learning arm freed marginally *less*.

**What that teaches:** correcting a belief only pays off if the corrected belief changes
*which set* of actions is taken, not merely their order. Greedy selection converged on
the same set either way. This is the honest ceiling of the current mechanism.

**Also observed:** D.O.'s own record-keeping competes with its housekeeping. In a
300–500 KB regime the ledger and memory grow measurably per cycle, which is why the
goal went unmet in both arms.

---

## Cross-cutting: what has been genuinely autonomous

| behaviour | status |
|---|---|
| finding the binding constraint (98% disk) | **autonomous** — measured, compared to a floor, propagated through a drive |
| forming the goal | **autonomous** as of M6 — derived from drive set point, no subject strings |
| classifying components safe/unsafe | **autonomous** — read from the action registry |
| choosing to investigate | **autonomous** — composition is not in default sensing |
| correcting its compression estimate | **autonomous** — 2.0× prior → ~1.74× correction from its own outcomes |
| promoting the corrected action | **autonomous** — H4a |
| the stage order (diagnose→reduce) | **seeded** — a rule I wrote |
| the action primitives | **seeded** |
| any new source code | **none** — D.O. has never written code |

---

## Security incidents

1. A Groq key was pasted into the session transcript. Flagged immediately; rotation
   advised.
2. A second key reached `.env.example` — a file deliberately *not* gitignored, so the
   next `git add -A` would have published it. Caught before any commit; zero
   occurrences in git history. **My own diagnostic then printed it**, putting a second
   key in the transcript. Both need rotating.
3. Fix is structural, not vigilance: `.githooks/pre-commit` blocks credential-shaped
   values and fails the commit. Verified with a decoy.

Also: `experiments/first_boot/environment.json` embeds 96 environment *variable names*
(values never read). Acceptable in a private repo; must be scrubbed before anything
public.

---

## M8 — Mortality and the fear ablation

**Question.** environment changes → P(continuity loss) → fear → goal priorities →
plans → **actions**. Control: identical world and state, `fear_enabled = False`.

**Design constraint that shaped everything:** fear must not become a second hidden
rule. So `P(loss) = P(interruption) × P(cannot recover)` is *estimated* from trends
over D.O.'s own episodic history, **fear is defined as** that estimate, and each
drive's relevance to continuity is **measured** by setting its metric to the
satisfying value and recomputing. No list of survival-relevant drives exists.

### First result: COSMETIC — and correct to report

Fear rose with deterioration, stayed at 0.0 in a stable world, and localised the
threat correctly. Behaviour was **identical to the control**.

The cause was structural, not a bug. Fear reached behaviour through
`err × (1 + fear × sensitivity)` — at most a ~17% nudge, while competing drive errors
differ by far more. **It could not flip an ordering by construction.** Raising the
multiplier would have made fear a hard-coded priority, so it was left and reported.

### Three instrument defects found before any verdict was trusted

1. **Resource gaps came from a hand-written list of three metrics**, so the `recovery`
   drive could never become a gap and `write_recovery_snapshot` was unreachable. The
   mechanism could not fire. Gaps are now derived from any drive declaring a metric.
2. **Trends were fitted over wall-clock seconds** while boots occur milliseconds
   apart: a 100 MB RAM jitter read as −50 MB/s and ~1 minute of runway, putting fear
   at 0.33 in a stable world. Rates are now fitted **per operation**, with a
   consistency test that rejects a slope through noise.
3. **`cycle()` re-observes at the top**, silently overwriting the harness's injected
   decay with the real machine. The deteriorating world existed only during seed
   boots and never reached the organism. `cycle()` now accepts the perturbation.

### The fix: fear competes, it does not modulate

Mortality now emits a **drive** whose value is `1 − P(loss)`, with a weight alongside
every other drive in config, and its metric bound to whichever **actionable** lever
the sensitivity analysis says most reduces `P(loss)`. It then wins or loses attention
through exactly the machinery every other drive uses.

### Second result: SUPPORTED

| | fear ON | fear OFF (identical world) |
|---|---|---|
| p_interrupt | 0.6193 | 0.6193 |
| recovery paths | 1 | 1 |
| p_loss = fear | **0.3096** | 0.0 |
| sensitivity | continuity 0.667, recovery 0.333, rest 0.0 | — |
| focus | `resources.own.recovery_paths` | `resources.own.quota_used_ratio` |
| action | **`write_recovery_snapshot`** | `diagnose_footprint` |
| end paths | 2 | 1 |

Under rising continuity risk D.O. switched from **reclaiming storage to preserving
persistent state**; the control facing the same world kept reclaiming. In a stable
world both arms were byte-identical and fear stayed at 0.0 — the signal does not fire
when nothing is wrong.

`continuity` had the highest sensitivity (0.667) but no action moves the host disk, so
the lever selection skipped it for `recovery` (0.333). **Nothing says "when
threatened, snapshot."** The chain is: trend → p_interrupt → p_loss → mortality drive
→ sensitivity picks the actionable lever → gap → objective → action.

**What is still seeded:** the mortality drive's weight (1.5), the horizon (20
operations), and `CONTINUITY_METRICS` — the three resources whose exhaustion counts as
an interruption. Those are assumptions, not discoveries.
