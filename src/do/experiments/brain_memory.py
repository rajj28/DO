"""B2: is a brain-coded life smaller than the best general-purpose compressors?

For each world: record T ticks of life (frames and the actions taken), then store it

    raw      as JSON lines - how a naive ledger would hold it
    gzip -9, bz2 -9, xz -9e   general-purpose compressors over those JSON lines
    packed   one byte per value (schema known, like the brain), then bz2 / xz - the
             fair comparison: the brain is not credited for knowing the alphabet
    brain    arithmetic-coded residuals of the cortex (`brain/codec.py`)

and DECODE the brain version by replaying a fresh brain, checking the replay is
bit-exact. A compression number from a codec that was never decoded is a claim, not a
result.

Falsified if the brain's record is not smaller than the best of gzip/bz2/xz, or if the
replay is not exact.
"""
from __future__ import annotations

import bz2
import gzip
import json
import lzma
import math
import time
from pathlib import Path

from ..brain import codec
from ..brain.worlds import WORLDS


def record(world_name: str, seed: int, T: int) -> tuple[list[dict], list, object, float]:
    """Returns the life plus its entropy floor in bits: the oracle's code length for
    every frame (it sees the hidden state) plus the entropy of the action policy. No
    codec can beat this on average."""
    w = WORLDS[world_name](seed)
    frames, actions = [w.observe()], []
    h_act = -sum(p * math.log2(p) for p in w.action_probs if p > 0)
    floor = 0.0
    for _ in range(T):
        a = w.policy()
        truth = w.oracle(a)
        actions.append(a)
        frames.append(w.step(a))
        floor += h_act + sum(-math.log2(truth[v][vals.index(frames[-1][v])])
                             for v, vals in w.variables.items())
    return frames, actions, w, floor


def measure(world_name: str, seed: int = 0, T: int = 3000) -> dict:
    frames, actions, w, floor_bits = record(world_name, seed, T)
    lines = [json.dumps({"t": t, "act": actions[t - 1] if t else None, **f},
                        separators=(",", ":")) for t, f in enumerate(frames)]
    raw = ("\n".join(lines) + "\n").encode()
    names = list(w.variables)
    packed = bytes([w.variables[v].index(frames[0][v]) for v in names] + [
        b for t, a in enumerate(actions)
        for b in [w.actions.index(a)] + [w.variables[v].index(frames[t + 1][v])
                                         for v in names]])
    t0 = time.perf_counter()
    blob = codec.encode(frames, actions, w.variables, w.actions, seed=seed)
    t_enc = time.perf_counter() - t0
    t0 = time.perf_counter()
    f2, a2 = codec.decode(blob, T, w.variables, w.actions, seed=seed)
    t_dec = time.perf_counter() - t0
    sizes = {"raw_jsonl": len(raw),
             "gzip_9": len(gzip.compress(raw, 9)),
             "bz2_9": len(bz2.compress(raw, 9)),
             "xz_9e": len(lzma.compress(raw, preset=9 | lzma.PRESET_EXTREME)),
             "packed_bz2_9": len(bz2.compress(packed, 9)),
             "packed_xz_9e": len(lzma.compress(packed, preset=9 | lzma.PRESET_EXTREME)),
             "brain": len(blob)}
    best_general = min(v for k, v in sizes.items() if k not in ("raw_jsonl", "brain"))
    floor = floor_bits / 8
    return {"world": world_name, "seed": seed, "ticks": T, "bytes": sizes,
            "floor_bytes": round(floor),
            "brain_above_floor_pct": round(100 * (sizes["brain"] / floor - 1), 1),
            "best_general_above_floor_pct": round(100 * (best_general / floor - 1), 1),
            "exact_replay": f2 == frames and a2 == actions,
            "ratio_vs_raw": round(sizes["raw_jsonl"] / sizes["brain"], 1),
            "ratio_vs_best_general": round(best_general / sizes["brain"], 2),
            "encode_s": round(t_enc, 2), "decode_s": round(t_dec, 2)}


def run(config=None, T: int = 3000, seed: int = 0, out: Path | None = None) -> int:
    rows = []
    print(f"{'world':12s} {'raw':>8s} {'gzip':>7s} {'xz':>7s} {'pk-bz2':>7s} {'pk-xz':>7s}"
          f" {'brain':>7s}  vs-best  exact")
    for name in WORLDS:
        r = measure(name, seed, T)
        rows.append(r)
        b = r["bytes"]
        print(f"{name:12s} {b['raw_jsonl']:8d} {b['gzip_9']:7d} {b['xz_9e']:7d} "
              f"{b['packed_bz2_9']:7d} {b['packed_xz_9e']:7d} {b['brain']:7d}  "
              f"{r['ratio_vs_best_general']:5.2f}x  {r['exact_replay']}  floor "
              f"{r['floor_bytes']} (+{r['brain_above_floor_pct']}% vs "
              f"+{r['best_general_above_floor_pct']}%)", flush=True)
    if out is None and config is not None:
        out = config.root / "experiments" / "brain_memory"
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        (out / "results.json").write_text(json.dumps(
            {"protocol": __doc__.strip(), "T": T, "seed": seed, "rows": rows}, indent=1))
    return 0 if all(r["exact_replay"] for r in rows) else 1
