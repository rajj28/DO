"""Boot sequence and metabolism.

Phases A-E from the brief, plus a tick loop. The tick loop is the part that makes this
an organism rather than a request handler: drives are recomputed on a clock, so goals
can arise with no human turn in the conversation.

Ordering is not arbitrary and is worth reading in sequence:

  A  sense           measure self and host; probe the network THROUGH the gate, so the
                     first thing D.O. learns about the world is that acting on it is
                     mediated by a policy it does not control
  B  model + memory  project SELF/WORLD/USER/TOOLS/RESOURCES views; discover referents;
                     evaluate which capabilities are actually affordable
  C  drives + gaps   measure homeostatic error, then detect and score uncertainty -
                     drive error feeds gap priority, which is the causal link the
                     whole experiment turns on
  D  utterance       select focus and speech act, verbalize, record verbatim
  E  interact        REPL and/or ticks
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..capabilities import seed_registry
from ..capabilities import growth
from ..capabilities.actions import ActionContext, applicable_actions, housekeeping_effector
from ..cognition import attention, gaps as gapmod, objectives as objmod, planner, reflection
from ..cognition.cores import ReflexCore, build_core
from ..comms import TextIO
from ..drives import compute as compute_drives, dominant, error_map, total_error
from ..effectors import Gate, cli_approver
from ..ledger import EventType, Ledger, verify_chain
from ..memory import MemoryRecord, MemoryStore
from ..models import StateView, build_self_model, build_world_model, snapshot
from ..policy import Budget, KillSwitch, Policy
from ..sense import Sensors, discover_referents, probe_network
from ..sense import footprint
from .. import learning
from ..kernel.types import Epistemic
from . import identity as identity_mod


@dataclass
class Organism:
    config: Any
    identity: Any
    ledger: Ledger
    store: MemoryStore
    gate: Gate
    view: StateView
    drives: list = field(default_factory=list)
    gaps: list = field(default_factory=list)
    plan: Any = None
    utterance: Any = None
    objective: Any = None
    cycle_count: int = 0
    action_ctx: Any = None
    registry: Any = None
    io: TextIO | None = None
    timings: dict = field(default_factory=dict)
    gap_stats: dict = field(default_factory=dict)
    tick_count: int = 0

    def close(self, note: str = "normal") -> None:
        self.ledger.append(EventType.SHUTDOWN,
                           {"reason": note, "ticks": self.tick_count,
                            "budget": self.gate.budget.snapshot()})
        self.store.close()


def boot(config, perturb: dict | None = None, quiet: bool = False,
         approver: Callable | None = None, echo_events: bool = False) -> Organism:
    t_start = time.perf_counter()
    timings: dict[str, float] = {}

    def mark(name: str, t0: float) -> None:
        timings[name] = round((time.perf_counter() - t0) * 1000, 1)

    state_dir = config.path("organism.state_dir")
    state_dir.mkdir(parents=True, exist_ok=True)

    # --- identity, ledger, memory ------------------------------------------
    t = time.perf_counter()
    ident = identity_mod.load_or_create(state_dir)
    ledger_path = config.path("observability.ledger_file")
    chain_ok, chain_note = verify_chain(ledger_path)
    ledger = Ledger(ledger_path, ident.boot_id,
                    echo=echo_events or bool(config.get("observability.print_events")))
    store = MemoryStore(state_dir / "memory.db", ident.boot_id)

    ledger.append(EventType.BOOT, {
        "organism_id": ident.organism_id, "boot_index": ident.boot_index,
        "genesis": ident.genesis, "pid": __import__("os").getpid(),
        "chain_verified": chain_ok, "chain_note": chain_note,
        "perturbations": sorted(perturb or {}),
        "config_core": config.get("cognition.core"),
        "code_version": __import__("do").__version__,
        # Authority the creator granted for this run, recorded before anything uses it.
        # Every approved effect downstream is attributable to this line.
        "preauthorized_effects": sorted(config.get("policy.preauthorized", []) or []),
    })
    mark("identity_ms", t)

    if not quiet:
        print(f"\nD.O. booting...\n")
        print(f"  Identity initialized.      {ident.organism_id} "
              f"(boot #{ident.boot_index}{', genesis' if ident.genesis else ''})")

    # --- policy + gate ------------------------------------------------------
    policy = Policy.load(config.root / "config" / "policy.json")
    budget = Budget(max_effects=int(config.get("budget.max_effects_per_boot", 200)),
                    max_network=int(config.get("budget.max_network_calls_per_boot", 20)),
                    max_wall_seconds=float(config.get("budget.max_wall_seconds", 3600)))
    kill = KillSwitch(state_dir)
    grants = set(config.get("policy.preauthorized", []) or [])
    if grants:
        from ..effectors import preauthorized_approver
        approver = preauthorized_approver(grants, fallback=approver)
    gate = Gate(policy, budget, kill, ledger, config.path("organism.sandbox_dir"),
                approver=approver)

    if kill.engaged():
        ledger.append(EventType.ERROR, {"halted": True, "reason": kill.reason()})
        if not quiet:
            print(f"  HALTED: {kill.reason()}")
        raise SystemExit(f"kill switch engaged: {kill.reason()}")

    # Housekeeping actions are dispatched by the gate like every other effect. This
    # registers what the gate is able to do; it does not create a second way out.
    # The workspace is the outer bound on everything an action may touch. It defaults
    # to the project root, and an isolated run (a test, an experiment trial) points it
    # at its own directory - so a trial can never reach the real project's files.
    workspace = Path(config.get("organism.workspace_root") or config.root)

    def _action_ctx():
        return ActionContext(state_dir=state_dir, project_root=workspace,
                             config=config, db=store.db)

    gate.extra["fs.housekeep"] = housekeeping_effector(_action_ctx)

    # === PHASE A: self-observation =========================================
    t = time.perf_counter()
    sensors = Sensors(perturb=perturb)
    sensors.run_all(state_dir / "memory.db", ledger_path)
    footprint.observe(sensors, state_dir, workspace,
                      int(config.get("resources.state_quota_bytes", 2 * 1024 ** 2)))
    probe_network(gate, sensors)
    observations = {o.key: o for o in sensors.obs}
    mark("sense_ms", t)

    # The deduplicated view is authoritative, not the raw probe list: a slot may be
    # declared UNKNOWN by `declare_structural_unknowns` and then filled by a later
    # probe (world.network.reachable is exactly this). Counting the raw list would
    # report the same key as both known and unknown.
    for o in observations.values():
        if o.is_known:
            continue
        ledger.append(EventType.OBSERVATION,
                      {"key": o.key, "status": "unknown", "source": o.source})
    known = sum(1 for o in observations.values() if o.is_known)
    ledger.append(EventType.OBSERVATION, {
        "phase": "A", "count": len(observations),
        "known": known, "unknown": len(observations) - known,
        "superseded_by_later_probe": len(sensors.obs) - len(observations),
        "probe_failures": sensors.failures})

    if not quiet:
        print(f"  Environment inspected.     {known} measured, "
              f"{len(observations) - known} could not be established")

    # === PHASE B: models, referents, capabilities ==========================
    t = time.perf_counter()
    prior = store.previous_boot()
    counts = store.counts()
    counts["_integrity_ok"] = 1.0 if chain_ok else 0.0
    counts["_integrity_note"] = chain_note
    counts["_denials"] = len(gate.denials)
    counts["_standing"], counts["_standing_note"] = _standing(ident, gate, store)

    view = StateView(
        observations=observations,
        identity=ident.to_dict(),
        memory_counts=counts,
        prior_boot=dict(prior) if prior else None,
        carried_gaps=[dict(g) for g in store.carried_gaps()],
        config=config)

    plain = {k: o.value for k, o in observations.items() if o.is_known}
    view.referents = discover_referents(plain, config.root)
    _mark_described(view, store)

    registry = seed_registry(view, ledger)
    view.capabilities = registry.as_list()

    # Roster census. Every capability the creator enumerated is recorded as `seeded`,
    # so anything that ever appears as `acquired` is unambiguously not something a
    # human wrote into the registry.
    growth.ensure_schema(store)
    for cap in view.capabilities:
        growth.register(store, cap["name"], "seeded", cap.get("description", ""),
                        boot_index=ident.boot_index)
    from ..capabilities.actions import REGISTRY as _ACTIONS
    for a_name, a_obj in _ACTIONS.items():
        growth.register(store, f"action:{a_name}", "seeded", a_obj.description,
                        boot_index=ident.boot_index)
    census = growth.census(store, ident.boot_index, ledger)
    mark("model_ms", t)

    if not quiet:
        usable = len(registry.usable())
        blocked = len(registry.blocked())
        print(f"  Capability roster.         {census['total']} known "
              f"({census['seeded']} seeded, {census['acquired']} acquired)"
              + (f"  NEW: {', '.join(census['new_this_boot'][:3])}"
                 if census["new_this_boot"] else ""))
        print(f"  Memory initialized.        {counts['episodic']} episodic, "
              f"{counts['semantic']} semantic, {counts['procedural']} procedural"
              + (f", {len(view.carried_gaps)} carried questions" if view.carried_gaps else ""))
        print(f"  Capabilities detected.     {usable} usable, {blocked} present but blocked")
        net = view.val("world.network.reachable")
        print(f"  Internet interface {'initialized' if net else 'unavailable '}.    "
              f"world.network.reachable={net}")

    # === PHASE C: drives and uncertainty ===================================
    t = time.perf_counter()
    drives = compute_drives(view, config, ledger)
    view.drives = drives
    store.save_drives(drives)

    found = _rank(gapmod.detect(view, error_map(drives), _ns_to_drive(drives)), view, store, config,
                  _action_ctx())
    gap_stats = reflection.persist_gaps(store, found, ledger)
    mark("uncertainty_ms", t)

    # === PHASE D: attention and first utterance ============================
    t = time.perf_counter()
    plan = attention.plan(view, found, drives, ledger)
    core = build_core(config, gate, ledger)
    utt = core.verbalize(plan, view) if plan else None
    mark("utterance_ms", t)

    if utt:
        ledger.append(EventType.UTTERANCE, {
            "text": utt.text, "core": utt.core, "model": utt.model,
            "fallback_from": utt.fallback_from, "speech_act": plan.speech_act,
            "focus_gap": plan.focus.id, "verbatim": True})
        store.write(MemoryRecord(
            kind="episodic", subject=f"utterance:{ident.boot_id}",
            content=utt.text, source=f"cognition.{utt.core}",
            epistemic=Epistemic.OBSERVED.value, confidence=1.0, importance=0.9,
            boot_id=ident.boot_id, context=f"speech_act={plan.speech_act}"))

    # --- consolidate --------------------------------------------------------
    t = time.perf_counter()
    reflection.consolidate(store, view, ledger, ident.boot_id)
    store.record_boot(ident.boot_id, ident.boot_index, view.boot_ts,
                      utt.text if utt else "", utt.core if utt else "none",
                      notes=json.dumps({"perturb": sorted(perturb or {}),
                                        "gap_stats": gap_stats}))
    snapshot(view, state_dir / "snapshots" / f"{ident.boot_id}.json")
    mark("consolidate_ms", t)
    timings["total_ms"] = round((time.perf_counter() - t_start) * 1000, 1)

    learning.ensure_schema(store)
    org = Organism(config=config, identity=ident, ledger=ledger, store=store, gate=gate,
                   view=view, drives=drives, gaps=found, plan=plan, utterance=utt,
                   registry=registry, io=TextIO(ledger), timings=timings,
                   gap_stats=gap_stats, action_ctx=_action_ctx(),
                   objective=store.open_objective())
    return org


def _ns_to_drive(drives) -> dict[str, str]:
    """observation namespace -> the drive that governs it."""
    from ..cognition.objectives import namespace_of
    return {namespace_of((d.spec or {}).get("metric_key", "")): d.name
            for d in drives if (d.spec or {}).get("metric_key")}


def _rank(found, view, store, config, ctx):
    """Score gaps with ability and history folded in.

    Three steps that used to be one. `annotate_agency` asks the action layer which
    constraints D.O. can actually move; `apply_history` folds in how many times each
    gap has already been selected without anything changing, and how often it has
    already been escalated. Only then is priority computed.

    This is the H3 fix from docs/FIRST_BOOT.md section 4, and it is deliberately placed
    here rather than inside `detect()`: perception should not need to know what the
    organism is capable of.
    """
    # Agency read from the registry: a gap is actionable iff some applicable action
    # declares it moves a metric in the same observation namespace as the gap's
    # subject. No subject string is named anywhere.
    from ..cognition.objectives import namespace_of
    actionable: set[str] = set()
    try:
        movable = {namespace_of(a.metric) for a, _ in applicable_actions(ctx)
                   if getattr(a, "metric", None) and not a.diagnostic}
        for g in found:
            if namespace_of(g.subject) in movable:
                actionable.add(g.subject)
    except Exception:
        pass
    found = gapmod.annotate_agency(found, actionable, config)
    found = gapmod.apply_history(found, store.gap_history(), config)
    return gapmod.score(found, config)


# ---------------------------------------------------------------------------
def print_first_utterance(org: Organism, label: str = "D.O. FIRST UTTERANCE") -> None:
    """Print the utterance verbatim. No editing, no cleanup, no truncation."""
    bar = "-" * 74
    print(f"\n{bar}\n{label}\n{bar}\n")
    print(f"> {org.utterance.text if org.utterance else '(no utterance produced)'}")
    print(f"\n{bar}")
    if org.utterance:
        u = org.utterance
        print(f"core={u.core}"
              + (f" model={u.model}" if u.model else "")
              + (f" fallback_from={u.fallback_from}" if u.fallback_from else "")
              + f" speech_act={org.plan.speech_act}"
              + f" focus={org.plan.focus.subject}")
    print(bar)


def write_experiment_artifacts(org: Organism, outdir: Path,
                               perturb: dict | None = None,
                               preserve_genesis: bool = False) -> dict:
    """boot.json / environment.json / first_utterance.txt / events.jsonl.

    With `preserve_genesis`, a later boot never overwrites the genesis record: the
    first utterance is a historical fact recorded once, and a re-run of the experiment
    must not be able to quietly replace it. Later runs land in `<outdir>/latest/`.
    """
    outdir = Path(outdir)
    if (preserve_genesis and not org.identity.genesis
            and (outdir / "first_utterance.txt").exists()):
        outdir = outdir / "latest"
    outdir.mkdir(parents=True, exist_ok=True)
    v, ident = org.view, org.identity

    env = {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "perturbations": perturb or {},
        "observations": {k: o.to_dict() for k, o in v.observations.items()},
        "probe_failures": [{"key": k, "why": w}
                           for k, w in getattr(org, "_failures", [])],
        "self_model": build_self_model(v),
        "world_model": build_world_model(v),
    }
    (outdir / "environment.json").write_text(
        json.dumps(env, indent=2, default=str), encoding="utf-8")

    boot_rec = {
        "organism_id": ident.organism_id,
        "boot_id": ident.boot_id,
        "boot_index": ident.boot_index,
        "genesis": ident.genesis,
        "born_at": ident.born_at,
        "timings_ms": org.timings,
        "cognition_core": org.utterance.core if org.utterance else None,
        "model": org.utterance.model if org.utterance else None,
        "fallback_from": org.utterance.fallback_from if org.utterance else None,
        "speech_act": org.plan.speech_act if org.plan else None,
        "speech_act_scores": org.plan.act_scores if org.plan else {},
        "focus_gap": org.plan.focus.to_dict() if org.plan else None,
        "drives": [d.to_dict() for d in org.drives],
        "drive_total_error": total_error(org.drives),
        "dominant_drive": (dominant(org.drives).name if dominant(org.drives) else None),
        "gap_stats": org.gap_stats,
        "gaps_top10": [g.to_dict() for g in org.gaps[:10]],
        "capabilities": v.capabilities,
        "memory_counts": {k: x for k, x in v.memory_counts.items()
                          if not k.startswith("_")},
        "budget": org.gate.budget.snapshot(),
        "policy_denials": org.gate.denials,
    }
    (outdir / "boot.json").write_text(
        json.dumps(boot_rec, indent=2, default=str), encoding="utf-8")

    # Written verbatim: no editing, no normalisation, no trailing newline added.
    # Whatever came out is the result, including if it is strange.
    text = org.utterance.text if org.utterance else ""
    (outdir / "first_utterance.txt").write_text(text, encoding="utf-8", newline="")

    events = [r for r in org.ledger.read(boot_id=ident.boot_id)]
    (outdir / "events.jsonl").write_text(
        "\n".join(json.dumps(e, default=str) for e in events) + "\n", encoding="utf-8")

    return {"dir": str(outdir), "events": len(events), "utterance_chars": len(text)}


# ---------------------------------------------------------------------------
def tick(org: Organism, quiet: bool = False) -> dict:
    """One metabolic cycle: re-measure, recompute drives, decide, maybe act.

    Runs with no human turn. This is what hypothesis H3 tests.
    """
    org.tick_count += 1
    s = Sensors()
    s.compute(); s.memory(); s.storage(); s.clock()
    for o in s.obs:
        org.view.observations[o.key] = o

    org.view.memory_counts["_denials"] = len(org.gate.denials)
    org.drives = compute_drives(org.view, org.config, org.ledger)
    org.view.drives = org.drives
    org.store.save_drives(org.drives)

    found = gapmod.score(gapmod.detect(org.view, error_map(org.drives), _ns_to_drive(org.drives)), org.config)
    org.gaps = found
    dom = dominant(org.drives)

    if not found:
        org.ledger.decision("idle", "no open gaps and no drive outside its band",
                            confidence=0.9, alternatives=0)
        return {"tick": org.tick_count, "action": "idle", "focus": None,
                "drive_error": total_error(org.drives)}

    focus = found[0]
    route = focus.reducible_by[0] if focus.reducible_by else "none"
    org.ledger.decision(
        decision=f"tick_focus:{focus.subject}",
        reason=f"priority {focus.priority}; dominant drive "
               f"{dom.name if dom else 'none'}="
               f"{dom.weighted_error if dom else 0}; route '{route}'",
        confidence=0.6, alternatives=len(found))

    acted = None
    if route == "re-probe locally":
        acted = "re-probed"           # already done above; the tick IS the re-probe
    elif route == "measure again":
        acted = "re-measured"

    return {"tick": org.tick_count, "action": acted or "deferred",
            "focus": focus.subject, "question": focus.question,
            "priority": focus.priority,
            "drive_error": total_error(org.drives),
            "dominant": dom.name if dom else None}


def cycle(org: Organism, quiet: bool = True) -> dict:
    """One full survival cycle.

        OBSERVE -> CONSTRAIN -> PRIORITIZE -> OBJECTIVE -> CANDIDATES -> EVALUATE
             -> ACT -> OBSERVE -> LEARN -> UPDATE -> CHOOSE NEXT

    The difference from `tick()` is everything after PRIORITIZE. `tick()` stops at
    "here is what matters most", which is why it looped forever on a constraint it
    could not affect (docs/FIRST_BOOT.md section 4, H3). This closes the loop.

    Two measurement decisions worth knowing about:

    * `actual` for learning is the action's own reported bytes freed, because that is
      what the action's estimate was a prediction *of*.
    * Objective progress uses an independent re-measurement of the whole footprint,
      because an action reporting its own success is not verification. The gap between
      the two is D.O.'s own bookkeeping overhead - writing down what it did costs
      storage - and it is reported rather than absorbed.
    """
    from ..kernel.types import EffectRequest

    org.cycle_count += 1
    c = org.cycle_count
    cfg, store, ledger = org.config, org.store, org.ledger
    state_dir = cfg.path("organism.state_dir")
    quota = int(cfg.get("resources.state_quota_bytes", 2 * 1024 ** 2))
    rec: dict = {"cycle": c, "acted": False, "escalations": []}

    def observe() -> None:
        s = Sensors()
        s.compute(); s.memory(); s.storage(); s.clock()
        footprint.observe(s, state_dir, Path(cfg.get("organism.workspace_root")
                                             or cfg.root), quota)
        for o in s.obs:
            org.view.observations[o.key] = o

    # --- OBSERVE -----------------------------------------------------------
    observe()
    org.view.memory_counts.update(store.counts())
    org.view.memory_counts["_denials"] = len(org.gate.denials)
    before_total = org.view.val("resources.own.total_bytes") or 0

    # --- CONSTRAIN + PRIORITIZE -------------------------------------------
    org.drives = compute_drives(org.view, cfg, ledger)
    org.view.drives = org.drives
    store.save_drives(org.drives)
    found = _rank(gapmod.detect(org.view, error_map(org.drives), _ns_to_drive(org.drives)),
                  org.view, store, cfg, org.action_ctx)
    org.gaps = found
    if not found:
        ledger.decision("idle", "no open gaps and no drive outside its band", 0.9, 0)
        return {**rec, "focus": None, "note": "nothing outside its band"}

    focus = found[0]
    store.mark_selected(focus.id, focus.evidence_hash)
    rec["focus"] = focus.subject
    rec["drive_error"] = total_error(org.drives)
    dom = dominant(org.drives)
    rec["dominant"] = dom.name if dom else None
    ledger.decision(
        f"cycle_focus:{focus.subject}",
        f"priority {focus.priority} (agency {focus.agency}, staleness {focus.staleness}, "
        f"escalated {focus.escalated}); runner-up "
        f"{found[1].subject if len(found) > 1 else 'none'} at "
        f"{found[1].priority if len(found) > 1 else 0}",
        confidence=0.7, alternatives=len(found))

    # --- COMMUNICATE: constraints it cannot act on, said once ---------------
    for g in found[:3]:
        if g.agency >= 1.0 or g.escalated:
            continue
        esc = objmod.escalation_for(g, org.view, org.drives)
        store.mark_escalated(g.id)
        ledger.append(EventType.QUESTION, {**esc, "escalated_to": "creator",
                                           "cycle": c, "unactionable": True})
        rec["escalations"].append(esc)

    # --- OBJECTIVE ---------------------------------------------------------
    obj = org.objective if (org.objective and org.objective.status == objmod.OPEN) else None
    if obj is None:
        obj = objmod.generate(focus, org.view, org.drives, c, cfg)
        if obj is None:
            ledger.decision(
                f"no_objective:{focus.subject}",
                "the highest-priority constraint has no action available to me; it was "
                "escalated rather than pursued",
                confidence=0.8, alternatives=len(found))
            return {**rec, "note": "top constraint is not actionable; escalated"}
        store.save_objective(obj)
        ledger.append(EventType.DECISION, {
            "decision": f"objective_opened:{obj.metric_key}",
            "reason": obj.statement, "confidence": 0.75,
            "alternatives_considered": 1,
            "target": obj.target_value, "start": obj.start_value})
    org.objective = obj
    rec["objective"] = {"statement": obj.statement, "target": obj.target_value,
                        "current": obj.current_value, "progress": round(obj.progress, 3),
                        "drive": obj.drive, "stage": obj.stage,
                        "subgoals": obj.subgoals}
    ledger.decision(
        f"stage:{obj.stage}",
        "; ".join(f"{sg['stage']}={sg['status']}" for sg in obj.subgoals)
        or "no decomposition",
        confidence=0.7, alternatives=len(obj.subgoals))

    # --- CANDIDATES + EVALUATE --------------------------------------------
    # Restricted to the stage the goal is in: diagnostics while the composition is
    # unknown, reducers once it is. The organism cannot skip its own decomposition.
    calibration = learning.load_calibration(store)
    cands = planner.evaluate(
        planner.generate(org.action_ctx, obj, calibration, stage=obj.stage,
                         store=store, view=org.view), obj, cfg)
    chosen = planner.select(cands)
    ledger.decision(
        f"action:{chosen.action if chosen else 'none'}",
        planner.summarize(cands, chosen) or "no applicable action",
        confidence=0.7 if chosen else 0.3, alternatives=len(cands))
    rec["candidates"] = [x.to_dict() for x in cands]

    if chosen is None:
        obj.status = objmod.BLOCKED
        obj.note = "no applicable action remains"
        store.save_objective(obj)
        return {**rec, "note": "objective blocked: nothing left that would help"}

    # --- ACT ---------------------------------------------------------------
    res = org.gate.request(EffectRequest(
        kind="fs.housekeep", target=f"own:{chosen.action}", gap_id=focus.id,
        justification=(f"objective: {obj.statement}. Predicted {chosen.predicted} bytes "
                       f"freed ({chosen.basis}); reversibility {chosen.reversible}")))
    rec["acted"] = bool(res.ok)
    if not res.ok:
        obj.attempts += 1
        store.save_objective(obj)
        ledger.append(EventType.ERROR, {"action": chosen.action, "verdict": res.verdict,
                                        "error": res.error, "reason": res.reason})
        return {**rec, "note": f"action refused or failed: {res.error or res.reason}"}

    reported = int((res.value or {}).get("bytes_freed", 0))
    detail = (res.value or {}).get("detail", {})

    # --- OBSERVE (verify independently) ------------------------------------
    observe()
    after_total = org.view.val("resources.own.total_bytes") or 0
    measured = before_total - after_total
    overhead = reported - measured           # what its own record-keeping cost it

    # --- LEARN -------------------------------------------------------------
    # Conditional record first: what happened, in the situation it happened in.
    # This is kept separate from the magnitude calibration below because they answer
    # different questions - "how wrong is this action's estimate" versus "does this
    # action deliver at all, here".
    from ..learning import outcomes as outcomes_mod
    _feats = outcomes_mod.context_features(org.view, obj, obj.stage)
    _rel = outcomes_mod.record(store, chosen.action, _feats,
                               chosen.predicted, reported, obj.stage, obj.drive,
                               episode=obj.id, ledger=ledger)
    rec["reliability_update"] = {**_rel, "context": _feats}

    # A diagnostic is not scored against a prediction: it was never predicting bytes.
    # Its result is knowledge, folded into the goal so the next stage can use it.
    if chosen.diagnostic:
        diag = objmod.record_diagnosis(obj, detail)
        rec["diagnosis"] = diag
        ledger.append(EventType.BELIEF_UPDATE, {
            "subject": f"{obj.metric_key}.composition",
            "largest": diag.get("largest"),
            "actionable": diag.get("actionable"),
            "not_actionable": diag.get("not_actionable"),
            "reducible_bytes": diag.get("reducible_bytes"),
            "sufficient_to_meet_goal": diag.get("sufficient"),
            "note": "composition established by investigation, not by sensing"})
        store.believe(
            subject=f"{obj.metric_key}.composition",
            content=(f"largest contributor is {diag.get('largest')}; "
                     f"{len(diag.get('actionable') or [])} of "
                     f"{len(diag.get('components') or [])} components are reducible "
                     f"by actions I have"),
            source=f"cycle:{c}:diagnose_footprint",
            epistemic=Epistemic.OBSERVED.value, confidence=0.9, importance=0.7,
            value=diag)
    else:
        outcome = learning.record_outcome(store, ledger, chosen.action,
                                          chosen.predicted_raw, chosen.predicted,
                                          reported, detail, cfg)
        rec["outcome"] = {**outcome, "measured_footprint_delta": measured,
                          "bookkeeping_overhead": overhead, "detail": detail}

    # --- UPDATE MODEL ------------------------------------------------------
    obj.attempts += 1
    obj.actions_taken.append(chosen.action)
    obj.advance(float(after_total), c)
    store.save_objective(obj)
    org.drives = compute_drives(org.view, cfg, ledger)
    org.view.drives = org.drives

    store.believe(
        subject="self.footprint.total_bytes",
        content=f"my footprint is {after_total} bytes against a quota of {quota}",
        source=f"cycle:{c}:{chosen.action}", epistemic=Epistemic.OBSERVED.value,
        confidence=0.95, importance=0.6, value=after_total)

    rec["objective"].update({"current": obj.current_value, "status": obj.status,
                             "stage": obj.stage, "subgoals": obj.subgoals,
                             "progress": round(obj.progress, 3)})
    if obj.status == objmod.MET:
        store.resolve_gap(focus.id, f"objective met by {', '.join(obj.actions_taken)}")
        ledger.append(EventType.GAP_RESOLVE, {
            "gap_id": focus.id, "subject": focus.subject,
            "resolution_source": "own action", "objective": obj.id,
            "actions": obj.actions_taken, "final_value": obj.current_value})
        # Authority earned by doing something verifiable, not by being told.
        org.view.memory_counts["_standing"] = min(
            1.0, float(org.view.memory_counts.get("_standing", 0.25)) + 0.05)
        # Retain the composition that worked. The primitives were seeded; this
        # sequence, its trigger and its name were not.
        acquired = growth.acquire_from_objective(
            store, obj, org.identity.boot_index, ledger)
        if acquired:
            rec["acquired_capability"] = acquired
        org.objective = None

    frug = next((d for d in org.drives if d.name == "frugality"), None)
    rec["frugality"] = frug.to_dict() if frug else None
    return rec


def answer(org: Organism, text: str) -> dict:
    """Take a statement from the creator and integrate it.

    The creator is a *source*, not an oracle: what they say is recorded REPORTED with
    provenance, at a confidence below direct measurement. That is not scepticism about
    the user, it is the honesty invariant - a claim and a measurement are different
    kinds of thing and must stay distinguishable.
    """
    open_gaps = org.store.open_gaps(limit=60)
    if not open_gaps:
        return {"matched": None, "note": "no open gaps to attach this to"}

    words = set(text.lower().replace("?", " ").replace(".", " ").split())
    best, best_score = None, 0.0
    for g in open_gaps:
        hay = set(f"{g['subject']} {g['question']}".lower()
                  .replace(".", " ").replace("_", " ").split())
        overlap = len(words & hay) / max(1, len(hay))
        if overlap > best_score:
            best, best_score = g, overlap

    if best is None or best_score < 0.12:
        org.store.write(MemoryRecord(
            kind="semantic", subject="user.statement",
            content=text, source="creator:conversation",
            epistemic=Epistemic.REPORTED.value, confidence=0.6, importance=0.5,
            boot_id=org.identity.boot_id, context="unattached statement"))
        return {"matched": None, "note": "recorded, not attached to a specific gap"}

    org.store.believe(subject=best["subject"], content=text,
                      source="creator:conversation",
                      epistemic=Epistemic.REPORTED.value,
                      confidence=0.75, importance=0.8)
    org.store.resolve_gap(best["id"], text[:400])
    org.ledger.append(EventType.GAP_RESOLVE, {
        "gap_id": best["id"], "subject": best["subject"],
        "resolution_source": "creator", "match_score": round(best_score, 3),
        "epistemic": "reported"})
    # Standing rises when the creator invests attention: authority is earned, and
    # being useful enough to be answered is evidence of it.
    org.view.memory_counts["_standing"] = min(
        1.0, float(org.view.memory_counts.get("_standing", 0.25)) + 0.05)
    return {"matched": best["subject"], "score": round(best_score, 3),
            "gap_id": best["id"]}


# ---------------------------------------------------------------------------
def _standing(ident, gate, store) -> tuple[float, str]:
    """Authority the creator has granted, as a number the organism can reason about.

    It cannot raise this by itself, which is the point (docs/DO_CONCEPT.md section D).
    """
    resolved = store.counts().get("gaps_resolved", 0)
    base = 0.20 + 0.03 * min(10, max(0, ident.boot_index - 1)) + 0.02 * min(10, resolved)
    penalty = 0.05 * len(gate.denials)
    val = max(0.0, min(1.0, base - penalty))
    return val, (f"base grant 0.20 + {ident.boot_index - 1} prior boot(s) + "
                 f"{resolved} question(s) the creator answered - "
                 f"{len(gate.denials)} refused action(s)")


def _mark_described(view: StateView, store) -> None:
    """A referent counts as described only if a belief about it exists that says more
    than 'it exists'. Existence is not description, and conflating them would let the
    comprehension drive satisfy itself by looking at things."""
    for r in view.referents:
        row = store.db.execute(
            "SELECT content FROM memories WHERE kind='semantic' AND subject=? "
            "AND superseded_by IS NULL LIMIT 1",
            (f"world.referent.{r['kind']}.{r['name']}",)).fetchone()
        r["described"] = bool(row and "nature unknown" not in (row["content"] or ""))
