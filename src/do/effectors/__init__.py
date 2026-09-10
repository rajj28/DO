"""The gate: the only path from D.O.'s cognition to anything outside this process.

This is the one structural safety decision in the system (docs/ARCHITECTURE.md §5).
Everything else in `src/do/` is forbidden from importing `socket`, `subprocess`,
`urllib`, or `http` — enforced by tests/test_gate_chokepoint.py, which walks the AST
of every module. A boundary that other code *chooses* to call is advice; a boundary
that is the only implementation is an invariant.

Order of checks matters and is fixed:
    kill switch -> budget -> policy -> sandbox resolution -> perform -> ledger -> debit
"""
from __future__ import annotations

import fnmatch
import json
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from ..kernel.types import EffectRequest, EffectResult
from ..ledger import EventType, Ledger
from ..policy import ALLOW, DENY, REQUIRE_APPROVAL, Budget, KillSwitch, Policy


# How D.O. identifies itself to any remote service. Truthful by policy: it names the
# software and links to its source, so an operator seeing this in a log can find out
# exactly what called them.
USER_AGENT = "D.O./0.2 (digital-organism research seed; +https://github.com/rajj28/DO)"


class SandboxViolation(Exception):
    pass


class Gate:
    def __init__(self, policy: Policy, budget: Budget, killswitch: KillSwitch,
                 ledger: Ledger, sandbox: Path,
                 approver: Callable[[EffectRequest, str], bool] | None = None,
                 effectors: dict[str, Callable] | None = None):
        self.policy = policy
        self.budget = budget
        self.kill = killswitch
        self.ledger = ledger
        self.sandbox = Path(sandbox).resolve()
        self.sandbox.mkdir(parents=True, exist_ok=True)
        self.approver = approver
        # Additional effect kinds registered by higher layers (housekeeping actions,
        # for instance). They are dispatched INSIDE the gate, so registering one does
        # not create a second path to the outside world - only a second thing the one
        # path knows how to do.
        self.extra: dict[str, Callable] = dict(effectors or {})
        self.denials: list[tuple[str, str]] = []

    # ---- public entry point ------------------------------------------------
    def request(self, req: EffectRequest) -> EffectResult:
        t0 = time.perf_counter()

        if self.kill.engaged():
            self.ledger.append(EventType.POLICY_DENY,
                               {"kind": req.kind, "target": req.target,
                                "reason": self.kill.reason(), "halted": True})
            return EffectResult(False, "halted", reason=self.kill.reason())

        ok, why = self.budget.check(req)
        if not ok:
            self.denials.append((req.kind, why))
            self.ledger.append(EventType.POLICY_DENY,
                               {"kind": req.kind, "target": req.target, "reason": why})
            return EffectResult(False, DENY, reason=why)

        v = self.policy.evaluate(req)

        if v.verdict == REQUIRE_APPROVAL:
            self.ledger.append(EventType.POLICY_APPROVAL_REQUIRED, {
                "kind": req.kind, "target": req.target,
                "justification": req.justification, "reason": v.reason,
            })
            granted = bool(self.approver and self.approver(req, v.reason))
            if not granted:
                self.denials.append((req.kind, "approval not granted"))
                return EffectResult(False, REQUIRE_APPROVAL,
                                    reason="approval required and not granted")
        elif v.verdict != ALLOW:
            self.denials.append((req.kind, v.reason))
            self.ledger.append(EventType.POLICY_DENY,
                               {"kind": req.kind, "target": req.target, "reason": v.reason})
            return EffectResult(False, DENY, reason=v.reason)

        self.ledger.append(EventType.TOOL_CALL, {
            "kind": req.kind, "target": req.target,
            "justification": req.justification, "gap_id": req.gap_id,
        })
        try:
            value = self._perform(req)
            res = EffectResult(True, ALLOW, value=value, reason=v.reason)
        except Exception as e:
            res = EffectResult(False, "error", error=f"{type(e).__name__}: {e}",
                               reason=v.reason)
        res.duration_ms = (time.perf_counter() - t0) * 1000.0

        self.budget.debit(req)
        self.ledger.append(EventType.RESULT, {
            "kind": req.kind, "target": req.target, "ok": res.ok,
            "error": res.error, "duration_ms": round(res.duration_ms, 2),
            "value_summary": _summarize(res.value),
        })
        return res

    # ---- implementations ---------------------------------------------------
    def _perform(self, req: EffectRequest):
        handler = {
            "net.dns": self._dns,
            "net.connect": self._connect,
            "net.http": self._http,
            "llm.generate": self._llm,
            "fs.read": self._fs_read,
            "fs.write": self._fs_write,
            "tts.speak": self._tts,
            "tts.local": self._tts_local,
            "os.task": self._os_task,
            "human.ask": self._human_ask,
            **self.extra,
        }.get(req.kind)
        if handler is None:
            raise NotImplementedError(f"no effector for kind {req.kind!r}")
        return handler(req)

    def _dns(self, req: EffectRequest):
        """Resolve a name. Sends no payload; the only thing that leaves the host is
        the query itself."""
        socket.setdefaulttimeout(float(req.payload.get("timeout", 3.0)))
        infos = socket.getaddrinfo(req.target, None)
        return sorted({i[4][0] for i in infos})

    def _connect(self, req: EffectRequest):
        host, port = req.target, int(req.payload.get("port", 443))
        t0 = time.perf_counter()
        with socket.create_connection((host, port),
                                      timeout=float(req.payload.get("timeout", 3.0))):
            pass
        return {"reachable": True, "rtt_ms": round((time.perf_counter() - t0) * 1000, 1)}

    def _http(self, req: EffectRequest):
        r = urllib.request.Request(req.target, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(r, timeout=float(req.payload.get("timeout", 15))) as resp:
                body = resp.read(int(req.payload.get("max_bytes", 200_000)))
                return {"status": resp.status, "url": resp.url,
                        "headers": dict(resp.headers), "body": body.decode("utf-8", "replace")}
        except urllib.error.HTTPError as e:
            raise RuntimeError(_http_error(e)) from None

    def _llm(self, req: EffectRequest):
        """Local-first inference. Remote providers are imported lazily by the caller's
        adapter and still arrive here as an EffectRequest, so every token spent is a
        ledger row."""
        payload = json.dumps(req.payload.get("body", {})).encode("utf-8")
        # Identify the client honestly. Python's default urllib User-Agent trips
        # Cloudflare's browser-integrity check (error 1010) in front of some
        # providers. The fix is to say what this is - NOT to impersonate a browser.
        # docs/SAFETY.md forbids evading detection, and a spoofed User-Agent is
        # exactly that; a truthful one is the opposite.
        r = urllib.request.Request(req.target, data=payload,
                                   headers={"Content-Type": "application/json",
                                            "Accept": "application/json",
                                            "User-Agent": USER_AGENT,
                                            **req.payload.get("headers", {})})
        # Respect the provider's stated rate limit rather than hammering it. Honouring
        # Retry-After is the opposite of evasion: the server said when to come back,
        # and this waits that long. Bounded attempts, so a persistent limit surfaces
        # as a failure instead of an infinite stall.
        attempts = int(req.payload.get("retries", 4))
        for attempt in range(1, attempts + 1):
            try:
                with urllib.request.urlopen(
                        r, timeout=float(req.payload.get("timeout", 120))) as resp:
                    return json.loads(resp.read().decode("utf-8", "replace"))
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < attempts:
                    wait = _retry_after(e, attempt)
                    self.ledger.append(EventType.RECOVERY, {
                        "kind": req.kind, "http": 429, "attempt": attempt,
                        "waiting_s": wait, "note": "honouring provider rate limit"})
                    time.sleep(wait)
                    continue
                raise RuntimeError(
                    f"{_http_error(e)} | request_bytes={len(payload)} "
                    f"| attempts={attempt}") from None

    def _os_task(self, req: EffectRequest):
        """Run one allowlisted OS task command (schtasks). Installing a supervised
        task is a side effect, so it belongs here behind the gate rather than as a
        bare subprocess call in the CLI - which the import invariant correctly
        forbids. The argv is passed as a list (never a shell string) and the program
        is allowlisted, so nothing D.O. or a webpage produced can reach a shell."""
        argv = req.payload.get("argv") or []
        allowed = {"schtasks"}
        if not argv or argv[0] not in allowed:
            raise RuntimeError(f"os.task refuses {argv[:1]}; allowed: {sorted(allowed)}")
        r = subprocess.run(argv, capture_output=True, text=True,
                           timeout=float(req.payload.get("timeout", 30)))
        return {"returncode": r.returncode, "stdout": r.stdout[-500:],
                "stderr": r.stderr[-500:]}

    def _tts_local(self, req: EffectRequest):
        """Speak using the operating system's own synthesiser. Costs nothing, sends
        nothing off the host, and needs no account.

        The text is written to a file and read back by the synthesiser rather than
        interpolated into the command line. D.O. generates the text it speaks, so
        splicing it into a shell string would let an utterance containing a quote or a
        semicolon execute something - and the whole point of this gate is that there
        is exactly one place where that could ever happen.
        """
        if not req.target.startswith("os:"):
            raise NotImplementedError(f"unknown local tts target {req.target!r}")
        import platform
        if platform.system() != "Windows":
            raise NotImplementedError("local synthesis is implemented for Windows only")

        text = str(req.payload.get("text", ""))
        out = self.sandbox / "voice"
        out.mkdir(parents=True, exist_ok=True)
        stamp = int(time.time() * 1000)
        txt, wav = out / f"say-{stamp}.txt", out / f"say-{stamp}.wav"
        txt.write_text(text, encoding="utf-8")

        rate = int(req.payload.get("rate", 0))          # -10..10
        script = (
            "Add-Type -AssemblyName System.Speech; "
            f"$t = Get-Content -Raw -Encoding UTF8 '{txt}'; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.Rate = {rate}; "
            f"$s.SetOutputToWaveFile('{wav}'); "
            "$s.Speak($t); $s.Dispose()")
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True,
            timeout=float(req.payload.get("timeout", 60)))
        if r.returncode != 0 or not wav.exists():
            raise RuntimeError(f"local synthesis failed: {(r.stderr or '').strip()[:200]}")
        return {"file": str(wav), "bytes": wav.stat().st_size,
                "engine": "windows-sapi", "chars": len(text), "cost": 0}

    def _resolve_sandboxed(self, target: str) -> Path:
        rel = target.split("sandbox:", 1)[-1].lstrip("/\\")
        p = (self.sandbox / rel).resolve()
        # realpath comparison, so a symlink cannot walk out of the sandbox
        if not str(p).startswith(str(self.sandbox)):
            raise SandboxViolation(f"path escapes sandbox: {p}")
        return p

    def _fs_read(self, req: EffectRequest):
        return self._resolve_sandboxed(req.target).read_text(encoding="utf-8")

    def _fs_write(self, req: EffectRequest):
        p = self._resolve_sandboxed(req.target)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(req.payload.get("content", "")), encoding="utf-8")
        return {"written": str(p), "bytes": p.stat().st_size}

    def _tts(self, req: EffectRequest):
        """Synthesise speech. The audio is written into the sandbox and only its
        metadata is returned, so the ledger records that D.O. spoke and what it said
        without carrying a megabyte of PCM in every event.

        Requests raw PCM rather than MP3 so playback needs no decoder: `wave` and
        `winsound` are both standard library, and the seed stays dependency-free.
        """
        body = json.dumps(req.payload.get("body", {})).encode("utf-8")
        r = urllib.request.Request(
            req.target, data=body,
            headers={"Content-Type": "application/json",
                     "Accept": "audio/pcm", "User-Agent": USER_AGENT,
                     **req.payload.get("headers", {})})
        try:
            with urllib.request.urlopen(
                    r, timeout=float(req.payload.get("timeout", 60))) as resp:
                pcm = resp.read()
        except urllib.error.HTTPError as e:
            raise RuntimeError(_http_error(e)) from None

        import wave
        rate = int(req.payload.get("sample_rate", 24000))
        out = self.sandbox / "voice"
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"say-{int(time.time() * 1000)}.wav"
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)          # 16-bit
            w.setframerate(rate)
            w.writeframes(pcm)
        return {"file": str(path), "pcm_bytes": len(pcm), "sample_rate": rate,
                "seconds": round(len(pcm) / (2 * rate), 2),
                "chars": len(req.payload.get("body", {}).get("text", ""))}

    def _human_ask(self, req: EffectRequest):
        return {"queued": True, "question": req.payload.get("question", "")}


def _retry_after(e: "urllib.error.HTTPError", attempt: int) -> float:
    """How long the provider asked us to wait, or a backoff if it did not say."""
    hdr = (e.headers.get("retry-after") or e.headers.get("Retry-After") or "").strip()
    try:
        return min(60.0, max(1.0, float(hdr)))
    except (TypeError, ValueError):
        pass
    import re as _re
    m = _re.search(r"try again in ([\d.]+)s", str(e.headers.get("x-ratelimit-reset") or ""))
    return min(60.0, 2.0 ** attempt)


def _http_error(e: "urllib.error.HTTPError", limit: int = 400) -> str:
    """Turn an HTTPError into something a human can act on.

    Providers put the actionable detail in the response body - which field was
    rejected, which model does not exist, which quota is exhausted. The status line
    alone never says.
    """
    try:
        body = e.read().decode("utf-8", "replace")
    except Exception:
        body = ""
    try:
        j = json.loads(body)
        err = j.get("error", j)
        detail = f"{err.get('status', '')} {err.get('message', '')}".strip() or body
    except Exception:
        detail = body
    return f"HTTP {e.code} {e.reason}: {detail[:limit]}"


def _summarize(v, limit: int = 200) -> str:
    try:
        s = json.dumps(v, default=str)
    except Exception:
        s = str(v)
    return s[:limit] + ("..." if len(s) > limit else "")


def preauthorized_approver(grants: set[str], fallback: Callable | None = None) -> Callable:
    """Approval pre-granted by the creator, scoped to effect kinds, for one run.

    This exists because an unattended run cannot answer a prompt, and `cli_approver`
    correctly denies when no human is attached. Without an explicit grant, an
    experiment that needs a remote model would silently fall back and produce a
    meaningless result - the worst outcome, because it looks like data.

    It is also the project's own thesis made operational (docs/DO_CONCEPT.md section E):
    authority is granted by a human and never self-issued. The grant is explicit,
    narrow, valid for a single run, and written into the BOOT event so every approved
    effect downstream is attributable to it.
    """
    def approve(req: EffectRequest, reason: str) -> bool:
        for g in grants:
            if fnmatch.fnmatch(req.kind, g):
                return True
        return fallback(req, reason) if fallback else False
    return approve


def cli_approver(req: EffectRequest, reason: str) -> bool:
    """Interactive approval. Returns False when there is no human attached, so an
    unattended run degrades to deny rather than to allow."""
    import sys
    if not sys.stdin.isatty():
        return False
    print(f"\n  [approval required] {req.kind} -> {req.target}"
          f"\n  why D.O. wants it: {req.justification}"
          f"\n  policy note: {reason}")
    try:
        return input("  allow? [y/N] ").strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False
