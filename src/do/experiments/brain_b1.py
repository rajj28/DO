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
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        (out / "results.json").write_text(json.dumps(
            {"protocol": __doc__.strip(), "T": T, "seeds": seeds,
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
