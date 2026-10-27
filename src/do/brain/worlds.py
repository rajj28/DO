"""Synthetic worlds with known hidden structure, for testing the brain.

Why synthetic first (docs/DO_CONCEPT.md section I): D.O.'s real machine gives sparse,
slow, mostly-boring data with no ground truth. A world whose generating rules are known
lets a result be checked against the truth instead of against intuition.

Every world exposes the same interface:

    variables   {name: tuple_of_values}   what can be observed
    actions     tuple of action names     what can be done
    observe()   -> frame                  the current observable frame
    oracle(a)   -> {var: [p...]}          TRUE distribution of the next frame given the
                                          full state, INCLUDING anything hidden
    step(a)     -> frame                  advance one tick
    policy()    -> action                 the exploration policy used for B1

The oracle is the lower bound for every model: given the complete hidden state no
history can add information, so no learner can beat it on expected code length. The
gap between a model and the oracle ("excess bits") is the quantity that matters;
the oracle's own loss is the irreducible noise each world was built with.

Each world isolates one structure a brain must be able to find:

    conjunction   an effect that depends on two causes jointly (XOR, AND): pairwise
                  associations cannot represent it
    delayed       an action whose effect lands three ticks later
    distractors   one real relation buried in twelve variables of pure noise
    hidden_mode   a cause that is never observed, only inferred from its effects
    rule_change   a relation that silently reverses mid-life
    habitat       a D.O.-like machine: clock, a hidden nightly backup, disk, ledger
                  growth, conditional actions and a placebo action
"""
from __future__ import annotations

import random

ACT = "act"          # the action is part of the stream, under this variable name


def _pick(rng: random.Random, probs: list[float]) -> int:
    r, acc = rng.random(), 0.0
    for i, p in enumerate(probs):
        acc += p
        if r < acc:
            return i
    return len(probs) - 1


def _noisy(value_index: int, n: int, fidelity: float) -> list[float]:
    """value with probability `fidelity`, otherwise uniform over all n values."""
    rest = (1.0 - fidelity) / n
    return [fidelity + rest if i == value_index else rest for i in range(n)]


def _uniform(n: int) -> list[float]:
    return [1.0 / n] * n


class World:
    name = "world"
    variables: dict[str, tuple] = {}
    actions: tuple = ("none",)
    action_probs: tuple = (1.0,)
    structure = ""

    def __init__(self, seed: int = 0):
        self.rng = random.Random(seed)
        self.t = 0
        self.reset()

    def reset(self) -> None:
        self.state = {v: vals[0] for v, vals in self.variables.items()}

    def observe(self) -> dict:
        return {v: self.state[v] for v in self.variables}

    def policy(self) -> str:
        return self.actions[_pick(self.rng, list(self.action_probs))]

    def oracle(self, action: str) -> dict[str, list[float]]:
        raise NotImplementedError

    def step(self, action: str) -> dict:
        dist = self.oracle(action)
        self._advance(action)
        for v, vals in self.variables.items():
            self.state[v] = vals[_pick(self.rng, dist[v])]
        self.t += 1
        return self.observe()

    def _advance(self, action: str) -> None:
        """Hidden-state bookkeeping that happens before observables are drawn."""


class Conjunction(World):
    name = "conjunction"
    structure = "y' = a XOR b, z' = a AND c (95%); four 3-valued noise variables"
    variables = {"a": (0, 1), "b": (0, 1), "c": (0, 1), "y": (0, 1), "z": (0, 1),
                 "n1": (0, 1, 2), "n2": (0, 1, 2), "n3": (0, 1, 2), "n4": (0, 1, 2)}
    actions = ("none", "poke")
    action_probs = (0.5, 0.5)

    def oracle(self, action):
        s = self.state
        d = {v: _uniform(len(vals)) for v, vals in self.variables.items()}
        d["y"] = _noisy(s["a"] ^ s["b"], 2, 0.9)
        d["z"] = _noisy(s["a"] & s["c"], 2, 0.9)
        return d


class Delayed(World):
    name = "delayed"
    structure = "disk drains 1 level w.p. 0.3; 'clean' at t raises disk by 2 at t+3"
    variables = {"disk": (0, 1, 2, 3, 4), "n1": (0, 1, 2), "n2": (0, 1, 2),
                 "n3": (0, 1, 2)}
    actions = ("none", "clean")
    action_probs = (0.8, 0.2)

    def reset(self):
        super().reset()
        self.state["disk"] = 2
        self.queue = ["none", "none", "none"]    # actions at t-2, t-1, t

    def oracle(self, action):
        s = self.state
        landing = (self.queue[1:] + [action])[0]     # action taken at t-2
        d = {v: _uniform(len(vals)) for v, vals in self.variables.items()}
        base = s["disk"] + (2 if landing == "clean" else 0)
        p = [0.0] * 5
        p[max(0, min(4, base - 1))] += 0.3
        p[max(0, min(4, base))] += 0.7
        d["disk"] = p
        return d

    def _advance(self, action):
        self.queue = self.queue[1:] + [action]


class Distractors(World):
    name = "distractors"
    structure = "y' = x (90%); twelve 3-valued variables of pure noise"
    variables = {"x": (0, 1, 2), "y": (0, 1, 2),
                 **{f"n{i:02d}": (0, 1, 2) for i in range(12)}}
    actions = ("none", "poke")
    action_probs = (0.5, 0.5)

    def oracle(self, action):
        d = {v: _uniform(len(vals)) for v, vals in self.variables.items()}
        d["y"] = _noisy(self.state["x"], 3, 0.9)
        return d


class HiddenMode(World):
    name = "hidden_mode"
    structure = ("hidden mode M flips w.p. 0.04; o1..o3 equal M w.p. 0.8; M is never "
                 "observed")
    variables = {"o1": (0, 1), "o2": (0, 1), "o3": (0, 1),
                 "n1": (0, 1, 2), "n2": (0, 1, 2), "n3": (0, 1, 2)}
    actions = ("none", "poke")
    action_probs = (0.5, 0.5)
    FLIP, FID = 0.04, 0.8

    def reset(self):
        super().reset()
        self.mode = 0

    def oracle(self, action):
        p1 = (1 - self.FLIP) if self.mode == 1 else self.FLIP      # P(M' = 1)
        d = {v: _uniform(len(vals)) for v, vals in self.variables.items()}
        for o in ("o1", "o2", "o3"):
            on = p1 * self.FID + (1 - p1) * (1 - self.FID)
            d[o] = [1 - on, on]
        return d

    def step(self, action):
        # Observables are conditionally dependent through M', so they are drawn from
        # M' itself rather than from the factored oracle marginals.
        if self.rng.random() < self.FLIP:
            self.mode = 1 - self.mode
        for o in ("o1", "o2", "o3"):
            self.state[o] = self.mode if self.rng.random() < self.FID else 1 - self.mode
        for n in ("n1", "n2", "n3"):
            self.state[n] = self.rng.randrange(3)
        self.t += 1
        return self.observe()


class RuleChange(World):
    name = "rule_change"
    structure = "y' = x for 1500 ticks, then y' = x+1 mod 3, alternating every 1500"
    variables = {"x": (0, 1, 2), "y": (0, 1, 2), "n1": (0, 1, 2), "n2": (0, 1, 2),
                 "n3": (0, 1, 2)}
    actions = ("none", "poke")
    action_probs = (0.5, 0.5)
    PERIOD = 1500

    def oracle(self, action):
        shift = (self.t // self.PERIOD) % 2
        d = {v: _uniform(len(vals)) for v, vals in self.variables.items()}
        d["y"] = _noisy((self.state["x"] + shift) % 3, 3, 0.9)
        return d


class Habitat(World):
    """A D.O.-shaped life. A 24-tick day observed through 8 clock bins; a backup the
    organism cannot see runs in bin 1 on 90% of nights, loading the CPU and draining the
    disk; the ledger grows; `rotate` frees disk only when the ledger is large;
    `snapshot` refreshes the snapshot only when disk is not empty; `vacuum` is a
    placebo that does nothing at all."""

    name = "habitat"
    structure = ("hidden nightly backup drives cpu+disk; rotate helps only if ledger>=2; "
                 "snapshot fails at disk 0; vacuum is a placebo; 4 noise variables")
    variables = {"clock": tuple(range(8)), "cpu": ("low", "mid", "high"),
                 "disk": (0, 1, 2, 3, 4), "ledger": (0, 1, 2, 3),
                 "snap_age": (0, 1, 2, 3), "net": ("up", "down"),
                 "e1": (0, 1, 2), "e2": (0, 1, 2), "e3": (0, 1), "e4": (0, 1)}
    actions = ("none", "rotate", "snapshot", "vacuum")
    action_probs = (0.55, 0.15, 0.15, 0.15)

    def reset(self):
        super().reset()
        self.hour = 0
        self.backup_tonight = True
        self.state.update(disk=3, ledger=1, cpu="low", net="up", snap_age=1)

    def _backup_running(self, hour: int) -> bool:
        return self.backup_tonight and 3 <= hour < 6

    def oracle(self, action):
        s = self.state
        V = self.variables
        nh = (self.hour + 1) % 24
        d = {v: _uniform(len(vals)) for v, vals in V.items()}
        d["clock"] = [1.0 if i == nh // 3 else 0.0 for i in range(8)]
        if nh == 0:
            # A new night begins: whether tonight's backup runs is not yet known.
            run_p = 0.9
        else:
            run_p = 1.0 if self.backup_tonight else 0.0
        running_p = run_p if 3 <= nh < 6 else 0.0
        busy, idle = [0.05, 0.15, 0.8], [0.6, 0.35, 0.05]
        d["cpu"] = [running_p * b + (1 - running_p) * i for b, i in zip(busy, idle)]

        # ledger: rotate empties it; otherwise it grows w.p. 0.1
        if action == "rotate":
            d["ledger"] = [1.0, 0.0, 0.0, 0.0]
        else:
            L = s["ledger"]
            p = [0.0] * 4
            p[L] += 0.9
            p[min(3, L + 1)] += 0.1
            d["ledger"] = p

        # disk: the backup drains it, rotating a large ledger refills it
        gain = 1 if (action == "rotate" and s["ledger"] >= 2) else 0
        drain = running_p * 0.5 + (1 - running_p) * 0.05
        p = [0.0] * 5
        p[max(0, min(4, s["disk"] + gain - 1))] += drain
        p[max(0, min(4, s["disk"] + gain))] += 1 - drain
        d["disk"] = p

        # snapshot age: a snapshot resets it, unless the disk is empty
        if action == "snapshot" and s["disk"] > 0:
            d["snap_age"] = [1.0, 0.0, 0.0, 0.0]
        else:
            A = s["snap_age"]
            p = [0.0] * 4
            p[A] += 0.8
            p[min(3, A + 1)] += 0.2
            d["snap_age"] = p

        d["net"] = [0.97, 0.03] if s["net"] == "up" else [0.3, 0.7]
        return d

    def _advance(self, action):
        self.hour = (self.hour + 1) % 24
        if self.hour == 0:
            self.backup_tonight = self.rng.random() < 0.9


WORLDS = {w.name: w for w in (Conjunction, Delayed, Distractors, HiddenMode,
                              RuleChange, Habitat)}
