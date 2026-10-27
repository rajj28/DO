"""Baselines the brain has to beat. If it cannot, it is decoration.

Each one is a real, named method, not a strawman:

    Marginal      how often each value occurs; knows nothing about time
    Persistence   "next tick equals this tick" with a learned stay-rate. The roadmap's
                  own bar for Phase 3: anything worse than persistence is decoration.
    Markov1       each variable predicted from its own previous value
    JointTable    the classic tabular world model: the whole current frame (plus the
                  action) as the state, backed off to Markov1 when the state is rare
    HebbianV1     the first brain design proposed for D.O.: associative edges from every
                  active symbol to every outcome, learned by Rescorla-Wagner

All share the cortex interface: `predict(frame, action) -> {var: [p...]}`, then
`update(next_frame)`.
"""
from __future__ import annotations

from collections import deque

from .cortex import ACT, sym


class _Base:
    def __init__(self, variables: dict, actions: tuple, alpha: float = 0.4, **_):
        self.values = {v: tuple(x) for v, x in variables.items()}
        self.targets = list(variables)
        self.vidx = {v: {x: i for i, x in enumerate(vals)}
                     for v, vals in self.values.items()}
        self.alpha = alpha
        self.frame: dict | None = None
        self.action = None

    def _est(self, counts: list[float]) -> list[float]:
        z = sum(counts) + self.alpha * len(counts)
        return [(c + self.alpha) / z for c in counts]

    def stats(self) -> dict:
        return {}


class Marginal(_Base):
    def __init__(self, variables, actions, **kw):
        super().__init__(variables, actions, **kw)
        self.c = {v: [0.0] * len(self.values[v]) for v in self.targets}

    def predict(self, frame, action):
        return {v: self._est(self.c[v]) for v in self.targets}

    def update(self, nxt):
        for v in self.targets:
            self.c[v][self.vidx[v][nxt[v]]] += 1


class Persistence(_Base):
    def __init__(self, variables, actions, **kw):
        super().__init__(variables, actions, **kw)
        self.stay = {v: [1.0, 1.0] for v in self.targets}      # [stayed, total]

    def predict(self, frame, action):
        self.frame = frame
        out = {}
        for v in self.targets:
            n = len(self.values[v])
            s, t = self.stay[v]
            ps = (s + self.alpha) / (t + 2 * self.alpha)
            p = [(1 - ps) / max(1, n - 1)] * n
            p[self.vidx[v][frame[v]]] = ps
            out[v] = p
        return out

    def update(self, nxt):
        for v in self.targets:
            self.stay[v][0] += 1.0 if nxt[v] == self.frame[v] else 0.0
            self.stay[v][1] += 1.0


class Markov1(_Base):
    def __init__(self, variables, actions, **kw):
        super().__init__(variables, actions, **kw)
        self.c = {v: {} for v in self.targets}

    def predict(self, frame, action):
        self.frame = frame
        return {v: self._est(self.c[v].get(frame[v], [0.0] * len(self.values[v])))
                for v in self.targets}

    def update(self, nxt):
        for v in self.targets:
            row = self.c[v].setdefault(self.frame[v], [0.0] * len(self.values[v]))
            row[self.vidx[v][nxt[v]]] += 1


class JointTable(Markov1):
    """State = the entire observable frame plus the action, as one key."""

    def __init__(self, variables, actions, **kw):
        super().__init__(variables, actions, **kw)
        self.j = {v: {} for v in self.targets}

    def _key(self, frame, action):
        return (action,) + tuple(frame[v] for v in self.targets)

    def predict(self, frame, action):
        back = super().predict(frame, action)
        self.key = k = self._key(frame, action)
        out = {}
        for v in self.targets:
            row = self.j[v].get(k)
            if not row:
                out[v] = back[v]
                continue
            n = sum(row)
            lam = n / (n + 2.0)                    # trust the state once it is seen
            pj = self._est(row)
            out[v] = [lam * a + (1 - lam) * b for a, b in zip(pj, back[v])]
        return out

    def update(self, nxt):
        super().update(nxt)
        for v in self.targets:
            row = self.j[v].setdefault(self.key, [0.0] * len(self.values[v]))
            row[self.vidx[v][nxt[v]]] += 1


class HebbianV1(_Base):
    """The first proposed brain: PREDICT edges from every active symbol (all lags plus a
    bias node) to every outcome, Rescorla-Wagner learning, activation read out as a
    probability. Faithful to that design, including its weakness: edges are pairwise."""

    def __init__(self, variables, actions, lags: int = 3, rate: float = 0.1,
                 floor: float = 0.05, **kw):
        super().__init__(variables, actions, **kw)
        self.values_all = {**self.values, ACT: tuple(actions)}
        self.lags, self.rate, self.floor = lags, rate, floor
        self.history: deque = deque(maxlen=lags)
        self.V: dict[str, dict[str, list[float]]] = {v: {} for v in self.targets}

    def predict(self, frame, action):
        self.history.appendleft({**frame, ACT: action})
        self.active = ["bias"] + [sym(var, val, lag)
                                  for lag, fr in enumerate(self.history)
                                  for var, val in fr.items()]
        out, self.strength = {}, {}
        for v in self.targets:
            n = len(self.values[v])
            s = [0.0] * n
            Vv = self.V[v]
            for a in self.active:
                row = Vv.get(a)
                if row:
                    for i in range(n):
                        s[i] += row[i]
            self.strength[v] = s
            # Readout chosen in v1's favour: of the variants tried (clip at 0.01,
            # relu + 0.05/0.1 floor, rates 0.1-1.0) this was best on average.
            act = [max(0.0, x) + self.floor for x in s]
            z = sum(act)
            out[v] = [x / z for x in act]
        return out

    def update(self, nxt):
        for v in self.targets:
            n = len(self.values[v])
            xi = self.vidx[v][nxt[v]]
            s = self.strength[v]
            delta = [(1.0 if i == xi else 0.0) - s[i] for i in range(n)]
            Vv = self.V[v]
            step = self.rate / len(self.active)   # RW is stable only below 1/#cues
            for a in self.active:
                row = Vv.setdefault(a, [0.0] * n)
                for i in range(n):
                    row[i] += step * delta[i]

    def stats(self):
        return {"edges": sum(len(r) for V in self.V.values() for r in V.values())}


BASELINES = {"marginal": Marginal, "persistence": Persistence, "markov1": Markov1,
             "joint_table": JointTable, "hebbian_v1": HebbianV1}
