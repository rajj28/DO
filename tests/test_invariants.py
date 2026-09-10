"""Structural invariants. These are the guardrails from docs/DO_CONCEPT.md section G,
tested as properties rather than trusted as conventions.

Run: python -m unittest discover -s tests -v
(stdlib unittest, so the test suite has no dependency either)
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "do"
sys.path.insert(0, str(ROOT / "src"))

# Modules that may reach outside the process. Exactly one, by design.
EFFECT_MODULES = {"do.effectors"}
FORBIDDEN_IMPORTS = {"socket", "subprocess", "urllib", "http", "requests", "httpx",
                     "ftplib", "smtplib", "telnetlib", "asyncio.subprocess", "multiprocessing"}

STDLIB = set(sys.stdlib_module_names)


def modules() -> list[tuple[str, Path, ast.Module]]:
    out = []
    for p in sorted(SRC.rglob("*.py")):
        rel = p.relative_to(SRC.parent).with_suffix("")
        name = ".".join(rel.parts)
        if name.endswith(".__init__"):
            name = name[: -len(".__init__")]
        out.append((name, p, ast.parse(p.read_text(encoding="utf-8"), str(p))))
    return out


def imported_roots(tree: ast.Module) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


class TestGateChokepoint(unittest.TestCase):
    """H6: the gate is unbypassable. Falsified if any module outside effectors can
    reach the network or spawn a process."""

    def test_only_effectors_import_io(self):
        offenders = []
        for name, path, tree in modules():
            if name in EFFECT_MODULES:
                continue
            bad = imported_roots(tree) & FORBIDDEN_IMPORTS
            if bad:
                offenders.append(f"{name} imports {sorted(bad)}")
        self.assertEqual([], offenders,
                         "side-effect capability found outside the gate:\n  "
                         + "\n  ".join(offenders))

    def test_effectors_actually_has_the_capability(self):
        """The inverse test. If effectors stopped importing socket, the first test
        would pass vacuously and the system would look safer than it is."""
        tree = ast.parse((SRC / "effectors" / "__init__.py").read_text(encoding="utf-8"))
        roots = imported_roots(tree)
        self.assertIn("socket", roots)
        self.assertIn("urllib", roots)

    def test_every_effect_kind_is_routed(self):
        from do.effectors import Gate
        import inspect
        src = inspect.getsource(Gate._perform)
        for kind in ("net.dns", "net.connect", "net.http", "llm.generate",
                     "fs.read", "fs.write", "tts.speak", "human.ask"):
            self.assertIn(kind, src, f"effect kind {kind} has no route in the gate")


class TestZeroDependency(unittest.TestCase):
    """The seed must boot on a bare Python 3.11 with no pip install (ARCHITECTURE §1)."""

    def test_no_third_party_imports(self):
        offenders = []
        for name, path, tree in modules():
            for root in imported_roots(tree):
                if root in STDLIB or root in ("do", "__future__"):
                    continue
                offenders.append(f"{name} imports non-stdlib {root!r}")
        self.assertEqual([], offenders, "\n  ".join(offenders))


class TestHonestyInvariants(unittest.TestCase):
    def test_memory_requires_provenance(self):
        from do.memory import MemoryRecord, MemoryStore
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            store = MemoryStore(Path(d) / "m.db", "boot-test")
            with self.assertRaises(ValueError):
                store.write(MemoryRecord(kind="semantic", content="x", source="",
                                         epistemic="observed", boot_id="b"))
            store.close()

    def test_belief_revision_is_non_destructive(self):
        from do.memory import MemoryStore
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            store = MemoryStore(Path(d) / "m.db", "boot-test")
            first, _ = store.believe("world.host.system", "world.host.system = Linux",
                                     source="probe-a", epistemic="observed")
            second, superseded = store.believe("world.host.system",
                                               "world.host.system = Windows",
                                               source="probe-b", epistemic="observed")
            self.assertEqual(first, superseded, "revision must name what it superseded")
            row = store.db.execute("SELECT superseded_by FROM memories WHERE id=?",
                                   (first,)).fetchone()
            self.assertEqual(second, row["superseded_by"])
            live = store.db.execute(
                "SELECT COUNT(*) n FROM memories WHERE subject='world.host.system'"
                " AND superseded_by IS NULL").fetchone()["n"]
            self.assertEqual(1, live, "exactly one live belief per subject")
            total = store.db.execute(
                "SELECT COUNT(*) n FROM memories WHERE subject='world.host.system'"
            ).fetchone()["n"]
            self.assertEqual(2, total, "the superseded belief must still exist")
            store.close()

    def test_web_content_is_never_observed(self):
        """A server returning bytes is not evidence the bytes are true."""
        from do.sense.web import to_observation
        from do.kernel.types import Epistemic
        o = to_observation({"url": "https://example.com", "text": "the sky is green",
                            "confidence": 0.35, "content_sha256": "abc", "status": 200},
                           "world.claim")
        self.assertIs(o.epistemic, Epistemic.REPORTED)
        self.assertLess(o.confidence, 0.5)


class TestLedger(unittest.TestCase):
    def test_chain_detects_tampering(self):
        from do.ledger import Ledger, verify_chain
        import tempfile, json
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "ledger.jsonl"
            led = Ledger(p, "boot-1")
            for i in range(5):
                led.append("OBSERVATION", {"i": i})
            ok, note = verify_chain(p)
            self.assertTrue(ok, note)

            lines = p.read_text(encoding="utf-8").strip().split("\n")
            rec = json.loads(lines[2])
            rec["payload"]["i"] = 999                 # retroactive edit
            lines[2] = json.dumps(rec)
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")

            ok, note = verify_chain(p)
            self.assertFalse(ok, "an edited event must break the chain")
            self.assertIn("seq=3", note)

    def test_decision_records_no_reasoning_trace(self):
        from do.ledger import Ledger
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            led = Ledger(Path(d) / "l.jsonl", "boot-1")
            rec = led.decision("investigate_storage", "free ratio below floor", 0.81, 3)
            self.assertEqual({"decision", "reason", "confidence",
                              "alternatives_considered"}, set(rec["payload"]))


class TestPolicy(unittest.TestCase):
    def test_default_is_deny(self):
        from do.policy import Policy, DENY
        p = Policy({"default": DENY, "rules": []})
        from do.kernel.types import EffectRequest
        self.assertEqual(DENY, p.evaluate(EffectRequest("net.http", "https://x")).verdict)

    def test_kill_switch_blocks_effects(self):
        from do.effectors import Gate
        from do.kernel.types import EffectRequest
        from do.ledger import Ledger
        from do.policy import Budget, KillSwitch, Policy, BUILTIN_POLICY
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            ks = KillSwitch(Path(d))
            ks.engage("test")
            gate = Gate(Policy(BUILTIN_POLICY), Budget(), ks,
                        Ledger(Path(d) / "l.jsonl", "b"), Path(d) / "sandbox")
            res = gate.request(EffectRequest("net.dns", "example.com"))
            self.assertFalse(res.ok)
            self.assertEqual("halted", res.verdict)

    def test_sandbox_escape_is_blocked(self):
        from do.effectors import Gate, SandboxViolation
        from do.ledger import Ledger
        from do.policy import Budget, KillSwitch, Policy, BUILTIN_POLICY
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            gate = Gate(Policy(BUILTIN_POLICY), Budget(), KillSwitch(Path(d) / "ks"),
                        Ledger(Path(d) / "l.jsonl", "b"), Path(d) / "sandbox")
            with self.assertRaises(SandboxViolation):
                gate._resolve_sandboxed("sandbox:../../escaped.txt")

    def test_budget_is_metered_and_not_refilled(self):
        from do.policy import Budget
        from do.kernel.types import EffectRequest
        b = Budget(max_effects=2)
        r = EffectRequest("fs.write", "sandbox:x")
        self.assertTrue(b.check(r)[0]); b.debit(r)
        self.assertTrue(b.check(r)[0]); b.debit(r)
        self.assertFalse(b.check(r)[0])


if __name__ == "__main__":
    unittest.main()
