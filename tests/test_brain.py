"""The brain's claims, tested as properties.

Each test is a claim from docs/BRAIN.md that would otherwise only be asserted:
it finds joint causes, structure that does not pay dies, a broken rule is forgotten
quickly, and a life stored as the brain's residuals replays exactly.

Run: python -m unittest discover -s tests -v
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from do.brain import codec  # noqa: E402
from do.brain.baselines import Markov1  # noqa: E402
from do.brain.cortex import Cortex  # noqa: E402
from do.brain.worlds import WORLDS  # noqa: E402


def live(world_name: str, model, T: int, seed: int = 0, tail_from: float = 0.7):
    """Run a model through a world; return its excess bits/tick over the oracle in the
    tail of its life."""
    w = WORLDS[world_name](seed)
    frame, excess, n = w.observe(), 0.0, 0
    for t in range(T):
        a = w.policy()
        p = model.predict(frame, a)
        truth = w.oracle(a)
        nxt = w.step(a)
        if t >= tail_from * T:
            for v, vals in w.variables.items():
                i = vals.index(nxt[v])
                excess += -math.log2(p[v][i]) + math.log2(truth[v][i])
            n += 1
        model.update(nxt)
        frame = nxt
    return excess / max(1, n)


class TestStructureDiscovery(unittest.TestCase):
    def test_finds_a_joint_cause_pairwise_methods_cannot_see(self):
        """y' = a XOR b: no single symbol carries any information about y. The brain
        must find the pair, and keep it."""
        w = WORLDS["conjunction"](0)
        c = Cortex(w.variables, w.actions, seed=0)
        excess = live("conjunction", c, 2000)
        kept = [u for u in c.units["y"].values() if u.paid_off]
        xor_units = []
        for u in kept:
            ctx = dict(s.split("@")[0].split("=") for s in u.ctx)
            if set(ctx) == {"a", "b"} and all(s.endswith("@0") for s in u.ctx):
                xor_units.append(u)
        self.assertTrue(xor_units, "no paid-off unit on exactly {a, b} for y")
        for u in xor_units:
            ctx = dict(s.split("@")[0].split("=") for s in u.ctx)
            want = int(ctx["a"]) ^ int(ctx["b"])
            p = [math.exp(x) for x in u.logprobs(c.alpha)]
            self.assertGreater(p[want], 0.8, f"{u.ctx} does not encode XOR")
        m = Markov1(w.variables, w.actions)
        self.assertLess(excess, 0.5 * live("conjunction", m, 2000))

    def test_structure_that_does_not_pay_dies(self):
        """Twelve variables of pure noise and one real relation. Nothing about the noise
        may survive to be paid off; the real relation must."""
        w = WORLDS["distractors"](0)
        c = Cortex(w.variables, w.actions, seed=0)
        live("distractors", c, 2000)
        noise = [v for v in c.targets if v.startswith("n")]
        paid_noise = [u.ctx for v in noise for u in c.units[v].values()
                      if u.ctx and u.paid_off]
        self.assertEqual([], paid_noise, "structure about pure noise was kept")
        paid_y = [u.ctx for u in c.units["y"].values() if u.paid_off]
        self.assertTrue(any(ctx == (f"x={k}@0",) for ctx in paid_y for k in range(3)),
                        f"the real relation y'=x was not kept: {paid_y}")

    def test_a_broken_rule_is_forgotten_fast(self):
        """The rule reverses at tick 1500. Per-unit rupture detection must recover
        faster than the same brain without it."""
        w = WORLDS["rule_change"](0)
        on = Cortex(w.variables, w.actions, seed=0)
        off = Cortex(w.variables, w.actions, seed=0, rupture=False)
        tail_on = live("rule_change", on, 2000, tail_from=0.75)
        tail_off = live("rule_change", off, 2000, tail_from=0.75)
        self.assertGreater(on.ruptures, 0)
        self.assertLess(tail_on, tail_off)


class TestBrainHygiene(unittest.TestCase):
    def test_predictions_are_distributions(self):
        w = WORLDS["habitat"](0)
        c = Cortex(w.variables, w.actions, seed=0)
        frame = w.observe()
        for _ in range(200):
            a = w.policy()
            p = c.predict(frame, a)
            for v, dist in p.items():
                self.assertAlmostEqual(1.0, sum(dist), places=9)
                self.assertTrue(all(x > 0 for x in dist), f"{v} has a zero")
            frame = w.step(a)
            c.update(frame)

    def test_same_seed_same_brain(self):
        """Determinism is what makes replay - and therefore residual memory - possible."""
        def run():
            w = WORLDS["habitat"](3)
            c = Cortex(w.variables, w.actions, seed=3)
            frame, out = w.observe(), []
            for _ in range(300):
                a = w.policy()
                out.append(c.predict(frame, a))
                frame = w.step(a)
                c.update(frame)
            return out, c.stats()
        self.assertEqual(run(), run())


class TestResidualMemory(unittest.TestCase):
    def test_life_replays_exactly_and_is_small(self):
        w = WORLDS["habitat"](1)
        frames, actions = [w.observe()], []
        for _ in range(400):
            a = w.policy()
            actions.append(a)
            frames.append(w.step(a))
        blob = codec.encode(frames, actions, w.variables, w.actions, seed=1)
        f2, a2 = codec.decode(blob, 400, w.variables, w.actions, seed=1)
        self.assertEqual(frames, f2)
        self.assertEqual(actions, a2)
        packed_bytes = 401 * (len(w.variables) + 1)
        self.assertLess(len(blob), packed_bytes / 4)

    def test_wrong_brain_cannot_read_the_record(self):
        """The record is only memory to the brain that wrote it."""
        w = WORLDS["conjunction"](0)
        frames, actions = [w.observe()], []
        for _ in range(200):
            a = w.policy()
            actions.append(a)
            frames.append(w.step(a))
        blob = codec.encode(frames, actions, w.variables, w.actions, seed=0)
        f2, _ = codec.decode(blob, 200, w.variables, w.actions, seed=0, half_life=50.0)
        self.assertNotEqual(frames, f2)


if __name__ == "__main__":
    unittest.main()
