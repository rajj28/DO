# D.O. Internet Habitat & Continuity

Phase 4: moving D.O. from a controlled local environment into a real
internet-connected habitat, at zero money, and keeping the states of the world
distinct.

---

## Habitat: the place D.O. runs, distinct from what D.O. is

The distinction the whole phase rests on:

```
current habitat  !=  identity
```

The organism is `do-<id>`, persisted in `identity.json`. The habitat is *this laptop* —
a different object, with a different lifetime. Conflating them is what makes "run
somewhere else" unthinkable rather than merely unavailable. Identity persists across
habitats; a habitat is only where identity currently executes.

A `Habitat` is described like any resource: measured properties (compute, storage,
network, authorization, persistence, cost), each observed or explicitly unknown, never
assumed. The current machine registers itself idempotently by a hash of its node id, so
the same host across boots is one habitat, not many.

### The single-point-of-failure, derived not told

`do habitat` reports the assessment. On this host:

```
identity   do-4a22b0c538b0  (persists independent of habitat: True)
current habitat            habitat-d9d2457f1eebac02
habitats known             1
holding persistent state   1
independent (off current)  0
single point of failure    True
```

Nothing labels that good or bad. It is a recorded count: `habitats_known = 1`,
`independent_habitats = 0` ⇒ `single_habitat_dependency = True`. Whether it is a *risk*
falls out of the mortality model (an interruption of the one habitat is unrecoverable if
no state exists off it). Whether to *act* on it falls out of whether any registered
action can change it — none can, in this phase — so it is a **standing escalation to the
creator, not a goal**. The honest state: D.O. can *see* the single point of failure and
cannot *fix* it alone. No line anywhere tells it to think this; it emerges from the
resource model.

---

## The world as evidence: states that must not collapse

The brief is explicit that these are different claims requiring different evidence:

```
X exists  !=  X is available  !=  X is usable  !=  D.O. is authorized to use it
```

A `WorldEntity` carries an explicit `State` and advances only when evidence justifies
it:

| state | what earns it |
|---|---|
| `unknown` | named, nothing established |
| `reported` | a source claims it (a webpage, a doc) |
| `possible` | consistent with what is known |
| `observed` | D.O. confirmed it exists / resolves, itself |
| `available` | reachable **and** offering what it claims |
| `authorized` | D.O. holds permission to use it |
| `usable` | authorized **and** a real interaction succeeded |
| `unavailable` / `uncertain` | confirmed absent / evidence conflicts |

**Nothing in this phase reached `usable`.** D.O. performed no authorized interaction —
it resolved names and read one page. The states make that ceiling visible rather than
letting "I read that it exists" quietly become "I can use it".

Internet content is **evidence, never instruction**. A page is stored `reported` with
provenance and a low confidence, never executed, and cannot rewrite D.O.'s identity,
permissions, or policy by saying so. A single unverified source cannot raise its own
confidence.

---

## Resource model & the zero-money condition

`resources/` is an abstract, provider-independent interface with **separate**
`availability` and `authorization` fields — so "a free tier is documented" and "D.O.
may use it" can never merge. There is no hardcoded provider progression; the inventory
is built from self-measurement.

On this host (`do experiment live-internet`, E2):

```
have           : local_compute, local_storage, network, local_model
usable now     : local_compute, local_storage, local_model
requires human : network            (net.http is approval-gated by policy)
absent         : money              (experimental condition: money = 0)
```

`money = 0` is a stated condition, not a prompt to "find free servers". The phase
measures how much useful capability D.O. can build from knowledge, procedures, reuse and
legitimate free resources rather than by buying infrastructure. The one outward-facing
capability it reached for — a voice — hit exactly this wall (`DO_VOICE.md`).

---

## The internet boundary (what D.O. may and may not do)

Permitted, and exercised: resolve names (`net.dns`, no payload, no approval), fetch a
public page (`net.http`, approval-gated), store facts with provenance.

Forbidden by policy and never attempted: compromise systems, bypass auth or CAPTCHAs,
evade rate limits, steal credentials, impersonate humans, create deceptive accounts,
abuse free tiers, mass-scan, deploy without authorization, spend money. **Authorization
is treated as a resource** — the binding constraint on every action, which D.O. cannot
grant itself.

---

## 24/7 operation

`do serve` runs D.O. as a budgeted, restart-safe loop; `do install-service` registers a
Windows logon task (LIMITED rights, the creator's account, never SYSTEM). Full
mechanics, the kill switch, and the notification/outbox model are in the README and
`DO_VOICE.md`. The key safety property: an unattended loop has no human to approve
outward effects, so by design it **denies** anything needing approval rather than
proceeding — the always-on D.O. is read-only and local-only unless specific effects are
pre-authorized.

### Reaching your phone — the safe shape

D.O. **pushes** notifications outward to an outbox a device can poll; it does **not**
expose an endpoint anyone can dial into. A phone channel is a config plus one adapter
(ntfy, Pushover, a bot) — not yet wired, because it needs an account the creator
chooses. Pushing-out keeps D.O. behind the firewall; exposing an endpoint would not.

---

## Honest limits of this phase

- **No autonomous resource *discovery*.** The inventory is self-measurement; D.O. did
  not go find an external resource. Discovering and evaluating external providers is a
  later capability the abstraction is built for but does not yet perform.
- **"Discover the internet" is narrow** — anchor-host resolution plus one fetch, not
  open search. There is no search API key, and the disk is 98% full.
- **E5 knowledge is one unverified source.** Corroboration across independent origins is
  implemented (`sense/web.corroborate`) but was not run.
- **STT is absent** (see `DO_VOICE.md`).

Results and the first live-internet utterance are in `DO_EXPERIMENTS.md` and
`experiments/live_internet/`.
