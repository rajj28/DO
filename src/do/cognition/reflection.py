"""Reflection: turn a boot's raw observations into memory, and revise what changed.

Two jobs, and the second is the interesting one:

1. **Consolidate** — write episodic records of what was observed and semantic beliefs
   about what is now held to be true, each with provenance and epistemic status.

2. **Revise** — compare this boot's measurements against beliefs carried from earlier
   boots. Where they disagree, supersede the old belief rather than overwriting it, so
   the change itself becomes part of the record. A belief that quietly changes value
   is indistinguishable from a belief that was always wrong.

Selectivity is deliberate: writing every observation to semantic memory would make
"what D.O. believes" synonymous with "what D.O. last measured", which is a log, not a
belief system. Only stable, decision-relevant keys are promoted.
"""
from __future__ import annotations

import time
from typing import Any

from ..kernel.types import Epistemic
from ..ledger import EventType
from ..memory import MemoryRecord

# Keys promoted to semantic belief. Chosen because they are stable enough that a
# change between boots is informative rather than noise.
BELIEF_KEYS = [
    "world.host.system", "world.host.machine", "self.runtime.version",
    "resources.cpu.logical", "resources.ram.total_bytes",
    "resources.disk.total_bytes", "world.network.reachable",
    "resources.disk.root",
]

# Volatile keys: recorded episodically (this is what I saw at this time), never as
# standing belief.
EPISODIC_ONLY = {"resources.ram.available_bytes", "resources.ram.free_ratio",
                 "resources.disk.free_bytes", "resources.disk.free_ratio",
                 "resources.cpu.load1", "self.clock.epoch", "self.process.pid"}


def consolidate(store, view, ledger, boot_id: str) -> dict:
    """Write memory for this boot. Returns a summary of what changed."""
    written = revised = 0
    revisions: list[dict] = []

    # 1. Episodic: one record summarising this boot's perception.
    obs_known = {k: o for k, o in view.observations.items() if o.is_known}
    store.write(MemoryRecord(
        kind="episodic",
        subject=f"boot:{boot_id}",
        content=(f"observed {len(obs_known)} values, "
                 f"{len(view.observations) - len(obs_known)} unknown; "
                 f"{len(view.referents)} referents visible; "
                 f"{len(view.capabilities)} capabilities declared"),
        value={k: o.value for k, o in obs_known.items()
               if not isinstance(o.value, (list, dict))},
        source=f"self_inspection@{boot_id}",
        epistemic=Epistemic.OBSERVED.value,
        confidence=1.0, importance=0.7, boot_id=boot_id,
        context="phase A self-observation"))
    written += 1

    # 2. Episodic: volatile resource readings, timestamped, never promoted.
    for key in EPISODIC_ONLY:
        o = view.observations.get(key)
        if not o or not o.is_known:
            continue
        store.write(MemoryRecord(
            kind="episodic", subject=key, content=f"{key}={o.value}{o.unit or ''}",
            value=o.value, source=o.source, epistemic=o.epistemic.value,
            confidence=o.confidence, importance=0.35, boot_id=boot_id,
            context="volatile reading; not promoted to belief"))
        written += 1

    # 3. Semantic: stable beliefs, revised on disagreement.
    for key in BELIEF_KEYS:
        o = view.observations.get(key)
        if not o or not o.is_known:
            continue
        content = f"{key} = {o.value}"
        mem_id, superseded = store.believe(
            subject=key, content=content, source=o.source,
            epistemic=o.epistemic.value,
            confidence=min(0.99, 0.6 + 0.1 * o.confidence),
            importance=0.6, value=o.value)
        written += 1
        if superseded:
            revised += 1
            revisions.append({"subject": key, "new": content, "superseded_id": superseded})
            ledger.append(EventType.BELIEF_UPDATE, {
                "subject": key, "new_value": o.value, "source": o.source,
                "superseded": superseded,
                "note": "prior belief retained and marked superseded, not deleted"})

    # 4. Semantic: what exists here, from referents. Existence is observed; identity
    #    is not, and the record says so.
    for r in view.referents[:60]:
        store.believe(
            subject=f"world.referent.{r['kind']}.{r['name']}",
            content=f"a referent named {r['name']} exists in this environment "
                    f"({r['evidence']}); nature unknown",
            source=r["source"], epistemic=Epistemic.OBSERVED.value,
            confidence=0.85, importance=0.3 + 0.3 * r["weight"],
            value={"kind": r["kind"], "described": False})
        store.relate("world", "contains", r["name"], source=r["source"], confidence=0.85)
        written += 1

    # 5. Procedural: what it now knows how to do, and at what cost.
    for c in view.capabilities:
        if c.get("status") != "available":
            continue
        store.write(MemoryRecord(
            kind="procedural", subject=f"capability.{c['name']}",
            content=f"{c['name']}: {c['description']} (permissions: "
                    f"{', '.join(c.get('permissions') or []) or 'none'})",
            value={"version": c.get("version"), "risk": c.get("risk")},
            source="capabilities.registry", epistemic=Epistemic.OBSERVED.value,
            confidence=0.9, importance=0.5, boot_id=boot_id))
        written += 1

    ledger.append(EventType.MEMORY_WRITE, {
        "written": written, "revised": revised,
        "kinds": store.counts()})
    return {"written": written, "revised": revised, "revisions": revisions}


def persist_gaps(store, gaps, ledger) -> dict:
    """Persist the uncertainty register. New gaps and carried gaps are distinguished,
    because a question the organism has been carrying is different information from a
    question it just formed."""
    new = carried = 0
    for g in gaps:
        is_new = store.upsert_gap(g.to_dict())
        g.is_new = is_new
        if is_new:
            new += 1
            ledger.append(EventType.GAP_OPEN, {
                "gap_id": g.id, "kind": g.kind, "about": g.about,
                "subject": g.subject, "priority": g.priority,
                "question": g.question})
        else:
            carried += 1
    return {"new": new, "carried": carried, "total": len(gaps)}


def summarize_boot(view, plan, utterance, drives) -> dict:
    from ..drives import total_error
    return {
        "ts": time.time(),
        "observations": len(view.observations),
        "known": sum(1 for o in view.observations.values() if o.is_known),
        "referents": len(view.referents),
        "capabilities_usable": sum(1 for c in view.capabilities
                                   if c.get("status") == "available"),
        "drive_total_error": total_error(drives),
        "focus": plan.focus.subject if plan else None,
        "speech_act": plan.speech_act if plan else None,
        "utterance_chars": len(utterance or ""),
    }
