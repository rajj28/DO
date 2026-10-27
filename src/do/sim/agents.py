"""Agents for the simulated habitat.

Every agent sees only the observation `Habitat.observe()` returns. None holds a
reference to the habitat or its world, and `tests/test_sim.py` walks this module's AST
to keep it that way: a learner that can read the true compression ratio has not learned
it.

    RandomAgent    uniform over what is applicable: the floor
    PlannerAgent   D.O.'s own planner (`cognition/planner.py`), called unmodified on
                   candidates built from the habitat's promises. Optionally with
                   calibration (the H4 mechanism), and optionally with a hand-written
                   flow term: what I would add if I already knew the answer.
    TDAgent        learns action values from its own experience by Q-learning over
                   features of the observation. gamma=0 makes it a learner with no
                   temporal credit assignment: it learns what each action does to the
                   next measurement, which is the most H4's calibration could ever
                   learn. That is the control that matters.
"""
from __future__ import annotations

import hashlib
import json
import random
from types import SimpleNamespace

from ..capabilities.actions import REGISTRY
from ..cognition import planner
from .habitat import ACTIONS, FLOW_ACTION, WAIT

# Risk and reversibility come from the live registry, so the planner scores the
# habitat's actions exactly as it scores the real ones.
TRAITS = {name: (a.risk, a.reversible) for name, a in REGISTRY.items()}
TRAITS[FLOW_ACTION] = (0.05, "derived")    # sim-only: nothing to read from the registry


class RandomAgent:
    name = "random"
    training = False

    def begin(self, obs) -> None:
        pass

    def act(self, obs, rng: random.Random) -> str:
        return rng.choice(list(obs["options"]))

    def learn(self, *args) -> None:
        pass


class PlannerAgent:
    """The live organism's decision procedure, transplanted whole.

    Reactive like the live loop: an objective exists only while the drive is out of
    band, and with no objective there is nothing to plan for. Each candidate is scored
    by `planner.evaluate()` and chosen by `planner.select()`; nothing here re-weights
    anything.
    """

    def __init__(self, config, *, calibrate: bool = False, flow_term: bool = False,
                 reactive: bool = True):
        self.config = config
        self.calibrate, self.flow_term, self.reactive = calibrate, flow_term, reactive
        self.name = ("planner" + ("+cal" if calibrate else "")
                     + ("+flow" if flow_term else "") + ("" if reactive else "-always"))
        self.alpha = float(config.get("learning.alpha", 0.4))
        spec = config.get("drives.frugality", {}) or {}
        # The metric value at which the drive is back in band (Drive.satisfying_metric_value).
        self.satisfying = 1.0 - (spec.get("target", 0.5) - spec.get("deadband", 0.2))
        self.horizon_guess = int(config.get("objectives.deadline_cycles", 6))
        self.k: dict[str, float] = {}
        self.samples: dict[str, int] = {}
        self.training = False
        self._start = 0

    def begin(self, obs) -> None:
        self._start = obs["total"]

    def act(self, obs, rng: random.Random) -> str:
        if self.reactive and obs["error"] <= 0:
            return WAIT
        objective = SimpleNamespace(
            start_value=float(self._start), current_value=float(obs["total"]),
            target_value=self.satisfying * obs["quota"], direction="decrease")
        cands = []
        for name, raw in obs["options"].items():
            if name == WAIT:
                continue
            if name == FLOW_ACTION and self.flow_term:
                # The term I would write knowing what H8 is about: last cycle's ledger
                # growth, a guessed 50% cut, over the objective deadline from config.
                # It needs the horizon and the cut, neither of which D.O. can measure
                # before acting.
                raw = int(obs["grew_ledger_last"] * 0.5 * self.horizon_guess)
            k = self.k.get(name, 1.0)
            risk, reversible = TRAITS[name]
            cands.append(planner.Candidate(
                action=name, description="", component="", predicted_raw=int(raw),
                calibration_k=round(k, 4), predicted=int(raw * k),
                basis="habitat promise", precondition="applicable",
                risk=risk, reversible=reversible, cost_s=0.5))
        chosen = planner.select(planner.evaluate(cands, objective, self.config))
        return chosen.action if chosen else WAIT

    def learn(self, obs, action, reward, nobs, info, done) -> None:
        """H4's update: k <- (1 - alpha) k + alpha * actual/predicted_raw.

        The flow action is excluded. Its error signal is measured in bytes freed this
        cycle, so it "under-delivers" every time by definition and calibration would
        drive its k to zero - the update is as one-step as the score it corrects.
        """
        if not (self.calibrate and self.training) or action in (WAIT, FLOW_ACTION):
            return
        raw = info["promised"]
        if raw <= 0:
            return
        observed = info["freed"] / raw
        n = self.samples.get(action, 0)
        self.k[action] = observed if n == 0 else (
            (1 - self.alpha) * self.k[action] + self.alpha * observed)
        self.samples[action] = n + 1


# ---- features ------------------------------------------------------------------
# Situation, never action: the same features describe a state whichever action is
# being valued, so any link between a feature and an action's worth is learned (the
# rule outcomes.context_features follows on the live organism).
U_EDGES = (0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.00)   # used/quota; 0.70 = band edge
G_EDGES = (0.005, 0.01, 0.02, 0.03, 0.045)             # last cycle's growth / quota
R_EDGES = (0.05, 0.15, 0.30)                           # sealable ledger / quota
_NU, _NG, _NR = len(U_EDGES) + 1, len(G_EDGES) + 1, len(R_EDGES) + 1
_U, _G = 1, 1 + _NU
_UG = _G + _NG
_CONS = _UG + _NU * _NG
_ROT = _CONS + 2
_EXP = _ROT + _NR
_BYTE = _EXP + 2
_FREE = _BYTE + 2
_PRUNE = _FREE + 3
N_FEATURES = _PRUNE + 2


def _bin(x: float, edges: tuple) -> int:
    for i, e in enumerate(edges):
        if x < e:
            return i
    return len(edges)


def features(obs) -> tuple[int, ...]:
    """Indices of the active binary features. Ten are active in every state."""
    q = obs["quota"]
    u = _bin(obs["used_ratio"], U_EDGES)
    g = _bin(obs["grew_last"] / q, G_EDGES)
    free = obs["freelist"]
    return (
        0,                                              # bias
        _U + u, _G + g,
        _UG + u * _NG + g,                              # how far out x how fast growing
        _CONS + int(obs["consolidated"]),
        _ROT + _bin(max(0, obs["ledger_live"] - obs["keep_live"]) / q, R_EDGES),
        _EXP + int(obs["experiments"] > 0),
        _BYTE + int(obs["bytecode"] > 0),
        _FREE + (0 if free == 0 else 1 if free < 0.02 * q else 2),
        _PRUNE + int(obs["prunable"] > 0),
    )


class TDAgent:
    """Linear Q-learning from the organism's own experience.

    Q(s, a) = w_a . phi(s), with phi the binary features above.

        target = r + gamma * max_a' Q(s', a')          over actions applicable in s'
        w_a   += (alpha / |phi(s)|) * (target - Q(s, a)) * phi(s)

    The reward is -(frugality drive's weighted error) after the step: the organism's own
    homeostatic signal, nothing added for the experiment.

    A time limit is not a terminal state. The organism does not die at cycle 16; the
    experiment stops watching. So the last step bootstraps like every other (Pardo et
    al. 2018), keeping the values those of a task whose end the agent cannot see -
    it has no clock feature, and should not need one.
    """

    def __init__(self, *, gamma: float = 0.9, alpha: float = 0.1,
                 eps_start: float = 0.3, eps_end: float = 0.02, seed: int = 0,
                 name: str | None = None):
        self.gamma, self.alpha = gamma, alpha
        self.eps_start, self.eps_end = eps_start, eps_end
        self.seed = seed
        self.rng = random.Random(seed)
        self.name = name or f"td(gamma={gamma:g})"
        self.training = False
        self.progress = 0.0          # fraction of the training budget used; set by harness
        self.wipe()

    def wipe(self) -> None:
        """Ablation support: remove everything experience produced, keep the code."""
        self.w = {a: [0.0] * N_FEATURES for a in ACTIONS}

    def epsilon(self) -> float:
        return self.eps_start + (self.eps_end - self.eps_start) * min(1.0, self.progress)

    def q(self, phi: tuple[int, ...], action: str) -> float:
        wa = self.w[action]
        return sum(wa[i] for i in phi)

    def begin(self, obs) -> None:
        pass

    def act(self, obs, rng: random.Random) -> str:
        opts = list(obs["options"])
        if self.training and self.rng.random() < self.epsilon():
            return self.rng.choice(opts)
        phi = features(obs)
        vals = [(self.q(phi, a), a) for a in opts]
        top = max(v for v, _ in vals)
        best = [a for v, a in vals if v >= top - 1e-12]
        return best[0] if len(best) == 1 else rng.choice(best)

    def learn(self, obs, action, reward, nobs, info, done) -> None:
        if not self.training:
            return
        phi = features(obs)
        target = reward
        if self.gamma:
            nphi = features(nobs)
            target += self.gamma * max(self.q(nphi, b) for b in nobs["options"])
        delta = target - self.q(phi, action)
        step = self.alpha / len(phi)
        wa = self.w[action]
        for i in phi:
            wa[i] += step * delta

    def export_state(self) -> dict:
        return {"weights": {a: list(v) for a, v in self.w.items()}}

    def fingerprint(self) -> str:
        blob = json.dumps({a: [round(x, 12) for x in v] for a, v in self.w.items()},
                          sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]
