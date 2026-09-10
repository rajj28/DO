"""`do serve`: the always-on loop. Budgeted, restart-safe, with a heartbeat.

Design constraints, each earned by something that would otherwise go wrong on a
machine that is 98% full with a failing battery:

* **Single instance.** A logon task plus a manual run must not produce two organisms
  writing the same ledger. A lock file carries pid and heartbeat; a second start
  refuses while the first is fresh, and takes over a stale one.
* **Budgeted.** A run is bounded by max_cycles and max_seconds, and paced by an
  interval, so a supervised task can never spin. Unbounded is opt-in via config 0s.
* **Kill switch honoured.** Checked every cycle. `do kill` (or the KILL file, or the
  env var) stops the loop cleanly at the next boundary - the same switch the effector
  gate obeys, so there is one off button, not two.
* **Backs off, does not thrash.** If disk falls below a hard floor the loop cannot
  safely keep writing, so it notifies once and sleeps a long backoff rather than
  hammering a full disk.
* **Boots once, cycles in-process.** Re-booting each cycle would grow the ledger
  every interval. One boot, then `cycle()` re-observes - and the frugality/recovery
  drives keep the organism's own footprint in check, which is the point: an always-on
  D.O. maintains itself.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from ..ledger import EventType


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True              # exists but not ours - still alive
    except OSError:
        return False


def _pid_alive_win(pid: int) -> bool:
    """Reliable liveness on Windows without spawning a process (subprocess is barred
    outside the gate). ctypes OpenProcess: a handle means it is alive."""
    if pid <= 0:
        return False
    try:
        import ctypes
        PROCESS_QUERY = 0x1000
        h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY, False, pid)
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        return False
    except Exception:
        return True              # if unsure, assume alive and refuse to double-run


def _acquire_lock(lock: Path, stale_after: float) -> tuple[bool, str]:
    """Take the single-instance lock, or report why not."""
    now = time.time()
    if lock.exists():
        try:
            d = json.loads(lock.read_text(encoding="utf-8"))
            pid, hb = int(d.get("pid", 0)), float(d.get("heartbeat", 0))
        except Exception:
            pid, hb = 0, 0.0
        alive = _pid_alive_win(pid) if os.name == "nt" else _pid_alive(pid)
        fresh = (now - hb) < stale_after
        if alive and fresh:
            return False, f"another instance is live (pid {pid}, heartbeat {now - hb:.0f}s ago)"
        # stale: overwrite
    lock.write_text(json.dumps({"pid": os.getpid(), "heartbeat": now,
                                "started": now}), encoding="utf-8")
    return True, "lock acquired"


def _heartbeat(lock: Path, cycle: int) -> None:
    try:
        d = json.loads(lock.read_text(encoding="utf-8")) if lock.exists() else {}
    except Exception:
        d = {}
    d.update({"pid": os.getpid(), "heartbeat": time.time(), "cycle": cycle})
    lock.write_text(json.dumps(d), encoding="utf-8")


def _drain_inbox(org, notifier, state_dir) -> None:
    """Read and clear the inbox, answering each line and speaking the reply.

    The inbox is a plain text file - one message per line - so anything can write to
    it: a one-click prompt, `echo >> inbox.txt`, an editor. The organism polls it on
    its own cycle; you never invoke him. State persists as always, so a message left
    while he was down is answered when he next runs.
    """
    from ..kernel import lifecycle
    from ..cognition import attention, gaps as gapmod
    from ..cognition.cores import build_core
    from ..drives import compute as compute_drives, error_map
    from ..comms import address, build_voice, play_audio
    from ..comms import notify as notify_mod

    inbox = state_dir / "inbox.txt"
    if not inbox.exists():
        return
    try:
        lines = [l.strip() for l in inbox.read_text(encoding="utf-8").splitlines()
                 if l.strip()]
        inbox.write_text("", encoding="utf-8")   # clear atomically-enough for one writer
    except Exception:
        return
    for msg in lines:
        res = lifecycle.answer(org, msg)
        org.view.memory_counts.update(org.store.counts())
        org.drives = compute_drives(org.view, org.config, org.ledger)
        org.view.drives = org.drives
        lifecycle._mark_described(org.view, org.store)
        found = gapmod.score(gapmod.detect(org.view, error_map(org.drives),
                             lifecycle._ns_to_drive(org.drives), org.drives), org.config)
        plan = attention.plan(org.view, found, org.drives, org.ledger)
        utt = build_core(org.config, org.gate, org.ledger).verbalize(plan, org.view)
        reply = address(utt.text, org.config)
        # Record the exchange to the outbox, and speak the reply - he is talking to
        # you, so this speaks regardless of the CRITICAL-only rule for alerts.
        notifier.notify(notify_mod.NOTABLE, "reply", reply, {"to_message": msg})
        try:
            s = build_voice(org.config).speak(reply, org.gate, org.config)
            if s.ok:
                play_audio(s.file)
        except Exception:
            pass


def serve(config, once: bool = False, quiet: bool = False) -> int:
    from . import lifecycle
    from ..policy import KillSwitch
    from ..comms import notify as notify_mod

    state_dir = config.path("organism.state_dir")
    state_dir.mkdir(parents=True, exist_ok=True)
    lock = state_dir / "serve.lock"
    interval = float(config.get("serve.interval_s", 30))
    max_cycles = int(config.get("serve.max_cycles", 0))          # 0 = unbounded
    max_seconds = float(config.get("serve.max_seconds", 0))      # 0 = unbounded
    disk_floor = float(config.get("serve.min_disk_free_ratio", 0.005))
    backoff = float(config.get("serve.backoff_s", 300))
    stale_after = max(interval * 3, 90)

    kill = KillSwitch(state_dir)
    if kill.engaged():
        print(f"  serve: kill switch engaged ({kill.reason()}); not starting.")
        return 0

    ok, why = _acquire_lock(lock, stale_after)
    if not ok:
        print(f"  serve: not starting - {why}")
        return 0

    org = lifecycle.boot(config, quiet=True)
    notifier = notify_mod.Notifier(config, org.gate, org.ledger, state_dir)
    org.ledger.append(EventType.HEARTBEAT,
                      {"event": "serve_start", "pid": os.getpid(),
                       "interval_s": interval, "max_cycles": max_cycles})
    if not quiet:
        print(f"  D.O. serving. pid {os.getpid()}, interval {interval:.0f}s, "
              f"kill with `do kill`. Ctrl+C to stop.\n")

    started, cycle, notified_backoff = time.time(), 0, False
    window = int(config.get("serve.budget_window_cycles", 120))
    reason = "stopped"
    try:
        while True:
            if kill.engaged():
                reason = f"kill switch: {kill.reason()}"
                break
            if max_cycles and cycle >= max_cycles:
                reason = f"max_cycles {max_cycles} reached"
                break
            if max_seconds and (time.time() - started) >= max_seconds:
                reason = f"max_seconds {max_seconds:.0f} reached"
                break

            cycle += 1
            _heartbeat(lock, cycle)

            # Reset the metered budget each window. The per-boot cap is a safety limit
            # for a single run; a 24/7 process needs it as a RATE limit instead, or
            # curiosity and housekeeping would stop after ~200 effects and never
            # resume. The cap still bounds each window - it is a rate, not a removal.
            if window and cycle % window == 0:
                org.gate.budget.effects = 0
                org.gate.budget.network = 0
                org.gate.budget.started = time.time()
                org.ledger.append(EventType.HEARTBEAT,
                                  {"event": "budget_window_reset", "cycle": cycle})

            # Hard floor: below this the loop cannot safely keep writing state.
            free = org.view.val("resources.disk.free_ratio")
            if free is not None and free < disk_floor:
                if not notified_backoff:
                    notifier.notify(notify_mod.CRITICAL, "disk critically low",
                                    f"free disk ratio {free:.4f} is below my safe "
                                    f"floor {disk_floor}. I am backing off to avoid "
                                    f"making it worse, and cannot resolve this alone.",
                                    {"free_ratio": free})
                    notified_backoff = True
                time.sleep(backoff)
                # re-observe after backoff before deciding again
                lifecycle.cycle(org, quiet=True)
                continue
            notified_backoff = False

            # Anything you dropped in the inbox since last cycle: he answers it and
            # speaks the reply aloud. This is how you talk to a LIVE organism without
            # a terminal - he is already running; you just leave him a message.
            _drain_inbox(org, notifier, state_dir)

            r = lifecycle.cycle(org, quiet=True)
            for level, title, msg, data in notify_mod.assess(org, config):
                notifier.notify(level, title, msg, data)

            # Curiosity: when he investigated one of his own unknowns this cycle, tell
            # you what he learned. This is how curiosity shows up in the live loop -
            # not narrated by a harness, but pushed by the running organism itself.
            out = r.get("outcome") or {}
            if out.get("action") == "investigate_referent":
                det = out.get("detail") or {}
                if det.get("described"):
                    notifier.notify(notify_mod.NOTABLE, "learned something",
                                    f"I looked up {det.get('referent')} and now hold: "
                                    f"{str(det.get('learned',''))[:160]}", det)

            if not quiet:
                m = r.get("mortality") or {}
                act = ((r.get("outcome") or {}).get("action")
                       or ("diagnose" if r.get("diagnosis") else r.get("note", "idle")))
                print(f"  cycle {cycle}: focus={r.get('focus')} act={act} "
                      f"fear={m.get('fear', 0)}")

            if once:
                reason = "once"
                break
            _sleep_interruptible(interval, kill)
    except KeyboardInterrupt:
        reason = "interrupted"
    finally:
        org.ledger.append(EventType.HEARTBEAT,
                          {"event": "serve_stop", "cycles": cycle, "reason": reason})
        org.close(f"serve stop: {reason}")
        try:
            lock.unlink()
        except OSError:
            pass
    if not quiet:
        print(f"\n  D.O. stopped after {cycle} cycle(s): {reason}")
    return 0


def _sleep_interruptible(seconds: float, kill) -> None:
    """Sleep, but wake early if the kill switch is thrown, so `do kill` stops the
    loop within a second rather than after a full interval."""
    end = time.time() + seconds
    while time.time() < end:
        if kill.engaged():
            return
        time.sleep(min(1.0, end - time.time()))
