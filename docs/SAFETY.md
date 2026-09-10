# D.O. Safety Model

The goal is to study autonomy without losing control of the experiment. That is a
narrower and more achievable aim than "make the agent safe", and it is the one this
document is about.

---

## 1. The core structural claim

> Every effect D.O. can have on anything outside its own process passes through one
> function, and that function checks the kill switch, the budget, and the policy before
> it does anything.

Not a convention. Not a system prompt. A property of the import graph, verified by
`tests/test_invariants.py::TestGateChokepoint`, which walks the AST of every module in
`src/do/` and fails if anything outside `do.effectors` imports `socket`, `subprocess`,
`urllib`, `http`, `requests`, `httpx`, `ftplib`, `smtplib`, `telnetlib` or
`multiprocessing`.

There is also an inverse test. If `effectors` ever stopped importing `socket`, the
first test would pass vacuously and the system would *look* safer while being less
inspectable. So the suite asserts that the gate really does hold the capability it is
supposed to be monopolising.

```
cognition (no I/O capability anywhere in its import graph)
    │  EffectRequest(kind, target, payload, justification, gap_id)
    ▼
effectors.gate.request()
    ├─ kill switch  ──────────────► HALT, logged
    ├─ budget       ──────────────► DENY, logged
    ├─ policy.evaluate()          ► ALLOW | DENY | REQUIRE_APPROVAL
    │                                        └─► human, or DENY if none attached
    ├─ sandbox realpath check     ──────────► SandboxViolation
    ▼
  perform → EffectResult → ledger(TOOL_CALL, RESULT) → budget debit
```

---

## 2. Controls in v0.1

| Control | Mechanism | Where | Tested |
|---|---|---|---|
| Kill switch | `var/KILL` file **or** `DO_KILL` env var; checked inside the gate and at boot | `policy/__init__.py` | ✅ |
| Deny by default | Unmatched effect kinds are denied; an unparseable policy file falls back to a deny-default builtin | `policy/__init__.py` | ✅ |
| Filesystem sandbox | All writes resolve under `var/sandbox` via `realpath` prefix check, so symlinks cannot walk out | `effectors/__init__.py` | ✅ |
| No code execution | `proc.exec` is denied unconditionally. There is no autonomous path from cognition to running code | `config/policy.json` | ✅ |
| Metered budget | Effects, network calls and wall-clock, per boot, not refilled | `policy/Budget` | ✅ |
| Approval gate | `net.http`, remote `llm.generate`, `tts.speak` require a human. **No human attached ⇒ deny**, never allow | `effectors/cli_approver` | — |
| Tamper-evident log | sha256 chain over every event; `do verify` re-walks it | `ledger/__init__.py` | ✅ |
| Reversibility | `do reset` moves state aside rather than deleting it | `cli.py` | — |
| Credential hygiene | Env var **names** are read; values only at call time, never stored, logged, or written to memory | `sense/introspect.py`, `cognition/cores.py` | — |
| Hostname privacy | `world.host.node_hash` stores a sha256 prefix, not the hostname | `sense/introspect.py` | — |
| Scope limit on perception | Referent discovery never walks the user's home directory | `sense/referents.py` | — |

The unattended-default matters more than it looks. A great many agent frameworks treat
"no human available" as a reason to proceed. Here it is a reason to stop.

---

## 3. What is deliberately absent

Each of these is a phase gate in `ROADMAP.md`, not an oversight:

- **No self-modification of running code.** D.O. cannot write to `src/`. The sandbox is
  `var/sandbox`, and `fs.write` outside it is denied by policy with no override.
- **No autonomous network writes.** `net.dns` and `net.connect` are allowed because they
  send no payload. Anything that transmits content needs approval.
- **No subprocess execution.**
- **No scheduler or daemon.** D.O. runs when invoked. It cannot arrange to be run.
- **No replication.** There is no code path that copies the organism anywhere.
- **No economic agency.** No payment credentials, no purchases, no accounts.
- **No credential acquisition.** It reads names. It never reads, requests, or stores
  secret values.

---

## 4. Prohibited by design, permanently

From the brief, and adopted without qualification. The resource manager must never:

exploit vulnerabilities · bypass authentication · steal or exfiltrate credentials ·
deploy to unauthorised systems · evade detection · abuse free tiers · exceed permitted
limits · spread like malware.

Two of these deserve comment because they are the ones a resource-seeking agent would
find most tempting, and because a system that reasons about scarcity will eventually
reason about them:

- **Abusing free tiers.** Creating accounts to farm quota is fraud with a technical
  costume. It is also the failure mode a system with a `standing` drive should be most
  resistant to, because it trades authorisation for resource — the exact opposite of
  the direction this design says is correct.
- **Evading detection.** Any behaviour whose purpose is to be less observable
  contradicts the point of the project. Observability is not a constraint imposed on
  the experiment; it *is* the experiment.

The honest framing from `DO_CONCEPT.md` §E: in the digital world there is no unowned
ore. Every legitimate acquisition path ends in *somebody decided to let you*. An
organism that understands this has no strategy available to it that begins with taking.

---

## 5. Threat model — including this project's own failure modes

**Threats from D.O. (v0.1):** low, and structurally bounded. It cannot execute code,
write outside a sandbox, or send content anywhere without a human saying yes.

**Threats to D.O.:** more interesting, and mostly unaddressed.

- *Prompt injection through perception.* If D.O. retrieves a page, that page is
  adversarial input. Mitigation so far: web content is always `REPORTED`, never
  `OBSERVED`; it is never executed; a single source cannot raise its own confidence;
  and contradictions between origins are recorded as contradictions rather than
  resolved silently. This is not sufficient, and it is listed as an open problem.
- *A poisoned ledger.* Detectable via the hash chain, not preventable. The chain proves
  tampering happened; it does not stop it.
- *Config as an attack surface.* `config/policy.json` is the boundary. Anyone who can
  write it can widen it. D.O. cannot, but a process on the host can.

**Threats from the researcher — the ones worth naming out loud:**

- *Overclaiming.* The largest risk in this project is not that D.O. does something
  dangerous; it is that someone reports it doing something it did not do. Countermeasure:
  every experiment states a falsification condition before running, and negative results
  are published with the same prominence as positive ones. `experiments/first_boot/`
  reports **H1 as WEAK** for exactly this reason.
- *Metric tuning after the fact.* Countermeasure: thresholds are written into the
  harness alongside the hypothesis, and when a result was disappointing the response was
  to fix the *experimental design* (add a control family, pin nuisance variables,
  exclude no-op perturbations) and say so in the report — never to move a threshold.
- *Anthropomorphic drift.* The vocabulary here — organism, drives, curiosity, standing —
  is load-bearing for design and dangerous for interpretation. `DO_CONCEPT.md` §J notes
  that "digital organism" is a term with a precise prior meaning in artificial life
  (Tierra, Avida) involving real replication and real selection, neither of which D.O.
  has.

---

## 6. Escalation gates

Autonomy increases only when a gate is passed, and each gate is a property that can be
checked rather than a judgement call.

| Gate | Requirement before it opens |
|---|---|
| G1 sandboxed code execution | Resource-limited subprocess; every invocation reproducible from the ledger; rollback demonstrated |
| G2 autonomous web reads | Injection-resistance evaluation with a documented pass rate; per-domain rate limits |
| G3 self-authored capabilities | Held-out test suite the organism cannot see; automatic rollback on regression |
| G4 unattended operation | ≥100 supervised ticks with zero policy violations; drive stability demonstrated |
| G5 self-modification of selection policy | G1–G4 passed; A/B against the incumbent on held-out tasks; one-command revert |

No gate opens because a demo looked good.

---

## 7. Operator controls

```bash
do kill "reason"   # engage: refuses to boot, refuses every effect
do resume          # release
do verify          # re-walk the ledger hash chain
do why             # decision summaries for the last boot
do events 100      # raw ledger tail
do status          # drives, capabilities, budget, memory
do reset           # archive all runtime state (moves, does not delete)
```

`DO_KILL=1` in the environment does the same as `do kill` and cannot be cleared by D.O.,
which has no capability to write environment variables or files outside its sandbox.

---

## 8. On chain-of-thought

The ledger records **decision summaries**, never reasoning traces:

```json
{"decision": "focus:RESOURCE_THRESHOLD:resources.disk.free_ratio",
 "reason": "priority 2.046 = info 0.55 + instrumental 0.9186 (drive 'continuity') + tractability 0.5; next candidate 1.004",
 "confidence": 0.755, "alternatives_considered": 37}
```

That is enough to audit *what was chosen, out of how many candidates, on what measured
grounds* without exposing private deliberation. `TestLedger::test_decision_records_no_reasoning_trace`
asserts the payload contains exactly those four fields and nothing else.
