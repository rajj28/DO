"""Constrained web perception.

Every web observation carries source, timestamp, a content hash, and REPORTED
epistemic status — never OBSERVED. The distinction is the whole point: D.O. measured
that a server returned some bytes; it did not measure that the bytes are true.

Web content is treated as potentially false, stale, adversarial, or contradictory.
Concretely: retrieved text is never executed, never written to semantic memory without
a second corroborating source, and never allowed to raise its own confidence.

HTML extraction is a deliberately dumb regex stripper. A real parser is a dependency,
and the seed has none (docs/ARCHITECTURE.md section 1).
"""
from __future__ import annotations

import hashlib
import html
import re
import time

from ..kernel.types import EffectRequest, Epistemic, Namespace, Observation

_TAG = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_ANY = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def extract_text(body: str, limit: int = 4000) -> str:
    s = _TAG.sub(" ", body)
    s = _ANY.sub(" ", s)
    return _WS.sub(" ", html.unescape(s)).strip()[:limit]


def fetch(gate, url: str, justification: str, gap_id: str | None = None) -> dict:
    """Retrieve a page through the gate. Returns a provenance record, never bare text."""
    res = gate.request(EffectRequest(
        kind="net.http", target=url, justification=justification, gap_id=gap_id,
        payload={"timeout": 15, "max_bytes": 200_000}))
    rec = {
        "url": url, "ts": time.time(), "ok": res.ok, "verdict": res.verdict,
        "error": res.error, "epistemic": Epistemic.REPORTED.value,
        "confidence": 0.35,           # a single unverified source starts low and stays low
        "verification": "unverified",
    }
    if res.ok and isinstance(res.value, dict):
        body = res.value.get("body", "")
        text = extract_text(body)
        rec.update({
            "status": res.value.get("status"),
            "final_url": res.value.get("url"),
            "content_sha256": hashlib.sha256(body.encode("utf-8", "replace")).hexdigest(),
            "bytes": len(body),
            "text": text,
            "text_chars": len(text),
        })
    return rec


def corroborate(records: list[dict]) -> dict:
    """Compare independent retrievals of the same claim.

    Agreement between sources raises confidence; disagreement does not silently pick a
    winner — it produces a contradiction, which the gap detector treats as information
    rather than as a problem to be smoothed over.
    """
    ok = [r for r in records if r.get("ok") and r.get("text")]
    if len(ok) < 2:
        return {"verification": "unverified", "confidence": 0.35,
                "note": f"{len(ok)} usable source(s); corroboration needs at least 2"}
    hashes = {r["content_sha256"] for r in ok}
    domains = {r["url"].split("/")[2] if "//" in r["url"] else r["url"] for r in ok}
    if len(domains) < 2:
        return {"verification": "unverified", "confidence": 0.4,
                "note": "multiple retrievals but a single origin; not independent"}
    if len(hashes) == 1:
        return {"verification": "corroborated", "confidence": 0.7,
                "note": "byte-identical across origins; possibly a shared upstream"}
    return {"verification": "contradicted", "confidence": 0.3,
            "note": f"{len(ok)} sources across {len(domains)} origins differ in content",
            "contradiction": True}


def to_observation(rec: dict, key: str) -> Observation:
    return Observation(
        key=key, value=rec.get("text", "")[:500],
        epistemic=Epistemic.REPORTED, source=f"web:{rec['url']}",
        namespace=Namespace.WORLD, confidence=rec.get("confidence", 0.35),
        note=f"sha256:{rec.get('content_sha256', '')[:16]} status={rec.get('status')}")
