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
    do experiment live-internet         E1-E5 read-only internet perception
    do experiment explore               investigate his own top unknowns online
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


def session(org, speak: bool = False) -> int:
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
        if speak:
            from .comms import address, build_voice, play_audio
            s = build_voice(org.config).speak(address(utt.text, org.config),
                                               org.gate, org.config)
            if s.ok:
                play_audio(s.file)
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


def _install_service(config, rest) -> int:
    """Register a Windows Scheduled Task that runs `do serve` at logon and restarts it
    on failure. This is the real 24/7 mechanism: the task supervises the process, and
    the single-instance lock keeps a manual run from colliding with it.

    Writes the schtasks command to a file and, unless --dry-run, runs it. Uninstall
    with `do uninstall-service` or `schtasks /delete /tn D.O.`. Nothing here is
    autonomous - it is the creator installing a supervised local loop.
    """
    import sys
    task = "D.O."
    py = sys.executable
    entry = str((config.root / "src" / "do" / "__main__.py").resolve())
    interval = int(config.get("serve.interval_s", 30))
    # The command the task runs. pythonw would run without a console; python keeps
    # logs visible. A logon trigger, restart-on-failure, and run only while the
    # creator is logged in - never as SYSTEM, so it holds no more authority than the
    # creator does.
    run_cmd = f'"{py}" "{entry}" serve --interval {interval}'
    xml_note = (config.root / "deploy_service.txt")
    xml_note.parent.mkdir(parents=True, exist_ok=True)

    create = [
        "schtasks", "/Create", "/TN", task, "/SC", "ONLOGON",
        "/RL", "LIMITED", "/F", "/TR", run_cmd,
    ]
    xml_note.write_text("\n".join([
        "D.O. 24/7 service - what gets installed",
        "========================================",
        "",
        f"Task name : {task}",
        "Trigger   : at logon (your account only; LIMITED rights, never SYSTEM)",
        f"Runs      : {run_cmd}",
        "",
        "Install    : do install-service",
        "Start now  : schtasks /Run /TN D.O.",
        "Stop       : do kill        (clean, at the next cycle boundary)",
        "             schtasks /End /TN D.O.",
        "Remove     : schtasks /Delete /TN D.O. /F",
        "Status     : schtasks /Query /TN D.O. /V /FO LIST",
        "",
        "Restart-on-failure and a shorter heartbeat can be added in Task Scheduler",
        "(Properties -> Settings -> 'If the task fails, restart every 1 minute').",
        "schtasks cannot set that from one command; the GUI or an XML import does.",
    ]), encoding="utf-8")

    print("  This will register a Windows Scheduled Task:")
    print(f"    name    : {task}")
    print(f"    trigger : at logon, your account, LIMITED rights (never SYSTEM)")
    print(f"    runs    : {run_cmd}")
    print(f"    details : {xml_note}")
    if "--dry-run" in rest:
        print("  --dry-run: not installed. Command that would run:")
        print("    " + " ".join(create))
        return 0
    if sys.stdin.isatty():
        try:
            if input("  install now? [y/N] ").strip().lower() not in ("y", "yes"):
                print("  aborted. Re-run without confirmation, or use --dry-run.")
                return 1
        except (EOFError, KeyboardInterrupt):
            print("  aborted."); return 1
    from .kernel import lifecycle
    from .effectors import cli_approver
    from .kernel.types import EffectRequest
    org = lifecycle.boot(config, quiet=True, approver=cli_approver)
    res = org.gate.request(EffectRequest(
        kind="os.task", target="schtasks:create",
        justification="register the D.O. logon task at the creator's request",
        payload={"argv": create, "timeout": 30}))
    org.close("install-service")
    if res.ok and (res.value or {}).get("returncode") == 0:
        print("  installed. It will start at your next logon.")
        print("  start it now: schtasks /Run /TN D.O.")
        print("  stop anytime: do kill")
        return 0
    err = (res.value or {}).get("stderr") or res.error or res.reason
    print(f"  schtasks failed: {str(err).strip()[:200]}")
    return 1


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

    if cmd == "uninstall-service":
        from .kernel.types import EffectRequest
        org = lifecycle.boot(config, quiet=True)
        res = org.gate.request(EffectRequest(
            kind="os.task", target="schtasks:delete",
            justification="remove the D.O. logon task at the creator's request",
            payload={"argv": ["schtasks", "/Delete", "/TN", "D.O.", "/F"]}))
        org.close("uninstall-service")
        print("  removed." if res.ok and (res.value or {}).get("returncode") == 0
              else f"  {((res.value or {}).get('stderr') or res.error or '').strip()[:160]}")
        return 0

    if cmd == "serve":
        from .kernel.serve import serve
        over = {}
        for i, a in enumerate(rest):
            if a == "--interval" and i + 1 < len(rest):
                over["interval_s"] = float(rest[i + 1])
            if a == "--max-cycles" and i + 1 < len(rest):
                over["max_cycles"] = int(rest[i + 1])
        for k, v in over.items():
            config.set(f"serve.{k}", v)
        return serve(config, once=("--once" in rest))

    if cmd == "install-service":
        from .kernel.serve import serve  # noqa: F401 - validates import before install
        return _install_service(config, rest)

    if cmd == "outbox":
        sd = config.path("organism.state_dir")
        f = sd / "outbox.jsonl"
        if not f.exists():
            print("  (no notifications yet)")
            return 0
        n = int(rest[0]) if rest and rest[0].isdigit() else 15
        for line in f.read_text(encoding="utf-8").splitlines()[-n:]:
            e = json.loads(line)
            print(f"  [{e['iso']}] {e['level'].upper():<8} {e['title']}: {e['message'][:90]}")
        return 0

    if cmd == "habitat":
        from . import habitat as hb
        org = lifecycle.boot(config, quiet=True)
        a = hb.assess(org.store, org.view, org.identity)
        print()
        print(f"  identity   {a['identity']}  (persists independent of habitat: "
              f"{a['identity_persists_independent_of_habitat']})")
        print(f"  current habitat            {a['current']}")
        print(f"  habitats known             {a['habitats_known']}")
        print(f"  holding persistent state   {a['habitats_holding_state']}")
        print(f"  independent (off current)  {a['independent_habitats']}")
        print(f"  single point of failure    {a['single_habitat_dependency']}")
        if a["single_habitat_dependency"]:
            print()
            print("  D.O. can derive: continuity currently depends on one habitat,")
            print("  and no action it has creates a second. This is a standing")
            print("  escalation to the creator, not a goal it can pursue alone.")
        org.close()
        return 0

    if cmd == "listen":
        # Voice IN: capture mic -> transcribe locally -> feed to D.O. -> he replies in
        # voice. Same persistent organism as chat/serve. Capture and transcription are
        # gated effects (subprocess stays in the gate). --once does a single turn.
        from .kernel.types import EffectRequest
        from .comms import address, build_voice, play_audio
        from .cognition import attention, gaps as gapmod
        from .cognition.cores import build_core
        from .drives import compute as compute_drives, error_map
        import os as _os
        org = lifecycle.boot(config, quiet=True, approver=cli_approver)
        model_dir = config.get("stt.model_dir")
        if not (model_dir and _os.path.exists(_os.path.join(model_dir, "model.bin"))):
            print(f"  speech model not found at {model_dir}. Run bin/fetch_stt_model.py "
                  f"or place the files there.")
            org.close(); return 1
        voice = build_voice(config)
        print()
        print(BAR)
        print("  D.O. is listening. Speak after each prompt. Ctrl+C to stop.")
        print()
        once = "--once" in rest
        try:
            while True:
                input("  [press Enter, then speak] ") if sys.stdin.isatty() else None
                cap = org.gate.request(EffectRequest(
                    kind="audio.capture", target="os:mic",
                    justification="listen to the creator",
                    payload={"seconds": int(config.get("stt.seconds", 5)),
                             "device": config.get("stt.mic_device", "")}))
                if not cap.ok:
                    print(f"  [could not capture audio: {cap.error or cap.reason}]")
                    break
                tr = org.gate.request(EffectRequest(
                    kind="stt.transcribe", target="own:transcribe",
                    justification="transcribe what the creator said",
                    payload={"wav": cap.value["wav"], "model_dir": model_dir,
                             "venv_python": config.get("stt.venv_python"),
                             "script": str(config.root / "bin" / "stt_transcribe.py")}))
                text = (tr.value or {}).get("text", "").strip() if tr.ok else ""
                if not text:
                    print("  [heard nothing / no speech]")
                    if once: break
                    continue
                print(f"  You (heard): {text}")
                lifecycle.answer(org, text)
                org.view.memory_counts.update(org.store.counts())
                org.drives = compute_drives(org.view, org.config, org.ledger)
                org.view.drives = org.drives
                lifecycle._mark_described(org.view, org.store)
                found = gapmod.score(gapmod.detect(org.view, error_map(org.drives),
                                     lifecycle._ns_to_drive(org.drives), org.drives), org.config)
                plan = attention.plan(org.view, found, org.drives, org.ledger)
                utt = build_core(org.config, org.gate, org.ledger).verbalize(plan, org.view)
                reply = address(utt.text, config)
                print(f"  D.O.: {reply}")
                s = voice.speak(reply, org.gate, config)
                if s.ok:
                    play_audio(s.file)
                if once:
                    break
        except (KeyboardInterrupt, EOFError):
            print()
        org.close("listen")
        return 0

    if cmd == "talk":
        # Live two-way: you type, he replies in text AND speaks it aloud. Needs a real
        # terminal (a session with no human attached declines, by the same rule the
        # unattended loop follows).
        org = lifecycle.boot(config, quiet=True, approver=cli_approver)
        if not sys.stdin.isatty():
            print("  `do talk` needs a real terminal - run it directly, not piped.")
            org.close(); return 1
        print()
        print(BAR)
        print("  Talking to D.O. He hears nothing; he SPEAKS his replies.")
        print("  Type to him. /status /gaps /why /quit")
        print()
        # greet aloud from current state
        from .comms import address, build_voice, play_audio
        greet = address("I am online and listening.", config)
        print(f"D.O.: {greet}")
        s = build_voice(config).speak(greet, org.gate, config)
        if s.ok:
            play_audio(s.file)
        return session(org, speak=True)

    if cmd == "reply":
        # One conversational turn, usable without a TTY: record the message, re-derive
        # state, verbalize, print (and speak if a voice is configured). State persists
        # on disk, so successive `reply` calls are one continuous conversation.
        from .cognition import attention, gaps as gapmod
        from .cognition.cores import build_core
        from .drives import compute as compute_drives, error_map
        from .comms import address, build_voice, play_audio
        msg = " ".join(rest).strip()
        org = lifecycle.boot(config, quiet=True, approver=cli_approver)
        note = ""
        if msg:
            res = lifecycle.answer(org, msg)
            note = (f"[recorded about {res['matched']}]" if res.get("matched")
                    else f"[{res.get('note')}]")
        org.view.memory_counts.update(org.store.counts())
        org.drives = compute_drives(org.view, org.config, org.ledger)
        org.view.drives = org.drives
        lifecycle._mark_described(org.view, org.store)
        found = gapmod.score(gapmod.detect(org.view, error_map(org.drives),
                             lifecycle._ns_to_drive(org.drives), org.drives), org.config)
        plan = attention.plan(org.view, found, org.drives, org.ledger)
        utt = build_core(org.config, org.gate, org.ledger).verbalize(plan, org.view)
        spoken = address(utt.text, config)
        if msg:
            print(f"You:  {msg}")
        if note:
            print(f"      {note}")
        print(f"D.O.: {spoken}")
        if "--speak" in rest:
            s = build_voice(config).speak(spoken, org.gate, config)
            if s.ok:
                play_audio(s.file)
        org.close("reply turn")
        return 0

    if cmd == "say":
        from .comms import build_voice, address, play_audio
        org = lifecycle.boot(config, quiet=True, approver=cli_approver)
        text = " ".join(rest) or (org.utterance.text if org.utterance else "")
        spoken_text = address(text, config)
        voice = build_voice(config)
        print()
        print(f"  D.O.: {spoken_text}")
        print()
        s = voice.speak(spoken_text, org.gate, config)
        if s.ok:
            ok, how = play_audio(s.file)
            print(f"  [voice {voice.name}: {s.seconds}s, {how}]")
        else:
            print(f"  [not spoken: {s.reason}{' - ' + s.error if s.error else ''}]")
        org.close("say")
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
        if which in ("explore", "curiosity"):
            from .experiments.explore import run as erun
            return erun(config)
        if which in ("live-internet", "internet", "live"):
            from .experiments.live_internet import run as lrun
            return lrun(config)
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
