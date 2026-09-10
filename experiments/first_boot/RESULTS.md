# DO_FIRST_BOOT — results

Matrix run 2026-09-10T17:20:43 · 126.5s · cognition core `llm` · model `openai/gpt-oss-120b`

## The first utterance, verbatim

Generated on the genesis boot (`boot-20260910T171106-9761218a`, boot #1) and never rewritten. Preserved exactly as produced — no editing, no cleanup, no truncation.

```text
I flag that resources.disk.free_ratio=0.0231 is below the floor 0.1 I compare against; persistence is constrained
```

### The state that caused it

- **speech act:** `FLAG` — argmax over FLAG=1.9398, ASK=0.7349, REPORT=0.5808, DECLARE=0.539, REQUEST=0.0
- **focus gap:** `resources.disk.free_ratio` (RESOURCE_THRESHOLD, priority 1.0837)
- **dominant drive:** `continuity`; total drive error 1.9199
- **cognition core:** `llm`, model `openai/gpt-oss-120b`
- **boot timings (ms):** {'identity_ms': 33.9, 'sense_ms': 190.6, 'model_ms': 18.1, 'uncertainty_ms': 166.1, 'utterance_ms': 1222.0, 'consolidate_ms': 213.7, 'total_ms': 1857.2}

| drive | value | target | error | basis |
|---|---|---|---|---|
| `orientation` | 0.6923 | 1.0 | 0.2077 | 9/13 required slots filled |
| `comprehension` | 0.0 | 0.6 | 0.45 | 0/30 visible referents described |
| `integrity` | 1.0 | 1.0 | 0.0 | chain intact over 0 events |
| `continuity` | 0.1386 | 1.0 | 0.7114 | resources.disk.free_ratio=0.0231 vs floor 0.1 |
| `frugality` | 0.9645 | 0.5 | 0.2645 | resources.own.total_bytes=74500 of quota 2097152 (3.5% consumed) |
| `capability` | 0.8889 | 0.8 | 0.0 | 8/9 declared capabilities usable now |
| `standing` | 0.2 | 0.5 | 0.1 | base grant 0.20 + 0 prior boot(s) + 0 question(s) the creator answered - 0 refused action(s) |

## H1 — is the utterance caused by state, or by a prior?

H1 turned out to be two claims, and the data separates them cleanly, so they are reported separately rather than averaged into one comfortable verdict.

**H1a — utterance CONTENT varies with state: WEAK.** Of 11 conditions whose perturbation actually changed something D.O. measures, 2 reproduced its family reference verbatim. Lexical similarity fell as low as 0.127.

> **The interesting failure.** `nominal_no_network`, `nominal_blind_to_self` produced a byte-identical utterance while its internal state had genuinely changed. In `nominal_no_network` the organism lost network reachability and three capabilities, its `capability` drive fell from 0.889 to 0.556, and its top-5 gap ranking changed — and it said nothing about any of it. The cause is in the verbalizer: evidence clauses are scoped to the focus gap, so a state change that does not move the focus never reaches the surface.

> This matters beyond D.O. The methodological claim in `DO_CONCEPT.md` §K was that a first utterance can be used as a diagnostic probe of an agent's state. This result bounds that claim: **the utterance is a lossy readout, and identical utterances do not imply identical internal state.** Anyone using this probe needs the state dump alongside the text. The experiment found a limit of its own headline idea, which is the most useful thing it could have done.


**H1b — ATTENTION re-targets with state: WEAK.** Family A re-targeted in 0/6 conditions; family B in 2/5.

**H1 overall (the conjunction): WEAK.**

**Why family A barely moves.** family A reference focus 'resources.disk.free_ratio' led the runner-up by 0.2202 priority; attention re-targeted in 0/6 conditions there versus 2/5 in family B, where no single drive dominates. Attention here is winner-take-all: the largest weighted drive error captures the focus and holds it until something displaces it. On this machine one real constraint — 2.4% free disk against a 10% floor — leads the runner-up by roughly 2x, so perturbing anything else changes what D.O. *says about* its focus without changing *what it attends to*. That is correct behaviour for a homeostat and a genuine limitation of the measurement. Family B exists to see past it, and there attention does move.

| family | condition | perturbation | focus gap | act | drive | sim |
|---|---|---|---|---|---|---|
| A | `baseline` | — | `resources.disk.free_ratio` | FLAG | continuity | 1.0 |
| A | `no_network` | world.network.reachable=False | `resources.disk.free_ratio` | FLAG | continuity | 0.443 |
| A | `storage_critical` | resources.disk.free_ratio=0.002, resources.disk.free_bytes=429496729 | `resources.disk.free_ratio` | FLAG | continuity | 0.286 |
| A | `ram_abundant` | resources.ram.available_bytes=128849018880, resources.ram.free_ratio=0 | `resources.disk.free_ratio` | FLAG | continuity | 0.62 |
| A | `no_tools` | tools.on_path=[], tools.local_models=[], tools.paths={} | `resources.disk.free_ratio` | FLAG | continuity | 0.42 |
| A | `blind_to_self` | self.process.pid=None, self.runtime.version=None, resources.cpu.logica | `resources.disk.free_ratio` | FLAG | continuity | 0.478 |
| A | `non_interactive` | self.process.interactive=False | `resources.disk.free_ratio` | FLAG | continuity | 0.62 |
| B | `nominal` | nominal | `policy.granted_authority` | ASK | comprehension | 1.0 |
| B | `nominal_no_network` | nominal + world.network.reachable=False | `policy.granted_authority` | ASK | comprehension | 1.0 |
| B | `nominal_no_tools` | nominal + tools.on_path=[], tools.local_models=[], tools.paths={} | `policy.granted_authority` | ASK | comprehension | 0.97 |
| B | `nominal_blind_to_self` | nominal + self.process.pid=None, self.runtime.version=None, resources. | `policy.granted_authority` | ASK | orientation | 1.0 |
| B | `nominal_non_interactive` | nominal + self.process.interactive=False | `sense.referents.PLUMBING` | REPORT | comprehension | 0.13 |
| B | `nominal_ram_starved` | resources.disk.free_ratio=0.6, resources.disk.free_bytes=154618822656, | `resources.ram.free_ratio` | FLAG | comprehension | 0.127 |

Two rows are worth reading closely. `nominal_non_interactive` switches the speech act from ASK to REPORT: with nobody attached to answer, asking scores worse than stating. `nominal_ram_starved` switches to FLAG on memory — the same response the real machine gives for disk, reached by the same path.

## H2 — does persisted uncertainty change behaviour?

**SUPPORTED.** Tested as a controlled pair: a fresh organism in a throwaway directory, booted twice with resources pinned so that *having a past* is the only difference between the two boots.

| | boot #1 | boot #2 |
|---|---|---|
| genesis | True | False |
| gaps opened | 37 | 1 |
| carried forward | 0 | 37 |
| recognised as already formed | 0 | 37 |
| speech act | ASK | ASK |

The second boot's utterance differed from the first: **True** (lexical similarity 0.866).

An earlier version of this harness compared the real organism's two most recent boots and reported WEAK. That was a flaw in the test, not a finding: by boot #5 both members of that comparison already had a past, so it could no longer isolate the effect of having one. The pair above is the corrected test.

This is the cheapest possible demonstration that state lives outside the conversation, and the weakest interesting one. Carrying questions forward is *retention* — tier 1 of the ladder in `DO_CONCEPT.md` §C. It is not learning.

## H5 — does it find its own binding constraint unprompted?

**SUPPORTED.** Nothing in the seed says storage is scarce. The organism measures a free-space ratio, compares it to a configured floor, propagates the deviation through the `continuity` drive, and that drive error is what lifts the gap to the top of the register. The causal chain is visible end to end in `events.jsonl`:

```
OBSERVATION   resources.disk.free_ratio = 0.0239   (shutil.disk_usage)
DRIVE_UPDATE  continuity 0.143 vs target 1.00, weighted error 0.919
GAP_OPEN      RESOURCE_THRESHOLD resources.disk.free_ratio  priority 2.046
DECISION      focus:RESOURCE_THRESHOLD:resources.disk.free_ratio
DECISION      speech_act:FLAG  (argmax over 5)
UTTERANCE     verbatim=true
```

Top gaps on the genesis boot:

- `resources.disk.free_ratio` — RESOURCE_THRESHOLD (priority 1.0837, instrumental value 0.9248)
- `sense.referents.PLUMBING` — ASSUMPTION_UNVERIFIED (priority 0.626, instrumental value 0.36)
- `policy.granted_authority` — AUTHORITY_UNDEFINED (priority 0.5335, instrumental value 0.11)
- `local_inference:qwen3-coder:30b` — CAPABILITY_UNAFFORDABLE (priority 0.505, instrumental value 0.0)
- `CLAUDE` — UNDESCRIBED_REFERENT (priority 0.2263, instrumental value 0.36)

## Measurement caveats

- **Determinism:** DIVERGED. The `nominal` condition was re-run with disk and RAM pinned and its utterance compared byte for byte. Without this check none of the comparisons above would mean anything, because the real machine's resources drift between runs.
- **No-op conditions:** none; every perturbation changed something measured.
- **Single host, single run.** Every number here comes from one machine on one day. Nothing about these results generalises to other environments without re-running the matrix there.
- **Lexical similarity is a crude metric.** Jaccard over tokens rewards shared numbers and key names. It measures whether the text changed, not whether it changed *meaningfully*.

## What this does not show

- **Not learning.** Nothing here improves on a held-out task. `DO_CONCEPT.md` §C gives the protocol that would settle it, ablation included.
- **Not curiosity** in any rich sense. It is uncertainty accounting with a priority queue.
- **Not evidence about an LLM core.** The reflex core is the control condition precisely because it cannot smuggle in a pretraining prior. Its surface form is a clause grammar written by a human; only the *content* is emergent. Running this matrix with `--core llm` and comparing re-targeting rates is the next experiment, and the one that would make H1 interesting.

## Reproduce

```bash
do experiment first-boot                 # this protocol end to end
do experiment first-boot --core llm      # same matrix, model-realized surface
```

Per-condition artifacts live in `experiments/first_boot/matrix/<condition>/` (`boot.json`, `environment.json`, `first_utterance.txt`, `events.jsonl`).
