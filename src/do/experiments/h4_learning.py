"""H4 - does D.O. learn from the consequences of its own actions?

The question, stated so it can come back NO:

    Does experience of its own outcomes make later decisions better, without anyone
    adding a rule between runs?

Design:

                        SAME CODE
                            |
                   identical environment
                            |
              +-------------+-------------+
              v                           v
          ABLATED                     LEARNING
      (fresh every run)        (own prior experience carried)
              |                           |
           run 1..N                    run 1..N
              |                           |
              +----------- compare -------+

Both arms rebuild the environment from the same seed every run, so the only difference
is whether the organism starts with what it learned last time. Nothing is edited
between runs: the code, the config, the action registry and the environment are fixed
before run 1 and never touched again.

**Where the improvement has to come from.** `rotate_ledger` estimates the space it
will free by assuming a 2.0x compression ratio, because nothing can know in advance
how well its own history compresses. The true figure on this host is near 5.7x, so on
first contact the action *under-promises by roughly a factor of three* and the planner
ranks it below smaller, correctly-estimated actions. The organism therefore spends
cycles on small wins before reaching the large one. If learning works, calibration
corrects the estimate, the ordering changes, and the goal is reached in fewer cycles
with fewer under-delivering actions.

That is the whole mechanism, and it is worth being clear that it is narrow: this
measures whether D.O. can correct a quantitative belief about its own capability and
act differently as a result. It is not open-ended learning.
"""
from __future__ import annotations

import json
import random
import shutil
import statistics
import time
from pathlib import Path

from ..kernel import lifecycle
from ..kernel.config import Config
from ..learning import outcomes as outcomes_mod
from ..capabilities import growth

SEED = 4242
LEDGER_BOOTS = 6        # history to grow before each trial; identical in both arms
MAX_CYCLES = 8

# How much the goal requires freeing. Fixed BEFORE any run, and chosen from measured
# action yields so the experiment can discriminate at all:
#
#   clear_experiment_matrix  promises 72,000  delivers 72,000   (honest)
#   rotate_ledger            promises ~56,000 delivers ~98,000  (under-promises 1.7x)
#
# With NEEDED just above the honest action's yield, an organism that believes the
# promises must spend two actions (matrix, then ledger) while one that has learned
# the correction reaches the target in one (ledger alone). A first version of this
# harness used a quota no sequence could reach, so "cycles to solve" measured
# "cycles to exhaust" and the arms were identical by construction. That is a blind
# instrument, and a null result from one means nothing.
NEEDED_BYTES = 95_000
MATRIX_BYTES = 72_000   # honest distractor: promises exactly what it delivers
BYTECODE_BYTES = 6_000


def _build_env(root: Path) -> None:
    """Rebuild the workspace identically. Deterministic sizes, fixed seed."""
    if root.exists():
        shutil.rmtree(root)
    (root / "var").mkdir(parents=True)
    rnd = random.Random(SEED)
    # Exact byte sizes, so both arms face a byte-identical world every run.
    d = root / "experiments" / "run0" / "matrix" / "cond"
    d.mkdir(parents=True)
    (d / "data.json").write_bytes(b"x" * MATRIX_BYTES)
    pyc = root / "src" / "__pycache__"
    pyc.mkdir(parents=True)
    (pyc / "m.pyc").write_bytes(bytes(rnd.getrandbits(8) for _ in range(BYTECODE_BYTES)))


def _cfg(root: Path, quota: int = 10 ** 9) -> Config:
    return Config.load(overrides={
        "organism": {"state_dir": str(root / "var"),
                     "sandbox_dir": str(root / "var" / "sandbox"),
                     "workspace_root": str(root)},
        "observability": {"ledger_file": str(root / "var" / "ledger.jsonl")},
        "resources": {"state_quota_bytes": quota, "ledger_keep_live": 25,
                      "snapshot_keep": 40},
    })


def _trial(root: Path, carry: dict | None) -> dict:
    """One run: rebuild the world, optionally transplant experience, then solve."""
    _build_env(root)
    cfg = _cfg(root)                      # huge quota: no goal forms while growing

    # BOTH arms boot here, so boot counts - and therefore ledger sizes - match.
    # An earlier version booted only the learning arm to transplant, which left it
    # with a larger ledger and more to reclaim. The extra bytes it freed looked like
    # skill and were volume. Environments must match or the comparison is worthless.
    o = lifecycle.boot(cfg, quiet=True)
    if carry:
        outcomes_mod.import_state(o.store, carry)
    o.close("transplant" if carry else "transplant-noop")

    for _ in range(LEDGER_BOOTS):
        o = lifecycle.boot(cfg, quiet=True)
        o.close("grow history")

    # Size the goal from the measured world so it is reachable, using the same
    # formula in both arms. NEEDED_BYTES was fixed before any run.
    probe = lifecycle.boot(cfg, quiet=True)
    measured = probe.view.val("resources.own.total_bytes") or 0
    probe.close("probe")
    quota = max(1, int((measured - NEEDED_BYTES) / 0.7))

    org = lifecycle.boot(_cfg(root, quota), quiet=True)
    start = org.view.val("resources.own.total_bytes") or 0
    reducers, failures, freed, diagnostics = [], 0, 0, 0
    met, cycles = False, 0

    for _ in range(MAX_CYCLES):
        r = lifecycle.cycle(org)
        cycles = r["cycle"]
        ru = r.get("reliability_update")
        if r.get("outcome"):
            # A reducer: it promised bytes, so it can under-deliver.
            reducers.append(r["outcome"]["action"])
            freed += int(r["outcome"]["actual"])
            if ru and not ru["success"]:
                failures += 1
        elif r.get("diagnosis"):
            # A diagnostic frees nothing by definition. Counting it as a failed
            # action, as an earlier version did, made every run show one failure
            # that was purely an artefact of the scoring rule.
            diagnostics += 1
        o = r.get("objective") or {}
        if o.get("status") in ("met", "abandoned") or r.get("note", "").startswith(
                "objective blocked"):
            met = o.get("status") == "met"
            break

    end = org.view.val("resources.own.total_bytes") or 0
    from ..learning import calibration_report
    cal = {c["action"]: c["k"] for c in calibration_report(org.store)}
    acquired = [c for c in growth.roster(org.store) if c["origin"] == "acquired"]
    exported = outcomes_mod.export_state(org.store)
    relations = outcomes_mod.learned_relations(org.store)
    org.close("h4 trial")

    return {
        "cycles": cycles, "actions": reducers, "n_actions": len(reducers),
        "failures": failures, "diagnostics": diagnostics,
        "bytes_freed": freed, "start_bytes": start, "end_bytes": end,
        "quota": quota, "needed": NEEDED_BYTES, "met": met, "calibration": cal,
        # Where the under-promising action ended up in the sequence. This is the
        # thing calibration is supposed to move.
        "rotate_position": (reducers.index("rotate_ledger") + 1
                            if "rotate_ledger" in reducers else None),
        "acquired": [a["name"] for a in acquired],
        "relations": relations, "_export": exported,
    }


def run(config, runs: int = 5) -> int:
    bar = "=" * 78
    t0 = time.time()
    root = config.root / "experiments" / "h4_learning"
    root.mkdir(parents=True, exist_ok=True)
    work = root / "trials"

    print(f"\n{bar}\nH4 - LEARNING FROM ONE'S OWN OUTCOMES\n{bar}")
    print(f"\n  question: do later decisions get better WITHOUT adding a rule?")
    print(f"  design  : identical environment every run (seed {SEED}); the only "
          f"difference\n            between arms is whether prior experience is carried.")
    print(f"  runs    : {runs} per arm\n")

    results: dict[str, list[dict]] = {}
    for arm in ("ablated", "learning"):
        carry: dict | None = None
        rows = []
        print(f"  --- arm: {arm} " + "-" * (58 - len(arm)))
        for i in range(1, runs + 1):
            r = _trial(work / arm, carry if arm == "learning" else None)
            rows.append(r)
            if arm == "learning":
                carry = r["_export"]          # only this arm keeps what it learned
            k = r["calibration"].get("rotate_ledger")
            print(f"    run {i}: cycles={r['cycles']}  actions={r['n_actions']}  "
                  f"failures={r['failures']}  freed={r['bytes_freed']:>7}B  "
                  f"met={str(r['met']):<5} "
                  f"k(rotate_ledger)={k if k is not None else '-'}")
        results[arm] = rows

    # --- analysis -----------------------------------------------------------
    print(f"\n{bar}\n  ANALYSIS\n{bar}")

    def series(arm, key):
        return [r[key] for r in results[arm]]

    print(f"\n  {'metric':<22}{'ablated (run 1 -> N)':<28}{'learning (run 1 -> N)':<28}")
    for key, label in (("n_actions", "actions to solve"),
                       ("cycles", "cycles to solve"),
                       ("failures", "under-delivering actions"),
                       ("rotate_position", "rank of rotate_ledger"),
                       ("met", "goal met")):
        a, l = series("ablated", key), series("learning", key)
        print(f"  {label:<22}{str(a):<28}{str(l):<28}")

    first_l, last_l = results["learning"][0], results["learning"][-1]
    a_mean = statistics.mean(series("ablated", "n_actions"))
    l_last = last_l["n_actions"]
    improved = (l_last < first_l["n_actions"]) or (
        last_l["failures"] < first_l["failures"])
    flat_control = (max(series("ablated", "n_actions"))
                    - min(series("ablated", "n_actions"))) <= 1

    # H4 is two claims, and this setup separates them cleanly. One verdict would hide
    # the more interesting half.
    #   H4a  does carried experience change the DECISION?
    #   H4b  does the changed decision produce a better OUTCOME?
    rank_a = [r for r in series("ablated", "rotate_position") if r]
    rank_l = [r for r in series("learning", "rotate_position") if r]
    decision_changed = bool(rank_a and rank_l and min(rank_l) < min(rank_a)
                            and len(set(rank_a)) == 1)
    outcome_improved = (l_last < first_l["n_actions"]
                        or last_l["failures"] < first_l["failures"]
                        or (last_l["met"] and not first_l["met"]))

    verdict_a = "SUPPORTED" if decision_changed else "FALSIFIED"
    verdict_b = ("SUPPORTED" if outcome_improved and l_last < a_mean
                 else "NOT SUPPORTED")
    verdict = ("SUPPORTED" if decision_changed and outcome_improved else
               "PARTIAL" if decision_changed else "FALSIFIED")

    print(f"\n  learning arm: run 1 = {first_l['n_actions']} actions / "
          f"{first_l['failures']} failures  ->  run {len(results['learning'])} = "
          f"{l_last} actions / {last_l['failures']} failures")
    print(f"  ablated arm mean actions: {a_mean:.1f}  (control flat: {flat_control})")
    print(f"\n  H4 verdict: {verdict}")

    print("\n  what experience taught (verifiable rows, not assertions):")
    for rel in (last_l["relations"] or [])[:6]:
        print(f"    {rel['reads_as']}  [n={rel['attempts']}, "
              f"mean yield {rel['mean_yield']}]")
    if not last_l["relations"]:
        print("    (none reached the minimum sample threshold)")

    print("\n  calibration carried into the final learning run:")
    for act, k in sorted((last_l["calibration"] or {}).items()):
        print(f"    {act:<26} k={k}")

    summary = {
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "duration_s": round(time.time() - t0, 1),
        "design": {"seed": SEED, "runs_per_arm": runs, "needed_bytes": NEEDED_BYTES,
                   "ledger_boots": LEDGER_BOOTS, "max_cycles": MAX_CYCLES},
        "verdict": verdict, "verdict_decision": verdict_a,
        "verdict_outcome": verdict_b,
        "rotate_rank": {"ablated": rank_a, "learning": rank_l},
        "arms": {arm: [{k: v for k, v in r.items() if k != "_export"} for r in rows]
                 for arm, rows in results.items()},
    }
    (root / "results.json").write_text(json.dumps(summary, indent=2, default=str),
                                       encoding="utf-8")
    print(f"\n  data: {root / 'results.json'}\n{bar}\n")
    return 0
