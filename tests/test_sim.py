"""Simulated-habitat tests: the properties H8's conclusions rest on.

If any of these broke, an H8 verdict could describe the simulator instead of the
learner - a habitat that mints bytes, an agent that can read the answer, or a "flow
action" that secretly pays off immediately.
"""
from __future__ import annotations

import ast
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from do.drives import Drive                                       # noqa: E402
from do.kernel.config import Config                               # noqa: E402
from do.sim.agents import PlannerAgent, TDAgent, features, N_FEATURES  # noqa: E402
from do.sim.habitat import (FLOW_ACTION, HIDDEN, OBSERVABLE, WAIT,  # noqa: E402
                            Habitat, World, sample_world)

CFG = Config.load()
SPEC = CFG.get("drives.frugality")


def walk(env: Habitat, rng: random.Random):
    """Random applicable actions to the horizon; yields (obs, action, info)."""
    obs, done = env.reset(), False
    while not done:
        a = rng.choice(list(obs["options"]))
        nobs, _, done, info = env.step(a)
        yield obs, a, info
        obs = nobs


class TestHabitat(unittest.TestCase):
    def test_accounting_balances_and_nothing_goes_negative(self):
        """step() asserts the books balance; here a few hundred random lives run
        through it, and no component may ever go below zero."""
        rng = random.Random(1)
        for seed in range(300):
            env = Habitat(sample_world(seed), SPEC)
            for _ in walk(env, rng):
                for part in (env.experiments, env.bytecode, env.memory, env.freelist,
                             env.ledger_live, env.segments, env.snapshots):
                    self.assertGreaterEqual(part, 0)
                self.assertLessEqual(env.freelist, env.memory)

    def test_observation_is_the_contract_and_read_only(self):
        obs = Habitat(sample_world(7), SPEC).reset()
        self.assertEqual(OBSERVABLE, set(obs))
        with self.assertRaises(TypeError):
            obs["total"] = 0                       # MappingProxyType: no writing back
        self.assertTrue(HIDDEN <= set(World.__dataclass_fields__))
        self.assertFalse(HIDDEN & set(obs), "a hidden world parameter is observable")

    def test_flow_action_pays_nothing_now_and_something_later(self):
        """The load-bearing property: consolidation's immediate consequence is exactly
        WAIT's, so only a learner that propagates value through time can prefer it."""
        w = sample_world(11)
        a, b = Habitat(w, SPEC), Habitat(w, SPEC)
        oa, ra, _, _ = a.step(WAIT)
        ob, rb, _, _ = b.step(FLOW_ACTION)
        self.assertEqual(ra, rb)
        self.assertEqual(oa["total"], ob["total"])
        a.step(WAIT)
        b.step(WAIT)
        self.assertLess(b.total(), a.total(), "consolidation never cut growth")

    def test_rotation_under_promises_like_the_live_registry(self):
        env = Habitat(sample_world(3), SPEC)
        obs = env.reset()
        self.assertIn("rotate_ledger", obs["options"])
        _, _, _, info = env.step("rotate_ledger")
        self.assertGreater(info["freed"], info["promised"])

    def test_reward_is_the_live_frugality_drive(self):
        env = Habitat(sample_world(5), SPEC)
        env.reset()
        d = env.drive()
        self.assertIs(type(d), Drive)
        self.assertEqual("frugality", d.name)
        _, r, _, _ = env.step(WAIT)
        self.assertEqual(-env.drive().weighted_error, r)

    def test_a_world_is_a_pure_function_of_its_seed(self):
        self.assertEqual(sample_world(42), sample_world(42))
        self.assertNotEqual(sample_world(42), sample_world(43))


class TestAgents(unittest.TestCase):
    def test_agents_cannot_read_the_world(self):
        """Structural, like the gate test: the agents module must not reach a habitat's
        world or name a hidden parameter. A learner that can read the true compression
        ratio has not learned it."""
        src = (ROOT / "src" / "do" / "sim" / "agents.py").read_text(encoding="utf-8")
        offenders = []
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Attribute) and node.attr in HIDDEN | {"world"}:
                offenders.append(node.attr)
            if isinstance(node, ast.Constant) and node.value in HIDDEN:
                offenders.append(node.value)
            if isinstance(node, ast.alias) and node.name in {"Habitat", "World",
                                                             "sample_world"}:
                offenders.append(node.name)
        self.assertEqual([], offenders)

    def test_live_planner_never_chooses_the_flow_action(self):
        """By construction: it predicts zero bytes, and planner.evaluate rejects that."""
        for reactive in (True, False):
            agent = PlannerAgent(CFG, calibrate=True, reactive=reactive)
            rng = random.Random(0)
            for seed in range(40):
                env = Habitat(sample_world(seed), SPEC)
                obs, done = env.reset(), False
                agent.begin(obs)
                while not done:
                    a = agent.act(obs, rng)
                    self.assertNotEqual(FLOW_ACTION, a)
                    obs, _, done, _ = env.step(a)

    def test_features_describe_the_situation_not_the_action(self):
        obs = Habitat(sample_world(9), SPEC).reset()
        phi = features(obs)
        self.assertEqual(10, len(phi))
        self.assertTrue(all(0 <= i < N_FEATURES for i in phi))
        self.assertEqual(len(phi), len(set(phi)))

    def test_wipe_restores_the_untrained_agent_exactly(self):
        """S0' == S0 at the unit level: wiping leaves no learned residue anywhere."""
        fresh, trained = TDAgent(seed=3), TDAgent(seed=3)
        trained.training = True
        rng = random.Random(0)
        for seed in range(20):
            env = Habitat(sample_world(seed), SPEC)
            obs, done = env.reset(), False
            while not done:
                a = trained.act(obs, trained.rng)
                nobs, r, done, info = env.step(a)
                trained.learn(obs, a, r, nobs, info, done)
                obs = nobs
        self.assertNotEqual(fresh.fingerprint(), trained.fingerprint())
        trained.wipe()
        self.assertEqual(fresh.fingerprint(), trained.fingerprint())

    def test_gamma_zero_cannot_value_the_flow_action(self):
        """With no bootstrapping, the only thing that separates consolidating from
        waiting is the reward one step later - which is identical. So after training,
        a gamma=0 learner's two values must stay tied wherever both were tried equally."""
        td = TDAgent(gamma=0.0, seed=1)
        td.training = True
        w = sample_world(2)
        for _ in range(200):
            for a in (WAIT, FLOW_ACTION):
                env = Habitat(w, SPEC)
                obs = env.reset()
                nobs, r, done, info = env.step(a)
                td.learn(obs, a, r, nobs, info, done)
        phi = features(Habitat(w, SPEC).reset())
        self.assertAlmostEqual(td.q(phi, WAIT), td.q(phi, FLOW_ACTION), places=9)


if __name__ == "__main__":
    unittest.main()
