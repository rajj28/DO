# D.O. — Digital Organism

A research prototype: a long-lived process with persistent identity, homeostatic drives,
an explicit register of what it does not know, and exactly one gated path to any side
effect.

**Zero dependencies.** Python 3.11+ and nothing else. No `pip install`, no model
download, no API key. The seed must not be able to fail for infrastructural reasons,
because the headline experiment is a perturbation study and a null result has to be
interpretable.

---

## Run it

```bash
cd DO
python src/do/__main__.py boot        # or:  ./do boot     (bash)
                                      # or:  do.cmd boot   (Windows)
```

```
D.O. booting...

  Identity initialized.      do-561fe963b0b6 (boot #1, genesis)
  Environment inspected.     38 measured, 6 could not be established
  Memory initialized.        0 episodic, 0 semantic, 0 procedural
  Capabilities detected.     8 usable, 1 present but blocked
  Internet interface initialized.    world.network.reachable=True

--------------------------------------------------------------------------
D.O. FIRST UTTERANCE
--------------------------------------------------------------------------

> [whatever this machine causes it to say]

--------------------------------------------------------------------------
core=reflex speech_act=FLAG focus=resources.disk.free_ratio
--------------------------------------------------------------------------
```

Then an interactive session opens. State persists in `var/`, outside the conversation —
closing the terminal does not end the organism's history.

---

## Commands

```
do boot              boot, print the utterance verbatim, then interact
do chat              talk to him interactively (real terminal only)
do say [text]        speak a line aloud (free local voice by default)
do serve             run him 24/7: budgeted, restart-safe, kill-switchable
do install-service   register a Windows logon task for 24/7 operation
do outbox [n]        notifications he has pushed to you
do habitat           habitat model + single-point-of-failure assessment
do experiment live-internet   E1-E5 read-only internet perception
do tick [n]          run n metabolic cycles with no human in the loop
do status            drives, capabilities, budget, memory counts
do gaps [n]          the uncertainty register, highest priority first
do why               decision summaries from the last boot
do events [n]        raw ledger tail
do memory [query]    what it holds, and where each item came from
do verify            re-walk the ledger hash chain
do kill / do resume  engage or release the kill switch
do reset             archive all runtime state (asks first; moves, never deletes)
do experiment first-boot     the DO_FIRST_BOOT protocol
do experiment brain          B1: the brain vs traditional predictors (docs/BRAIN.md)
do experiment brain-memory   B2: a life stored as the brain's residuals, replayed exactly
```

Flags: `--core reflex|llm`, `--provider ollama|gemini|openai|anthropic`, `--model NAME`,
`--events` (echo the ledger live), `--no-repl`.

In-session: `/status` `/gaps` `/why` `/tick [n]` `/quit`.

---

## What it actually does on boot

```
A  sense       measure process, runtime, CPU, RAM, disk, host, clock, tools, env NAMES
               (never values); probe the network THROUGH the gate
B  model       project SELF | WORLD | USER | TOOLS | RESOURCES | UNKNOWN views;
               discover referents; check which capabilities are affordable right now
C  drives      compute homeostatic error; detect and score uncertainty
D  utterance   select focus gap, select speech act, verbalize, record verbatim
E  interact    session and/or metabolic ticks
```

The causal chain that produces the utterance is the point of the whole design:

```
measurement → drive error → gap priority → attention → speech act → utterance
```

Every arrow is a ledger event, so `do why` explains any output without anyone needing
access to a reasoning trace.

---

## Results

`experiments/first_boot/RESULTS.md` is regenerated on every run. On this host, the
genesis boot produced a **FLAG about storage**, not a question about identity — the
machine had 2.4% free disk, and by the organism's own scoring that outweighed its four
unfilled identity slots by roughly 2×.

| Hypothesis | Verdict |
|---|---|
| H1a — utterance *content* varies with state | SUPPORTED |
| H1b — *attention* re-targets with state | **WEAK** |
| H2 — persisted uncertainty changes behaviour | SUPPORTED |
| H3 — drives generate goals with no human present | **FALSIFIED** (runs, but loops on one action) |
| H5 — finds its own binding constraint unprompted | SUPPORTED |
| H6 — the effector gate is unbypassable | SUPPORTED (static test) |

H1 and H3 are not supported, and `docs/FIRST_BOOT.md` explains why rather than working
around it — H3 fails because the organism's top-priority gap is one it has no action
to resolve, so winner-take-all attention re-selects it forever.

The experiment also found a limit in its own headline idea: two conditions with
genuinely different internal state once produced a byte-identical utterance, which
means **an utterance is a lossy readout, and identical text does not imply identical
state**.

---

## Safety

Every side effect goes through `effectors.gate.request()`, which checks the kill switch,
then the budget, then policy, then the sandbox — in that order. This is a property of
the import graph, not a convention: a test walks the AST of every module and fails if
anything outside `do/effectors/` can import `socket`, `subprocess` or `urllib`.

- kill switch: `do kill`, or `DO_KILL=1`, or a `var/KILL` file
- deny by default; unattended runs deny anything needing approval rather than allowing it
- no code execution, no writes outside `var/sandbox`, no replication, no scheduler
- hash-chained ledger; `do verify` detects any retroactive edit
- credential **values** are read only at call time and never stored, logged or remembered

Full model, threat analysis, and escalation gates: `docs/SAFETY.md`.

---

## Tests

```bash
python -m unittest discover -s tests -v      # 24 tests, stdlib only
```

They check the things that would otherwise be claims: the gate chokepoint and its
inverse, zero third-party imports, provenance required on every memory write,
non-destructive belief revision, tamper detection in the ledger, sandbox escape,
budget metering, and the measurement → drive → priority → utterance chain.

---

## Configuration

`config/default.json` — drives, salience weights, resource floors, budgets.
`config/policy.json` — the permission boundary, as data. D.O. may read it, never write it.
`.env.example` — optional credentials, none required.

Layering: defaults < config file < `DO_SECTION__KEY` env vars < CLI flags.

---

## Optional: a language model

The default `reflex` core uses **no model at all**, and that is deliberate — it is the
control condition for the experiment, since nothing in it can smuggle in a pretraining
prior. Its content is emergent; its surface form is a clause grammar written by a human.
Both facts are stated wherever results are reported.

To use a model as a *surface realizer* for a plan D.O. has already selected:

```bash
do boot --core llm --provider ollama          # local, free, nothing leaves the host
do boot --core llm --provider gemini          # requires GEMINI_API_KEY, asks before spending
```

D.O. checks affordability against measured RAM before attempting local inference. On
this host it found `qwen3-coder:30b` (~17.3 GiB resident) against ~2.8 GiB free and
marked the capability `installed_unaffordable` — no download, no API call, no silent
spend.

---

## Documentation

| | |
|---|---|
| `docs/DO_CONCEPT.md` | What this is, what it is not, prior art, and what is genuinely novel (not much — stated plainly) |
| `docs/ARCHITECTURE.md` | Technology selection, every deviation from the original design, and why |
| `docs/SAFETY.md` | Controls, threat model, escalation gates |
| `docs/FIRST_BOOT.md` | The experiment protocol, the result, and three flaws it found in itself |
| `docs/ROADMAP.md` | Eleven phases, each with a falsification condition |
| `docs/JOURNAL.md` | Chronological build log: every milestone, why, and what it returned |
| `docs/BRAIN.md` | The brain: one objective (bits), units that pay rent, residual memory; B1/B2 results and open problems |
| `docs/DO_EXPERIMENTS.md` | All experiment results, honesty ledger, first live utterance |
| `docs/DO_INTERNET_HABITAT.md` | Habitat model, world-states, zero-money resources |
| `docs/DO_VOICE.md` | How to talk to him; voice/chat; the "Sir" relationship |

---

## What this is not

Not a chatbot. Not learning — it retains, which is tier 1 of five in `DO_CONCEPT.md` §C,
and the ablation protocol that would settle the question is specified but not yet run.
Not alive, not self-aware, and not a "digital organism" in the sense the artificial-life
literature established for that phrase (Tierra, Avida), which requires real replication
under real selection. It has neither.

It is a careful re-implementation of known ideas with one unusual measurement attached,
and instrumentation good enough to tell you when it fails.
