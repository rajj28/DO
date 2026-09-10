"""Persistent memory: working, episodic, semantic, procedural.

sqlite3 because it is in the standard library, ACID, single-file, and needs no
server — the seed must not depend on anything that can fail to install
(docs/ARCHITECTURE.md §1).

Two design points worth defending:

1. **Belief revision is non-destructive.** Revising a semantic memory inserts a new
   row and stamps `superseded_by` on the old one. The justification trail is what
   makes a revision auditable rather than merely a different answer. This is a cheap
   approximation of a truth-maintenance system (Doyle 1979); it keeps the dependency
   record without the propagation machinery.

2. **Retrieval is recency x importance x relevance**, which is Park et al. (2023)'s
   memory stream, credited rather than reinvented. Relevance here is lexical, not
   embedding-based, because embeddings would cost a dependency and several hundred MB
   this host does not have.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,              -- episodic | semantic | procedural
    subject TEXT,
    content TEXT NOT NULL,
    value_json TEXT,
    source TEXT NOT NULL,            -- provenance: never null, never blank
    epistemic TEXT NOT NULL,
    ts REAL NOT NULL,
    confidence REAL NOT NULL,
    importance REAL NOT NULL,
    context TEXT,
    verification TEXT NOT NULL,      -- unverified|corroborated|contradicted|verified
    superseded_by TEXT,
    boot_id TEXT NOT NULL,
    access_count INTEGER DEFAULT 0,
    last_access REAL
);
CREATE INDEX IF NOT EXISTS idx_mem_kind    ON memories(kind);
CREATE INDEX IF NOT EXISTS idx_mem_subject ON memories(subject);
CREATE INDEX IF NOT EXISTS idx_mem_live    ON memories(superseded_by);

CREATE TABLE IF NOT EXISTS relations (
    src TEXT NOT NULL, rel TEXT NOT NULL, dst TEXT NOT NULL,
    confidence REAL DEFAULT 0.5, source TEXT, ts REAL,
    PRIMARY KEY (src, rel, dst)
);

CREATE TABLE IF NOT EXISTS gaps (
    id TEXT PRIMARY KEY,
    question TEXT NOT NULL, about TEXT NOT NULL, kind TEXT NOT NULL,
    subject TEXT, why_it_matters TEXT, reducible_by TEXT,
    info_gain REAL, instrumental REAL, tractability REAL, cost REAL, risk REAL,
    priority REAL, status TEXT NOT NULL DEFAULT 'open',
    first_seen_boot TEXT, first_seen_ts REAL,
    resolved_boot TEXT, resolved_ts REAL, resolution TEXT,
    times_seen INTEGER DEFAULT 1,
    selected_count INTEGER DEFAULT 0,
    escalated INTEGER DEFAULT 0,
    evidence_hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_gap_status ON gaps(status);

CREATE TABLE IF NOT EXISTS drives (
    name TEXT PRIMARY KEY, value REAL, target REAL, error REAL,
    updated_ts REAL, boot_id TEXT
);

CREATE TABLE IF NOT EXISTS objectives (
    id TEXT PRIMARY KEY, gap_id TEXT, statement TEXT, metric_key TEXT,
    direction TEXT, start_value REAL, current_value REAL, target_value REAL,
    deadline_cycles INTEGER, opened_cycle INTEGER, status TEXT,
    attempts INTEGER DEFAULT 0, actions_taken TEXT, closed_cycle INTEGER,
    note TEXT, boot_id TEXT, updated_ts REAL,
    drive TEXT, stage TEXT, subgoals TEXT, diagnosis TEXT
);
CREATE INDEX IF NOT EXISTS idx_obj_status ON objectives(status);

CREATE TABLE IF NOT EXISTS boots (
    boot_id TEXT PRIMARY KEY, boot_index INTEGER, started REAL, ended REAL,
    utterance TEXT, core TEXT, notes TEXT
);
"""


@dataclass
class MemoryRecord:
    kind: str
    content: str
    source: str
    epistemic: str
    boot_id: str
    subject: str | None = None
    value: Any = None
    confidence: float = 0.5
    importance: float = 0.5
    context: str | None = None
    verification: str = "unverified"
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    ts: float = field(default_factory=time.time)


class WorkingMemory:
    """Bounded, in-process, NOT persisted. If it survived a restart it would be
    long-term memory wearing a different name."""

    def __init__(self, capacity: int = 32):
        self.capacity = capacity
        self._items: list[tuple[float, str, Any]] = []

    def put(self, key: str, value: Any, salience: float = 0.5) -> None:
        self._items = [i for i in self._items if i[1] != key]
        self._items.append((salience, key, value))
        self._items.sort(key=lambda i: -i[0])
        del self._items[self.capacity:]        # least salient falls out, like attention

    def get(self, key: str, default: Any = None) -> Any:
        for _, k, v in self._items:
            if k == key:
                return v
        return default

    def contents(self) -> dict:
        return {k: v for _, k, v in self._items}

    def __len__(self) -> int:
        return len(self._items)


class MemoryStore:
    def __init__(self, path: Path, boot_id: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.boot_id = boot_id
        self.db = sqlite3.connect(str(self.path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self._migrate()
        self.db.commit()
        self.working = WorkingMemory()

    def _migrate(self) -> None:
        """Additive migrations for databases created by an earlier version.

        sqlite has no ADD COLUMN IF NOT EXISTS, and an organism whose whole premise is
        continuity must not lose its history to a schema change.
        """
        ocols = {r[1] for r in self.db.execute(
            "PRAGMA table_info(objectives)").fetchall()}
        for name, decl in (("drive", "TEXT"), ("stage", "TEXT"),
                           ("subgoals", "TEXT"), ("diagnosis", "TEXT")):
            if ocols and name not in ocols:
                self.db.execute(f"ALTER TABLE objectives ADD COLUMN {name} {decl}")
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(gaps)").fetchall()}
        for name, decl in (("selected_count", "INTEGER DEFAULT 0"),
                           ("escalated", "INTEGER DEFAULT 0"),
                           ("evidence_hash", "TEXT")):
            if name not in cols:
                self.db.execute(f"ALTER TABLE gaps ADD COLUMN {name} {decl}")
        self.db.commit()

    def close(self) -> None:
        self.db.commit()
        self.db.close()

    # ---- writing ----------------------------------------------------------
    def write(self, rec: MemoryRecord) -> str:
        if not rec.source or not rec.source.strip():
            # Honesty invariant: nothing enters memory without provenance.
            raise ValueError("memory write rejected: empty source (provenance required)")
        self.db.execute(
            "INSERT OR REPLACE INTO memories (id,kind,subject,content,value_json,source,"
            "epistemic,ts,confidence,importance,context,verification,superseded_by,boot_id)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
            (rec.id, rec.kind, rec.subject, rec.content,
             json.dumps(rec.value, default=str) if rec.value is not None else None,
             rec.source, rec.epistemic, rec.ts, rec.confidence, rec.importance,
             rec.context, rec.verification, rec.boot_id))
        self.db.commit()
        return rec.id

    def revise(self, old_id: str, new: MemoryRecord, reason: str) -> str:
        """Supersede a belief instead of overwriting it."""
        new_id = self.write(new)
        self.db.execute("UPDATE memories SET superseded_by=?, context=COALESCE(context,'')||? "
                        "WHERE id=?", (new_id, f" | superseded: {reason}", old_id))
        self.db.commit()
        return new_id

    def believe(self, subject: str, content: str, source: str, epistemic: str,
                confidence: float = 0.5, importance: float = 0.5,
                value: Any = None) -> tuple[str, str | None]:
        """Assert a semantic belief about `subject`.

        Returns (memory_id, superseded_id). If a live belief about the same subject
        exists with different content, it is revised rather than duplicated.
        """
        cur = self.db.execute(
            "SELECT * FROM memories WHERE kind='semantic' AND subject=? AND superseded_by IS NULL"
            " ORDER BY ts DESC LIMIT 1", (subject,)).fetchone()
        rec = MemoryRecord(kind="semantic", subject=subject, content=content, source=source,
                           epistemic=epistemic, confidence=confidence, importance=importance,
                           value=value, boot_id=self.boot_id)
        if cur is None:
            return self.write(rec), None
        if cur["content"] == content:
            self.db.execute("UPDATE memories SET confidence=MIN(1.0, confidence+0.05),"
                            " verification='corroborated' WHERE id=?", (cur["id"],))
            self.db.commit()
            return cur["id"], None
        return self.revise(cur["id"], rec, f"new evidence from {source}"), cur["id"]

    def relate(self, src: str, rel: str, dst: str, source: str, confidence: float = 0.5) -> None:
        self.db.execute("INSERT OR REPLACE INTO relations VALUES (?,?,?,?,?,?)",
                        (src, rel, dst, confidence, source, time.time()))
        self.db.commit()

    # ---- reading ----------------------------------------------------------
    def live(self, kind: str | None = None, limit: int = 100) -> list[sqlite3.Row]:
        q = "SELECT * FROM memories WHERE superseded_by IS NULL"
        args: list = []
        if kind:
            q += " AND kind=?"
            args.append(kind)
        q += " ORDER BY ts DESC LIMIT ?"
        args.append(limit)
        return self.db.execute(q, args).fetchall()

    def recall(self, query: str, k: int = 5, now: float | None = None) -> list[sqlite3.Row]:
        """recency x importance x relevance (Park et al. 2023)."""
        now = now or time.time()
        terms = set(re.findall(r"[a-z0-9_.]+", query.lower()))
        scored = []
        for row in self.db.execute(
                "SELECT * FROM memories WHERE superseded_by IS NULL ORDER BY ts DESC LIMIT 500"):
            age_h = max(0.0, (now - row["ts"]) / 3600.0)
            recency = math.exp(-0.03 * age_h)
            text = f"{row['subject'] or ''} {row['content']}".lower()
            hay = set(re.findall(r"[a-z0-9_.]+", text))
            relevance = len(terms & hay) / max(1, len(terms))
            score = recency * 0.3 + row["importance"] * 0.3 + relevance * 0.4
            if relevance > 0 or not terms:
                scored.append((score, row))
        scored.sort(key=lambda s: -s[0])
        out = [r for _, r in scored[:k]]
        for r in out:
            self.db.execute("UPDATE memories SET access_count=access_count+1, last_access=?"
                            " WHERE id=?", (now, r["id"]))
        self.db.commit()
        return out

    def counts(self) -> dict:
        c = {}
        for kind in ("episodic", "semantic", "procedural"):
            c[kind] = self.db.execute(
                "SELECT COUNT(*) n FROM memories WHERE kind=? AND superseded_by IS NULL",
                (kind,)).fetchone()["n"]
        c["superseded"] = self.db.execute(
            "SELECT COUNT(*) n FROM memories WHERE superseded_by IS NOT NULL").fetchone()["n"]
        c["relations"] = self.db.execute("SELECT COUNT(*) n FROM relations").fetchone()["n"]
        c["gaps_open"] = self.db.execute(
            "SELECT COUNT(*) n FROM gaps WHERE status='open'").fetchone()["n"]
        c["gaps_resolved"] = self.db.execute(
            "SELECT COUNT(*) n FROM gaps WHERE status='resolved'").fetchone()["n"]
        c["boots"] = self.db.execute("SELECT COUNT(*) n FROM boots").fetchone()["n"]
        return c

    # ---- gaps (the uncertainty register) ----------------------------------
    def upsert_gap(self, g: dict) -> bool:
        """Returns True if this gap is new to the organism (never seen in any boot)."""
        row = self.db.execute("SELECT id, times_seen FROM gaps WHERE id=?", (g["id"],)).fetchone()
        if row:
            self.db.execute(
                "UPDATE gaps SET priority=?, info_gain=?, instrumental=?, tractability=?,"
                " cost=?, risk=?, times_seen=times_seen+1, status=CASE WHEN status='resolved'"
                " THEN 'open' ELSE status END WHERE id=?",
                (g["priority"], g["info_gain"], g["instrumental"], g["tractability"],
                 g["cost"], g["risk"], g["id"]))
            self.db.commit()
            return False
        self.db.execute(
            "INSERT INTO gaps (id,question,about,kind,subject,why_it_matters,reducible_by,"
            "info_gain,instrumental,tractability,cost,risk,priority,status,first_seen_boot,"
            "first_seen_ts) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?, 'open',?,?)",
            (g["id"], g["question"], g["about"], g["kind"], g.get("subject"),
             g.get("why_it_matters"), json.dumps(g.get("reducible_by", [])),
             g["info_gain"], g["instrumental"], g["tractability"], g["cost"], g["risk"],
             g["priority"], self.boot_id, time.time()))
        self.db.commit()
        return True

    def open_gaps(self, limit: int = 50) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT * FROM gaps WHERE status='open' ORDER BY priority DESC LIMIT ?",
            (limit,)).fetchall()

    def carried_gaps(self) -> list[sqlite3.Row]:
        """Open gaps first seen in an earlier boot. The organism's grudges."""
        return self.db.execute(
            "SELECT * FROM gaps WHERE status='open' AND first_seen_boot != ?"
            " ORDER BY priority DESC", (self.boot_id,)).fetchall()

    def gap_history(self) -> dict[str, dict]:
        """What happened last time each open gap was selected. Feeds staleness and
        escalation damping in cognition.gaps.apply_history."""
        return {r["id"]: {"selected_count": r["selected_count"] or 0,
                          "escalated": r["escalated"] or 0,
                          "evidence_hash": r["evidence_hash"]}
                for r in self.db.execute(
                    "SELECT id, selected_count, escalated, evidence_hash FROM gaps")}

    def mark_selected(self, gap_id: str, evidence_hash: str) -> None:
        self.db.execute("UPDATE gaps SET selected_count=COALESCE(selected_count,0)+1,"
                        " evidence_hash=? WHERE id=?", (evidence_hash, gap_id))
        self.db.commit()

    def mark_escalated(self, gap_id: str) -> None:
        self.db.execute("UPDATE gaps SET escalated=COALESCE(escalated,0)+1 WHERE id=?",
                        (gap_id,))
        self.db.commit()

    def resolve_gap(self, gap_id: str, resolution: str) -> None:
        self.db.execute("UPDATE gaps SET status='resolved', resolved_boot=?, resolved_ts=?,"
                        " resolution=? WHERE id=?",
                        (self.boot_id, time.time(), resolution, gap_id))
        self.db.commit()

    # ---- drives & boots ---------------------------------------------------
    def save_drives(self, drives: Iterable) -> None:
        for d in drives:
            self.db.execute("INSERT OR REPLACE INTO drives VALUES (?,?,?,?,?,?)",
                            (d.name, d.value, d.target, d.error, time.time(), self.boot_id))
        self.db.commit()

    def last_drives(self) -> dict[str, dict]:
        return {r["name"]: dict(r) for r in self.db.execute(
            "SELECT * FROM drives").fetchall()}

    def record_boot(self, boot_id: str, boot_index: int, started: float,
                    utterance: str, core: str, notes: str = "") -> None:
        self.db.execute("INSERT OR REPLACE INTO boots VALUES (?,?,?,?,?,?,?)",
                        (boot_id, boot_index, started, time.time(), utterance, core, notes))
        self.db.commit()

    # ---- objectives -------------------------------------------------------
    def save_objective(self, o) -> None:
        """Objectives outlive the process. A goal that evaporates on exit is a task
        list, not an intention."""
        self.db.execute(
            "INSERT OR REPLACE INTO objectives (id,gap_id,statement,metric_key,direction,"
            "start_value,current_value,target_value,deadline_cycles,opened_cycle,status,"
            "attempts,actions_taken,closed_cycle,note,boot_id,updated_ts,"
            "drive,stage,subgoals,diagnosis)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (o.id, o.gap_id, o.statement, o.metric_key, o.direction, o.start_value,
             o.current_value, o.target_value, o.deadline_cycles, o.opened_cycle,
             o.status, o.attempts, json.dumps(o.actions_taken), o.closed_cycle,
             o.note, self.boot_id, time.time(),
             o.drive, o.stage, json.dumps(o.subgoals),
             json.dumps(o.diagnosis) if o.diagnosis else None))
        self.db.commit()

    def open_objective(self):
        r = self.db.execute("SELECT * FROM objectives WHERE status='open'"
                            " ORDER BY updated_ts DESC LIMIT 1").fetchone()
        if r is None:
            return None
        from ..cognition.objectives import Objective
        return Objective(
            id=r["id"], gap_id=r["gap_id"], drive=r["drive"] or "",
            statement=r["statement"],
            metric_key=r["metric_key"], direction=r["direction"],
            start_value=r["start_value"], current_value=r["current_value"],
            target_value=r["target_value"], deadline_cycles=r["deadline_cycles"],
            opened_cycle=r["opened_cycle"], status=r["status"],
            attempts=r["attempts"] or 0,
            actions_taken=json.loads(r["actions_taken"] or "[]"),
            closed_cycle=r["closed_cycle"], note=r["note"] or "",
            stage=r["stage"] or "reduce",
            subgoals=json.loads(r["subgoals"] or "[]"),
            diagnosis=json.loads(r["diagnosis"]) if r["diagnosis"] else None)

    def objectives_summary(self) -> dict:
        rows = self.db.execute("SELECT status, COUNT(*) n FROM objectives"
                               " GROUP BY status").fetchall()
        return {r["status"]: r["n"] for r in rows}

    def previous_boot(self) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT * FROM boots WHERE boot_id != ? ORDER BY started DESC LIMIT 1",
            (self.boot_id,)).fetchone()
