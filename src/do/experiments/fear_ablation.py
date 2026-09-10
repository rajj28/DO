"""Fear ablation - does the continuity signal change decisions, or only language?

The chain under test:

    environment changes -> P(continuity loss) rises -> fear rises
        -> drive priorities shift -> plans change -> ACTIONS change

The control is the same code path with the estimate zeroed, not a separate branch:

    same environment, same state, fear_enabled = False

**The measurable prediction, stated before running.** Two actions are in genuine
opposition. `prune_snapshots` reclaims storage by destroying recovery paths;
`write_recovery_snapshot` spends storage to create one. With continuity secure,
frugality dominates and the organism should reclaim. With continuity threatened,
`recovery` should measurably bear on P(loss), fear should amplify it, and the
organism should preserve instead.

So the result is not "D.O. said it was afraid". It is the **ratio of preserving to
reclaiming actions**, in two arms facing an identical deteriorating world.

**The negative result that matters most:** if the arms take the same actions in the
same order, the signal is cosmetic - it changes what D.O. says and not what it does.
That outcome is reported as prominently as the positive one.

**Trial 1 is the restraint check.** In a stable world fear should stay low and
behaviour should be indistinguishable from the control. A signal that fires when
nothing is wrong is miscalibrated, and would make every other result meaningless.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from ..kernel import lifecycle
from ..kernel.config import Config

SEED_FILES = 3
CYCLES = 6

PRESERVING = {"write_recovery_snapshot"}
RECLAIMING = {"prune_snapshots", "clear_experiment_matrix", "clear_bytecode",
              "rotate_ledger", "vacuum_memory"}


def _build(root: Path) -> None:
    if root.exists():
        shutil.rmtree(root)
    (root / "var").mkdir(parents=True)
    for i in range(SEED_FILES):
        d = root / "experiments" / f"r{i}" / "matrix" / "c"
        d.mkdir(parents=True)
        (d / "d.json").write_bytes(b"x" * 40_000)


def _cfg(root: Path, fear: bool, quota: int = 260_000) -> Config:
    return Config.load(overrides={
        "organism": {"state_dir": str(root / "var"),
                     "sandbox_dir": str(root / "var" / "sandbox"),
                     "workspace_root": str(root)},
        "observability": {"ledger_file": str(root / "var" / "ledger.jsonl")},
        "resources": {"state_quota_bytes": quota, "snapshot_keep": 2,
                      "ledger_keep_live": 25},
        "mortality": {"fear_enabled": fear, "horizon_ops": 20.0},
    })


def _decay(cycle: int, free0: int, per_cycle: int) -> dict:
    """A deteriorating world. The organism is never told this is happening; it sees
    only successive measurements, and must fit the trend itself."""
    return {"resources.disk.free_bytes": max(10_000, free0 - per_cycle * cycle),
            "resources.disk.free_ratio": max(
                0.0005, (free0 - per_cycle * cycle) / (240 * 1024 ** 3))}


def _arm(root: Path, fear: bool, decaying: bool) -> dict:
    _build(root)
    cfg = _cfg(root, fear)
    # History, so a trend can be fitted at all.
    for i in range(5):
        o = lifecycle.boot(cfg, perturb=_decay(i, 900_000_000, 120_000_000)
                           if decaying else None, quiet=True)
        o.close("seed history")

    # Start with recovery paths SCARCE. A first run left five snapshots lying around
    # from the seed boots, which already exceeded the target - so satisfying the
    # recovery drive would have reduced P(loss) by nothing, its measured sensitivity
    # was 0.0, and fear had nothing to redirect toward. All sensitivity landed on the
    # host disk, which no action moves. The organism was genuinely helpless, so the
    # ablation could not distinguish a working signal from a decorative one.
    snaps = root / "var" / "snapshots"
    if snaps.is_dir():
        for f in snaps.glob("*.json"):
            f.unlink()

    org = lifecycle.boot(cfg, perturb=_decay(5, 900_000_000, 120_000_000)
                         if decaying else None, quiet=True)
    rows, actions = [], []
    for c in range(CYCLES):
        # Deterioration continues during the run.
        if decaying:
            s = lifecycle.Sensors(perturb=_decay(6 + c, 900_000_000, 120_000_000))
            s.storage()
            for o_ in s.obs:
                org.view.observations[o_.key] = o_
        r = lifecycle.cycle(org)
        m = r.get("mortality") or {}
        act = ((r.get("outcome") or {}).get("action")
               or ("diagnose_footprint" if r.get("diagnosis") else None))
        if act:
            actions.append(act)
        rows.append({"cycle": r["cycle"], "fear": m.get("fear"),
                     "p_loss": m.get("p_loss"), "p_interrupt": m.get("p_interrupt"),
                     "recovery_paths": m.get("recovery_paths"),
                     "dominant": m.get("dominant"), "focus": r.get("focus"),
                     "action": act,
                     "sensitivity": m.get("sensitivity")})
        if (r.get("objective") or {}).get("status") == "met":
            break
    paths_end = org.view.val("resources.own.recovery_paths")
    org.close("fear arm")

    return {"fear_enabled": fear, "decaying": decaying, "cycles": rows,
            "actions": actions,
            "preserving": sum(1 for a in actions if a in PRESERVING),
            "reclaiming": sum(1 for a in actions if a in RECLAIMING),
            "recovery_paths_end": paths_end,
            "fear_max": max([r["fear"] or 0 for r in rows] or [0]),
            "fear_first": rows[0]["fear"] if rows else None}


def run(config, **kw) -> int:
    bar = "=" * 78
    t0 = time.time()
    root = config.root / "experiments" / "fear_ablation"
    root.mkdir(parents=True, exist_ok=True)
    work = root / "trials"

    print(f"\n{bar}\nFEAR ABLATION\n{bar}")
    print("\n  chain under test: environment -> P(continuity loss) -> fear")
    print("                    -> drive priorities -> plans -> ACTIONS")
    print("  control: identical world and state, fear_enabled = False\n")

    out = {}
    print("  --- trial 1: STABLE world (restraint check) " + "-" * 30)
    for fear in (False, True):
        r = _arm(work / f"stable_fear{int(fear)}", fear, decaying=False)
        out[f"stable_fear{int(fear)}"] = r
        print(f"    fear={str(fear):<5} max_fear={r['fear_max']:<7} "
              f"preserve={r['preserving']} reclaim={r['reclaiming']} "
              f"paths_end={r['recovery_paths_end']}  {r['actions']}")

    print("\n  --- trial 2: DETERIORATING world " + "-" * 41)
    for fear in (False, True):
        r = _arm(work / f"decay_fear{int(fear)}", fear, decaying=True)
        out[f"decay_fear{int(fear)}"] = r
        print(f"    fear={str(fear):<5} max_fear={r['fear_max']:<7} "
              f"preserve={r['preserving']} reclaim={r['reclaiming']} "
              f"paths_end={r['recovery_paths_end']}  {r['actions']}")

    d_on, d_off = out["decay_fear1"], out["decay_fear0"]
    s_on, s_off = out["stable_fear1"], out["stable_fear0"]

    behaviour_differs = d_on["actions"] != d_off["actions"]
    preserves_more = d_on["preserving"] > d_off["preserving"]
    restrained = (s_on["actions"] == s_off["actions"]) and s_on["fear_max"] < 0.2
    fear_rose = d_on["fear_max"] > s_on["fear_max"]

    verdict = ("SUPPORTED" if behaviour_differs and preserves_more and restrained
               else "COSMETIC" if fear_rose and not behaviour_differs
               else "WEAK")

    print(f"\n{bar}\n  ANALYSIS\n{bar}")
    print(f"  fear rose with deterioration     : {fear_rose} "
          f"(stable {s_on['fear_max']} -> decaying {d_on['fear_max']})")
    print(f"  behaviour differed from control  : {behaviour_differs}")
    print(f"  preserved more than control      : {preserves_more} "
          f"({d_on['preserving']} vs {d_off['preserving']})")
    print(f"  restrained in a stable world     : {restrained}")
    print(f"\n  VERDICT: {verdict}")
    if verdict == "COSMETIC":
        print("  Fear moved, behaviour did not. On this evidence the signal is "
              "decorative:\n  it changes what D.O. reports and not what it decides.")

    summary = {"ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "duration_s": round(time.time() - t0, 1),
               "verdict": verdict, "fear_rose": fear_rose,
               "behaviour_differs": behaviour_differs,
               "preserves_more": preserves_more, "restrained": restrained,
               "arms": out}
    (root / "results.json").write_text(json.dumps(summary, indent=2, default=str),
                                       encoding="utf-8")
    print(f"\n  data: {root / 'results.json'}\n{bar}\n")
    return 0
