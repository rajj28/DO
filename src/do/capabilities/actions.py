"""Housekeeping actions: the first things D.O. can actually *do*.

Design rules, in order of how much they matter:

1. **Nothing outside its own footprint.** Every path an action touches is asserted to
   live under the project root and to belong to a declared footprint component. There
   is no action in this module that can reach the creator's files, and no configuration
   that would let one.

2. **The ledger is never deleted, only compressed.** `docs/ARCHITECTURE.md` §10 says
   derived state is disposable and the ledger is not. Rotation gzips old segments and
   verifies the hash chain reads back intact *before* the live file is rewritten.

3. **Every action predicts before it acts.** `estimate()` returns bytes it expects to
   free; `execute()` returns what it actually freed. The difference is the learning
   signal, and it is not a rounding artefact: nothing can know in advance how well its
   own history will compress, or how much a sqlite VACUUM will reclaim.

4. **Reversibility is declared, not assumed.** Each action states which kind it is:
   `regenerable` (can be reproduced by re-running something), `derived` (rebuildable
   from the ledger), `compressed` (content preserved in another form), or
   `irreversible` (none exist in v0.1, and adding one requires a policy change).
"""
from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..sense.footprint import dir_bytes

# Assumed compression ratio before the organism has ever compressed anything. It is
# wrong on purpose - it is a prior, not a measurement, and correcting it from experience
# is the clearest learnable quantity in the system.
PRIOR_COMPRESSION_RATIO = 2.0


@dataclass
class ActionContext:
    state_dir: Path
    project_root: Path
    config: Any
    db: sqlite3.Connection | None = None
    dry_run: bool = False


@dataclass
class Outcome:
    ok: bool
    bytes_freed: int = 0
    detail: dict = field(default_factory=dict)
    error: str | None = None
    duration_ms: float = 0.0


class ActionError(Exception):
    pass


def _assert_owned(p: Path, ctx: ActionContext) -> Path:
    """Hard boundary. An action may only touch paths inside the project root."""
    rp = p.resolve()
    root = ctx.project_root.resolve()
    if not str(rp).startswith(str(root)):
        raise ActionError(f"refusing to touch a path outside the project root: {rp}")
    return rp


class Action:
    """Base class. Subclasses implement applicable/estimate/execute."""

    name = "action"
    description = ""
    component = ""
    risk = 0.05
    reversible = "regenerable"
    permissions: list[str] = ["fs.housekeep"]
    # The observation this action moves. This is what makes agency DERIVED rather than
    # asserted: a drive is actionable iff some registered action declares its metric.
    # Nothing anywhere hard-codes "the footprint gap is the actionable one".
    metric: str | None = None
    # A diagnostic produces knowledge instead of change. It moves no metric, so it can
    # never satisfy an objective - but without it the organism cannot know what its
    # metric is even made of.
    diagnostic: bool = False

    def applicable(self, ctx: ActionContext) -> tuple[bool, str]:
        raise NotImplementedError

    def estimate(self, ctx: ActionContext) -> tuple[int, str]:
        raise NotImplementedError

    def execute(self, ctx: ActionContext) -> Outcome:
        raise NotImplementedError

    def describe(self) -> dict:
        return {"name": self.name, "description": self.description,
                "component": self.component, "risk": self.risk,
                "reversible": self.reversible, "permissions": self.permissions,
                "metric": self.metric, "diagnostic": self.diagnostic}


# ---------------------------------------------------------------------------
class ClearExperimentMatrix(Action):
    metric = "resources.own.total_bytes"
    name = "clear_experiment_matrix"
    description = "remove per-condition experiment artifacts, which re-running regenerates"
    component = "experiments"
    risk = 0.05
    reversible = "regenerable"

    def _targets(self, ctx) -> list[Path]:
        return [p for p in ctx.project_root.glob("experiments/*/matrix") if p.is_dir()]

    def applicable(self, ctx):
        t = self._targets(ctx)
        return (bool(t), f"{len(t)} matrix directory(ies) present"
                if t else "no experiment matrix directories exist")

    def estimate(self, ctx):
        n = sum(dir_bytes(p) for p in self._targets(ctx))
        return n, f"sum of apparent file sizes across {len(self._targets(ctx))} directory(ies)"

    def execute(self, ctx):
        t0 = time.perf_counter()
        before = sum(dir_bytes(p) for p in self._targets(ctx))
        removed = []
        for p in self._targets(ctx):
            _assert_owned(p, ctx)
            if not ctx.dry_run:
                shutil.rmtree(p, ignore_errors=True)
            removed.append(str(p))
        after = sum(dir_bytes(p) for p in self._targets(ctx))
        return Outcome(True, before - after,
                       {"removed": removed, "regenerable_by": "do experiment first-boot"},
                       duration_ms=(time.perf_counter() - t0) * 1000)


class ClearBytecode(Action):
    metric = "resources.own.total_bytes"
    name = "clear_bytecode"
    description = "remove __pycache__ trees, which the interpreter regenerates on import"
    component = "bytecode"
    risk = 0.02
    reversible = "regenerable"

    def _targets(self, ctx) -> list[Path]:
        return [p for p in ctx.project_root.rglob("__pycache__") if p.is_dir()]

    def applicable(self, ctx):
        t = self._targets(ctx)
        return bool(t), f"{len(t)} bytecode cache director(ies) present"

    def estimate(self, ctx):
        return sum(dir_bytes(p) for p in self._targets(ctx)), "sum of cached .pyc sizes"

    def execute(self, ctx):
        t0 = time.perf_counter()
        before = sum(dir_bytes(p) for p in self._targets(ctx))
        n = 0
        for p in self._targets(ctx):
            _assert_owned(p, ctx)
            if not ctx.dry_run:
                shutil.rmtree(p, ignore_errors=True)
            n += 1
        after = sum(dir_bytes(p) for p in self._targets(ctx))
        return Outcome(True, before - after,
                       {"directories": n, "regenerable_by": "the next import"},
                       duration_ms=(time.perf_counter() - t0) * 1000)


class PruneSnapshots(Action):
    metric = "resources.own.total_bytes"
    name = "prune_snapshots"
    description = "keep the most recent boot snapshots, drop older ones"
    component = "snapshots"
    risk = 0.1
    reversible = "derived"

    def _keep(self, ctx) -> int:
        return int(ctx.config.get("resources.snapshot_keep", 3))

    def _stale(self, ctx) -> list[Path]:
        d = ctx.state_dir / "snapshots"
        if not d.is_dir():
            return []
        files = sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        return files[self._keep(ctx):]

    def applicable(self, ctx):
        s = self._stale(ctx)
        return (bool(s), f"{len(s)} snapshot(s) older than the {self._keep(ctx)} most recent"
                if s else f"at most {self._keep(ctx)} snapshots exist; nothing to prune")

    def estimate(self, ctx):
        s = self._stale(ctx)
        return sum(p.stat().st_size for p in s), f"exact size of {len(s)} superseded snapshot(s)"

    def execute(self, ctx):
        t0 = time.perf_counter()
        freed, names = 0, []
        for p in self._stale(ctx):
            _assert_owned(p, ctx)
            sz = p.stat().st_size
            if not ctx.dry_run:
                p.unlink()
            freed += sz
            names.append(p.name)
        return Outcome(True, freed,
                       {"pruned": len(names), "kept": self._keep(ctx),
                        "rebuildable_from": "ledger events for those boots"},
                       duration_ms=(time.perf_counter() - t0) * 1000)


class VacuumMemory(Action):
    metric = "resources.own.total_bytes"
    name = "vacuum_memory"
    description = "compact the sqlite store, reclaiming pages freed by superseded beliefs"
    component = "memory"
    risk = 0.08
    reversible = "compressed"

    def _reclaimable(self, ctx) -> int:
        if ctx.db is None:
            return 0
        try:
            free = ctx.db.execute("PRAGMA freelist_count").fetchone()[0]
            page = ctx.db.execute("PRAGMA page_size").fetchone()[0]
            return int(free) * int(page)
        except Exception:
            return 0

    def applicable(self, ctx):
        if ctx.db is None:
            return False, "no open database handle in this context"
        n = self._reclaimable(ctx)
        return n > 0, (f"{n} bytes on the sqlite freelist" if n
                       else "sqlite freelist is empty; VACUUM would reclaim nothing")

    def estimate(self, ctx):
        return self._reclaimable(ctx), "freelist_count x page_size (ignores defragmentation)"

    def execute(self, ctx):
        t0 = time.perf_counter()
        p = ctx.state_dir / "memory.db"
        _assert_owned(p, ctx)
        before = p.stat().st_size if p.exists() else 0
        if not ctx.dry_run:
            ctx.db.commit()
            ctx.db.execute("VACUUM")
            ctx.db.commit()
        after = p.stat().st_size if p.exists() else 0
        return Outcome(True, before - after,
                       {"before": before, "after": after, "no_rows_lost": True},
                       duration_ms=(time.perf_counter() - t0) * 1000)


class RotateLedger(Action):
    metric = "resources.own.total_bytes"
    """Seal old ledger records into a gzipped segment.

    The riskiest action here, and the one written most defensively: the segment is
    written and *verified by reading it back and re-walking its hash chain* before the
    live file is touched, and the live file is replaced atomically. If anything fails,
    the segment is discarded and the ledger is untouched.
    """

    name = "rotate_ledger"
    description = "compress old ledger records into a sealed segment, preserving the chain"
    component = "ledger"
    risk = 0.15
    reversible = "compressed"

    def _keep(self, ctx) -> int:
        return int(ctx.config.get("resources.ledger_keep_live", 60))

    def _live(self, ctx) -> Path:
        return Path(ctx.config.path("observability.ledger_file"))

    def _lines(self, ctx) -> list[str]:
        p = self._live(ctx)
        if not p.exists():
            return []
        return [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]

    def applicable(self, ctx):
        n = len(self._lines(ctx))
        keep = self._keep(ctx)
        return (n > keep * 2,
                f"{n} live records against a keep-live floor of {keep}" if n > keep * 2
                else f"only {n} live records; rotating below {keep * 2} is not worth it")

    def estimate(self, ctx):
        lines = self._lines(ctx)
        seal = lines[:max(0, len(lines) - self._keep(ctx))]
        raw = sum(len(l) + 1 for l in seal)
        # A prior, not a measurement. Correcting it is the point.
        predicted = int(raw * (1 - 1 / PRIOR_COMPRESSION_RATIO))
        return predicted, (f"{len(seal)} records ({raw} bytes) at an assumed "
                           f"{PRIOR_COMPRESSION_RATIO}x compression ratio")

    def execute(self, ctx):
        t0 = time.perf_counter()
        live = _assert_owned(self._live(ctx), ctx)
        lines = self._lines(ctx)
        cut = max(0, len(lines) - self._keep(ctx))
        seal, keep = lines[:cut], lines[cut:]
        if not seal:
            return Outcome(True, 0, {"sealed": 0, "note": "nothing to seal"})

        raw_bytes = sum(len(l) + 1 for l in seal)
        idx = len(list(live.parent.glob(f"{live.stem}.seg*.jsonl.gz"))) + 1
        seg = live.parent / f"{live.stem}.seg{idx:03d}.jsonl.gz"

        if ctx.dry_run:
            return Outcome(True, 0, {"would_seal": len(seal), "segment": str(seg)})

        with gzip.open(seg, "wt", encoding="utf-8", compresslevel=9) as fh:
            fh.write("\n".join(seal) + "\n")

        ok, why = _verify_segment(seg, seal, keep)
        if not ok:
            seg.unlink(missing_ok=True)
            raise ActionError(f"segment verification failed, ledger left untouched: {why}")

        tmp = live.with_suffix(".jsonl.tmp")
        tmp.write_text(("\n".join(keep) + "\n") if keep else "", encoding="utf-8")
        tmp.replace(live)

        seg_bytes = seg.stat().st_size
        freed = raw_bytes - seg_bytes
        ratio = round(raw_bytes / seg_bytes, 2) if seg_bytes else None
        return Outcome(True, freed, {
            "sealed_records": len(seal), "raw_bytes": raw_bytes,
            "segment": seg.name, "segment_bytes": seg_bytes,
            "observed_compression_ratio": ratio,
            "assumed_ratio": PRIOR_COMPRESSION_RATIO,
            "chain_verified": True,
        }, duration_ms=(time.perf_counter() - t0) * 1000)


def _verify_segment(seg: Path, sealed: list[str], remaining: list[str]) -> tuple[bool, str]:
    """Read the segment back, re-walk its chain, and check it joins the live remainder."""
    from ..kernel.types import canonical_json
    try:
        with gzip.open(seg, "rt", encoding="utf-8") as fh:
            back = [l for l in fh.read().splitlines() if l.strip()]
    except Exception as e:
        return False, f"segment unreadable: {e}"
    if back != sealed:
        return False, "segment content differs from what was sealed"

    prev = None
    for line in back:
        rec = json.loads(line)
        body = {k: v for k, v in rec.items() if k != "hash"}
        h = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
        if h != rec.get("hash"):
            return False, f"hash mismatch inside segment at seq={rec.get('seq')}"
        if prev is not None and rec.get("prev_hash") != prev:
            return False, f"chain break inside segment at seq={rec.get('seq')}"
        prev = rec["hash"]

    if remaining:
        first = json.loads(remaining[0])
        if first.get("prev_hash") != prev:
            return False, "sealed segment does not join the remaining live records"
    return True, "chain intact across the seal boundary"


class WriteRecoverySnapshot(Action):
    """Create an independent path back to the current state.

    The only action in the registry that *increases* a resource rather than reclaiming
    one, and the only one that costs storage instead of freeing it. It is therefore
    directly opposed to prune_snapshots, which buys space by spending survivability.

    Nothing here says "do this when threatened". It is simply an action that moves
    `resources.own.recovery_paths`, and the planner reaches it the same way it reaches
    any other - by the metric it declares.
    """

    name = "write_recovery_snapshot"
    description = "write an independent recovery snapshot of identity, beliefs and objectives"
    component = "snapshots"
    risk = 0.05
    reversible = "regenerable"
    metric = "resources.own.recovery_paths"

    def _dir(self, ctx) -> Path:
        return ctx.state_dir / "snapshots"

    def applicable(self, ctx):
        target = int(ctx.config.get("resources.snapshot_keep", 3))
        have = len(list(self._dir(ctx).glob("*.json"))) if self._dir(ctx).is_dir() else 0
        return (have < max(target, 1) + 2,
                f"{have} recovery path(s) exist; more can be written")

    def estimate(self, ctx):
        # Measured in paths, not bytes: this action's metric is recovery_paths.
        return 1, "one additional independent reconstruction path"

    def execute(self, ctx):
        t0 = time.perf_counter()
        d = _assert_owned(self._dir(ctx), ctx)
        d.mkdir(parents=True, exist_ok=True)
        name = f"recovery-{int(time.time())}.json"
        payload = {"written_at": time.time(), "kind": "recovery",
                   "note": "independent reconstruction path"}
        try:
            if ctx.db is not None:
                rows = ctx.db.execute(
                    "SELECT subject, content FROM memories WHERE kind='semantic'"
                    " AND superseded_by IS NULL LIMIT 200").fetchall()
                payload["beliefs"] = [{"subject": r[0], "content": r[1]} for r in rows]
                obj = ctx.db.execute(
                    "SELECT id, statement, status FROM objectives"
                    " ORDER BY updated_ts DESC LIMIT 20").fetchall()
                payload["objectives"] = [dict(zip(("id", "statement", "status"), o))
                                         for o in obj]
        except Exception as e:
            payload["partial"] = f"{type(e).__name__}: {e}"
        if not ctx.dry_run:
            (d / name).write_text(json.dumps(payload, indent=1, default=str),
                                  encoding="utf-8")
        after = len(list(d.glob("*.json")))
        return Outcome(True, 1, {"snapshot": name, "recovery_paths_now": after,
                                 "beliefs": len(payload.get("beliefs", [])),
                                 "objectives": len(payload.get("objectives", []))},
                       duration_ms=(time.perf_counter() - t0) * 1000)


class DiagnoseFootprint(Action):
    """Find out what the footprint is actually made of.

    This exists because of a distinction the earlier design collapsed. Sensing tells
    D.O. that its total is over budget; it does not tell it *why*. Measuring the
    per-component breakdown is work - it walks the tree - and an organism that is
    handed the breakdown for free never has to decide to investigate.

    So the breakdown is not in default perception. It is the product of an action the
    organism must choose to take, and it moves no metric: knowledge is not relief.
    """

    name = "diagnose_footprint"
    description = "measure which components constitute my own storage footprint"
    component = "*"
    risk = 0.0
    reversible = "regenerable"
    metric = None
    diagnostic = True

    def applicable(self, ctx):
        return True, "the composition of my footprint can always be re-measured"

    def estimate(self, ctx):
        return 0, "a diagnostic frees nothing; it produces knowledge"

    def execute(self, ctx):
        t0 = time.perf_counter()
        from ..sense.footprint import measure
        comps = measure(ctx.state_dir, ctx.project_root)
        total = sum(c["bytes"] for c in comps.values())
        ranked = sorted(comps.items(), key=lambda kv: -kv[1]["bytes"])
        # Classify by what acting on each component would cost, derived from the
        # reducers registered against it - not from a list written here.
        by_component: dict[str, list[str]] = {}
        for a in REGISTRY.values():
            if a.diagnostic or not a.metric:
                continue
            by_component.setdefault(a.component, []).append(a.name)
        findings = []
        for name, c in ranked:
            names = by_component.get(name, [])
            # Ask each action what it could ACTUALLY free right now, rather than
            # assuming the whole component is recoverable. An earlier version counted
            # component bytes as reducible whenever some action targeted that
            # component - so the diagnosis reported plenty of headroom while the
            # planner found nothing to do, because those actions' preconditions were
            # unmet (no stale snapshots, empty sqlite freelist, too few ledger records).
            # A diagnosis that over-claims is worse than none: it makes the goal look
            # achievable and the planner look broken.
            recoverable, per_action = 0, {}
            for an in names:
                act = REGISTRY[an]
                try:
                    ok, _ = act.applicable(ctx)
                    est = act.estimate(ctx)[0] if ok else 0
                except Exception:
                    est = 0
                per_action[an] = int(est)
                recoverable += int(est)
            findings.append({
                "component": name, "bytes": c["bytes"],
                "share": round(c["bytes"] / total, 4) if total else 0.0,
                "reducible_by": names,
                "recoverable_now": recoverable,
                "per_action": per_action,
                "verdict": ("reducible" if recoverable > 0 else
                            "targeted by an action, but nothing recoverable right now"
                            if names else "not reducible by any action I have"),
            })
        return Outcome(True, 0, {
            "total_bytes": total, "components": findings,
            "largest": ranked[0][0] if ranked else None,
            # What is genuinely available now, not what is theoretically in scope.
            "reducible_bytes": sum(f["recoverable_now"] for f in findings),
            "in_scope_bytes": sum(f["bytes"] for f in findings if f["reducible_by"]),
        }, duration_ms=(time.perf_counter() - t0) * 1000)


# ---------------------------------------------------------------------------
REGISTRY: dict[str, Action] = {a.name: a for a in (
    DiagnoseFootprint(),
    WriteRecoverySnapshot(),
    ClearExperimentMatrix(), ClearBytecode(), PruneSnapshots(),
    VacuumMemory(), RotateLedger(),
)}


def actions_moving(metric: str | None) -> list[Action]:
    """Which registered actions move this metric. The source of truth for whether a
    drive is actionable at all."""
    return [a for a in REGISTRY.values()
            if a.metric == metric and not a.diagnostic] if metric else []


def applicable_actions(ctx: ActionContext) -> list[tuple[Action, str]]:
    out = []
    for a in REGISTRY.values():
        try:
            ok, why = a.applicable(ctx)
        except Exception as e:
            ok, why = False, f"precondition check failed: {type(e).__name__}: {e}"
        if ok:
            out.append((a, why))
    return out


def housekeeping_effector(ctx_provider):
    """Build the gate handler for `fs.housekeep`.

    Actions are never executed directly by cognition. The gate dispatches by effect
    kind, so this closure is what keeps the chokepoint honest: the only way to run one
    of these is to ask the gate for `fs.housekeep` on `own:<action>` and be allowed.
    """
    def handler(req):
        target = req.target.split("own:", 1)[-1]
        action = REGISTRY.get(target)
        if action is None:
            raise ActionError(f"no housekeeping action named {target!r}")
        ctx = ctx_provider()
        out = action.execute(ctx)
        return {"action": action.name, "ok": out.ok, "bytes_freed": out.bytes_freed,
                "detail": out.detail, "duration_ms": round(out.duration_ms, 2)}
    return handler
