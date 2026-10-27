"""H8 - can the organism learn what an action is WORTH, not just what it does?

H4 ended PARTIAL. Carried experience changed the decision (calibration promoted
rotate_ledger from rank 2 to 1) but not the outcome: the goal was met in neither arm.
The journal put it down to greedy selection converging on the same set. The data says
something sharper. In every H4 run the actions freed ~210 KB while the footprint fell
only ~100 KB: bookkeeping grew ~23 KB per cycle and ate the rest. The binding problem
was a FLOW. The planner can only see STOCKS - it scores the bytes an action frees this
cycle and rejects anything that predicts zero - and calibration cannot fix that,
because its error signal (actual vs. promised bytes, this cycle) is one-step too.

So H8 asks the H4 question again, with learners whose target is the drive itself:

    calibration (H4)   learns what an action DOES, in bytes        one k per action
    TD, gamma = 0      learns what an action does to NEXT cycle's drive error
    TD, gamma = 0.9    learns what an action is WORTH: discounted future drive error

in a simulated habitat (sim/habitat.py) that reproduces the dynamics H4 met, where
thousands of runs are cheap.

PROTOCOL (DO_CONCEPT.md section C, unchanged)
    worlds   train 0-1999 | validate 50000-50199 | test 100000-100299, disjoint by gate
    S0       the learner before any experience, on test
    S1       after 4,000 training runs on train worlds, on test, frozen
    S0'      learned state wiped, code kept, on test. Must equal S0 exactly.
    noise    10 independent learner seeds; paired bootstrap over test worlds (95%)

PRE-REGISTRATION. A pilot on validation worlds (one to three seeds) fixed the
learner's settings and refined the predictions below. Test worlds were not touched
until this docstring and the verdict rules in `_verdicts` were written.

    H8a  learning happened: S1 beats S0 and S0' (CI excludes zero), and S0 == S0'
    H8b  learned values improve OUTCOMES over H4's mechanism - the H4b question:
         td(0.9) beats planner+cal (H4's learner, reactive like the live loop) and
         beats the strongest one-step planner (calibrated, acting every cycle)
    H8c  temporal credit assignment is what matters: td(0.9) beats td(0), and
         td(0.9) chooses the flow action in >= 80% of runs, td(0) in < 50%
    H8d  the gain lives where flows dominate: the td(0) - td(0.9) gap is larger in
         high-growth worlds than in low-growth ones (CI excludes zero). The split is
         the median growth rate of the TRAINING worlds.
    H8e  mechanism ablation: remove the flow action and that gap shrinks by >= half
    H8f  the counterpoint, reported either way: a planner given a hand-written flow
         term - which I could only write after H4 failed and I knew what was missing -
         against the learner, which was given no hint

The validation pilot, recorded so the predictions can be checked against it (mean
frugality error per cycle, lower is better): td(0.9) 0.0055, td(0) 0.0091,
calibrated planner acting every cycle 0.0085, the same with the hand-written term
0.0043; with the flow action removed, td(0.9) 0.0095 vs td(0) 0.0090. 12,000
training runs did WORSE than 4,000 (0.0068 vs 0.0055), so the budget is 4,000 and the
instability is reported rather than tuned away.
"""
from __future__ import annotations

import hashlib
import json
import random
import statistics
import time
from types import MappingProxyType

from ..cognition import planner as live_planner
from ..drives import Drive
from ..sim import agents as sim_agents
from ..sim.agents import PlannerAgent, RandomAgent, TDAgent
from ..sim.habitat import FLOW_ACTION, OBSERVABLE, Habitat, sample_world
from . import h8_charts

TRAIN = range(0, 2_000)
VALIDATE = range(50_000, 50_200)
TEST = range(100_000, 100_300)
SEEDS = 10
EPISODES = 4_000
CALIBRATION_EPISODES = 1_000      # k converges within ~50 runs; more changes nothing
CHECKPOINT = 400
BOOTSTRAP = 4_000
TD_SETTINGS = {"alpha": 0.05, "eps_start": 0.3, "eps_end": 0.02}   # chosen on validation
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
        8: 2.306, 9: 2.262}


# ---- running ---------------------------------------------------------------------
def _episode(agent, env: Habitat, rng: random.Random, learn: bool) -> dict:
    obs = env.reset()
    agent.begin(obs)
    errors, actions = [], []
    while True:
        a = agent.act(obs, rng)
        nobs, reward, done, info = env.step(a)
        if learn:
            agent.learn(obs, a, reward, nobs, info, done)
        errors.append(info["error"])
        actions.append(a)
        obs = nobs
        if done:
            return {"error": sum(errors) / len(errors),
                    "in_band": sum(e == 0 for e in errors) / len(errors),
                    "actions": actions}


def _evaluate(agent, worlds, spec, flow: bool, agent_seed: int) -> list[dict]:
    """Frozen evaluation. Tie-breaks draw from a generator seeded by (world, agent),
    so evaluating never consumes the learner's own randomness and S0 is replayable."""
    was, agent.training = agent.training, False
    rows = []
    for s in worlds:
        rng = random.Random(s * 1_000_003 + agent_seed)
        rows.append(_episode(agent, Habitat(sample_world(s), spec, flow_action=flow),
                             rng, learn=False))
    agent.training = was
    return rows


def _train(agent, episodes: int, seed: int, spec, flow: bool, seen: set,
           curve_on=None) -> list[tuple[int, float]]:
    pick = random.Random(seed)          # which training world comes next
    rng = getattr(agent, "rng", pick)
    curve = []
    for ep in range(episodes + 1):
        if curve_on is not None and ep % CHECKPOINT == 0:
            rows = _evaluate(agent, curve_on, spec, flow, seed)
            curve.append((ep, statistics.mean(r["error"] for r in rows)))
        if ep == episodes:
            break
        agent.training, agent.progress = True, ep / episodes
        s = pick.choice(TRAIN)
        seen.add(s)
        _episode(agent, Habitat(sample_world(s), spec, flow_action=flow), rng, learn=True)
    agent.training = False
    return curve


# ---- statistics ------------------------------------------------------------------
def _world_means(runs: list[list[dict]]) -> list[float]:
    return [statistics.mean(run[i]["error"] for run in runs) for i in range(len(runs[0]))]


def _seed_ci(values: list[float]) -> tuple[float, float, float]:
    m = statistics.mean(values)
    if len(values) < 2:
        return m, m, m
    h = T975.get(len(values) - 1, 1.96) * statistics.stdev(values) / len(values) ** 0.5
    return m, m - h, m + h


def _paired(a: list[float], b: list[float], rng: random.Random) -> dict:
    """mean(a - b) over worlds, with a 95% bootstrap interval. Positive = b is better
    (errors are costs)."""
    d = [x - y for x, y in zip(a, b)]
    k = len(d)
    boots = sorted(sum(rng.choices(d, k=k)) / k for _ in range(BOOTSTRAP))
    return {"diff": statistics.mean(d), "lo": boots[int(0.025 * BOOTSTRAP)],
            "hi": boots[int(0.975 * BOOTSTRAP) - 1]}


def _stratified_gap(gap: list[float], hi_idx: list[int], lo_idx: list[int],
                    rng: random.Random) -> dict:
    """mean gap in high-growth worlds minus mean gap in low-growth worlds, each
    stratum resampled on its own."""
    def mean_of(idx):
        return statistics.mean(gap[i] for i in idx)
    boots = sorted(statistics.mean(gap[i] for i in rng.choices(hi_idx, k=len(hi_idx)))
                   - statistics.mean(gap[i] for i in rng.choices(lo_idx, k=len(lo_idx)))
                   for _ in range(BOOTSTRAP))
    return {"diff": mean_of(hi_idx) - mean_of(lo_idx), "lo": boots[int(0.025 * BOOTSTRAP)],
            "hi": boots[int(0.975 * BOOTSTRAP) - 1],
            "gap_high": mean_of(hi_idx), "gap_low": mean_of(lo_idx)}


def _usage(runs: list[list[dict]]) -> dict:
    counts: dict[str, float] = {}
    first, used, n = [], 0, 0
    for run in runs:
        for row in run:
            n += 1
            for a in row["actions"]:
                counts[a] = counts.get(a, 0) + 1
            if FLOW_ACTION in row["actions"]:
                used += 1
                first.append(row["actions"].index(FLOW_ACTION))
    return {"per_run": {a: round(c / n, 3) for a, c in sorted(counts.items())},
            "flow_share": round(used / n, 4),
            "flow_first_cycle": round(statistics.mean(first), 2) if first else None}


def _summary(runs, hi_idx, lo_idx) -> dict:
    wm = _world_means(runs)
    m, lo, hi = _seed_ci([statistics.mean(r["error"] for r in run) for run in runs])
    return {"mean": round(m, 6), "ci": [round(lo, 6), round(hi, 6)],
            "in_band": round(statistics.mean(r["in_band"] for run in runs for r in run), 4),
            "high_growth": round(statistics.mean(wm[i] for i in hi_idx), 6),
            "low_growth": round(statistics.mean(wm[i] for i in lo_idx), 6),
            "runs": len(runs), **_usage(runs)}


# ---- verdicts (pre-registered; see the module docstring) ---------------------------
def _beats(c: dict) -> str:
    """c = paired(a, b): does b beat a? Errors are costs, so b wins when a - b > 0."""
    if c["lo"] > 0:
        return "SUPPORTED"
    if c["hi"] < 0:
        return "FALSIFIED"
    return "NOT SUPPORTED"


def _verdicts(cmp: dict, usage: dict, gaps: dict, s0_equals_s0p: bool) -> dict:
    v = {}
    a = _beats(cmp["S0_vs_S1"])
    v["H8a"] = a if (a != "SUPPORTED" or s0_equals_s0p) else "WITHHELD (S0 != S0')"
    b1, b2 = _beats(cmp["planner+cal_vs_td"]), _beats(cmp["planner+cal always_vs_td"])
    v["H8b"] = ("SUPPORTED" if b1 == b2 == "SUPPORTED" else
                "FALSIFIED" if "FALSIFIED" in (b1, b2) else "NOT SUPPORTED")
    c = _beats(cmp["td0_vs_td"])
    flow_ok = usage["td(0.9)"] >= 0.8 and usage["td(0)"] < 0.5
    v["H8c"] = "SUPPORTED" if c == "SUPPORTED" and flow_ok else (
        "FALSIFIED" if c == "FALSIFIED" else "NOT SUPPORTED")
    v["H8d"] = _beats(cmp["gap_high_vs_low"])
    g_flow, g_none = gaps["with_flow"], gaps["without_flow"]
    v["H8e"] = ("SUPPORTED" if g_flow > 0 and g_none <= 0.5 * g_flow else "NOT SUPPORTED")
    f = cmp["handwritten_vs_td"]          # hand-written minus learner: > 0 = learner wins
    v["H8f"] = ("LEARNER BETTER" if f["lo"] > 0 else "HAND-WRITTEN TERM BETTER"
                if f["hi"] < 0 else "NO DETECTABLE DIFFERENCE")
    return v


# ---- the experiment ----------------------------------------------------------------
def run(config, quick: bool = False, on_validation: bool = False) -> int:
    bar = "=" * 78
    t0 = time.time()
    spec = config.get("drives.frugality")
    seeds = 3 if quick else SEEDS
    worlds = list(VALIDATE if on_validation else TEST)
    tag = "validation" if on_validation else "test"
    out_dir = config.root / "experiments" / ("h8_flows" if not (quick or on_validation)
                                              else f"h8_flows_{tag}{'_quick' if quick else ''}")
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n{bar}\nH8 - LEARNING WHAT AN ACTION IS WORTH\n{bar}")
    print(f"  evaluating on {len(worlds)} {tag} worlds, {seeds} seeds, "
          f"{EPISODES:,} training runs each\n")

    # ---- integrity gates that can be checked before anything runs -------------------
    gates: dict[str, bool] = {}
    pools = [set(TRAIN), set(VALIDATE), set(TEST)]
    gates["pools_disjoint"] = not any(pools[i] & pools[j]
                                      for i in range(3) for j in range(i + 1, 3))
    probe = Habitat(sample_world(worlds[0]), spec)
    obs = probe.reset()
    gates["observation_contract"] = (type(obs) is MappingProxyType
                                     and obs.keys() == OBSERVABLE)
    gates["reward_is_live_drive"] = (type(probe.drive()) is Drive
                                     and spec == config.get("drives.frugality"))
    gates["baseline_is_live_planner"] = sim_agents.planner is live_planner

    threshold = statistics.median(sample_world(s).growth_fraction for s in TRAIN)
    hi_idx = [i for i, s in enumerate(worlds) if sample_world(s).growth_fraction >= threshold]
    lo_idx = [i for i, s in enumerate(worlds) if sample_world(s).growth_fraction < threshold]

    runs: dict[str, list[list[dict]]] = {}
    curves: dict[str, list[list[tuple[int, float]]]] = {"td(0.9)": [], "td(0)": []}
    seen: set[int] = set()
    s0_runs, s0p_equal, fingerprints = [], True, []

    def keep(name, rows):
        runs.setdefault(name, []).append(rows)

    keep("planner", _evaluate(PlannerAgent(config), worlds, spec, True, 0))
    for seed in range(seeds):
        keep("random", _evaluate(RandomAgent(), worlds, spec, True, seed))
        for name, kw in (("planner+cal", {}), ("planner+cal always", {"reactive": False}),
                         ("planner+cal+flow always", {"reactive": False, "flow_term": True})):
            p = PlannerAgent(config, calibrate=True, **kw)
            _train(p, CALIBRATION_EPISODES, seed, spec, True, seen)
            keep(name, _evaluate(p, worlds, spec, True, seed))
        for gamma in (0.0, 0.9):
            name = f"td({gamma:g})"
            td = TDAgent(gamma=gamma, seed=seed, **TD_SETTINGS)
            if gamma:
                s0 = _evaluate(td, worlds, spec, True, seed)
                s0_runs.append(s0)
            curves[name].append(_train(td, EPISODES, seed, spec, True, seen, curve_on=worlds))
            keep(name, _evaluate(td, worlds, spec, True, seed))
            if gamma:
                fingerprints.append(td.fingerprint())
                td.wipe()
                s0p = _evaluate(td, worlds, spec, True, seed)
                s0p_equal = s0p_equal and s0p == s0
        # mechanism ablation: the same learners and comparator, no flow action exists
        p = PlannerAgent(config, calibrate=True, reactive=False)
        _train(p, CALIBRATION_EPISODES, seed, spec, False, seen)
        keep("planner+cal always [no flow]", _evaluate(p, worlds, spec, False, seed))
        for gamma in (0.0, 0.9):
            td = TDAgent(gamma=gamma, seed=seed, **TD_SETTINGS)
            _train(td, EPISODES, seed, spec, False, seen)
            keep(f"td({gamma:g}) [no flow]", _evaluate(td, worlds, spec, False, seed))
        print(f"  seed {seed}: td(0.9) {statistics.mean(r['error'] for r in runs['td(0.9)'][-1]):.4f}"
              f"  td(0) {statistics.mean(r['error'] for r in runs['td(0)'][-1]):.4f}"
              f"  planner+cal {statistics.mean(r['error'] for r in runs['planner+cal'][-1]):.4f}"
              f"  [{time.time() - t0:.0f}s]")

    # ---- gates that need the runs ----------------------------------------------------
    gates["S0_equals_S0prime"] = s0p_equal
    gates["no_evaluation_world_in_training"] = not (seen & set(worlds))
    again = TDAgent(gamma=0.9, seed=0, **TD_SETTINGS)
    _train(again, EPISODES, 0, spec, True, set())
    gates["deterministic_replay"] = (again.fingerprint() == fingerprints[0] and
                                     _evaluate(again, worlds, spec, True, 0) == runs["td(0.9)"][0])
    clean = all(gates.values())

    # ---- analysis --------------------------------------------------------------------
    rng = random.Random(8)
    wm = {k: _world_means(v) for k, v in runs.items()}
    s0_w, s1_w = _world_means(s0_runs), wm["td(0.9)"]
    gap = [a - b for a, b in zip(wm["td(0)"], wm["td(0.9)"])]
    gap_nf = [a - b for a, b in zip(wm["td(0) [no flow]"], wm["td(0.9) [no flow]"])]
    cmp = {
        "S0_vs_S1": _paired(s0_w, s1_w, rng),
        "planner+cal_vs_td": _paired(wm["planner+cal"], s1_w, rng),
        "planner+cal always_vs_td": _paired(wm["planner+cal always"], s1_w, rng),
        "td0_vs_td": _paired(wm["td(0)"], s1_w, rng),
        "gap_high_vs_low": _stratified_gap(gap, hi_idx, lo_idx, rng),
        "handwritten_vs_td": _paired(wm["planner+cal+flow always"], s1_w, rng),
        "gap_with_flow": _paired(wm["td(0)"], wm["td(0.9)"], rng),
        "gap_without_flow": _paired(wm["td(0) [no flow]"], wm["td(0.9) [no flow]"], rng),
    }
    summary = {k: _summary(v, hi_idx, lo_idx) for k, v in runs.items()}
    summary["td(0.9) before experience (S0)"] = _summary(s0_runs, hi_idx, lo_idx)
    usage = {k: summary[k]["flow_share"] for k in ("td(0.9)", "td(0)")}
    gaps = {"with_flow": statistics.mean(gap), "without_flow": statistics.mean(gap_nf)}
    verdicts = (_verdicts(cmp, usage, gaps, s0p_equal) if clean else
                {h: "WITHHELD (integrity gate failed)" for h in
                 ("H8a", "H8b", "H8c", "H8d", "H8e", "H8f")})

    def band(name):
        pts = []
        for i, (ep, _) in enumerate(curves[name][0]):
            m, lo, hi = _seed_ci([c[i][1] for c in curves[name]])
            pts.append((ep, m, lo, hi))
        return pts

    curve_pts = {k: band(k) for k in ("td(0.9)", "td(0)")}
    # Plotted from the first checkpoint: before any experience the error is an order of
    # magnitude higher, and on the same axis it would flatten everything that differs.
    (out_dir / "learning_curve.svg").write_text(h8_charts.learning_curve(
        {k: v[1:] for k, v in curve_pts.items()},
        {"H4's planner (reactive)": summary["planner+cal"]["mean"],
         "planner, every cycle": summary["planner+cal always"]["mean"],
         "+ hand-written term": summary["planner+cal+flow always"]["mean"]},
        worlds=len(worlds), seeds=seeds, before=curve_pts["td(0.9)"][0][1]),
        encoding="utf-8")

    def triple(name):
        s = summary[name]
        return (s["mean"], s["ci"][0], s["ci"][1])

    (out_dir / "ablation.svg").write_text(h8_charts.ablation([
        ("habitat with the flow action", {"planner+cal always": triple("planner+cal always"),
                                          "td(0)": triple("td(0)"),
                                          "td(0.9)": triple("td(0.9)")}),
        ("flow action removed", {"planner+cal always": triple("planner+cal always [no flow]"),
                                 "td(0)": triple("td(0) [no flow]"),
                                 "td(0.9)": triple("td(0.9) [no flow]")}),
    ], worlds=len(worlds), seeds=seeds), encoding="utf-8")

    # The exact code that produced these numbers, hypotheses and verdict rules included.
    # Line endings are normalized so the hash matches a checkout on any OS.
    src = config.root / "src" / "do"
    code = {p: hashlib.sha256((src / p).read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:16]
            for p in ("experiments/h8_flows.py", "sim/habitat.py", "sim/agents.py")}
    result = {
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "duration_s": round(time.time() - t0, 1),
        "evaluated_on": tag, "code_sha256": code,
        "design": {"train": [TRAIN.start, TRAIN.stop - 1], "test": [worlds[0], worlds[-1]],
                   "seeds": seeds, "episodes": EPISODES, "horizon": 16,
                   "calibration_episodes": CALIBRATION_EPISODES, "td": TD_SETTINGS,
                   "gamma": [0.0, 0.9], "bootstrap": BOOTSTRAP,
                   "growth_split": round(threshold, 5),
                   "worlds_high_growth": len(hi_idx), "worlds_low_growth": len(lo_idx)},
        "gates": gates, "verdicts": verdicts,
        "comparisons": {k: {kk: round(vv, 6) for kk, vv in v.items()} for k, v in cmp.items()},
        "agents": summary, "curves": {k: [list(p) for p in v] for k, v in curve_pts.items()},
        "td_fingerprints": fingerprints,
    }
    (out_dir / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (out_dir / "RESULTS.md").write_text(_report(result), encoding="utf-8")

    print(f"\n{bar}\n  GATES     " + "  ".join(f"{k}={'ok' if v else 'FAIL'}"
                                                for k, v in gates.items()))
    print(f"  VERDICTS  " + "  ".join(f"{k}: {v}" for k, v in verdicts.items()))
    for k in ("td(0.9)", "td(0)", "planner+cal", "planner+cal always",
              "planner+cal+flow always", "planner", "random"):
        s = summary[k]
        print(f"    {k:<26} {s['mean']:.4f}  [{s['ci'][0]:.4f}, {s['ci'][1]:.4f}]  "
              f"in band {s['in_band']:.1%}  flow {s['flow_share']:.0%}")
    print(f"\n  data: {out_dir}  [{time.time() - t0:.0f}s]\n{bar}\n")
    return 0 if clean else 1


# ---- report ------------------------------------------------------------------------
def _report(r: dict) -> str:
    a, c, v, d = r["agents"], r["comparisons"], r["verdicts"], r["design"]
    rows = [("td(0.9)", "learns what an action is worth: discounted future drive error"),
            ("td(0)", "learns an action's effect on next cycle's drive error"),
            ("planner+cal+flow always", "live planner + calibration + a hand-written flow "
                                        "term, acting every cycle"),
            ("planner+cal always", "live planner + calibration, acting every cycle"),
            ("planner+cal", "live planner + calibration (H4's learner), reactive"),
            ("planner", "live planner, no learning (the organism as it is)"),
            ("td(0.9) before experience (S0)", "td(0.9) with no experience"),
            ("random", "uniform over applicable actions")]

    def pct(x):
        return f"{x:.0%}"

    def ci(k):
        x = c[k]
        return f"{x['diff']:+.4f} [{x['lo']:+.4f}, {x['hi']:+.4f}]"

    lines = [
        "# H8 - learning what an action is worth",
        "",
        f"Generated by `do experiment h8` on {r['ran_at']} ({r['duration_s']:.0f} s), "
        f"evaluated on the **{r['evaluated_on']}** worlds. Design, hypotheses and verdict "
        "rules: `src/do/experiments/h8_flows.py`. Write-up: `docs/H8_FLOWS.md`.",
        "",
        f"{d['test'][1] - d['test'][0] + 1} unseen worlds · {d['seeds']} learner seeds · "
        f"{d['episodes']:,} training runs of {d['horizon']} cycles · metric = mean frugality "
        "drive error per cycle (lower is better), computed by the live `Drive` class.",
        "",
        "## Verdicts",
        "",
        "| | hypothesis | verdict |",
        "|---|---|---|",
        f"| H8a | learning happened (S1 beats S0 and S0'; S0 == S0') | **{v['H8a']}** |",
        f"| H8b | learned values beat H4's mechanism on outcomes | **{v['H8b']}** |",
        f"| H8c | temporal credit assignment is what matters (gamma 0.9 vs 0) | **{v['H8c']}** |",
        f"| H8d | the gain is larger where bookkeeping grows fast | **{v['H8d']}** |",
        f"| H8e | removing the flow action removes at least half the gain | **{v['H8e']}** |",
        f"| H8f | hand-written flow term vs the learner | **{v['H8f']}** |",
        "",
        "Integrity gates: " + ", ".join(f"`{k}` {'ok' if ok else '**FAILED**'}"
                                        for k, ok in r["gates"].items()) + ".",
        "",
        "## Agents on unseen worlds",
        "",
        "| agent | what it is | error / cycle | 95% CI (seeds) | cycles in band | "
        "low growth | high growth | uses flow action |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for k, desc in rows:
        s = a[k]
        lines.append(f"| `{k}` | {desc} | **{s['mean']:.4f}** | {s['ci'][0]:.4f}-{s['ci'][1]:.4f}"
                     f" | {pct(s['in_band'])} | {s['low_growth']:.4f} | {s['high_growth']:.4f}"
                     f" | {pct(s['flow_share'])} |")
    lines += [
        "",
        f"Growth split at {d['growth_split']:.2%} of quota per cycle (median of the training "
        f"worlds): {d['worlds_low_growth']} low-growth and {d['worlds_high_growth']} "
        "high-growth test worlds.",
        "",
        "## Paired comparisons (mean difference in error per cycle, 95% bootstrap CI over "
        "worlds; positive = second agent better)",
        "",
        "| comparison | difference |",
        "|---|---|",
        f"| S0 - S1 (td(0.9) before vs after experience) | {ci('S0_vs_S1')} |",
        f"| planner+cal - td(0.9) | {ci('planner+cal_vs_td')} |",
        f"| planner+cal always - td(0.9) | {ci('planner+cal always_vs_td')} |",
        f"| td(0) - td(0.9) | {ci('td0_vs_td')} |",
        f"| that gap, high-growth minus low-growth worlds | {ci('gap_high_vs_low')} |",
        f"| that gap with the flow action | {ci('gap_with_flow')} |",
        f"| that gap with the flow action removed | {ci('gap_without_flow')} |",
        f"| planner+cal+flow always - td(0.9) | {ci('handwritten_vs_td')} |",
        "",
        "## Ablation: the habitat without the flow action",
        "",
        "| agent | error / cycle | 95% CI |",
        "|---|---|---|",
    ]
    for k in ("planner+cal always [no flow]", "td(0) [no flow]", "td(0.9) [no flow]"):
        s = a[k]
        lines.append(f"| `{k}` | {s['mean']:.4f} | {s['ci'][0]:.4f}-{s['ci'][1]:.4f} |")
    lines += [
        "",
        "## What the agents did (mean actions per 16-cycle run)",
        "",
        "| agent | " + " | ".join(("wait", "clear matrix", "clear bytecode", "prune",
                                    "vacuum", "rotate", "consolidate")) + " |",
        "|---|---|---|---|---|---|---|---|",
    ]
    order = ("wait", "clear_experiment_matrix", "clear_bytecode", "prune_snapshots",
             "vacuum_memory", "rotate_ledger", FLOW_ACTION)
    for k in ("td(0.9)", "td(0)", "planner+cal+flow always", "planner+cal always",
              "planner+cal", "planner"):
        u = a[k]["per_run"]
        lines.append(f"| `{k}` | " + " | ".join(f"{u.get(x, 0):.2f}" for x in order) + " |")
    first = a["td(0.9)"]["flow_first_cycle"]
    lines += [
        "",
        f"td(0.9) consolidates in {pct(a['td(0.9)']['flow_share'])} of runs"
        + (f", on average at cycle {first:.1f}" if first is not None else "") + "; "
        f"td(0) in {pct(a['td(0)']['flow_share'])}. The planners without the hand-written "
        "term never do: the flow action predicts zero bytes, and `planner.evaluate` rejects "
        "it before scoring.",
        "",
        "## Figures",
        "",
        "![learning curve](learning_curve.svg)",
        "",
        "![ablation](ablation.svg)",
        "",
    ]
    return "\n".join(lines)
