"""Capability growth: the measurement that replaces "does it sound intelligent?"

The scientific question this exists to answer:

    Can D.O. acquire capabilities that were not explicitly enumerated by its creator?

That question is only meaningful if the answer can be **no**, and if "no" is visible.
So every capability is recorded with an origin:

    seeded    enumerated by the creator in capabilities.seed_registry
    acquired  came into existence at runtime, not present in the seed

and the count is tracked per boot, so growth (or its absence) is a curve rather than
an anecdote.

**The honest state of this, today: acquisition is 0 and will stay 0** until something
can create a capability. That is not a bug in the metric - it is the metric working.
A growth chart that only ever goes up because the author added actions between runs
would measure the author, not the organism.

The one acquisition path that exists is deliberately modest and should not be
oversold: when an objective is met, the *sequence of actions that met it* is retained
as a named procedure keyed to the drive it relieved. The primitives were seeded; the
composition, its trigger condition, and its name were not. That is tier-3 procedural
acquisition in the ladder of docs/DO_CONCEPT.md section C - retaining a routine that
worked - and it is emphatically **not** writing new code, which is Phase 6 and needs
sandboxed execution that does not exist yet.
"""
from __future__ import annotations

import json
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS capabilities (
    name TEXT PRIMARY KEY,
    origin TEXT NOT NULL,            -- seeded | acquired
    description TEXT,
    definition TEXT,                 -- for acquired: the composition that worked
    first_seen_boot TEXT,
    first_seen_index INTEGER,
    first_seen_ts REAL,
    times_used INTEGER DEFAULT 0,
    last_used_ts REAL
);
CREATE TABLE IF NOT EXISTS capability_census (
    boot_id TEXT PRIMARY KEY,
    boot_index INTEGER,
    ts REAL,
    seeded INTEGER,
    acquired INTEGER,
    total INTEGER,
    new_this_boot TEXT
);
"""


def ensure_schema(store) -> None:
    store.db.executescript(SCHEMA)
    store.db.commit()


def register(store, name: str, origin: str, description: str = "",
             definition: dict | None = None, boot_index: int = 0) -> bool:
    """Record a capability. Returns True if it is new to this organism, ever."""
    ensure_schema(store)
    row = store.db.execute("SELECT name FROM capabilities WHERE name=?",
                           (name,)).fetchone()
    if row:
        return False
    store.db.execute(
        "INSERT INTO capabilities (name,origin,description,definition,first_seen_boot,"
        "first_seen_index,first_seen_ts) VALUES (?,?,?,?,?,?,?)",
        (name, origin, description,
         json.dumps(definition) if definition else None,
         store.boot_id, boot_index, time.time()))
    store.db.commit()
    return True


def census(store, boot_index: int, ledger=None) -> dict:
    """Snapshot the roster for this boot. This is the row that makes growth legible."""
    ensure_schema(store)
    rows = store.db.execute("SELECT origin, COUNT(*) n FROM capabilities"
                            " GROUP BY origin").fetchall()
    counts = {r["origin"]: r["n"] for r in rows}
    new = [r["name"] for r in store.db.execute(
        "SELECT name FROM capabilities WHERE first_seen_boot=?",
        (store.boot_id,)).fetchall()]
    rec = {"boot_id": store.boot_id, "boot_index": boot_index, "ts": time.time(),
           "seeded": counts.get("seeded", 0), "acquired": counts.get("acquired", 0),
           "total": sum(counts.values()), "new_this_boot": new}
    store.db.execute(
        "INSERT OR REPLACE INTO capability_census VALUES (?,?,?,?,?,?,?)",
        (rec["boot_id"], rec["boot_index"], rec["ts"], rec["seeded"],
         rec["acquired"], rec["total"], json.dumps(new)))
    store.db.commit()
    if ledger is not None and new:
        from ..ledger import EventType
        ledger.append(EventType.CAPABILITY_CHANGE, {
            "new_capabilities": new, "seeded": rec["seeded"],
            "acquired": rec["acquired"], "total": rec["total"]})
    return rec


def acquire_from_objective(store, objective, boot_index: int, ledger=None) -> str | None:
    """Retain the composition that met an objective, as a named procedure.

    Named from the drive it relieved and the sequence that relieved it, so the name
    itself is not something the creator wrote. Returns the name if this is genuinely
    new, else None.

    What this is: a retained, replayable routine with a trigger condition.
    What it is not: new code. Nothing here synthesises behaviour that did not exist.
    """
    if not objective or objective.status != "met" or not objective.actions_taken:
        return None
    seq = [a for a in objective.actions_taken]
    name = f"resolve:{objective.drive}:" + "+".join(seq)
    definition = {
        "trigger": {"drive": objective.drive, "metric": objective.metric_key,
                    "direction": objective.direction},
        "sequence": seq,
        "learned_in_cycles": objective.attempts,
        "moved": {"from": objective.start_value, "to": objective.current_value,
                  "target": objective.target_value},
    }
    is_new = register(store, name, "acquired",
                      description=(f"a sequence that returned drive "
                                   f"'{objective.drive}' to its band"),
                      definition=definition, boot_index=boot_index)
    if is_new and ledger is not None:
        from ..ledger import EventType
        ledger.append(EventType.CAPABILITY_CHANGE, {
            "acquired": name, "origin": "acquired",
            "definition": definition,
            "note": "composition retained from an objective that was met; the "
                    "primitives were seeded, the composition was not"})
    return name if is_new else None


def history(store) -> list[dict]:
    ensure_schema(store)
    return [dict(r) for r in store.db.execute(
        "SELECT * FROM capability_census ORDER BY boot_index").fetchall()]


def roster(store) -> list[dict]:
    ensure_schema(store)
    return [dict(r) for r in store.db.execute(
        "SELECT name, origin, first_seen_index, times_used FROM capabilities"
        " ORDER BY origin DESC, first_seen_index, name").fetchall()]
