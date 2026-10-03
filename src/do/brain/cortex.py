"""The cortex: a self-growing predictor of D.O.'s own life, measured in bits.

**One objective.** Everything here serves a single quantity: the number of bits needed
to describe what happens next. Prediction is compression; a better brain is one whose
description of its own life is shorter. Every mechanism below is paid in that one
currency, which is what the first brain design lacked - seven organs, seven learning
rules, and no common measure of whether any of them helped.

**Units, not edges.** Knowledge is held by *units*. A unit is a small conjunctive
context ("disk=0 now AND snapshot age=3 now") attached to one target variable, holding
counts of what that variable did next whenever the context was true. A unit with an
empty context is the target's base rate and never dies. Pairwise associations cannot
represent "this matters only when that is also true"; a conjunction can.

The life of a unit:

  born        on SURPRISE, by CONTRASTIVE RECALL: among remembered surprises of the
              same target, what was present the times it came out this way and absent
              the times it came out another way? A birth needs that evidence; with no
              contrast in memory there is no birth, so noise does not breed structure.
  weighted    by log-linear pooling, p(x) ~ exp(sum_u w_u log p_u(x)). A newborn has
              weight 0 - no say until gradient on code length says it helps. Pooling
              multiplies independent evidence: three weak clues, one confident guess.
  paid        its exact leave-one-out value in bits each time it is active: how much
              worse the mixture would have coded the outcome without it.
  charged     rent, as a mortgage: it owes its own description length (MDL) once, paid
              per activation and per tick of existence until its lifetime savings cover
              it. Unused structure is not free. Once paid off it stays for as long as
              its recent contribution is not negative.
  ruptured    when a reliable unit is suddenly and repeatedly wrong (its recent loss
              far above its long-run loss), it forgets most of its counts at once.
              Change is detected per unit, from the unit's own statistics.
  generalized when it is rich: it tries the same rule with one condition dropped. If
              that condition never mattered, the general rule is active more often,
              earns more, and the specific one starves.
  dead        when its balance goes negative.

Each target's **fertility** is the measured success rate of its children - a target
whose births keep dying gets fewer of them.

**Lineage, credited.** Context mixing (PAQ, Mahoney); MDL (Rissanen); context-tree
methods and the MC-AIXI-CTW agent (Veness et al. 2011), the closest prior work: a
compressor as an agent's world model; latent-cause memory formation on surprise
(Gershman); contrast-set / emerging-pattern mining (Dong & Li 1999); compression
progress (Schmidhuber). What is tested here is the combination.

Stdlib only. No I/O: the cortex is pure computation and cannot reach the gate.
"""
from __future__ import annotations

import math
import random
from collections import deque

LN2 = math.log(2.0)
ACT = "act"
BEL = "~"                       # prefix of an inner sense: "~disk" = expected disk
LEVELS = ("lo", "mid", "hi")


def sym(var: str, val, lag: int) -> str:
    return f"{var}={val}@{lag}"


class Unit:
    __slots__ = ("target", "ctx", "counts", "total", "w", "balance", "acts", "born",
                 "cost", "matured", "fast", "slow", "ruptures", "earned", "recent",
                 "innate")

    def __init__(self, target: str, ctx: tuple, n: int, w: float, born: int,
                 cost: float):
        self.target = target
        self.ctx = ctx
        self.counts = [0.0] * n
        self.total = 0.0
        self.w = w
        self.cost = cost
        self.balance = cost          # endowment: a newborn can afford one half-life
        self.acts = 0
        self.born = born
        self.matured = False
        self.fast: float | None = None
        self.slow: float | None = None
        self.ruptures = 0
        self.earned = 0.0            # lifetime bits saved, undecayed
        self.recent = 0.0            # recent bits saved per activation
        self.innate = False          # wiring present at birth: never charged, never dies

    @property
    def paid_off(self) -> bool:
        """MDL: a unit owes its description length once. Once its lifetime savings
        exceed that, it has paid for itself, and only has to keep not doing harm."""
        return self.earned >= self.cost and self.acts >= 30

    def logprobs(self, alpha: float) -> list[float]:
        denom = self.total + alpha * len(self.counts)
        return [math.log((c + alpha) / denom) for c in self.counts]

    def to_dict(self, values: tuple, alpha: float) -> dict:
        lp = self.logprobs(alpha)
        best = max(range(len(lp)), key=lambda i: lp[i])
        return {"target": self.target, "context": list(self.ctx),
                "predicts": values[best], "p": round(math.exp(lp[best]), 3),
                "weight": round(self.w, 3), "balance_bits": round(self.balance, 2),
                "activations": self.acts, "cost_bits": round(self.cost, 2),
                "ruptures": self.ruptures}


class Cortex:
    def __init__(self, variables: dict, actions: tuple, *, lags: int = 3,
                 max_order: int = 3, capacity: int = 96, seed: int = 0,
                 alpha: float = 0.4, eta: float = 0.02, w_init: float = 0.0,
                 w_max: float = 4.0, count_cap: float = 255.0,
                 half_life: float = 300.0, existence_half_life: float = 1200.0,
                 surprise_bits: float = 0.3, memory: int = 64,
                 evidence_z: float = 2.0, pair_birth: float = 0.3,
                 rupture_bits: float = 2.0,
                 growth: bool = True, rent: bool = True, episodic: bool = True,
                 flat: bool = False, fertility: bool = True,
                 generalize: bool = True, rupture: bool = True,
                 beliefs: bool = False, innate: bool = False,
                 sweep_every: int = 25):
        self.rng = random.Random(seed)
        self.values = {v: tuple(vals) for v, vals in variables.items()}
        self.values[ACT] = tuple(actions)
        self.targets = [v for v in variables]          # actions are chosen, not predicted
        self.beliefs = beliefs
        if beliefs:
            # Inner senses: what I expected each variable to be, and how sure I was.
            for v in self.targets:
                self.values[BEL + v] = tuple(f"{x}/{c}" for x in self.values[v]
                                             for c in LEVELS)
        self._bel: dict = {}
        self._conf: dict = {}
        self.vidx = {v: {x: i for i, x in enumerate(vals)}
                     for v, vals in self.values.items()}
        self.lags, self.max_order, self.capacity = lags, max_order, capacity
        self.alpha, self.eta, self.w_init, self.w_max = alpha, eta, w_init, w_max
        self.count_cap, self.H, self.H_exist = count_cap, half_life, existence_half_life
        self.surprise_bits, self.pair_birth = surprise_bits, pair_birth
        self.evidence_z, self.rupture_bits = evidence_z, rupture_bits
        self.growth, self.rent, self.episodic = growth, rent, episodic
        self.use_fertility, self.sweep_every = fertility, sweep_every
        self.generalize, self.rupture = generalize, rupture
        n_sym = sum(len(v) for v in self.values.values()) * lags
        self.sym_bits = math.log2(max(2, n_sym))

        self.history: deque = deque(maxlen=lags)
        self.units: dict[str, dict[tuple, Unit]] = {v: {} for v in self.targets}
        self.index: dict[str, dict[str, list[Unit]]] = {v: {} for v in self.targets}
        self.root: dict[str, Unit] = {}
        self.tomb: dict[str, dict[tuple, int]] = {v: {} for v in self.targets}
        self.surprises: dict[str, deque] = {v: deque(maxlen=memory)
                                            for v in self.targets}
        self.kids: dict[str, list[int]] = {v: [0, 0] for v in self.targets}  # ok, failed
        self.t = 0
        self.births = self.deaths = self.ruptures = 0
        self._cache: dict = {}
        self._active: set = set()
        self._active_list: list = []

        for v in self.targets:
            r = Unit(v, (), len(self.values[v]), 1.0, 0, 0.0)
            self.root[v] = r
            self.units[v][()] = r

        if flat or innate:
            # Every first-order unit exists from birth. `flat` alone is an ablation
            # (nothing grows or dies: online logistic regression over all lagged
            # symbols). `innate` keeps growth on top: a dense, permanent first-order
            # layer - wiring present at birth - with conjunctions grown and paid for.
            if flat:
                self.growth = self.rent = False
            for v in self.targets:
                for var, vals in self.values.items():
                    for lag in range(lags):
                        for val in vals:
                            u = self._add(v, (sym(var, val, lag),), w=self.w_init)
                            u.innate = True

    # ---- structure ---------------------------------------------------------
    def _cost(self, ctx: tuple, target: str) -> float:
        """Description length of a unit: naming its context plus its parameters."""
        k = len(self.values[target]) - 1
        return len(ctx) * self.sym_bits + 0.5 * k * math.log2(self.H)

    def _add(self, v: str, ctx: tuple, w: float | None = None) -> Unit:
        u = Unit(v, ctx, len(self.values[v]), self.w_init if w is None else w, self.t,
                 self._cost(ctx, v))
        self.units[v][ctx] = u
        self.index[v].setdefault(ctx[0], []).append(u)
        self.births += 1
        return u

    def _remove(self, u: Unit) -> None:
        v = u.target
        del self.units[v][u.ctx]
        lst = self.index[v][u.ctx[0]]
        lst.remove(u)
        if not lst:
            del self.index[v][u.ctx[0]]
        self.tomb[v][u.ctx] = self.t + int(2 * self.H)
        self.deaths += 1
        if not u.matured:
            self.kids[v][1] += 1

    def fertility(self, v: str) -> float:
        """Success rate of this target's children, Laplace-smoothed, floored."""
        ok, failed = self.kids[v]
        return max(0.05, (ok + 1.0) / (ok + failed + 2.0))

    # ---- perception and prediction -----------------------------------------
    def predict(self, frame: dict, action) -> dict[str, list[float]]:
        """Take in the current frame and the action just chosen; predict the next frame."""
        self.history.appendleft({**frame, ACT: action, **self._bel})
        active = [sym(var, val, lag) for lag, fr in enumerate(self.history)
                  for var, val in fr.items()]
        self._active_list = active
        self._active = aset = set(active)
        out: dict[str, list[float]] = {}
        cache = {}
        for v in self.targets:
            idx = self.index[v]
            units = [self.root[v]]
            for s in active:
                for u in idx.get(s, ()):
                    if all(c in aset for c in u.ctx[1:]):
                        units.append(u)
            n = len(self.values[v])
            lps = [u.logprobs(self.alpha) for u in units]
            logits = [0.0] * n
            for u, lp in zip(units, lps):
                w = u.w
                if w:
                    for i in range(n):
                        logits[i] += w * lp[i]
            m = max(logits)
            ex = [math.exp(x - m) for x in logits]
            z = sum(ex)
            p = [e / z for e in ex]
            cache[v] = (units, lps, logits, p)
            out[v] = p
        self._cache = cache
        if self.beliefs:
            self._bel = {BEL + v: self._expectation(v, p) for v, p in out.items()}
        return out

    def _expectation(self, v: str, p: list[float]) -> str:
        """Discretize a prediction into an inner sense. Fed back as input next tick, it
        lets units condition on what the brain believed, not only on what it saw - a
        recurrent belief state built from its own predictions (cf. predictive state
        representations, Littman & Sutton 2002), which carries evidence further back
        than the raw history window."""
        i = max(range(len(p)), key=lambda k: p[k])
        top = p[i]
        # Levels are relative to this variable's own history of confidence: "more sure
        # than I usually am about this" is informative even where certainty is never
        # reached (a hidden cause seen through noisy effects).
        mu, var = self._conf.get(v, (top, 0.01))
        mu += 0.02 * (top - mu)
        var += 0.02 * ((top - mu) ** 2 - var)
        self._conf[v] = (mu, var)
        sd = max(1e-3, var ** 0.5)
        level = "hi" if top > mu + 0.5 * sd else "lo" if top < mu - 0.5 * sd else "mid"
        return f"{self.values[v][i]}/{level}"

    # ---- learning ----------------------------------------------------------
    def update(self, nxt: dict) -> float:
        """Observe what actually happened; learn; grow; pay rent. Returns bits spent."""
        self.t += 1
        total_bits = 0.0
        decay = 1.0 - 1.0 / self.H
        for v in self.targets:
            units, lps, logits, p = self._cache[v]
            xi = self.vidx[v][nxt[v]]
            logp = math.log(max(p[xi], 1e-300))
            bits = -logp / LN2
            total_bits += bits
            n = len(p)
            for u, lp in zip(units, lps):
                if u.ctx and self.rent and not u.innate:
                    # exact leave-one-out: the mixture without this unit
                    w = u.w
                    if w:
                        lm = [logits[i] - w * lp[i] for i in range(n)]
                        mm = max(lm)
                        lse = mm + math.log(sum(math.exp(x - mm) for x in lm))
                        contrib = (logp - (lm[xi] - lse)) / LN2
                    else:
                        contrib = 0.0
                    u.earned += contrib
                    u.recent += (contrib - u.recent) / self.H
                    if not u.paid_off:
                        u.balance = u.balance * decay + contrib - u.cost / self.H
                    if not u.matured and u.paid_off:
                        u.matured = True
                        self.kids[v][0] += 1
                u.acts += 1
                if self.rupture:
                    self._watch(u, -lp[xi] / LN2)
                g = lp[xi] - sum(p[i] * lp[i] for i in range(n))
                u.w = min(self.w_max, max(0.0, u.w + self.eta * g))
                u.counts[xi] += 1.0
                u.total += 1.0
                if u.total > self.count_cap:
                    u.counts = [c * 0.5 for c in u.counts]
                    u.total *= 0.5
            if self.growth and bits > self.surprise_bits:
                if not self.use_fertility or self.rng.random() < self.fertility(v):
                    self._grow(v, xi, units)
                self.surprises[v].append((xi, self._active))
        if self.rent and self.t % self.sweep_every == 0:
            self._sweep()
            if self.growth and self.generalize:
                self._generalize()
        return total_bits

    def _watch(self, u: Unit, b: float) -> None:
        """Rupture detection: a unit whose recent code length jumps far above its own
        long-run code length has seen its rule break. It keeps a trace of the old
        counts, so a rule that comes back is relearned faster than from nothing."""
        if u.fast is None:
            u.fast = u.slow = b
            return
        u.fast += 0.25 * (b - u.fast)
        u.slow += 0.02 * (b - u.slow)
        if u.acts > 30 and u.fast > u.slow + self.rupture_bits:
            u.counts = [c * 0.05 for c in u.counts]
            u.total *= 0.05
            u.fast = u.slow
            u.ruptures += 1
            self.ruptures += 1

    def _grow(self, v: str, xi: int, units: list[Unit]) -> None:
        """Specialize on surprise: extend an active unit by what recall says mattered."""
        parents = [u for u in units if len(u.ctx) < self.max_order]
        if not parents:
            return
        parent = self.rng.choice(parents)
        pctx = set(parent.ctx)
        pool = [s for s in self._active_list if s not in pctx]
        if not pool:
            return
        if self.episodic:
            ext, enough = self._recall(v, xi, pctx, pool)
            if ext is None:
                if enough:
                    return            # memory shows no contrast: no evidence, no birth
                ext = self._random_ext(pctx, pool)
        else:
            ext = self._random_ext(pctx, pool)
        self._try_add(v, tuple(sorted(pctx | set(ext))))

    def _random_ext(self, pctx: set, pool: list) -> list:
        k = 2 if (len(pctx) + 2 <= self.max_order and len(pool) >= 2
                  and self.rng.random() < self.pair_birth) else 1
        return self.rng.sample(pool, k)

    def _recall(self, v: str, xi: int, pctx: set, pool: list) -> tuple[list | None, bool]:
        """Contrastive episodic recall. Returns (extension, memory_was_sufficient).

        Among remembered surprises of this target that happened in the parent's context,
        compare the ones that came out the way this one did with the ones that did not:
        what was present then, and now, and absent when the outcome differed? Single
        symbols are scored directly; pairs are drawn from what this moment shares with
        one earlier moment of the same surprise, because a joint cause (XOR) is
        invisible to every single symbol and only shows up as a coincidence of two.
        A candidate must clear a significance bar, or there is no birth at all.
        """
        mem = [(x, s) for x, s in self.surprises[v] if pctx <= s]
        pos = [s for x, s in mem if x == xi]
        neg = [s for x, s in mem if x != xi]
        if len(pos) < 3 or len(neg) < 3:
            return None, False
        cands: list[tuple] = [(s,) for s in pool]
        if len(pctx) + 2 <= self.max_order:
            then = self.rng.choice(pos[:-1])
            shared = [s for s in pool if s in then]
            pairs = [(a, b) for i, a in enumerate(shared) for b in shared[i + 1:]]
            if len(pairs) > 40:
                pairs = self.rng.sample(pairs, 40)
            cands += pairs
        np_, nn = len(pos) + 1.0, len(neg) + 1.0
        se = math.sqrt(0.25 * (1.0 / np_ + 1.0 / nn))
        best, best_sc = [], None
        for c in cands:
            ctx = tuple(sorted(pctx | set(c)))
            if ctx in self.units[v] or self.tomb[v].get(ctx, -1) > self.t:
                continue
            a = sum(1 for e in pos if all(x in e for x in c))
            b = sum(1 for e in neg if all(x in e for x in c))
            sc = (a + 0.5) / np_ - (b + 0.5) / nn
            # The bar rises with order: there are far more candidate pairs than
            # singles, so a pair needs more evidence to not be a fluke of the search.
            margin = sc - self.evidence_z * len(c) * 0.5 * se
            if margin <= 0:
                continue
            if best_sc is None or margin > best_sc + 1e-9:
                best, best_sc = [c], margin
            elif abs(margin - best_sc) <= 1e-9:
                best.append(c)
        if not best:
            return None, True
        return list(self.rng.choice(best)), True

    def _try_add(self, v: str, ctx: tuple) -> None:
        if ctx in self.units[v] or self.tomb[v].get(ctx, -1) > self.t:
            return
        if len(self.units[v]) >= self.capacity and not self._evict(v):
            return
        self._add(v, ctx)

    def _generalize(self) -> None:
        """Generalize on success: a unit that is paying its way tries the same rule
        with one condition removed. If the condition never mattered, the general
        version is active more often, earns more, and the specific one is left
        redundant and dies of its own rent."""
        for v in self.targets:
            rich = [u for u in self.units[v].values()
                    if len(u.ctx) >= 2 and u.acts >= 30 and u.paid_off]
            for u in rich:
                if self.rng.random() < 0.2:
                    drop = self.rng.choice(u.ctx)
                    self._try_add(v, tuple(c for c in u.ctx if c != drop))

    def _evict(self, v: str) -> bool:
        """Make room by removing the poorest unit that has had a chance to prove itself."""
        eligible = [u for u in self.units[v].values()
                    if u.ctx and not u.innate and u.acts >= 20]
        if not eligible:
            return False
        def worth(u: Unit) -> float:
            if u.paid_off:
                return 1.0 + u.recent * self.H / max(1.0, u.cost)
            return u.balance / max(1.0, u.cost)
        self._remove(min(eligible, key=worth))
        return True

    def _sweep(self) -> None:
        """Existence rent, then death. Rent per tick means structure that is never
        used is not free: it must eventually be active and useful, or it goes."""
        due = self.sweep_every / self.H_exist
        for v in self.targets:
            dead = []
            for u in self.units[v].values():
                if not u.ctx or u.innate:
                    continue
                if u.paid_off:
                    if u.recent < -0.01:
                        dead.append(u)          # it used to help; lately it harms
                    continue
                u.balance -= u.cost * due
                if u.balance < 0:
                    dead.append(u)
            for u in dead:
                self._remove(u)

    # ---- introspection -----------------------------------------------------
    def size(self) -> int:
        return sum(len(u) - 1 for u in self.units.values())

    def grown(self) -> int:
        """Units the brain built itself, as opposed to wiring it was born with."""
        return sum(1 for us in self.units.values() for u in us.values()
                   if u.ctx and not u.innate)

    def explain(self, target: str | None = None, top: int = 5) -> list[dict]:
        """The structure the cortex has kept, strongest first. This is `do why` for
        beliefs: every prediction traces to named units with a balance in bits."""
        out = []
        for v in ([target] if target else self.targets):
            us = sorted((u for u in self.units[v].values() if u.ctx),
                        key=lambda u: -u.balance)[:top]
            out.extend(u.to_dict(self.values[v], self.alpha) for u in us)
        return out

    def stats(self) -> dict:
        return {"units": self.size(), "grown": self.grown(),
                "births": self.births, "deaths": self.deaths,
                "ruptures": self.ruptures,
                "fertility": {v: round(self.fertility(v), 3) for v in self.targets}}
