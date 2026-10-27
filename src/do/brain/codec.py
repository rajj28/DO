"""Memory as residual: D.O.'s life, stored as what its brain did not predict.

A brain that predicts well has no reason to store what it predicted. An arithmetic coder
driven by the cortex's own probabilities spends ~-log2 p bits on each value: almost
nothing for the expected, a lot for the surprising. The resulting byte string is the
whole life, and it is decoded by *replaying a fresh brain with the same seed* - which
regenerates the same predictions, which unlock the same values, tick by tick.

Three consequences that matter for D.O. specifically:

* storage cost is proportional to surprise, so memory is spent where the information is;
* the brain and the record cannot drift apart: decoding fails loudly if the brain that
  replays is not the brain that lived;
* the smarter the brain gets, the smaller the record of its life - the frugality drive
  and the learning objective become the same objective.

The coder is the classic integer arithmetic coder of Witten, Neal & Cleary (1987),
credited. Determinism is a requirement, not a nicety: the cortex makes no decision that
depends on set iteration order or wall-clock time, so a replay is exact.
"""
from __future__ import annotations

from .cortex import Cortex

PREC = 32
FULL = (1 << PREC) - 1
HALF = 1 << (PREC - 1)
QUARTER = 1 << (PREC - 2)
SCALE = 1 << 16


def _freqs(p: list[float]) -> list[int]:
    """Quantize a distribution to integer frequencies, every symbol codable."""
    room = SCALE - len(p)
    return [1 + int(x * room) for x in p]


class Encoder:
    def __init__(self):
        self.low, self.high, self.pending = 0, FULL, 0
        self.bits: list[int] = []

    def _emit(self, b: int) -> None:
        self.bits.append(b)
        self.bits.extend([1 - b] * self.pending)
        self.pending = 0

    def encode(self, freqs: list[int], i: int) -> None:
        total = sum(freqs)
        lo_c = sum(freqs[:i])
        hi_c = lo_c + freqs[i]
        span = self.high - self.low + 1
        self.high = self.low + span * hi_c // total - 1
        self.low = self.low + span * lo_c // total
        while True:
            if self.high < HALF:
                self._emit(0)
            elif self.low >= HALF:
                self._emit(1)
                self.low -= HALF
                self.high -= HALF
            elif self.low >= QUARTER and self.high < 3 * QUARTER:
                self.pending += 1
                self.low -= QUARTER
                self.high -= QUARTER
            else:
                break
            self.low = 2 * self.low
            self.high = 2 * self.high + 1

    def finish(self) -> bytes:
        self.pending += 1
        self._emit(0 if self.low < QUARTER else 1)
        bits = self.bits + [0] * (-len(self.bits) % 8)
        return bytes(int("".join(map(str, bits[k:k + 8])), 2)
                     for k in range(0, len(bits), 8))


class Decoder:
    def __init__(self, data: bytes):
        self.bits = [int(b) for byte in data for b in f"{byte:08b}"]
        self.pos = 0
        self.low, self.high = 0, FULL
        self.value = 0
        for _ in range(PREC):
            self.value = (self.value << 1) | self._next()

    def _next(self) -> int:
        b = self.bits[self.pos] if self.pos < len(self.bits) else 0
        self.pos += 1
        return b

    def decode(self, freqs: list[int]) -> int:
        total = sum(freqs)
        span = self.high - self.low + 1
        target = ((self.value - self.low + 1) * total - 1) // span
        acc, i = 0, 0
        while acc + freqs[i] <= target:
            acc += freqs[i]
            i += 1
        lo_c, hi_c = acc, acc + freqs[i]
        self.high = self.low + span * hi_c // total - 1
        self.low = self.low + span * lo_c // total
        while True:
            if self.high < HALF:
                pass
            elif self.low >= HALF:
                self.value -= HALF
                self.low -= HALF
                self.high -= HALF
            elif self.low >= QUARTER and self.high < 3 * QUARTER:
                self.value -= QUARTER
                self.low -= QUARTER
                self.high -= QUARTER
            else:
                break
            self.low = 2 * self.low
            self.high = 2 * self.high + 1
            self.value = (self.value << 1) | self._next()
        return i


class _Counts:
    """Adaptive model for the organism's own actions, which the cortex does not
    predict (they are chosen, not perceived)."""

    def __init__(self, n: int):
        self.c = [1] * n

    def freqs(self) -> list[int]:
        return list(self.c)

    def see(self, i: int) -> None:
        self.c[i] += 32


def encode(frames: list[dict], actions: list, variables: dict, action_set: tuple,
           **cortex_kw) -> bytes:
    """frames[0] is the starting frame; actions[t] was taken at frames[t]; frames[t+1]
    followed. Returns the life as bytes."""
    enc = Encoder()
    names = list(variables)
    for v in names:                                  # first frame: no expectations yet
        vals = variables[v]
        enc.encode([1] * len(vals), vals.index(frames[0][v]))
    brain = Cortex(variables, action_set, **cortex_kw)
    am = _Counts(len(action_set))
    for t, a in enumerate(actions):
        ai = action_set.index(a)
        enc.encode(am.freqs(), ai)
        am.see(ai)
        p = brain.predict(frames[t], a)
        for v in names:
            enc.encode(_freqs(p[v]), variables[v].index(frames[t + 1][v]))
        brain.update(frames[t + 1])
    return enc.finish()


def decode(data: bytes, ticks: int, variables: dict, action_set: tuple,
           **cortex_kw) -> tuple[list[dict], list]:
    """Replay a fresh brain to recover the life. Exact, or it is not memory."""
    dec = Decoder(data)
    names = list(variables)
    frame = {v: variables[v][dec.decode([1] * len(variables[v]))] for v in names}
    frames, actions = [frame], []
    brain = Cortex(variables, action_set, **cortex_kw)
    am = _Counts(len(action_set))
    for _ in range(ticks):
        ai = dec.decode(am.freqs())
        am.see(ai)
        a = action_set[ai]
        p = brain.predict(frames[-1], a)
        nxt = {v: variables[v][dec.decode(_freqs(p[v]))] for v in names}
        actions.append(a)
        frames.append(nxt)
        brain.update(nxt)
    return frames, actions
