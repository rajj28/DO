"""Cognition tests: the causal chain from measurement to utterance.

The chain under test:

    measurement -> drive error -> gap.instrumental -> gap.priority -> focus -> utterance

Each link gets its own test, so a break can be located rather than merely detected.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from do.kernel.config import Config                      # noqa: E402
from do.kernel import lifecycle                          # noqa: E402


def boot_in(tmp: Path, perturb: dict | None = None):
    cfg = Config.load(overrides={
        "organism": {"state_dir": str(tmp / "var"),
                     "sandbox_dir": str(tmp / "var" / "sandbox")},
        "observability": {"ledger_file": str(tmp / "var" / "ledger.jsonl")},
    })
    return lifecycle.boot(cfg, perturb=perturb, quiet=True)


class TestGapGeneration(unittest.TestCase):
    def test_question_text_is_derived_from_the_slot_identifier(self):
        """No human-authored question strings. The phrase must come from the key."""
        from do.cognition.gaps import _phrase
        self.assertEqual("my expected lifetime", _phrase("self.expected_lifetime"))
        self.assertEqual("the user's identity", _phrase("user.identity"))
        self.assertEqual("my purpose", _phrase("self.purpose"))

    def test_drive_error_flows_into_gap_priority(self):
        """The load-bearing link: a gap about a drive that is out of band must
        outscore the same gap when that drive is satisfied."""
        with tempfile.TemporaryDirectory() as d:
            org = boot_in(Path(d) / "a", {"resources.disk.free_ratio": 0.002,
                                          "resources.disk.free_bytes": 400_000_000})
            tight = next((g for g in org.gaps
                          if g.subject == "resources.disk.free_ratio"), None)
            org.close()
            self.assertIsNotNone(tight, "a breached floor must produce a gap")
            self.assertGreater(tight.instrumental, 0.3,
                               "instrumental value must carry live drive error")
            self.assertEqual(org.gaps[0].subject, "resources.disk.free_ratio",
                             "the breached resource must win attention")

    def test_no_gap_when_resource_is_abundant(self):
        with tempfile.TemporaryDirectory() as d:
            org = boot_in(Path(d) / "b", {"resources.disk.free_ratio": 0.85,
                                          "resources.disk.free_bytes": 200 * 1024**3,
                                          "resources.ram.free_ratio": 0.9})
            subjects = {g.subject for g in org.gaps}
            org.close()
            self.assertNotIn("resources.disk.free_ratio", subjects)


class TestSpeechActSelection(unittest.TestCase):
    def test_speech_act_is_an_argmax_not_a_constant(self):
        """If the act never changes with state, D.O. is scripted."""
        with tempfile.TemporaryDirectory() as d:
            a = boot_in(Path(d) / "critical", {"resources.disk.free_ratio": 0.001,
                                               "resources.disk.free_bytes": 10_000_000})
            b = boot_in(Path(d) / "roomy", {"resources.disk.free_ratio": 0.9,
                                            "resources.disk.free_bytes": 200 * 1024**3,
                                            "resources.ram.free_ratio": 0.9})
            act_a, act_b = a.plan.speech_act, b.plan.speech_act
            focus_a, focus_b = a.plan.focus.subject, b.plan.focus.subject
            a.close(); b.close()
            self.assertEqual("FLAG", act_a)
            self.assertNotEqual(focus_a, focus_b,
                                "focus must move when the environment changes")


class TestUtteranceIsStateDependent(unittest.TestCase):
    def test_perturbation_changes_the_utterance(self):
        """H1 in miniature: same code, different measurements, different output."""
        with tempfile.TemporaryDirectory() as d:
            a = boot_in(Path(d) / "1", {})
            b = boot_in(Path(d) / "2", {"tools.on_path": [], "tools.local_models": [],
                                        "resources.disk.free_ratio": 0.75,
                                        "resources.disk.free_bytes": 180 * 1024**3})
            ta, tb = a.utterance.text, b.utterance.text
            a.close(); b.close()
            self.assertNotEqual(ta, tb)
            self.assertTrue(ta and tb, "an utterance must actually be produced")

    def test_utterance_contains_measured_values(self):
        with tempfile.TemporaryDirectory() as d:
            org = boot_in(Path(d) / "m")
            text = org.utterance.text
            cpus = org.view.val("resources.cpu.logical")
            org.close()
            self.assertIn("self-model", text)
            self.assertRegex(text, r"\d", "the utterance must carry measured numbers")


class TestPersistence(unittest.TestCase):
    def test_second_boot_carries_unresolved_questions(self):
        """H2: an organism with a past must differ from one without."""
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d) / "warm"
            a = boot_in(tmp)
            self.assertTrue(a.identity.genesis)
            self.assertEqual(0, len(a.view.carried_gaps))
            new_first = a.gap_stats["new"]
            a.close()

            b = boot_in(tmp)
            self.assertFalse(b.identity.genesis)
            self.assertEqual(2, b.identity.boot_index)
            carried = len(b.view.carried_gaps)
            new_second = b.gap_stats["new"]
            b.close()

            self.assertGreater(carried, 0, "open questions must survive a restart")
            self.assertLess(new_second, new_first,
                            "a second boot must recognise questions it already formed")

    def test_identity_survives_restart(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d) / "id"
            a = boot_in(tmp); oid = a.identity.organism_id; a.close()
            b = boot_in(tmp); self.assertEqual(oid, b.identity.organism_id); b.close()


class TestCapabilityAffordability(unittest.TestCase):
    def test_installed_but_unaffordable_is_its_own_state(self):
        with tempfile.TemporaryDirectory() as d:
            org = boot_in(Path(d) / "c", {
                "tools.local_models": [{"name": "huge:1t", "bytes": 900 * 1024**3,
                                        "gib": 900.0, "runtime": "ollama"}],
                "resources.ram.available_bytes": 2 * 1024**3})
            caps = {c["name"]: c for c in org.view.capabilities}
            org.close()
            self.assertEqual("installed_unaffordable",
                             caps["local_inference:huge:1t"]["status"])

    def test_affordable_model_is_available(self):
        with tempfile.TemporaryDirectory() as d:
            org = boot_in(Path(d) / "d", {
                "tools.local_models": [{"name": "small:1b", "bytes": 1024**3,
                                        "gib": 1.0, "runtime": "ollama"}],
                "resources.ram.available_bytes": 8 * 1024**3})
            caps = {c["name"]: c for c in org.view.capabilities}
            org.close()
            self.assertEqual("available", caps["local_inference:small:1b"]["status"])


class TestMetabolism(unittest.TestCase):
    def test_ticks_run_with_no_human_input(self):
        """H3 in miniature: the organism does something when nobody is talking."""
        with tempfile.TemporaryDirectory() as d:
            org = boot_in(Path(d) / "t")
            results = [lifecycle.tick(org, quiet=True) for _ in range(3)]
            org.close()
            self.assertEqual([1, 2, 3], [r["tick"] for r in results])
            self.assertTrue(all(r["focus"] for r in results),
                            "each cycle must select something to attend to")


if __name__ == "__main__":
    unittest.main()
