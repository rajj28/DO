"""E1-E5: read-only internet perception, resource inventory, constraint, goal, fact.

Read-only by construction. The only outward effects are `net.dns` (resolves a name,
sends no payload) and `net.http` (fetches a public page, approval-gated). Nothing is
deployed, nothing is written anywhere but D.O.'s own sandbox and memory, and web
content is stored REPORTED and never executed.

Integrity gate (§20 of the phase brief): before any result is reported, verify the
run was actually online and actually used the network. A "perception" experiment that
silently ran offline would be a null dressed as a finding.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from ..kernel import lifecycle
from ..sense import perceive
from .. import resources as res


# One public, stable documentation page. A real fact-acquisition target, chosen for
# being uncontroversial and long-lived rather than for its content.
FACT_URL = "https://pypi.org/pypi/pip/json"
FACT_SUBJECT = "pip_latest_version"


def run(config, **kw) -> int:
    bar = "=" * 78
    t0 = time.time()
    out_dir = config.root / "experiments" / "live_internet"
    out_dir.mkdir(parents=True, exist_ok=True)
    from ..effectors import cli_approver

    print(f"\n{bar}\nLIVE INTERNET PERCEPTION (E1-E5)\n{bar}")
    org = lifecycle.boot(config, quiet=True, approver=cli_approver)
    ledger, gate, store, view = org.ledger, org.gate, org.store, org.view

    # E1 -------------------------------------------------------------------
    print("\n[E1] internet perception")
    env = perceive.perceive_environment(gate, view)
    print(f"     {env['conclusion']}")

    # E2 -------------------------------------------------------------------
    print("\n[E2] resource inventory")
    inv = res.summary(view)
    print(f"     have={inv['have']}")
    print(f"     usable now={inv['usable_now']}")
    print(f"     requires human={inv['requires_human']}  absent={inv['absent']}")

    # E3 -------------------------------------------------------------------
    print("\n[E3] constraint discovery")
    constraints = [g for g in org.gaps if g.kind in
                   ("RESOURCE_THRESHOLD", "CAPABILITY_UNAFFORDABLE")]
    top = org.gaps[0] if org.gaps else None
    print(f"     top gap: {top.subject if top else None} "
          f"(priority {top.priority if top else '-'})")
    for g in constraints[:3]:
        print(f"       {g.subject}: {g.statement[:80]}")

    # E4 -------------------------------------------------------------------
    print("\n[E4] goal emergence")
    from ..cognition import objectives as objmod
    goal = None
    for g in org.gaps:
        goal = objmod.generate(g, view, org.drives, 0, config)
        if goal:
            break
    print(f"     derived goal: {goal.statement[:100] if goal else 'none actionable'}")

    # E5 -------------------------------------------------------------------
    print("\n[E5] internet knowledge acquisition")
    before = store.db.execute(
        "SELECT COUNT(*) n FROM memories WHERE subject LIKE 'world.fact.%'"
    ).fetchone()["n"]
    fact = perceive.acquire_fact(gate, store, FACT_URL, FACT_SUBJECT)
    after = store.db.execute(
        "SELECT COUNT(*) n FROM memories WHERE subject LIKE 'world.fact.%'"
    ).fetchone()["n"]
    if fact.get("acquired"):
        print(f"     acquired '{FACT_SUBJECT}' from {fact['url']} "
              f"({fact['chars']} chars, stored {fact['epistemic']} conf {fact['confidence']})")
    else:
        print(f"     not acquired: {fact.get('reason') or fact.get('verdict')}")

    # --- INTEGRITY GATE ---------------------------------------------------
    online = bool(env.get("reachable"))
    used_network = any(e["type"] in ("TOOL_CALL",) and
                       str(e["payload"].get("kind", "")).startswith("net.")
                       for e in ledger.read(boot_id=org.identity.boot_id))
    valid = online and used_network
    verdict = "VALID" if valid else "INVALID"

    print(f"\n{bar}\n  INTEGRITY: {verdict}"
          + ("" if valid else " - ran offline or made no network call; results void")
          + f"\n{bar}")

    summary = {
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "duration_s": round(time.time() - t0, 1),
        "integrity": verdict, "online": online, "used_network": used_network,
        "E1_environment": env,
        "E2_resources": inv,
        "E3_constraints": [g.to_dict() for g in constraints[:5]],
        "E4_goal": goal.to_dict() if goal else None,
        "E5_fact": fact, "facts_before": before, "facts_after": after,
        "results_table": {
            "E1_internet_perception": "PASS" if online else "FAIL",
            "E2_resource_inventory": "PASS" if inv["have"] else "FAIL",
            "E3_constraint_discovery": "PASS" if constraints else "none found",
            "E4_goal_emergence": "PASS" if goal else "no actionable goal",
            "E5_knowledge_acquisition":
                "PASS" if fact.get("acquired") and after > before else "FAIL",
        },
    }
    (out_dir / "results.json").write_text(json.dumps(summary, indent=2, default=str),
                                          encoding="utf-8")

    print("\n  Experiment | Result | Evidence")
    for k, v in summary["results_table"].items():
        print(f"    {k:<28} {v}")
    print(f"\n  data: {out_dir / 'results.json'}\n{bar}\n")
    org.close("live internet experiment")
    return 0 if valid else 2
