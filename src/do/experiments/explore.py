"""Brutal (but read-only) internet exposure, driven by D.O.'s own curiosity.

What is his and what is mine, stated up front so the result is interpretable:

  HIS   : which unknowns matter, and in what order. The targets are his own
          top-ranked UNDESCRIBED_REFERENT gaps - the things his attention already
          says are the cheapest frontier of world-knowledge. I do not choose them.
  MINE  : the mechanism (a keyless Wikipedia summary fetch through the gate) and the
          trigger (running this). I hand him a way to look things up and turn it on.

So this is exposure, not autonomy: his autonomous cycle does NOT choose to investigate,
because survival (storage) dominates curiosity and no investigate-action is wired into
his planner. That is itself the finding, and it is reported rather than hidden. This
harness answers a different question: *given a way to read the world, and his own
priorities about what he does not know, what does he learn - and does the local model
come up in what he cares about?*

Everything is read-only, gated, and stored REPORTED with provenance. A page is evidence,
never instruction; it cannot change his identity, rules, or policy.
"""
from __future__ import annotations

import json
import time
import urllib.parse
from pathlib import Path

from ..kernel import lifecycle
from ..kernel.types import EffectRequest, Epistemic
from ..memory import MemoryRecord

WIKI = "https://en.wikipedia.org/api/rest_v1/page/summary/"


def _lookup(gate, term: str) -> dict:
    """Fetch a keyless summary for a term through the gate. Returns a provenance
    record; a 404 is information (no article), not a failure."""
    url = WIKI + urllib.parse.quote(term.replace(":", " ").split()[0]
                                    if ":" in term else term)
    r = gate.request(EffectRequest(
        kind="net.http", target=url,
        justification=f"reduce my ignorance about '{term}', a named thing here I "
                      f"cannot describe", payload={"timeout": 15, "max_bytes": 60000}))
    if not r.ok:
        return {"found": False, "reason": r.error or r.verdict, "url": url}
    try:
        d = json.loads((r.value or {}).get("body", "{}"))
    except Exception:
        return {"found": False, "reason": "unparseable", "url": url}
    if d.get("type") == "standard" and d.get("extract"):
        return {"found": True, "title": d.get("title"),
                "extract": d["extract"][:500], "url": url}
    return {"found": False, "reason": d.get("type", "no summary"), "url": url}


def run(config, **kw) -> int:
    bar = "=" * 78
    t0 = time.time()
    out = config.root / "experiments" / "explore"
    out.mkdir(parents=True, exist_ok=True)
    from ..effectors import cli_approver
    from ..drives import compute as compute_drives, error_map

    org = lifecycle.boot(config, quiet=True, approver=cli_approver)
    k = int(kw.get("k", 6))

    print(f"\n{bar}\nD.O. EXPLORES THE INTERNET (his curiosity, my mechanism)\n{bar}")

    comp0 = next((d for d in org.drives if d.name == "comprehension"), None)
    print(f"\n  Before: comprehension drive = {comp0.value:.3f} "
          f"({comp0.basis})" if comp0 else "")

    # HIS ranking: the undescribed referents his attention put highest.
    targets = [g for g in org.gaps if g.kind == "UNDESCRIBED_REFERENT"][:k]
    print(f"  He has {len([g for g in org.gaps if g.kind=='UNDESCRIBED_REFERENT'])} "
          f"things he cannot describe. Taking his top {len(targets)} by his own "
          f"ranking:\n")

    narration, learned, model_seen = [], 0, None
    for g in targets:
        term = g.subject
        print(f"  → rank-priority {g.priority}: \"{g.question}\"")
        rec = _lookup(org.gate, term)
        if rec["found"]:
            learned += 1
            org.store.believe(
                subject=f"world.referent.env_system.{term}",
                content=f"{rec['title']}: {rec['extract']}",
                source=f"web:{rec['url']}", epistemic=Epistemic.REPORTED.value,
                confidence=0.4, importance=0.4,
                value={"described": True, "url": rec["url"]})
            print(f"      learned: {rec['extract'][:120]}...")
            print(f"      [stored REPORTED, conf 0.40, source {rec['url'].split('/')[-1]}]")
        else:
            print(f"      no article found ({rec['reason']}) - still information: "
                  f"this name is not a common encyclopedia entry")
        if "qwen" in term.lower() or "inference" in term.lower():
            model_seen = {"term": term, **rec}
        narration.append({"term": term, "question": g.question,
                          "priority": g.priority, **rec})
        time.sleep(0.5)

    # Re-measure: did learning move the drive? (real, not asserted)
    lifecycle._mark_described(org.view, org.store)
    org.drives = compute_drives(org.view, org.config, org.ledger)
    comp1 = next((d for d in org.drives if d.name == "comprehension"), None)

    print(f"\n{bar}\n  WHAT CHANGED")
    print(f"  comprehension drive: {comp0.value:.3f} -> {comp1.value:.3f} "
          f"({learned} of {len(targets)} referents now described)")
    print(f"  learning is real, not asserted: described_ratio is recomputed from "
          f"memory,\n  and the drive value moved because beliefs were written.")

    print(f"\n  DID THE MODEL COME UP IN WHAT HE CARED ABOUT?")
    if model_seen:
        print(f"  Yes - '{model_seen['term']}' was among his top unknowns.")
        if model_seen.get("found"):
            print(f"    He now holds: {model_seen['extract'][:140]}")
            print(f"    But note: knowing WHAT it is does not make him want to RUN it.")
            print(f"    His architecture resolves 'what is X' (comprehension); it has")
            print(f"    no drive that turns 'X exists and is useful' into 'acquire X'.")
        else:
            print(f"    He could not describe it from the web ({model_seen.get('reason')}).")
    else:
        print(f"  No - the model referent ranked below his top {k} curiosities;")
        print(f"  other unknowns (environment systems) mattered more to him.")

    summary = {"ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "duration_s": round(time.time() - t0, 1),
               "comprehension_before": comp0.value if comp0 else None,
               "comprehension_after": comp1.value if comp1 else None,
               "referents_learned": learned, "targets": len(targets),
               "model_in_top_curiosities": bool(model_seen),
               "narration": narration}
    (out / "results.json").write_text(json.dumps(summary, indent=2, default=str),
                                      encoding="utf-8")
    print(f"\n  data: {out / 'results.json'}\n{bar}\n")
    org.close("explore")
    return 0
