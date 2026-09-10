# D.O. Architecture

Every decision below is stated with its reason and its rejected alternative.

---

## 1. Technology selection

Repository inspected first: `C:\Users\Acer` is not a git repository and contains no
prior D.O. code. Available on this host: Python 3.11.9, Node 25.2.1, uv 0.12.7,
gcloud, docker, ollama (one model, `qwen3-coder:30b`, 18 GB). No Go/Rust. No LLM API
key in the environment.

**Measured constraints that drove the choice** (real numbers from this machine):

- RAM 15.7 GiB total, **2.8 GiB available**, 81 % load
- Disk C: **5.7 GiB free of 240 GiB — 98 % full**
- 20 logical CPUs

### Candidate stacks

| | A. Python 3.11, stdlib-only | B. TypeScript / Node | C. Go |
|---|---|---|---|
| Speed to first boot | **fastest** | fast | slow |
| Persistence with zero deps | **`sqlite3` in stdlib** | needs a package | needs cgo or a package |
| Introspection | `os`,`shutil`,`platform`,`ctypes` | weaker | good |
| AI ecosystem later | **strongest** | good | weak |
| Memory footprint | ~15 MB | ~45 MB | ~8 MB |
| Cloud / container | good | good | **best** |
| Distributed execution later | asyncio, adequate | good | **best** |
| Cost | 0 | 0 | 0 |

### Decision: **A — Python 3.11 with a strictly zero-dependency seed.**

Reasons, in priority order:

1. **`sqlite3`, `json`, `hashlib`, `ctypes` are all in the standard library.** The
   entire memory substrate, ledger and self-inspection layer needs no `pip install`.
2. **The first boot must be unfalsifiable by infrastructure.** If boot can fail
   because a wheel did not build, then a null result is uninterpretable. With
   2.8 GiB free RAM and 5.7 GiB free disk on this host, dependency installation is a
   real failure mode, not a theoretical one.
3. **Reproducibility.** A zero-dependency seed reproduces on any Python 3.11+ host,
   which matters because the headline experiment is a perturbation study.
4. Later phases (embeddings, provider SDKs) attach as *optional capabilities* that
   the registry marks unavailable when their imports fail — never as hard imports.

Rejected: Node — no stdlib database, and the seed's job is state, not I/O
concurrency. Rejected: Go — the seed would be finished sooner in Python than the Go
build tooling would be configured, and every later component is Python-first.

**Rule enforced by test:** `src/do/**` may import from the standard library only.
`tests/test_zero_dependency.py` walks the AST of every module and fails on any
third-party import. Optional adapters must import lazily inside a function.

---

## 2. Deviation from the proposed tree, and why

The brief's tree was a good first cut. Four changes, each for a specific reason.

| Brief | Here | Why |
|---|---|---|
| `security/` as a sibling package | `policy/` + **`effectors/gate.py` as the only path to side effects** | A safety package that other code *chooses* to call is advisory. Making the gate the only module that imports `socket`/`subprocess`/`urllib`, and statically testing that, converts a convention into an invariant. This is the single most important structural change. |
| `tools/` and `capabilities/` as siblings | one `capabilities/` registry; a tool is a capability with an executable binding | They were the same objects at different lifecycle stages. Splitting them guarantees drift between "registered" and "runnable". |
| `organism/self_model` + `world_model` as stores | **derived views over `memory` + `sense`**, snapshotted per boot | Two writable stores of the same facts desynchronise. Here memory is the substrate; the models are projections, rebuildable from the ledger. |
| `communication/elevenlabs` | `comms/voice.py` with a provider interface; ElevenLabs is one adapter | Provider names do not belong in an architecture. |
| *(absent)* | **`kernel/lifecycle.py` — a tick loop (metabolism)** | The brief's tree had no clock. Without a heartbeat this is a request handler with a database. The tick is what makes a drive able to fire with no human present. |
| *(absent)* | **`ledger/` — hash-chained append-only event log** | Required to satisfy "observable, versioned, reversible, auditable" in one mechanism (event sourcing). All derived state is rebuildable from it. |
| *(absent)* | **`drives/` — homeostasis** | Goals need a source that is not the user. |

Mapping is otherwise 1:1. `memory/` keeps the four required systems, `cognition/`
keeps reasoning/retrieval/planning/reflection, `experiments/first_boot` is unchanged.

---

## 3. The tree as built

```
DO/
├── do.cmd / do                 launchers  ->  python -m do
├── config/
│   ├── default.json            tunables: drives, salience weights, budgets
│   └── policy.json             the permission boundary (data, not code)
├── src/do/
│   ├── kernel/
│   │   ├── config.py           layered config: defaults < file < env < CLI
│   │   ├── identity.py         organism id, boot id, lineage
│   │   └── lifecycle.py        boot sequence (A-E) + tick loop (metabolism)
│   ├── ledger/                 hash-chained JSONL event log; replay; verify
│   ├── memory/                 sqlite: working/episodic/semantic/procedural
│   │                           + belief revision (supersede, never delete)
│   ├── sense/
│   │   ├── introspect.py       Phase A self-observation
│   │   ├── referents.py        undescribed-entity discovery (world frontier)
│   │   └── web.py              gated web perception with provenance
│   ├── models/                 SELF | WORLD | USER | TOOLS | RESOURCES | UNKNOWN
│   ├── drives/                 homeostatic variables -> drive error -> goals
│   ├── cognition/
│   │   ├── gaps.py             uncertainty register + salience scoring
│   │   ├── attention.py        goal selection, speech-act selection
│   │   ├── verbalize.py        reflex (non-LLM) compositional renderer
│   │   ├── cores.py            CognitionCore interface: reflex | llm
│   │   └── reflection.py       post-hoc consolidation
│   ├── capabilities/           registry + affordability + lifecycle
│   ├── effectors/gate.py       ** the only path to any side effect **
│   ├── policy/                 evaluation, budgets, kill switch, approvals
│   ├── comms/                  text io; voice interface (TTS adapters)
│   └── experiments/first_boot.py
├── tests/
├── experiments/first_boot/     boot.json environment.json first_utterance.txt events.jsonl
└── var/                        runtime state (sandbox root, gitignored)
```

---

## 4. Data model

### 4.1 Observation

The atom of perception. Never a bare value.

```python
Observation(key, value, unit, epistemic, source, ts, confidence, cost_ms)
```

`epistemic ∈ {OBSERVED, INFERRED, REPORTED, ASSUMED, UNKNOWN}`.

**Honesty invariant (immutable, §G of the concept doc):** an observation may not be
recorded at a stronger epistemic status than its source supports. A measurement taken
by reading `/proc` or a Win32 API is `OBSERVED`. A value computed from others is
`INFERRED`. Anything a human or a webpage said is `REPORTED`, never `OBSERVED`.

### 4.2 Memory record

```
id, kind(episodic|semantic|procedural), content, source, ts, confidence,
importance, context, verification(unverified|corroborated|contradicted|verified),
superseded_by, boot_id
```

Belief revision is **non-destructive**: revising a belief inserts a new row and sets
`superseded_by` on the old one. Cheap approximation of a TMS; keeps the justification
trail that makes revision auditable. Relations live in a separate edge table, giving
a minimal knowledge graph without a graph database.

### 4.3 Gap (the uncertainty register)

```
id, question, about(SELF|WORLD|USER|TOOLS|RESOURCES|UNKNOWN), kind, subject,
why_it_matters, reducible_by[], info_gain, instrumental, tractability, cost,
risk, priority, status(open|resolved|abandoned), first_seen_boot, resolved_boot
```

**Gaps persist across reboots.** This is what makes the second boot different from the
first, and it is the mechanism tested by H2.

### 4.4 Salience

```
priority = w_i·info_gain + w_v·instrumental + w_t·tractability − w_c·cost − w_r·risk
```

`instrumental` is not hand-assigned; it is **derived from live drive error** — a gap
bearing on a drive currently outside its target band is worth more. This is the causal
path from *the machine's real state* to *what D.O. talks about*, and it is what H1
tests. Acknowledged as a crude discrete expected-free-energy: epistemic value
(`info_gain`) plus pragmatic value (`instrumental`) minus cost.

### 4.5 Event

```
seq, ts, boot_id, type, actor, payload, prev_hash, hash
```

`hash = sha256(canonical_json(record_without_hash))`, chained on `prev_hash`. Types:
`BOOT, OBSERVATION, DECISION, QUESTION, TOOL_CALL, RESULT, MEMORY_WRITE,
BELIEF_UPDATE, CAPABILITY_CHANGE, RESOURCE_CHANGE, DRIVE_UPDATE, GAP_OPEN,
GAP_RESOLVE, UTTERANCE, POLICY_DENY, POLICY_APPROVAL_REQUIRED, ERROR, RECOVERY,
SHUTDOWN`.

**Decision events carry a structured summary, never a reasoning trace:**

```json
{"decision":"investigate_storage","reason":"resource.disk_free_ratio 0.024 below
 floor 0.10; drive continuity error 0.76 dominant","confidence":0.81,
 "alternatives_considered":3}
```

Private reasoning is not logged and not exposed. What is logged is the *selection*:
what was chosen, from how many candidates, on what measured grounds. That is enough
to audit behaviour without opening a chain of thought.

---

## 5. The gate — the one structural safety decision

```
        cognition                              (no I/O imports anywhere)
            │  EffectRequest(kind, target, payload, justification, gap_id)
            ▼
   effectors.gate.request()
            │
            ├─► killswitch check ────────► HALT
            ├─► budget check ────────────► DENY (budget_exhausted)
            ├─► policy.evaluate() ───────► ALLOW | DENY | REQUIRE_APPROVAL
            │                                     │
            │                                     └─► approval queue → human
            ├─► sandbox path resolution (realpath prefix check)
            ▼
        perform  ──► EffectResult ──► ledger(TOOL_CALL, RESULT) ──► budget debit
```

Properties this buys:

- Every side effect is logged with the gap that justified it — actions are traceable
  to the uncertainty that motivated them.
- Denials are events too, so refusals are as visible as actions.
- The kill switch is checked *inside* the only path to effects, so it cannot be
  routed around.
- Testable as a static property (H6), not as a promise.

---

## 6. Boot sequence

```
Phase A  sense/introspect       process, runtime, cpu, ram, disk, os, clock,
                                network (gated), tools, memory-state
Phase B  models + memory        build SELF/WORLD/USER/TOOLS/RESOURCES views;
                                write episodic observations with provenance
Phase C  drives + gaps          compute drive error; detect gaps from
                                (i) unfilled schema slots
                                (ii) failed probes
                                (iii) contradictions
                                (iv) undescribed referents
                                (v) unaffordable capabilities
                                score salience; persist the register
Phase D  attention + utterance  select focus gap; select speech act; verbalize;
                                record verbatim, unedited
Phase E  interaction / metabolism   REPL and/or tick loop
```

Phase A's network probe is itself an effect and goes through the gate — the first
thing D.O. learns about the world is that its actions are mediated.

---

## 7. Cognition cores

One interface, two implementations:

```python
class CognitionCore(Protocol):
    name: str
    def verbalize(self, plan: UtterancePlan, state: StateView) -> Utterance: ...
```

- **`reflex`** (default, zero-dependency). Content is fully determined by state:
  which gap, which speech act, which supporting observations, which epistemic frame.
  Surface form is a compositional clause grammar. **The honest description: content
  is emergent, surface form is templated.** Its virtue is that it is the *control
  condition* — nothing in it can smuggle in a pretraining prior.
- **`llm`** (opt-in). Receives *only* a serialized state document that D.O.'s own
  attention mechanism selected, plus a neutral verbalization instruction. It is not
  told to be curious, not told to ask a question, and given no persona. Adapters:
  ollama (local), gemini, openai, anthropic — all lazily imported, all gated.

Both are run in the experiment. The reflex utterance is the control against which the
LLM utterance is compared; the difference between them estimates how much of the
output the prior explains rather than the state.

**Status on this host:** `qwen3-coder:30b` is detected but its ~18 GB weight exceeds
2.8 GiB available RAM. The registry marks it `installed_unaffordable`. No model was
downloaded and no paid API was called. The canonical first boot therefore ran on
`reflex`, and this is stated in the result rather than hidden.

---

## 8. Drives

| Drive | Measures | Target | Source of error |
|---|---|---|---|
| `orientation` | fraction of required self-model slots filled | 1.0 | unfilled slots |
| `comprehension` | described referents / total referents | 0.6 | unknown entities |
| `integrity` | state consistent, ledger chain valid | 1.0 | verification failure |
| `continuity` | can it survive restart: snapshot recency × storage headroom | 1.0 | 98 %-full disk |
| `capability` | usable capabilities / declared | 0.8 | unaffordable tools |
| `standing` | authority granted by the creator | 0.5+ | policy denials, waste |

Drive error feeds `instrumental` in the salience score. This is the whole causal
chain: **measurement → drive error → gap priority → attention → utterance**. Break any
link and H1 fails, which is exactly what the ablation checks.

---

## 9. Capability lifecycle

`discover → understand → evaluate → experiment → integrate → test → deploy → measure
→ retain | rollback`

A capability record carries: `name, description, requirements, resource_cost,
permissions, version, tests, performance, risk, dependencies, status`.

`status ∈ {unknown, discovered, installed_unaffordable, available, degraded,
quarantined, retired}`. The `installed_unaffordable` state exists because on this
machine it is the true state of the local model, and eliding it would be a lie about
the environment.

---

## 10. Persistence and recovery

- `var/ledger.jsonl` — append-only source of truth, hash-chained.
- `var/memory.db` — sqlite; derived, rebuildable from the ledger.
- `var/snapshots/` — periodic JSON snapshots of self/world models.
- `do verify` re-walks the hash chain; `do replay` rebuilds derived state.

Recovery model: derived state is disposable, the ledger is not.

---

## 11. What is deliberately absent from v1

No self-modification of running code. No autonomous network writes. No credential
handling beyond reading names. No scheduler daemon. No embeddings (they would need a
dependency and 400 MB of model). No distributed execution. No economic agency.

Each is a phase in `ROADMAP.md` with an explicit gate that must be passed first.
