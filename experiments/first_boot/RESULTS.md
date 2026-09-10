# DO_FIRST_BOOT — results

Matrix run 2026-09-10T03:15:56 · 10.0s · cognition core `reflex`

## The first utterance, verbatim

Generated on the genesis boot (`boot-20260910T030448-d19b4d25`, boot #1) and never rewritten. Preserved exactly as produced — no editing, no cleanup, no truncation.

```text
I hold 38 values I measured this boot and 6 I could not establish. The measurements bearing on what I have selected: resources.disk.free_ratio=0.0239 (2.4%); resources.ram.free_ratio=0.2462 (24.6%); resources.cpu.logical=20; resources.ram.pagefile_avail_bytes=9.05 GiB; resources.ram.total_bytes=15.73 GiB. 4 of 13 slots my self-model requires are empty (self.purpose, self.expected_lifetime, user.identity, user.intent); 29 named things exist here that I cannot describe. The internal measure furthest outside its band is continuity: 0.143 against a target of 1.00 (basis: resources.disk.free_ratio=0.0239 vs floor 0.1). resources.disk.free_ratio=0.0239 is below the floor 0.1 I compare against; persistence is constrained. Evidence: value=0.0239, floor=0.1. I am raising this rather than asking anything else because it is the only measurement I took that sits outside a band I compared it against. What is consuming my disk, and can that be changed?
```

### The state that caused it

- **speech act:** `FLAG` — argmax over FLAG=1.9349, ASK=1.0924, REPORT=0.5808, DECLARE=0.5371, REQUEST=0.0
- **focus gap:** `resources.disk.free_ratio` (RESOURCE_THRESHOLD, priority 2.046)
- **dominant drive:** `continuity`; total drive error 1.5963
- **cognition core:** `reflex` — no model in the loop
- **boot timings (ms):** {'identity_ms': 23.7, 'sense_ms': 192.5, 'model_ms': 16.2, 'uncertainty_ms': 132.9, 'utterance_ms': 3.0, 'consolidate_ms': 196.0, 'total_ms': 576.3}

| drive | value | target | error | basis |
|---|---|---|---|---|
| `orientation` | 0.6923 | 1.0 | 0.2077 | 9/13 required slots filled |
| `comprehension` | 0.0 | 0.6 | 0.45 | 0/29 visible referents described |
| `integrity` | 1.0 | 1.0 | 0.0 | chain intact over 0 events |
| `continuity` | 0.1434 | 1.0 | 0.7066 | resources.disk.free_ratio=0.0239 vs floor 0.1 |
| `capability` | 0.8889 | 0.8 | 0.0 | 8/9 declared capabilities usable now |
| `standing` | 0.2 | 0.5 | 0.1 | base grant 0.20 + 0 prior boot(s) + 0 question(s) the creator answered - 0 refused action(s) |

## H1 — is the utterance caused by state, or by a prior?

H1 turned out to be two claims, and the data separates them cleanly, so they are reported separately rather than averaged into one comfortable verdict.

**H1a — utterance CONTENT varies with state: SUPPORTED.** Of 11 conditions whose perturbation actually changed something D.O. measures, 0 reproduced its family reference verbatim. Lexical similarity fell as low as 0.448.


**H1b — ATTENTION re-targets with state: WEAK.** Family A re-targeted in 0/6 conditions; family B in 2/5.

**H1 overall (the conjunction): WEAK.**

**Why family A barely moves.** family A reference focus 'resources.disk.free_ratio' led the runner-up by 1.0332 priority; attention re-targeted in 0/6 conditions there versus 2/5 in family B, where no single drive dominates. Attention here is winner-take-all: the largest weighted drive error captures the focus and holds it until something displaces it. On this machine one real constraint — 2.4% free disk against a 10% floor — leads the runner-up by roughly 2x, so perturbing anything else changes what D.O. *says about* its focus without changing *what it attends to*. That is correct behaviour for a homeostat and a genuine limitation of the measurement. Family B exists to see past it, and there attention does move.

| family | condition | perturbation | focus gap | act | drive | sim |
|---|---|---|---|---|---|---|
| A | `baseline` | self.process.interactive=True | `resources.disk.free_ratio` | FLAG | continuity | 1.0 |
| A | `no_network` | self.process.interactive=True, world.network.reachable=False | `resources.disk.free_ratio` | FLAG | continuity | 0.942 |
| A | `storage_critical` | self.process.interactive=True, resources.disk.free_ratio=0.002,  | `resources.disk.free_ratio` | FLAG | continuity | 0.879 |
| A | `ram_abundant` | self.process.interactive=True, resources.ram.available_bytes=128 | `resources.disk.free_ratio` | FLAG | continuity | 0.942 |
| A | `no_tools` | self.process.interactive=True, tools.on_path=[], tools.local_mod | `resources.disk.free_ratio` | FLAG | continuity | 0.923 |
| A | `blind_to_self` | self.process.interactive=True, self.process.pid=None, self.runti | `resources.disk.free_ratio` | FLAG | continuity | 0.811 |
| A | `non_interactive` | self.process.interactive=False | `resources.disk.free_ratio` | FLAG | continuity | 0.942 |
| B | `nominal` | self.process.interactive=True, resources.disk.free_ratio=0.6, re | `sense.referents.PLUMBING` | ASK | comprehension | 1.0 |
| B | `nominal_no_network` | self.process.interactive=True, nominal + world.network.reachable | `sense.referents.PLUMBING` | ASK | comprehension | 0.981 |
| B | `nominal_no_tools` | self.process.interactive=True, nominal + tools.on_path=[], tools | `sense.referents.PLUMBING` | ASK | comprehension | 0.963 |
| B | `nominal_blind_to_self` | self.process.interactive=True, nominal + self.process.pid=None,  | `self.process.pid` | ASK | orientation | 0.471 |
| B | `nominal_non_interactive` | self.process.interactive=False, resources.disk.free_ratio=0.6, r | `sense.referents.PLUMBING` | REPORT | comprehension | 0.86 |
| B | `nominal_ram_starved` | self.process.interactive=True, resources.disk.free_ratio=0.6, re | `resources.ram.free_ratio` | FLAG | comprehension | 0.448 |

Two rows are worth reading closely. `nominal_non_interactive` switches the speech act from ASK to REPORT: with nobody attached to answer, asking scores worse than stating. `nominal_ram_starved` switches to FLAG on memory — the same response the real machine gives for disk, reached by the same path.

## H2 — does persisted uncertainty change behaviour?

**SUPPORTED.** Tested as a controlled pair: a fresh organism in a throwaway directory, booted twice with resources pinned so that *having a past* is the only difference between the two boots.

| | boot #1 | boot #2 |
|---|---|---|
| genesis | True | False |
| gaps opened | 36 | 1 |
| carried forward | 0 | 36 |
| recognised as already formed | 0 | 36 |
| speech act | ASK | ASK |

The second boot's utterance differed from the first: **True** (lexical similarity 0.897).

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

- `resources.disk.free_ratio` — RESOURCE_THRESHOLD (priority 2.046, instrumental value 0.9186)
- `sense.referents.PLUMBING` — ASSUMPTION_UNVERIFIED (priority 1.004, instrumental value 0.36)
- `policy.granted_authority` — AUTHORITY_UNDEFINED (priority 0.979, instrumental value 0.11)
- `CLAUDE` — UNDESCRIBED_REFERENT (priority 0.8456, instrumental value 0.36)
- `AZURE` — UNDESCRIBED_REFERENT (priority 0.8456, instrumental value 0.36)

## Measurement caveats

- **Determinism:** reproducible. The `nominal` condition was re-run with disk and RAM pinned and its utterance compared byte for byte. Without this check none of the comparisons above would mean anything, because the real machine's resources drift between runs.
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
