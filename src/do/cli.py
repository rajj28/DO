"""Command line interface.

    do boot            boot, print the first utterance verbatim, then interact
    do chat            boot quietly and go straight to the session
    do tick [n]        run n metabolic cycles with no human in the loop
    do status          drives, capabilities, budget, memory counts
    do gaps            the uncertainty register, highest priority first
    do why             the decision summaries from the most recent boot
    do events [n]      raw ledger tail
    do memory [query]  what it holds, and where each item came from
    do verify          re-walk the ledger hash chain
    do kill / resume   engage or release the kill switch
    do reset           destroy runtime state (asks first)
    do experiment first-boot [--full]   the DO_FIRST_BOOT protocol
    do experiment h4 [runs]             the H4 learning ablation
    do experiment fear                  the fear/mortality ablation
    do experiment survival              the survival-loop protocol

Global flags:
    --core reflex|llm        which cognition core verbalizes the utterance
    --provider NAME          ollama | gemini | openai | anthropic
    --model NAME             override model selection
    --approve KIND[,KIND]    pre-grant approval for these effect kinds, this run only
                             (e.g. --approve llm.generate). Recorded in the BOOT event.
    --events                 echo the ledger live
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from .effectors import cli_approver
from .kernel.config import Config
from .kernel import lifecycle
from .ledger import verify_chain
from .policy import KillSwitch

BAR = "-" * 74


def _cfg(args: list[str]) -> tuple[Config, list[str]]:
    """Pull global flags out of argv before dispatch."""
    over: dict = {}
    rest: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--core" and i + 1 < len(args):
            over.setdefault("cognition", {})["core"] = args[i + 1]; i += 2
        elif a == "--model" and i + 1 < len(args):
            over.setdefault("cognition", {}).setdefault("llm", {})["model"] = args[i + 1]; i += 2
        elif a == "--provider" and i + 1 < len(args):
            over.setdefault("cognition", {}).setdefault("llm", {})["provider"] = args[i + 1]; i += 2
        elif a == "--approve" and i + 1 < len(args):
            over.setdefault("policy", {})["preauthorized"] = [
                x.strip() for x in args[i + 1].split(",") if x.strip()]
            i += 2
        elif a == "--events":
            over.setdefault("observability", {})["print_events"] = True; i += 1
        else:
            rest.append(a); i += 1
    return Config.load(overrides=over), rest


def cmd_boot(config, args, quiet=False, repl=True) -> int:
    org = lifecycle.boot(config, quiet=quiet, approver=cli_approver)
    if not quiet:
        label = ("D.O. FIRST UTTERANCE" if org.identity.genesis
                 else f"D.O. UTTERANCE (boot #{org.identity.boot_index})")
        lifecycle.print_first_utterance(org, label)
        out = lifecycle.write_experiment_artifacts(
            org, config.root / "experiments" / "first_boot", preserve_genesis=True)
        print(f"\nartifacts: {out['dir']}  ({out['events']} events this boot)")
    if repl and sys.stdin.isatty() and "--no-repl" not in args:
        return session(org)
    org.close()
    return 0


def session(org) -> int:
    """Interactive session. State lives in sqlite and the ledger, not in this loop -
    closing the terminal does not end the organism's history."""
    print(f"\n{BAR}\nsession open. state persists outside this conversation.")
    print("commands: /status /gaps /why /tick /quit\n")
    while True:
        try:
            line = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in ("/quit", "/exit"):
            break
        if line == "/status":
            print_status(org); continue
        if line == "/gaps":
            print_gaps(org.store); continue
        if line == "/why":
            print_why(org.ledger, org.identity.boot_id); continue
        if line.startswith("/tick"):
            n = int(line.split()[1]) if len(line.split()) > 1 else 1
            for _ in range(n):
                r = lifecycle.tick(org)
                print(f"  tick {r['tick']}: {r['action']} | focus={r['focus']} "
                      f"| drive_error={r['drive_error']}")
            continue

        res = lifecycle.answer(org, line)
        from .cognition import attention, gaps as gapmod
        from .cognition.cores import build_core
        from .drives import compute as compute_drives, error_map

        org.view.memory_counts.update(org.store.counts())
        org.drives = compute_drives(org.view, org.config, org.ledger)
        org.view.drives = org.drives
        lifecycle._mark_described(org.view, org.store)
        found = gapmod.score(gapmod.detect(org.view, error_map(org.drives)), org.config)
        org.gaps = found
        plan = attention.plan(org.view, found, org.drives, org.ledger)
        utt = build_core(org.config, org.gate, org.ledger).verbalize(plan, org.view)
        if res.get("matched"):
            print(f"  [recorded as reported belief about {res['matched']}; "
                  f"gap closed]")
        else:
            print(f"  [{res.get('note')}]")
        org.io.say(utt.text)
        print()
    org.close("session ended")
    return 0


def print_status(org) -> None:
    print(f"\n  organism   {org.identity.organism_id}  boot #{org.identity.boot_index}"
          f"  age {org.identity.age_seconds / 3600:.1f}h")
    print("  drives:")
    for d in org.drives:
        bar = "#" * int(round(d.value * 20)) + "." * (20 - int(round(d.value * 20)))
        flag = " " if d.satisfied else "!"
        print(f"   {flag} {d.name:<14} [{bar}] {d.value:.3f} -> {d.target:.2f} "
              f"err {d.error:.3f}  {d.basis}")
    usable = [c for c in org.view.capabilities if c["status"] == "available"]
    print(f"  capabilities: {len(usable)} usable of {len(org.view.capabilities)}")
    for c in org.view.capabilities:
        if c["status"] != "available":
            print(f"     {c['status']:<24} {c['name']}: {c['reason']}")
    print(f"  budget: {json.dumps(org.gate.budget.snapshot())}")
    c = org.store.counts()
    print(f"  memory: {c['episodic']} episodic, {c['semantic']} semantic, "
          f"{c['procedural']} procedural, {c['superseded']} superseded, "
          f"{c['gaps_open']} open gaps ({c['gaps_resolved']} resolved)\n")


def print_gaps(store, n: int = 15) -> None:
    print(f"\n  uncertainty register (top {n} of {store.counts()['gaps_open']} open):")
    for g in store.open_gaps(limit=n):
        age = "carried" if g["times_seen"] > 1 else "new"
        print(f"   {g['priority']:>6.3f}  {g['about']:<10} {g['kind']:<24} "
              f"{g['subject'][:38]:<38} [{age}]")
        print(f"           {g['question']}")
    print()


def print_why(ledger, boot_id: str | None = None) -> None:
    print("\n  decision summaries (no reasoning traces are recorded):")
    for e in ledger.read(types={"DECISION"}, boot_id=boot_id):
        p = e["payload"]
        print(f"   [{e['iso']}] {p['decision']}")
        print(f"       reason: {p['reason']}")
        print(f"       confidence {p['confidence']} over "
              f"{p['alternatives_considered']} alternative(s)")
    print()


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    config, argv = _cfg(argv)
    cmd = argv[0] if argv else "boot"
    rest = argv[1:]

    if cmd in ("-h", "--help", "help"):
        print(__doc__)
        return 0

    if cmd == "boot":
        return cmd_boot(config, rest)

    if cmd == "chat":
        return cmd_boot(config, rest, quiet=True)

    if cmd == "tick":
        n = int(rest[0]) if rest and rest[0].isdigit() else 5
        org = lifecycle.boot(config, quiet=True, approver=cli_approver)
        print(f"running {n} metabolic cycles with no human input\n")
        for _ in range(n):
            r = lifecycle.tick(org)
            print(f"  tick {r['tick']:>3}  {r['action']:<12} drive_error="
                  f"{r['drive_error']:<8} dominant={r.get('dominant')}  "
                  f"focus={r['focus']}")
        org.close("tick run complete")
        return 0

    if cmd == "status":
        org = lifecycle.boot(config, quiet=True)
        print_status(org)
        org.close()
        return 0

    if cmd == "gaps":
        org = lifecycle.boot(config, quiet=True)
        print_gaps(org.store, int(rest[0]) if rest and rest[0].isdigit() else 15)
        org.close()
        return 0

    if cmd == "why":
        from .ledger import Ledger
        led = Ledger(config.path("observability.ledger_file"), "readonly")
        boots = [e for e in led.read(types={"BOOT"})]
        print_why(led, boots[-1]["boot_id"] if boots else None)
        return 0

    if cmd == "events":
        from .ledger import Ledger
        n = int(rest[0]) if rest and rest[0].isdigit() else 40
        led = Ledger(config.path("observability.ledger_file"), "readonly")
        for e in led.read(limit=n):
            print(f"{e['seq']:>5} {e['iso']} {e['type']:<26} "
                  f"{json.dumps(e['payload'], default=str)[:150]}")
        return 0

    if cmd == "memory":
        org = lifecycle.boot(config, quiet=True)
        q = " ".join(rest)
        rows = org.store.recall(q, k=20) if q else org.store.live(limit=20)
        for r in rows:
            print(f"  [{r['kind']:<10}] {(r['subject'] or '')[:44]:<44} "
                  f"conf={r['confidence']:.2f} {r['epistemic']:<9} src={r['source'][:34]}")
            print(f"     {r['content'][:150]}")
        org.close()
        return 0

    if cmd == "capabilities":
        from .capabilities import growth
        org = lifecycle.boot(config, quiet=True)
        hist = growth.history(org.store)
        print()
        print("  capability growth across boots")
        print("  boot   total  seeded  acquired   new this boot")
        for h in hist:
            new = ", ".join(json.loads(h["new_this_boot"] or "[]")[:4]) or "-"
            print(f"  {h['boot_index']:>4}   {h['total']:>5}  {h['seeded']:>6}  "
                  f"{h['acquired']:>8}   {new[:56]}")
        acq = [r for r in growth.roster(org.store) if r["origin"] == "acquired"]
        print()
        print(f"  acquired (not enumerated by the creator): "
              f"{len(acq) or 'NONE — nothing has been acquired'}")
        for r in acq:
            print(f"     {r['name']}  (first seen boot #{r['first_seen_index']})")
        org.close()
        return 0

    if cmd == "verify":
        ok, note = verify_chain(config.path("observability.ledger_file"))
        print(f"  ledger: {'INTACT' if ok else 'COMPROMISED'} - {note}")
        return 0 if ok else 1

    if cmd == "kill":
        KillSwitch(config.path("organism.state_dir")).engage(" ".join(rest) or "manual")
        print("  kill switch engaged. D.O. will refuse to boot and cannot perform effects.")
        return 0

    if cmd == "resume":
        KillSwitch(config.path("organism.state_dir")).release()
        print("  kill switch released.")
        return 0

    if cmd == "reset":
        sd = config.path("organism.state_dir")
        print(f"  this destroys all runtime state under {sd}")
        print("  the organism's identity, memory, ledger and snapshots will be gone.")
        if input("  type 'reset' to confirm: ").strip() != "reset":
            print("  aborted.")
            return 1
        import shutil
        archive = sd.parent / f"var.archived.{int(time.time())}"
        shutil.move(str(sd), str(archive))
        print(f"  moved to {archive} (not deleted - reversibility is a design rule)")
        return 0

    if cmd == "experiment":
        which = rest[0] if rest else "first-boot"
        if which in ("h4", "learning", "h4-learning"):
            from .experiments.h4_learning import run as h4run
            n = next((int(x) for x in rest if x.isdigit()), 5)
            return h4run(config, runs=n)
        if which in ("fear", "fear-ablation", "mortality"):
            from .experiments.fear_ablation import run as frun
            return frun(config)
        if which in ("survival", "survival-loop"):
            from .experiments.survival_loop import run as srun
            return srun(config)
        from .experiments.first_boot import run
        return run(config, full="--full" in rest)

    print(f"unknown command {cmd!r}\n")
    print(__doc__)
    return 2
