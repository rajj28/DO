"""B1: does the brain predict its world better than traditional methods?

Protocol (prequential, so every prediction is made before the outcome is seen and no
held-out split is needed - each tick is held out at the moment it is scored):

    for t in 1..T:
        a      = world.policy()                (random exploration, same for all models)
        p      = model.predict(frame, a)
        truth  = world.oracle(a)               (true distribution, sees hidden state)
        frame' = world.step(a)
        bits  += -log2 p[frame']               (scored here, by the harness, not the model)
        model.update(frame')

Every model sees the identical stream (same world seed). Reported per model:
bits per tick, and EXCESS bits over the oracle - the part that learning could remove.
Falsified if the brain does not beat the best baseline on excess bits, or if its
ablations match it (then the mechanism ablated is not what is helping).
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

from ..brain.baselines import BASELINES
from ..brain.cortex import Cortex
from ..brain.worlds import WORLDS

LN2 = math.log(2.0)

BRAINS = {
    "brain": {},
    # Strong traditional ML baseline: online logistic regression over every lagged
    # symbol - the brain with growth, rent and recall all switched off.
    "brain_flat": {"flat": True},
    "brain_no_rent": {"rent": False},          # growth, but nothing ever pays rent
    "brain_no_recall": {"episodic": False},    # births from random symbols, not recall
    "brain_no_rupture": {"rupture": False},    # no per-unit change detection
    "brain_no_generalize": {"generalize": False},
    "brain_inner_senses": {"beliefs": True},   # expectations fed back as input
    # Hybrid: a dense permanent first-order layer (innate wiring) + grown conjunctions.
    "brain_innate": {"innate": True, "capacity": 400},
}


def make(model: str, world, seed: int):
    if model in BASELINES:
        return BASELINES[model](world.variables, world.actions)
    return Cortex(world.variables, world.actions, seed=seed, **BRAINS[model])


def run_one(world_name: str, model: str, seed: int, T: int) -> dict:
    world = WORLDS[world_name](seed)
    m = make(model, world, seed)
    frame = world.observe()
    bits = oracle_bits = 0.0
    curve, window, owindow = [], 0.0, 0.0
    t0 = time.perf_counter()
    for t in range(T):
        a = world.policy()
        p = m.predict(frame, a)
        truth = world.oracle(a)
        nxt = world.step(a)
        b = ob = 0.0
        for v, vals in world.variables.items():
            i = vals.index(nxt[v])
            b -= math.log(max(p[v][i], 1e-12)) / LN2
            ob -= math.log(max(truth[v][i], 1e-12)) / LN2
        bits += b
        oracle_bits += ob
        window += b
        owindow += ob
        if (t + 1) % (T // 10) == 0:
            curve.append(round((window - owindow) / (T // 10), 4))
            window = owindow = 0.0
        m.update(nxt)
        frame = nxt
    tail = curve[-3:]
    return {"world": world_name, "model": model, "seed": seed, "T": T,
            "bits_per_tick": round(bits / T, 4),
            "oracle_bits_per_tick": round(oracle_bits / T, 4),
            "excess_bits_per_tick": round((bits - oracle_bits) / T, 4),
            "excess_last30pct": round(sum(tail) / len(tail), 4),
            "excess_curve": curve,
            "seconds": round(time.perf_counter() - t0, 2),
            "stats": {k: v for k, v in m.stats().items() if k != "fertility"}}


def ideal_filter_bound(seed: int, T: int) -> dict:
    """The best any observer of hidden_mode could do: the TRUE rules, with the hidden
    mode inferred from all history by exact Bayesian filtering. The oracle sees the
    mode itself, which no learner can, so this - not the oracle - is the ceiling for
    learning. Returns excess bits/tick over the oracle, whole life and last 30%."""
    w = WORLDS["hidden_mode"](seed)
    belief, total, tail = 0.5, 0.0, 0.0
    for t in range(T):
        a = w.policy()
        truth = w.oracle(a)
        pm = belief * (1 - w.FLIP) + (1 - belief) * w.FLIP
        po = pm * w.FID + (1 - pm) * (1 - w.FID)
        nxt = w.step(a)
        e = 0.0
        for o in ("o1", "o2", "o3"):
            q = po if nxt[o] == 1 else 1 - po
            e += -math.log2(q) + math.log2(truth[o][nxt[o]])
        total += e
        if t >= 0.7 * T:
            tail += e
        l1, l0 = pm, 1 - pm
        for o in ("o1", "o2", "o3"):
            l1 *= w.FID if nxt[o] == 1 else 1 - w.FID
            l0 *= (1 - w.FID) if nxt[o] == 1 else w.FID
        belief = l1 / (l1 + l0)
    return {"excess": round(total / T, 4), "excess_tail": round(tail / (T - int(0.7 * T)), 4)}


def verdicts(summary: dict) -> dict:
    """Apply B1's own falsifier per world: the brain must beat the best non-brain model
    (every baseline plus brain_flat, i.e. logistic regression) on excess bits."""
    out = {}
    for w, ms in summary.items():
        if "brain" not in ms:
            continue
        rivals = {m: s for m, s in ms.items() if not m.startswith("brain") or m == "brain_flat"}
        if not rivals:
            continue
        b = ms["brain"]
        best_all = min(rivals, key=lambda m: rivals[m]["excess"])
        best_tail = min(rivals, key=lambda m: rivals[m]["excess_tail"])
        out[w] = {
            "whole_life": "SUPPORTED" if b["excess"] < rivals[best_all]["excess"]
            else f"FALSIFIED (best rival {best_all} {rivals[best_all]['excess']} vs brain {b['excess']})",
            "after_learning": "SUPPORTED" if b["excess_tail"] < rivals[best_tail]["excess_tail"]
            else f"FALSIFIED (best rival {best_tail} {rivals[best_tail]['excess_tail']} vs brain {b['excess_tail']})",
        }
    return out


def run(config=None, T: int = 3000, seeds=(0, 1, 2, 3, 4), models=None, worlds=None,
        out: Path | None = None) -> int:
    models = models or list(BASELINES) + list(BRAINS)
    worlds = worlds or list(WORLDS)
    rows = []
    for w in worlds:
        for m in models:
            for s in seeds:
                rows.append(run_one(w, m, s, T))
                r = rows[-1]
                print(f"{w:12s} {m:16s} seed={s} excess={r['excess_bits_per_tick']:.4f}"
                      f" tail={r['excess_last30pct']:.4f} ({r['seconds']}s)", flush=True)
    if out is None and config is not None:
        out = config.root / "experiments" / "brain_b1"
    write_report(rows, T, list(seeds), out)
    return 0


def write_report(rows: list[dict], T: int, seeds: list, out: Path | None) -> dict:
    summary = summarize(rows)
    print_table(summary)
    verdict = verdicts(summary)
    bound = {s: ideal_filter_bound(s, T) for s in seeds}
    print("\nB1 falsifier (brain must beat every non-brain model, incl. logistic):")
    for w, v in verdict.items():
        print(f"   {w:12s} whole life: {v['whole_life']}\n   {'':12s} after learning: "
              f"{v['after_learning']}")
    print("hidden_mode ideal-filter bound (excess, last 30%):",
          [b["excess_tail"] for b in bound.values()])
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        (out / "results.json").write_text(json.dumps(
            {"protocol": __doc__.strip(), "T": T, "seeds": seeds,
             "verdicts": verdict, "hidden_mode_ideal_filter": bound,
             "summary": summary, "runs": rows}, indent=1))
    return summary


def summarize(rows: list[dict]) -> dict:
    agg: dict = {}
    for r in rows:
        a = agg.setdefault(r["world"], {}).setdefault(r["model"], [])
        a.append(r)
    out: dict = {}
    for w, ms in agg.items():
        out[w] = {}
        for m, rs in ms.items():
            ex = [r["excess_bits_per_tick"] for r in rs]
            tl = [r["excess_last30pct"] for r in rs]
            mu = sum(ex) / len(ex)
            sd = (sum((x - mu) ** 2 for x in ex) / max(1, len(ex) - 1)) ** 0.5
            units = [r["stats"].get("units") for r in rs if r["stats"].get("units")]
            out[w][m] = {"excess": round(mu, 4), "excess_sd": round(sd, 4),
                         "excess_tail": round(sum(tl) / len(tl), 4),
                         "units": round(sum(units) / len(units)) if units else None,
                         "bits": round(sum(r["bits_per_tick"] for r in rs) / len(rs), 4),
                         "oracle": rs[0]["oracle_bits_per_tick"],
                         "n": len(rs)}
    return out


def print_table(summary: dict) -> None:
    for w, ms in summary.items():
        print(f"\n{w}  (oracle {next(iter(ms.values()))['oracle']:.3f} bits/tick)")
        for m, s in sorted(ms.items(), key=lambda kv: kv[1]["excess"]):
            print(f"   {m:16s} excess {s['excess']:.4f} +/- {s['excess_sd']:.4f}"
                  f"   last30% {s['excess_tail']:.4f}")
