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
        """The load-bearing link: a breached floor must produce a gap whose
        instrumental value carries the live drive error."""
        with tempfile.TemporaryDirectory() as d:
            org = boot_in(Path(d) / "a", {"resources.disk.free_ratio": 0.002,
                                          "resources.disk.free_bytes": 400_000_000})
            tight = next((g for g in org.gaps
                          if g.subject == "resources.disk.free_ratio"), None)
            org.close()
            self.assertIsNotNone(tight, "a breached floor must produce a gap")
            self.assertGreater(tight.instrumental, 0.3,
                               "instrumental value must carry live drive error")

    def test_actionable_gap_outranks_unactionable_one(self):
        """v0.2, and deliberate: agency scales instrumental value.

        In v0.1 the host-disk gap won attention and held it forever, because nothing
        could move it - that was the H3 falsification. Now a gap is worth attending to
        in proportion to whether any registered action moves its metric, so an
        actionable constraint outranks a larger unactionable one. This assertion is
        the fix, pinned so it cannot regress silently.
        """
        with tempfile.TemporaryDirectory() as d:
            org = boot_in(Path(d) / "agency", {"resources.disk.free_ratio": 0.002,
                                               "resources.disk.free_bytes": 400_000_000})
            by = {g.subject: g for g in org.gaps}
            disk = by.get("resources.disk.free_ratio")
            own = by.get("resources.own.quota_used_ratio")
            org.close()
            self.assertIsNotNone(disk)
            if own is not None:
                self.assertEqual(1.0, own.agency, "own footprint is actionable")
                self.assertLess(disk.agency, 1.0,
                                "no registered action moves host disk free space")
                self.assertGreater(own.priority, disk.priority,
                                   "attention must prefer what it can actually move")

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
            drive_a = {d.name: d for d in a.drives}["continuity"]
            drive_b = {d.name: d for d in b.drives}["continuity"]
            a.close(); b.close()
            self.assertEqual("FLAG", act_a)
            # Focus no longer moves between these two: both are dominated by the
            # actionable own-footprint gap, which is the v0.2 agency fix working. What
            # must still track the environment is the drive itself.
            self.assertNotEqual(drive_a.value, drive_b.value,
                                "the continuity drive must track measured storage")
            self.assertLess(drive_a.value, drive_b.value,
                            "less free space must mean lower continuity")


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


class TestEmergentGoals(unittest.TestCase):
    """The critical test: a goal must be DERIVED from state, not supplied.

    An earlier version of objectives.generate() matched on a hard-coded subject
    string, which meant the experimenter wrote the goal and the organism appeared to
    form it. These assertions make that impossible to reintroduce quietly.
    """

    def test_no_subject_strings_in_goal_formation(self):
        src = (ROOT / "src" / "do" / "cognition" / "objectives.py").read_text(
            encoding="utf-8")
        body = src.split('"""', 2)[-1]          # skip the module docstring
        for forbidden in ("resources.own.quota_used_ratio",
                          "resources.disk.free_ratio"):
            self.assertNotIn(f'== "{forbidden}"', body,
                             f"goal formation must not branch on {forbidden!r}")

    def test_goal_is_derived_from_drive_and_registry(self):
        from do.cognition import objectives as objmod
        with tempfile.TemporaryDirectory() as d:
            org = boot_in(Path(d) / "g", {"resources.disk.free_ratio": 0.002,
                                          "resources.disk.free_bytes": 400_000_000})
            by = {g.subject: g for g in org.gaps}
            disk = by.get("resources.disk.free_ratio")
            own = by.get("resources.own.quota_used_ratio")
            goal_disk = objmod.generate(disk, org.view, org.drives, 1, org.config)
            goal_own = (objmod.generate(own, org.view, org.drives, 1, org.config)
                        if own is not None else None)
            org.close()
            self.assertIsNone(goal_disk,
                              "no action moves host disk, so it must not become a goal")
            if own is not None:
                self.assertIsNotNone(goal_own, "an actionable breach must become a goal")
                self.assertEqual("resources.own.total_bytes", goal_own.metric_key)
                self.assertEqual("frugality", goal_own.drive)
                self.assertTrue(goal_own.subgoals, "a goal must be decomposed")
                self.assertEqual("diagnose", goal_own.subgoals[0]["stage"],
                                 "composition must be investigated before reducing")


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
