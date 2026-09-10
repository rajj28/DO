"""Undescribed-referent discovery: the cheapest frontier of world knowledge.

An organism's environment is full of *names of things it cannot describe*. Those names
are free evidence that something exists, and they cost nothing to collect. This module
turns them into candidate referents, which the gap detector turns into questions.

Deliberate scope limit: this scans the organism's own project directory, the names
(never values) of environment variables, tools on PATH, and locally installed models.
It does **not** walk the user's home directory. Cataloguing someone's personal folders
into a persistent ledger is not the organism's business, and the ledger is forever.

Classification is honest about its own status: OS plumbing is recognised by pattern
and recorded as ASSUMED, never OBSERVED. "I think these are operating-system
variables" is a belief, and it can itself become a gap.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# Patterns believed to be operating-system or shell plumbing. This is an ASSUMPTION
# baked into the seed, and it is marked as one everywhere it is used.
PLUMBING = re.compile(
    r"^(PATH|PATHEXT|HOME|HOMEDRIVE|HOMEPATH|TEMP|TMP|TMPDIR|USER|USERNAME|USERPROFILE|"
    r"USERDOMAIN.*|COMPUTERNAME|COMSPEC|OS|NUMBER_OF_PROCESSORS|PROCESSOR_.*|"
    r"PROGRAM.*|COMMONPROGRAM.*|SYSTEM.*|WINDIR|APPDATA|LOCALAPPDATA|PUBLIC|"
    r"ALLUSERSPROFILE|DRIVERDATA|SHELL|TERM|TERM_.*|LANG|LC_.*|PWD|OLDPWD|SHLVL|_|"
    r"PS1|PSMODULEPATH|LOGONSERVER|SESSIONNAME|CLIENTNAME|EXEPATH|PLINK_PROTOCOL|"
    r"MSYSTEM|CONFIG_SITE|DISPLAY|WSLENV|ONEDRIVE.*|CHOCOLATEY.*)$", re.I)

# Tokens that indicate a secret. The name is world-knowledge; the value is not read.
SECRETISH = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH|DSN|CONNECTION)",
                       re.I)


def discover(observations: dict[str, Any], project_root: Path) -> list[dict]:
    """Return referents: things that demonstrably exist and are not described."""
    refs: list[dict] = []
    seen: set[str] = set()

    def add(name: str, source: str, evidence: str, kind: str, weight: float,
            detail: dict | None = None):
        key = f"{kind}:{name}"
        if key in seen or not name:
            return
        seen.add(key)
        refs.append({"name": name, "kind": kind, "source": source,
                     "evidence": evidence, "weight": weight, "detail": detail or {}})

    # 1. Environment variable prefixes. A cluster of >=2 variables sharing a prefix is
    #    strong evidence of an integrated system, not a stray setting.
    names = observations.get("world.env.names") or []
    clusters: dict[str, list[str]] = {}
    for n in names:
        if PLUMBING.match(n):
            continue
        head = re.split(r"[_\-]", n, 1)[0].upper()
        if len(head) < 3:
            continue
        clusters.setdefault(head, []).append(n)

    for head, members in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
        secretish = any(SECRETISH.search(m) for m in members)
        add(head, "world.env.names",
            f"{len(members)} environment variable name(s) share this prefix: "
            f"{', '.join(sorted(members)[:4])}",
            "env_system",
            weight=0.55 + 0.12 * min(len(members), 3) + (0.15 if secretish else 0.0),
            detail={"members": sorted(members),
                    "holds_credential_shaped_names": secretish})

    # 2. Executables present on PATH.
    for t in observations.get("tools.on_path") or []:
        add(t, "tools.on_path", f"executable {t!r} resolves on PATH", "executable",
            weight=0.5)

    # 3. Locally installed models: named artefacts with a measurable resource cost.
    for m in observations.get("tools.local_models") or []:
        add(m["name"], "tools.local_models",
            f"model artefact of {m['gib']} GiB present on local storage",
            "model", weight=0.75, detail=m)

    # 4. The organism's own body: files it is made of but has not read.
    try:
        py = sorted(p for p in (project_root / "src").rglob("*.py"))
        if py:
            add("self.source_tree", "filesystem",
                f"{len(py)} python module(s) under src/ constitute this process's own code",
                "self_artifact", weight=0.65,
                detail={"modules": len(py),
                        "bytes": sum(p.stat().st_size for p in py)})
    except Exception:
        pass

    return refs
