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
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from ..kernel.types import EffectRequest, EffectResult
from ..ledger import EventType, Ledger
from ..policy import ALLOW, DENY, REQUIRE_APPROVAL, Budget, KillSwitch, Policy


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
        r = urllib.request.Request(req.target, headers={"User-Agent": "D.O./0.1 (research seed)"})
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
        r = urllib.request.Request(req.target, data=payload,
                                   headers={"Content-Type": "application/json",
                                            **req.payload.get("headers", {})})
        try:
            with urllib.request.urlopen(r, timeout=float(req.payload.get("timeout", 120))) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            # A provider's error body says exactly what was wrong with the request.
            # Discarding it and logging only the status code makes a failure
            # undiagnosable, which in a project about observability is a defect.
            raise RuntimeError(f"{_http_error(e)} | request_bytes={len(payload)}") from None

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
        raise NotImplementedError("no TTS provider configured (see comms/voice.py)")

    def _human_ask(self, req: EffectRequest):
        return {"queued": True, "question": req.payload.get("question", "")}


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
