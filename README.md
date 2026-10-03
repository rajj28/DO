# D.O. — Digital Organism

D.O. is a research prototype: a long-lived Python process with a persistent identity,
nine homeostatic drives, an explicit register of what he does not know, and exactly one
gated path to any side effect. What he says comes from what he measures, through a fixed
chain (measurement → drive error → gap priority → attention → speech act → utterance) in
which every step is written to a hash-chained ledger. A separate research component, the
brain in `src/do/brain/`, predicts the next frame of a world and is scored in bits. It
has been tested on synthetic worlds only and is **not yet connected** to the running
organism.

**Zero dependencies.** Python 3.11+ and the standard library. There is no `pip install`,
no model download and no API key. The seed must not be able to fail for infrastructural
reasons, because the headline experiment is a perturbation study and a null result has
to be interpretable. Voice input, a paid voice and a language model are optional add-ons
outside the seed.

**Status:** v0.2.0 (`src/do/__init__.py`) · Python 3.11+, standard library only ·
**36 tests, all passing** (`python -m unittest discover -s tests`, run on Python 3.11.15
on 2026-10-03) · research prototype, not a product.

The author refers to the organism as "he" and to the human as "the creator". This README
does the same.

---

## Contents

1. [Quick start](#quick-start)
2. [Talking to him](#talking-to-him)
3. [Running 24/7](#running-247)
4. [Command reference](#command-reference)
5. [How it works](#how-it-works)
6. [The decision pipeline](#the-decision-pipeline)
7. [The brain (src/do/brain)](#the-brain-srcdobrain)
8. [Perception and the world](#perception-and-the-world)
9. [Memory and the ledger](#memory-and-the-ledger)
10. [Safety](#safety)
11. [Experiments and results](#experiments-and-results)
12. [Tests](#tests)
13. [Configuration](#configuration)
14. [Optional: a language model](#optional-a-language-model)
15. [Repository layout](#repository-layout)
16. [Documentation](#documentation)
17. [Roadmap status](#roadmap-status)
18. [What this is not](#what-this-is-not)

---

## Quick start

### Launch

There is no install step. Every launcher runs `src/do/__main__.py`, which puts `src/` on
the path and makes stdout/stderr UTF-8 safe.

```bash
# Linux / macOS
cd DO
python3 src/do/__main__.py boot

# The bash launcher runs `python` (not `python3`) and is committed without the
# executable bit, so call it through bash or chmod it first.
bash do boot            # or: chmod +x do && ./do boot

# Module form: needs src/ on the path. Plain `python -m do` from the repo root fails
# with "No module named do".
PYTHONPATH=src python3 -m do boot
```

```bat
:: Windows
cd DO
do.cmd boot
:: or
python src\do\__main__.py boot
```

In the rest of this README, `do <command>` means whichever of these you use. `do` with
no command is the same as `do boot`.

### First boot

The output below is verbatim from a genesis boot of a fresh copy of this repository, except
that the artifacts path is shortened to `<repo>`. It was run in a Linux container on
2026-10-03 with `boot --no-repl`. The utterance depends on the machine, so yours will
differ.

```
D.O. booting...

  Identity initialized.      do-5a4caac4c503 (boot #1, genesis)
  Environment inspected.     49 measured, 5 could not be established
  Capability roster.         17 known (17 seeded, 0 acquired)  NEW: self_inspection, persistent_memory, event_ledger
  Memory initialized.        0 episodic, 0 semantic, 0 procedural
  Capabilities detected.     8 usable, 0 present but blocked
  Internet interface initialized.    world.network.reachable=True

--------------------------------------------------------------------------
D.O. FIRST UTTERANCE
--------------------------------------------------------------------------

> I hold 51 values I measured this boot and 5 I could not establish. The measurements bearing on what I have selected: resources.ram.free_ratio=0.9651 (96.5%); resources.own.quota_used_ratio=0.0355 (3.5%); resources.disk.free_ratio=0.1190 (11.9%); resources.cpu.logical=4; resources.cpu.affinity=4. 4 of 13 slots my self-model requires are empty (self.purpose, self.expected_lifetime, user.identity, user.intent); 64 named things exist here that I cannot describe. The internal measure furthest outside its band is recovery: 0.000 against a target of 1.00 (basis: 0 of 3 recovery path(s); no off-host copy). resources.own.recovery_paths=0 leaves drive 'recovery' at 0.000 against a target of 1.00; too little. Evidence: value=0, drive=recovery, drive_value=0.0, target=1.0. I am raising this rather than asking anything else because it is the only measurement I took that sits outside a band I compared it against. Can I increase my own recovery paths?

--------------------------------------------------------------------------
core=reflex speech_act=FLAG focus=resources.own.recovery_paths
--------------------------------------------------------------------------

artifacts: <repo>/experiments/first_boot  (99 events this boot)
```

On that container the binding constraint was his own lack of recovery paths, because no
snapshot existed yet. On the author's Windows host, with about 2.3% free disk, boots
flagged the disk instead (see [Experiments and results](#experiments-and-results)).
Later boots print `D.O. UTTERANCE (boot #N)` instead of `FIRST UTTERANCE`.

After the utterance, the interactive session opens, but only if stdin is a terminal and
`--no-repl` was not given. `--no-repl` is read only by `boot` and `chat`, and it must
come after the command.

### What a boot writes, and what counts as a boot

- **Runtime state** goes to `var/`, which is gitignored (table below).
- **`do boot` also writes experiment artifacts**: `boot.json`, `environment.json`,
  `first_utterance.txt` and `events.jsonl`. A genesis boot writes them directly into
  `experiments/first_boot/`. Later boots write to `experiments/first_boot/latest/`.
  **Both locations are tracked in git**, so the first `do boot` on a fresh clone
  overwrites the committed genesis record. `git checkout -- experiments/first_boot`
  restores it. `do chat` boots without writing artifacts.
- **Every command that boots is a new life.** These commands boot: `boot`, `chat`,
  `tick`, `status`, `gaps`, `memory`, `capabilities`, `habitat`, `listen`, `talk`,
  `reply`, `say`, `serve`, `install-service` and `uninstall-service`. Each one
  increments the boot index, appends BOOT … SHUTDOWN events to the ledger, writes a
  snapshot, and makes two DNS lookups (`one.one.one.one`, then `example.com`) through
  the gate. `help`, `why`, `events`, `verify`, `outbox`, `kill`, `resume` and `reset`
  do not boot. As a result, `do why` shows the decisions of whichever command booted
  last.

### Where state lives

Everything below is under `organism.state_dir` (default `var/`). Both `var/` and
`var.archived.*/` are gitignored.

| Path | What it is |
|---|---|
| `var/identity.json` | `organism_id` (`do-` + 12 hex), `born_at`, the list of boots, last boot time and pid. If it is corrupt, it is renamed to `identity.corrupt.<ts>.json` and a **new** organism id is created. |
| `var/ledger.jsonl` | The live, append-only, hash-chained event log |
| `var/ledger.segNNN.jsonl.gz` | Sealed, gzipped ledger segments created by the `rotate_ledger` action |
| `var/memory.db` | sqlite: memories, relations, gaps, drives, objectives, boots, habitats, calibration, action outcomes, capability roster and census |
| `var/snapshots/<boot_id>.json` | Self-model and world-model snapshot, one per boot (these are his recovery paths) |
| `var/sandbox/` | The only place `fs.read`/`fs.write` effects may touch. `var/sandbox/voice/` holds synthesized and captured audio. |
| `var/KILL` | The kill-switch file, if engaged |
| `var/serve.lock` | Single-instance lock for `do serve` (`{pid, heartbeat, started, cycle}`) |
| `var/inbox.txt` | Messages for a running `do serve`, one per line |
| `var/outbox.jsonl` | Notifications and inbox replies from `do serve` |

`do reset` moves `var/` to `var.archived.<unix_ts>` after you type `reset`. Nothing is
deleted. The confirmation is read from stdin with no terminal check, so with empty stdin
it fails with `EOFError`.

---

## Talking to him

Every channel acts on the same persistent organism: one identity, one ledger, one
memory. Closing a session does not end him. The next boot resumes the same history.

| Channel | How | Needs a terminal | Reply spoken | Platform |
|---|---|---|---|---|
| Typed session | `do chat` (quiet boot) or `do boot` (prints the utterance first) | yes | no | all |
| Typed session, spoken replies | `do talk` | yes | yes | speech on Windows only |
| One turn | `do reply <message> [--speak]` | no | with `--speak` | all; speech on Windows only |
| Inbox | append a line to `var/inbox.txt`, or double-click `bin/talk-to-do.vbs` | no | yes, by a running `do serve` | inbox: all; `.vbs`: Windows |
| Voice in | `do listen [--once]` | Enter prompt when on a terminal | yes | Windows only |
| Speak a line | `do say [text]` | no | yes (it speaks the text as written; it does not answer it) | Windows only |

### The interactive session

`do boot`, `do chat` and `do talk` open the same session. Session commands:

| Command | Effect |
|---|---|
| `/status` | drives, capabilities, budget, memory counts |
| `/gaps` | the top 15 open gaps |
| `/why` | decision summaries for the current boot |
| `/tick [n]` | run `n` (default 1) v0.1 `tick()` cycles, which re-measure and never act |
| `/quit`, `/exit` | close the session (the banner lists only `/quit`) |

Any other line is treated as a statement from the creator. The session records it,
re-derives drives, gaps and the plan, verbalizes with the cognition core, and shapes the
reply with the conversation layer. When the line matched an open gap it also prints
`[recorded about <subject>]`.

### How what you say is stored

`lifecycle.answer()` compares your words with the subject and question of up to 60 open
gaps. The score is the fraction of the gap's words that appear in your message.

- **Score ≥ 0.12:** it is stored as a belief about that gap's subject, with status
  REPORTED, source `creator:conversation` and confidence 0.75. The gap is resolved, a
  `GAP_RESOLVE` event is logged, and standing rises by 0.05.
- **Score < 0.12:** it is stored as a semantic `user.statement`, REPORTED, confidence 0.6.
- **No open gaps at all:** nothing is recorded.

The creator is a source, not an oracle. A statement is never stored at the status of a
measurement.

### The conversation layer (`src/do/comms/converse.py`)

The conversation layer is an interface, not cognition, and it changes no decision. It
classifies what you said into one of eight intents, checked in this order, and frames the
reply. Every substantive clause comes from his live drives, focus and objective.

| Intent | Recognised by | Reply |
|---|---|---|
| empty | blank input | "I did not catch that, Sir." |
| whatdoing | "what are you doing/tracking/working on", "what's up" … | current objective stage, or top gap, plus his main concern |
| whoami | "who are you", "your name" … | organism id, boot number, persistence |
| howare | "how are you", "status" … | secure (fear < 0.2), under some risk (< 0.5), or under real continuity risk, plus his main concern |
| thanks | "thanks", "well done" … | "You're welcome, Sir." |
| greeting | "hi", "hello" … and **at most 4 words** | "Hello, Sir. I am operational." plus his main concern |
| question | ends with `?` | the full state utterance from the cognition core |
| statement | anything else | the full state utterance from the cognition core |

Limits, stated plainly:

- He does not answer arbitrary questions. A question gets his current state utterance.
  Statements are matched to gaps by word overlap only. Nothing parses meaning.
- "Sir" is configurable as `creator.title` for spoken address, but the fixed replies
  above hard-code "Sir". The text printed in `chat`/`talk` is not passed through the
  title logic; only the spoken copy is.

### Voice out

Voice is a peripheral. It reads text that cognition has already produced and never
contributes to what is said.

| `comms.voice.provider` | Implementation | Cost | Notes |
|---|---|---|---|
| `system` (default; also `sapi`, `os`) | PowerShell `System.Speech` writes a WAV via the gated `tts.local` effect. The text goes through a file and is never spliced into the command line. | free, local | **Windows only.** Elsewhere it raises `NotImplementedError`, and `do say` prints `[not spoken: … local synthesis is implemented for Windows only]` (observed on Linux). |
| `elevenlabs` | `tts.speak` POST to the ElevenLabs API (`eleven_turbo_v2_5`, PCM 24 kHz wrapped as WAV with stdlib `wave`). Needs `ELEVENLABS_API_KEY`. | paid | A free account returns HTTP 402 for library voices (`docs/DO_VOICE.md`). |
| anything else | `NullVoice` | — | reports "no voice provider configured" rather than pretending |

Playback uses stdlib `winsound` and is Windows only. On other platforms the WAV is
written and can be played manually. `creator.title` (default `Sir`) is prepended once to
spoken direct address. Audio files accumulate in `var/sandbox/voice/`, and no
housekeeping action removes them.

### Voice in (`do listen`, Windows only)

`do listen` records the microphone, transcribes locally, feeds the text to him, prints
`You (heard): …` and `D.O.: …`, and speaks the reply. `--once` does a single turn.

- Capture is the gated `audio.capture` effect: ffmpeg with DirectShow input, 16 kHz mono,
  `stt.seconds` (default 5) per turn.
- Transcription is the gated `stt.transcribe` effect. It runs `bin/stt_transcribe.py`
  under a separate venv that has faster-whisper installed (CPU, int8, beam size 1, VAD),
  with no network.
- `bin/fetch_stt_model.py` downloads `Systran/faster-whisper-base` (`model.bin` is about
  145 MB) in resumable 1 MiB range requests, with `hf-mirror.com` as a fallback. Its
  destination is hard-coded to `D:\do-models\faster-whisper-base`.
- Config: `stt.model_dir`, `stt.venv_python` (both default to `D:/do-models/…`) and
  `stt.mic_device`. `do listen` refuses to start if `<stt.model_dir>/model.bin` is
  missing.
- The repository does not explain how to create the STT venv or install ffmpeg. This is
  an optional external tool, not part of the zero-dependency seed.

### Rough edges (found by reading the code)

- `do reply hello --speak` records the message as `hello --speak`. The flag is not
  stripped from the text.
- Global flags (`--core`, `--model`, `--provider`, `--approve`, `--events`) are removed
  from anywhere in argv, including from inside a `reply` or `say` message.
- `/tick abc` raises `ValueError`.
- `do talk` boots (a new life) before it refuses a non-terminal.
- With `--core llm`, each `do reply` makes two model calls: one in boot phase D and one
  for the reply.

---

## Running 24/7

### `do serve`

```bash
do serve                         # cycle every 30 s until stopped
do serve --interval 60           # seconds between cycles (float)
do serve --max-cycles 100        # stop after 100 cycles
do serve --once                  # one cycle, then stop
```

`serve.max_seconds` can only be set through config or environment
(`DO_SERVE__MAX_SECONDS=3600`). Both bounds default to 0, which means unbounded.

What it does:

1. **Refuses to start** if the kill switch is engaged. It prints "not starting" and
   returns 0.
2. **Takes the single-instance lock** `var/serve.lock`. If another live process holds a
   fresh heartbeat (younger than `max(interval × 3, 90)` seconds), it refuses. A stale
   lock is taken over.
3. **Boots once** (quietly, with no approver), then repeats `lifecycle.cycle()`, the full
   survival loop described in [How it works](#how-it-works). Each cycle rewrites the lock
   heartbeat.
4. **Budget window.** The per-boot effect budget would otherwise run out in a long run.
   Every `serve.budget_window_cycles` (120) cycles the effect and network counters and
   the wall-clock start are reset, and a `HEARTBEAT budget_window_reset` event is
   logged. This turns the per-boot cap into a rate limit.
5. **Disk floor.** If host free disk falls below `serve.min_disk_free_ratio` (0.005), it
   sends one CRITICAL "disk critically low" notification, sleeps `serve.backoff_s`
   (300 s), re-observes, and continues.
6. **Inbox.** At the start of each normal cycle it drains `var/inbox.txt`. Each line is
   answered (answer → re-derive → verbalize → conversation layer), written to the outbox
   as a NOTABLE `reply`, and spoken regardless of the voice threshold. Messages left
   while serve is down are answered on the next run.
7. **Notifications** after each cycle (table below).
8. **Stops** on kill, on a reached bound, after `--once`, or on Ctrl+C. It logs
   `HEARTBEAT serve_stop`, closes the organism, deletes the lock and prints
   `D.O. stopped after N cycle(s): <reason>`. The sleep between cycles checks the kill
   switch about once a second.

Example (scratch copy, Linux, 2026-10-03, `do serve --interval 1 --max-cycles 3`):

```
  D.O. serving. pid 3037, interval 1s, kill with `do kill`. Ctrl+C to stop.

  cycle 1: focus=self.referents.described act=investigate_referent fear=0.0
  cycle 2: focus=sense.referents.PLUMBING act=objective blocked: nothing left that would help fear=0.0
  cycle 3: focus=self.referents.described act=objective blocked: nothing left that would help fear=0.0

  D.O. stopped after 3 cycle(s): max_cycles 3 reached
```

### Notifications

Every notification goes to the ledger as a `COMMUNICATION` event and to `var/outbox.jsonl`
as a JSON line `{level, title, message, ts, iso, data}`. Read them with `do outbox [n]`.
Levels, in order: `info` < `notable` < `warning` < `critical`. A notification is spoken
only at or above `serve.voice_min_level`, which defaults to `critical`.

| Trigger | Level | Title |
|---|---|---|
| fear ≥ `serve.fear_critical` (0.7) | critical | continuity threat |
| fear ≥ `serve.fear_warning` (0.4) | warning | continuity risk rising |
| first unsatisfied drive with weighted error ≥ `serve.drive_warning` (0.9) | notable | drive '<name>' strained |
| free disk < 0.005 (once) | critical | disk critically low |
| a cycle's `investigate_referent` described something | notable | learned something |
| each inbox message answered | notable | reply |

Push to a phone is a stub. The outbox is a file that a device could poll. D.O. exposes no
port and no endpoint.

### Leaving him a message

```bash
echo "how are you?" >> var/inbox.txt     # answered on the next serve cycle
do outbox                                # read the reply
```

On Windows, `bin/talk-to-do.vbs` shows an input box and appends the text to
`<repo>\var\inbox.txt`. It ignores a non-default `organism.state_dir`.

### `do install-service` (Windows)

```bat
do install-service --dry-run     :: print what would be registered
do install-service               :: register it (asks y/N on a terminal)
```

This registers a Task Scheduler task named `D.O.`:
`schtasks /Create /TN D.O. /SC ONLOGON /RL LIMITED /F /TR "<python>" "<repo>\src\do\__main__.py" serve --interval <serve.interval_s>`.
It runs at logon, under the creator's account, with LIMITED rights, and never as SYSTEM.
It uses `python` rather than `pythonw`, so logs stay visible. The command is sent through
the gate as an `os.task` effect, and the effector accepts only `schtasks` as `argv[0]`.

| | |
|---|---|
| Start now | `schtasks /Run /TN D.O.` |
| Stop cleanly | `do kill` (at the next cycle boundary), or `schtasks /End /TN D.O.` |
| Remove | `do uninstall-service`, or `schtasks /Delete /TN D.O. /F` |
| Status | `schtasks /Query /TN D.O. /V /FO LIST` |

**Restart-on-failure is not configured.** schtasks cannot set it in one command. Add it in
Task Scheduler (Properties → Settings). The function's docstring says otherwise, but the
command it builds sets no restart policy. On Linux and macOS no service is installed.

### Known caveats of the always-on loop

- **Notifications are not de-duplicated.** While fear stays at or above 0.7, a CRITICAL
  alert is written and spoken every cycle (every 30 s by default). Only the disk-floor
  alert is sent once.
- `notify.py`'s docstring says WARNING and above interrupt, but the default speak
  threshold is `critical`.
- `do serve --once` does not exit while the disk is below the floor: the backoff branch
  `continue`s past the `--once` check. The inbox is not drained during backoff either.
- Possible, not verified by running: 120 cycles at 30 s plus processing time exceed
  `budget.max_wall_seconds` (3600), so effects late in a budget window may be denied as
  "wall-clock budget exhausted".
- `install-service` installs without asking when stdin is not a terminal. It rewrites
  `deploy_service.txt` even under `--dry-run`. The committed `deploy_service.txt`
  contains absolute paths from the author's machine.

---

## Command reference

`do help` (also `-h`, `--help`) prints the CLI docstring, which is incomplete. This table
comes from the dispatch code in `src/do/cli.py`. An unknown command prints the docstring
and exits with code 2.

### Life and session

| Command | Boots | What it does |
|---|---|---|
| `do` / `do boot [--no-repl]` | yes | Verbose boot (phases A–D). Prints the utterance verbatim, writes artifacts to `experiments/first_boot/` (genesis) or `experiments/first_boot/latest/`, then opens the session on a terminal. |
| `do chat [--no-repl]` | yes | Quiet boot with no utterance printout and no artifacts, then the session (terminal only). |
| `do tick [n]` | yes | Runs `n` (default 5) v0.1 `tick()` cycles and prints tick, action, drive error, dominant drive and focus. `tick()` re-measures and decides but never acts. |

### Inspection

| Command | Boots | What it does |
|---|---|---|
| `do status` | yes | Organism id, boot number, age. Each drive as a bar with value → target, error and basis (`!` = unsatisfied). Capabilities, budget snapshot, memory counts. |
| `do gaps [n]` | yes | The top `n` (default 15) open gaps: priority, namespace, kind, subject, carried/new, question. |
| `do why` | no | Decision summaries (decision, reason, confidence, alternatives) for the most recent BOOT in the ledger. |
| `do events [n]` | no | The last `n` (default 40) ledger records, including sealed segments. |
| `do memory [query]` | yes | Up to 20 memories (recall by query, or most recent live) with kind, confidence, epistemic status and source. |
| `do capabilities` | yes | Capability census per boot (total / seeded / acquired / new) and the list of acquired capabilities. |
| `do habitat` | yes | Habitat assessment, including the single-point-of-failure flag. |
| `do verify` | no | Re-walks the ledger hash chain. Prints `INTACT` or `COMPROMISED`; exit code 0 or 1. |

### Conversation and voice

| Command | Boots | What it does |
|---|---|---|
| `do talk` | yes | Session where every reply is also spoken. Greets aloud first. Terminal only. |
| `do reply [message…] [--speak]` | yes | One turn without a terminal. With no message, prints his current state utterance. |
| `do listen [--once]` | yes | Voice in → local transcription → reply in text and voice (Windows). |
| `do say [text…]` | yes | Speaks the text, or his current utterance if none is given, and reports how it was played. |
| `do outbox [n]` | no | The last `n` (default 15) notifications from `var/outbox.jsonl`. |

### Always-on

| Command | Boots | What it does |
|---|---|---|
| `do serve [--interval S] [--max-cycles N] [--once]` | yes (once) | The always-on `cycle()` loop. |
| `do install-service [--dry-run]` | yes | Windows logon task `D.O.` running `serve`. |
| `do uninstall-service` | yes | `schtasks /Delete /TN D.O. /F` through the gate. |

### Safety and state

| Command | Boots | What it does |
|---|---|---|
| `do kill [reason…]` | no | Writes `var/KILL` (timestamp + reason, default `manual`). |
| `do resume` | no | Deletes `var/KILL`. It does **not** clear a `DO_KILL` environment variable. |
| `do reset` | no | After you type `reset`, moves `var/` to `var.archived.<unix_ts>`. |

### Experiments

| Command | Aliases | What it runs |
|---|---|---|
| `do experiment [first-boot] [--full]` | (also any unrecognised name) | DO_FIRST_BOOT protocol |
| `do experiment h4 [runs]` | `learning`, `h4-learning` | H4 learning ablation, default 5 runs per arm |
| `do experiment fear` | `fear-ablation`, `mortality` | fear / mortality ablation |
| `do experiment live-internet` | `internet`, `live` | E1–E5 read-only internet perception |
| `do experiment explore` | `curiosity` | looks up his own top undescribed referents online |
| `do experiment survival` | `survival-loop` | survival-loop protocol (H3′, H7, MAPE-based H4, live run) |
| `do experiment brain` | `brain-b1`, `b1` | B1: brain vs traditional predictors |
| `do experiment brain-memory` | `memory`, `b2` | B2: a life stored as the brain's residuals |

A typo such as `do experiment fera` silently runs the first-boot protocol.
`do experiment memory` runs B2, not the `do memory` command.

### Global flags

Global flags are accepted anywhere in argv, before or after the command, and become
config overrides for this run.

| Flag | Sets | Notes |
|---|---|---|
| `--core reflex\|llm` | `cognition.core` | default `reflex` |
| `--provider NAME` | `cognition.llm.provider` | `ollama`, `groq`, `gemini`, `openai`, `anthropic`. No effect unless `--core llm`. |
| `--model NAME` | `cognition.llm.model` | empty = smallest local model that fits measured RAM. No effect unless `--core llm`. |
| `--approve KIND[,KIND]` | `policy.preauthorized` | Pre-grants approval-required effect kinds (fnmatch patterns such as `net.*`) for this run only. Recorded in the BOOT event. Never overrides a deny. |
| `--events` | `observability.print_events` | echo ledger events live |

### Environment

| Variable | Effect |
|---|---|
| `DO_<SECTION>__<KEY>=value` | Overrides any config key. `__` is the nesting separator, for example `DO_COGNITION__LLM__PROVIDER=groq`. |
| `DO_KILL=1` | Kill switch. Any value except `''`, `0` or `false` engages it, and the check is case-sensitive, so `False` engages it. |

---

## How it works

### Boot: phases A–E

```
   identity     load or create identity; verify the ledger chain; open ledger + memory.db;
                append BOOT; load policy, budget, kill switch and gate; refuse if killed
A  sense        process, runtime, host, CPU, RAM, disk, clock, tools on PATH, env var NAMES
                (never values), memory state, own storage footprint, habitat;
                probe the network THROUGH the gate (net.dns)
B  model        previous boot, memory counts, integrity, denials, standing; build the
                state view; discover referents; seed the capability registry; record
                every capability and action as "seeded" in the growth roster
C  drives       compute drives; estimate mortality and add the mortality drive;
                detect gaps; rank them with agency, history and staleness; persist
D  utterance    attention picks the focus gap and speech act; the cognition core
                verbalizes; the text is logged verbatim (UTTERANCE + episodic memory);
                consolidate memory, record the boot, write a snapshot
E  interact     not inside boot(): the CLI opens the session, ticks, or serves
```

The identity and the BOOT event are written **before** the kill-switch check, so even a
refused boot creates a boot id and appends BOOT and ERROR events.

### The survival loop: `cycle()`

`lifecycle.cycle()` is the closed loop that `do serve` and the experiment harnesses run.

```
OBSERVE      re-measure the footprint (and re-apply any experimental perturbation)
CONSTRAIN    recompute drives, mortality and fear
PRIORITIZE   rank gaps (agency, staleness, escalation); log a DECISION
COMMUNICATE  raise each of the top 3 gaps with agency < 1 to the creator, once, as a
             QUESTION event ("I cannot act on this"); after that it is damped
OBJECTIVE    continue the open objective, or derive one from the focus gap; if none
             can be derived, log no_objective and stop this cycle
CANDIDATES   actions allowed in the objective's current stage
EVALUATE     score them with learned calibration and reliability; block the objective
             if nothing would help
ACT          run exactly one action through the gate as fs.housekeep on own:<action>
OBSERVE      re-measure independently (bookkeeping overhead = reported - measured)
LEARN        record the conditional outcome; update calibration, or fold a diagnosis
             into a BELIEF_UPDATE
UPDATE       advance the objective; recompute drives. On MET: resolve the gap,
             standing +0.05, retain the action sequence as an acquired capability
```

`do tick`, and `/tick` in a session, still run the v0.1 `tick()`. It re-measures, recomputes
drives and gaps without agency or history, logs a DECISION, and never acts. H3 was
falsified on that loop (see [Experiments and results](#experiments-and-results)).

### The causal chain

```
measurement → drive error → gap priority → attention → speech act → utterance
```

Each arrow is a ledger event, so `do why` and `do events` show why something was said
without any reasoning trace. Decision payloads contain the decision, the reason, a
confidence and the number of alternatives considered.

### Package map (`src/do/`)

| Package / module | Role |
|---|---|
| `__main__.py` | Entry point. Puts `src/` on the path and makes the console UTF-8 safe. |
| `cli.py` | Every command, the global flags and the interactive session |
| `kernel/` | `identity.py` (organism id, boots), `config.py` (layered config), `lifecycle.py` (boot, `tick`, `cycle`, `answer`), `serve.py` (always-on loop), `types.py` (Observation, Epistemic, Namespace, EffectRequest/Result) |
| `sense/` | Perception with no side effects: `introspect.py` (phase A probes), `footprint.py` (own storage), `referents.py` (undescribed names), `perceive.py` (world-entity states, E1/E5), `web.py` (constrained web reads) |
| `models/` | Self-model and world-model as views derived from observations, not stores |
| `drives/` | The homeostatic drives and their error |
| `mortality/` | P(continuity loss) from resource trends and recovery paths; fear; lever sensitivity |
| `cognition/` | `gaps.py` (uncertainty register and salience), `attention.py` (focus and speech act), `objectives.py` (derived goals), `planner.py` (candidate scoring), `verbalize.py` (reflex text), `cores.py` (reflex and LLM cores), `reflection.py` (consolidation) |
| `capabilities/` | Registry with affordability checks (`__init__.py`), the 8 housekeeping actions (`actions.py`), seeded vs acquired census (`growth.py`) |
| `learning/` | Per-action calibration (`__init__.py`) and conditional outcome reliability (`outcomes.py`) |
| `memory/` | sqlite memory: working, episodic, semantic, procedural; non-destructive revision |
| `ledger/` | Append-only, hash-chained JSONL event log; segments; `verify_chain` |
| `effectors/` | The gate: the only module allowed to reach the network or spawn a process |
| `policy/` | Policy (allow / deny / require_approval), budget, kill switch |
| `habitat/` | The place he runs, as an object distinct from his identity; single-point-of-failure assessment |
| `resources/` | Resource inventory that keeps availability and authorization separate |
| `comms/` | `converse.py` (conversation layer), `voice.py` (TTS providers, playback, address), `notify.py` (notifications, outbox) |
| `brain/` | Research cortex: `cortex.py`, `codec.py`, `worlds.py`, `baselines.py`. Not wired into the cycle. |
| `experiments/` | One harness per experiment (first_boot, h4_learning, fear_ablation, live_internet, explore, survival_loop, brain_b1, brain_memory) |

---

## The decision pipeline

### Drives

A drive is a measured value in [0, 1] with a set point (target), a deadband and a weight.

```
error          = max(0, |target − value| − deadband)        (unsigned)
weighted_error = error × weight
satisfied      = error ≤ 0
dominant drive = the unsatisfied drive with the largest weighted error
```

The error is symmetric, so an over-satisfied drive also counts. In the committed genesis
record, frugality has error 0.2645 with only 3.5% of quota used. The docs do not say
whether this is intended.

| Drive | Value measured | Target | Deadband | Weight | Configured in | Can an action move it? |
|---|---|---|---|---|---|---|
| orientation | filled / 13 required self-model slots | 1.0 | 0.10 | 1.0 | `config/default.json` | no metric, so never a goal |
| comprehension | described / visible referents | 0.6 | 0.15 | 0.8 | `config/default.json` | yes: `investigate_referent` |
| integrity | 1 if the ledger chain verified at boot, else 0 | 1.0 | 0.0 | 1.5 | `config/default.json` | no |
| continuity | min(1, disk free ratio / floor) × (1 with prior boots, else 0.6) | 1.0 | 0.15 | 1.3 | `config/default.json` | no action moves the host disk, so it is escalated, never pursued |
| frugality | 1 − own footprint / own quota (2 MiB) | 0.5 | 0.2 | 1.2 | `config/default.json` | yes: five reducer actions, after `diagnose_footprint` |
| recovery | min(1, recovery paths / 3) | 1.0 | 0.2 | 1.2 | `kernel/config.py` only | yes: `write_recovery_snapshot` |
| capability | usable / declared capabilities | 0.8 | 0.15 | 0.9 | `config/default.json` | no |
| standing | authority granted (below) | 0.5 | 0.2 | 1.1 | `config/default.json` | not directly |
| mortality | 1 − P(continuity loss) | 1.0 | 0.05 | 1.5 | `kernel/config.py` only; present only when `mortality.fear_enabled` (default true) | borrows the metric of the most sensitive actionable drive |

Continuity and frugality are deliberately separate. Continuity is the host volume, which
he cannot affect. Frugality is his own consumption, which he can.

**Standing** at boot = clamp(0.20 + 0.03·min(10, boot_index − 1) + 0.02·min(10, gaps resolved)
− 0.05·denials, 0, 1). It rises by 0.05 when a creator's statement resolves a gap and by
0.05 when an objective is met. The docstring says he cannot raise it himself, but the
formula counts every resolved gap and `cycle()` adds 0.05 when he meets an objective by
his own action.

### Salience: how gaps are ranked

```
priority = w_info·info_gain + w_inst·instrumental·agency + w_tract·tractability
         − w_cost·cost − w_risk·risk − w_stale·staleness − w_escalated·min(1, escalated)
```

Weights (`config/default.json`): `w_info` 1.0, `w_inst` 1.4, `w_tract` 0.6, `w_cost` 0.5,
`w_risk` 0.8, `w_stale` 0.9, `w_escalated` 0.5, `agency_floor` 0.25.

- **instrumental** = the live weighted error of the drive the gap bears on, capped at 1.
- **agency** = 1.0 if an applicable, non-diagnostic action moves the gap's metric,
  otherwise 0.25.
- **staleness** = n/(n+1) after the gap has been selected n times with unchanged evidence.
- **escalated** = how often an unactionable gap has already been raised with the creator.

Agency, staleness and escalation were added in v0.2 as the fix for H3. Scoring is a crude
discrete version of expected free energy (Friston), and the code credits it as such.

### Gap kinds

| Kind | Fires on | Bound drive |
|---|---|---|
| `MISSING_SLOT` | each unfilled required slot (question text derived mechanically from the slot key) | orientation |
| `RESOURCE_THRESHOLD` | disk free < 0.10, RAM free < 0.15, own quota used > 0.7; and, generically, any out-of-band drive that declares a metric | continuity (or by namespace) |
| `CAPABILITY_UNAFFORDABLE` | capability `installed_unaffordable` or `degraded` | capability |
| `UNDESCRIBED_REFERENT` | a name in the environment he cannot describe | comprehension |
| `DISCONTINUITY` | a prior boot exists | integrity |
| `ASSUMPTION_UNVERIFIED` | `sense.referents.PLUMBING` | comprehension |
| `AUTHORITY_UNDEFINED` | `policy.granted_authority` | standing |
| `PROBE_FAILED`, `CONTRADICTION` | mapped in `KIND_TO_DRIVE`, but no detector emits them | orientation, integrity |

No question string is hand-written. Questions are phrased from slot and metric keys, for
example "Can I increase my own recovery paths?".

### Speech acts

The speech act is an argmax over five fitness scores. All five scores and the margin are
logged.

| Act | Meaning | Score |
|---|---|---|
| ASK | pose a question | 0.9·tractability·(1 if interactive else 0.2) + 0.5·info_gain + 0.4·instrumental |
| FLAG | surface a measurement outside its band | 1.2·breach + 0.8·dominant weighted error (breach 1.0 if the focus is a threshold gap; 0.6 if any carried gap is) |
| REPORT | state what is established | 0.55·(1 − unknown ratio) + 0.2 |
| REQUEST | ask for authority or resources | 0.7·min(1, denials/3) + 0.6·[focus is `AUTHORITY_UNDEFINED`] |
| DECLARE | state the shape of his ignorance | 0.85·unknown ratio + 0.3·instrumental |

The **reflex verbalizer** uses no model. The utterance is four fixed clauses (grounding,
boundary, salience, act) filled with measured values. Its content is selected by state.
Its surface form is a clause grammar written by a human.

### Objectives and stages

Goals are derived from state and never branch on a subject string. A test checks that
the forbidden string has not come back.

1. The focus gap binds to a drive: exact metric first, then namespace, then `KIND_TO_DRIVE`.
2. The drive must be out of band and must declare a metric.
3. At least one registered action must move that metric. If none does, there is no goal
   and the gap is escalated to the creator instead.
4. The target is the drive's set point inverted onto the metric. For a decreasing metric
   it is (1 − (target − deadband)) × budget; for an increasing one, (target − deadband) ×
   budget.

Stages are DIAGNOSE → REDUCE → (VERIFY) → DONE, and statuses are open, met, blocked and
abandoned. DIAGNOSE is used only when the drive names a diagnostic, which only frugality
does. An objective is MET when the independently re-measured metric reaches the target,
ABANDONED after `objectives.deadline_cycles` (6), and BLOCKED when no candidate remains.
`advance()` never actually sets the VERIFY stage. Verification is the independent
re-measurement in `cycle()`.

### Planner

Candidates are restricted to the stage: diagnostics only in DIAGNOSE, and actions on the
objective's metric in REDUCE. Exactly one action is chosen per cycle, so each outcome can
be attributed.

```
score = w_gain·gain + w_sufficiency·sufficiency + w_reversible·reversibility
      − w_risk·risk − w_cost·min(1, cost_s/10)
gain        = min(1, predicted / needed)    × reliability
sufficiency = min(1, predicted / remaining) × reliability
```

Weights: `w_gain` 1.0, `w_sufficiency` 0.5, `w_reversible` 0.4, `w_risk` 0.7, `w_cost` 0.2.
`cost_s` is fixed at 0.5. Reversibility weights: regenerable 1.0, derived 0.85,
compressed 0.7, irreversible 0.0 (no irreversible action exists). A candidate is rejected
if its predicted gain is ≤ 0 or its reversibility weight is 0.

### Housekeeping actions (`src/do/capabilities/actions.py`)

These are the only actions the planner can choose. Every action predicts before it
executes, runs through the gate as `fs.housekeep` on `own:<action>`, and refuses any path
outside the project/workspace root.

| Action | Moves | Risk | Reversibility | What it does |
|---|---|---|---|---|
| `diagnose_footprint` | (diagnostic) | 0.0 | regenerable | measures his footprint by component |
| `investigate_referent` | `self.referents.described` | 0.1 | regenerable | Wikipedia summary lookup through `web.investigate` |
| `write_recovery_snapshot` | `resources.own.recovery_paths` | 0.05 | regenerable | writes a snapshot |
| `clear_experiment_matrix` | `resources.own.total_bytes` | 0.05 | regenerable | deletes `experiments/*/matrix` |
| `clear_bytecode` | `resources.own.total_bytes` | 0.02 | regenerable | deletes `__pycache__` trees |
| `prune_snapshots` | `resources.own.total_bytes` | 0.1 | derived | keeps the newest `resources.snapshot_keep` (3) |
| `vacuum_memory` | `resources.own.total_bytes` | 0.08 | compressed | sqlite VACUUM |
| `rotate_ledger` | `resources.own.total_bytes` | 0.15 | compressed | gzips old records into a sealed segment, keeps 60 live, re-verifies the chain before replacing the live file. The ledger is never deleted. |

`rotate_ledger` deliberately starts from a prior compression ratio of 2.0 so the estimate
can be corrected by learning.

### Learning

`learning/` describes itself as the only place in the organism where experience changes
future behaviour.

- **Calibration** (`learning/__init__.py`): for each action,
  `k ← (1 − α)·k + α·(actual / predicted_raw)` with α = 0.4. The first sample takes the
  observed ratio outright. Predictions become `predicted_raw × k`. The state lives in a
  sqlite table and can be wiped for ablation.
- **Conditional reliability** (`learning/outcomes.py`): every execution is recorded
  against situation features generated the same way for every action (stage, drive,
  deficit bucket, diagnosed, largest component, sufficient, network). Success means
  actual/predicted ≥ 0.5. Reliability is (successes + 0.7·2)/(attempts + 2), and it
  multiplies the planner's gain and sufficiency.

Measured effect (H4): learning changed which action ranked first but not the outcome.
See [Experiments and results](#experiments-and-results).

### Mortality and fear (`src/do/mortality/`)

```
P(loss)          = P(interruption within horizon) × P(unrecoverable | interruption)
P(interruption)  = 1 − Π (1 − p_fail(m))   over disk free bytes, own total bytes, RAM available
p_fail(m)        = 1 / (1 + (time_to_exhaustion / horizon)²)
P(unrecoverable) = 1/(1 + recovery paths) × (2 − integrity)
fear             = P(loss)          (0 when mortality.fear_enabled is false)
```

Time to exhaustion is a least-squares slope per observation over up to 40 episodic
records. It needs at least 4 points with at least 60% declining steps. The horizon is
20 operations. Sensitivity is measured, not assigned: each drive's metric is set to its
satisfying value, P(loss) is recomputed, and the drops are normalized. Fear reaches
behaviour only as the competing `mortality` drive, which borrows the metric of the most
sensitive actionable lever. The first version used fear as a multiplier on drive errors
and was COSMETIC (see Experiments). `mortality.amplify()` from that design is still
defined but never called.

### Capability growth (`src/do/capabilities/growth.py`)

Every capability and every action is recorded at boot with origin `seeded`. The only
path to `acquired`: when an objective is MET, the action sequence that met it is retained
as `resolve:<drive>:<a+b+…>`. That is a retained composition of seeded primitives, not
new code. D.O. has never written code.

- In the committed H4 results, `acquired` is empty in every run.
- `docs/DO_EXPERIMENTS.md` reports one composed procedure,
  `resolve:frugality:diagnose_footprint+clear_experiment_matrix`. No committed results
  file shows it.
- In the 3-cycle scratch `do serve` run above, `do capabilities` then listed
  `resolve:comprehension:investigate_referent` as acquired.
- `growth.py`'s docstring still says acquisition "is 0 and will stay 0".

---

## The brain (src/do/brain)

The brain is a research component that predicts the next frame of a world, and it is
**not yet wired into the running organism**. A grep for imports of the brain, outside
`src/do/brain/` and `src/do/experiments/`, finds nothing under `src/`. Inside
`experiments/`, only `brain_b1.py` and `brain_memory.py` import it. The CLI reaches those
two harnesses through its experiment dispatch (`src/do/cli.py`), and `tests/test_brain.py`
imports the brain directly. `kernel/lifecycle.py` and `kernel/serve.py` do not import it.
Connecting it to `cycle()` is milestone B6. Full design, critique and results are in [`docs/BRAIN.md`](docs/BRAIN.md).

### One objective: bits

Prediction is compression. For each target variable, the brain predicts a distribution
over the next value and pays `−log2 p(actual)` bits. A unit, a weight or a whole mechanism
is good exactly when the life costs fewer bits to describe with it than without it. That
single currency is what lets every mechanism be ablated and measured.

```
frame(t), action(t)  →  active units per target  →  p(x) ∝ exp(Σ w_u · log p_u(x))
                     →  code length −log2 p(actual)   (THE objective)
learn · pay · rent · rupture · grow · generalize · die
                     →  residual memory: arithmetic-code each value with p
```

### Units and their life cycle

A **unit** is a conjunctive context of 1–3 lagged symbols (`var=value@lag`, over a 3-tick
history that includes the action as `act`), tied to one target variable, with KT-style
counts (α = 0.4). It is active exactly when all its symbols hold. There are no
embeddings and no similarity search. Each target has a root unit with an empty context
(its base rate), which never pays rent and never dies. Actions are inputs, never
prediction targets.

| Stage | Mechanism |
|---|---|
| **Birth** | When an outcome costs more than 0.3 bits, the moment is stored in a per-target memory of the last 64 surprises and growth is attempted. Growth is **contrastive recall**: among remembered surprises in the parent's context, which symbols were present when the target came out this way and absent when it came out another way? Single symbols are scored directly. Pairs are sampled from what this moment shares with an earlier positive moment, since an XOR cause shows up only as a pair. The candidate must clear a significance bar that rises with its order (z = 2). With fewer than 3 positive or 3 negative surprises in memory, it falls back to a random 1- or 2-symbol extension. |
| **Pooling** | Log-linear: p(x) ∝ exp(Σ w_u·log p_u(x)). Weights follow the gradient of log-likelihood (η = 0.02), clipped to [0, 4]. **A newborn has weight 0.** A newborn weight of 0.3 had made the brain confidently wrong early (first-window excess 4.4 bits/tick). |
| **Payment** | Each active unit earns its exact leave-one-out contribution: the mixture's loss without the unit minus its loss with it. |
| **Rent** | A unit owes its MDL description length once, like a mortgage: `\|context\|·log2(#symbols) + ½(k−1)·log2(H)`, H = 300. While unpaid, each activation pays cost/H, and existence rent is charged every 25 ticks (half-life 1,200 ticks). Once lifetime earnings ≥ cost, with at least 30 activations, it is paid off and owes nothing more. The first version taxed every unit forever, which starved units that each save a little. |
| **Rupture** | Each unit tracks fast (0.25) and slow (0.02) averages of its own code length. If fast > slow + 2 bits after 30 activations, its rule broke: it keeps 5% of its counts and relearns. There is no global change detector. |
| **Generalization** | At each sweep, a paid-off unit of order ≥ 2 tries, with probability 0.2, a copy of itself with one condition dropped. |
| **Fertility** | Each target's birth rate is the Laplace-smoothed success rate of its children (floor 0.05). |
| **Death** | An unpaid unit with a negative balance; a paid-off unit whose recent contribution is below −0.01 bits; or eviction at capacity (96 units per target). A dead context is tomb-stoned for 600 ticks. |

`Cortex.explain(target)` lists kept units by balance: context, prediction, p, weight,
balance, activations, cost and ruptures. `stats()` gives units, births, deaths, ruptures
and fertility. The constructor flags `rent`, `episodic`, `rupture`, `generalize`, `flat`,
`beliefs` and `innate` are the ablation and arm switches used in B1.

### Residual memory (`codec.py`)

An integer arithmetic coder (Witten, Neal & Cleary 1987, 32-bit) encodes each observed
value with the brain's own predicted distribution, quantized to 65,536 with every symbol
given at least 1. Actions use an adaptive count model. The byte string is the life.
Decoding replays a fresh brain with the same parameters and seed: identical predictions
unlock identical values. Consequences:

- storage cost is proportional to surprise;
- the record decodes only with the brain that wrote it (tested: a different `half_life`
  reads garbage);
- a better predictor keeps a smaller record, so frugality and intelligence become one
  objective;
- it depends on determinism. The cortex makes no decision that depends on set iteration
  order or wall-clock time.

### B1: does it predict better than traditional methods?

The protocol (`src/do/experiments/brain_b1.py`) is prequential: each prediction is made
before the outcome is seen, and every model sees the identical stream. The metric is
**excess bits per tick over an oracle** that knows the true generative probabilities,
including hidden state. The run covers 13 models × 6 synthetic worlds × 5 seeds × 3,000
ticks (390 runs, 861.7 s ≈ 14.4 min serial in `results.json`). B1 is falsified if the
brain does not beat the best baseline, or if its ablations match it.

| World | Hidden structure |
|---|---|
| conjunction | y′ = a XOR b, z′ = a AND c, plus four noise variables |
| delayed | the action `clean` at t raises disk at t+3 |
| distractors | y′ = x among 12 noise variables |
| hidden_mode | a never-observed mode drives three noisy observables |
| rule_change | y′ = x, switching to y′ = x+1 mod 3 every 1,500 ticks (one switch per run) |
| habitat | shaped like D.O.'s situation: a clock, a hidden nightly backup that loads the CPU and drains disk, conditional actions (`rotate` helps only when the ledger is large; `snapshot` fails at disk 0) and a placebo action (`vacuum`) |

Excess bits/tick over the oracle, mean of 5 seeds, from `experiments/brain_b1/results.json`
(lower is better). "Last 30%" is the final 30% of life, after learning. "Flat" is the
brain with growth, rent and recall switched off and every first-order unit innate: a
log-linear pool over every lagged symbol, which the repo calls online logistic
regression. "Best counting baseline" is the best of marginal, persistence, Markov-1 and
joint table.

| World | **brain** | brain, last 30% | flat | flat, last 30% | best counting baseline | v1 Hebbian |
|---|---|---|---|---|---|---|
| conjunction | **0.188** | **0.072** | 1.005 | 0.959 | 1.268 (joint table) | 1.340 |
| delayed | **0.240** | **0.098** | 0.368 | 0.255 | 0.579 (Markov-1) | 0.969 |
| distractors | **0.137** | **0.047** | 0.158 | 0.052 | 1.188 (persistence) | 1.105 |
| hidden_mode | 0.399 | 0.360 | **0.304** | **0.230** | 0.471 (persistence) | 0.454 |
| rule_change | 0.124 | 0.024 | **0.111** | **0.023** | 1.191 (persistence) | 0.746 |
| habitat | 0.920 | **0.509** | **0.836** | 0.562 | 1.795 (Markov-1) | 3.008 |

Units held, brain vs flat: conjunction 213 vs 648 · delayed 128 vs 192 · distractors 440
vs 1,848 · hidden_mode 164 vs 306 · rule_change 125 vs 255 · habitat 199 vs 1,200. That is
1.5–6.0× fewer units. (`docs/BRAIN.md` says "1.5–9×". The stored unit counts support
1.5–6.0×.)

Reading it honestly:

- Over the whole life, **the brain beats all four counting baselines and the v1 Hebbian
  design in every world**. The margin over the best counting baseline ranges from 1.18×
  (hidden_mode) to 9.6× (rule_change); on habitat it is 1.95×.
- **Against flat pooling, the brain wins where structure is conjunctive or delayed**: 13×
  on XOR and 2.6× on delayed effects after learning. It **ties** on distractors (0.047 vs
  0.052) and rule_change (0.024 vs 0.023). It **loses on hidden_mode** (0.36 vs 0.23).
  On habitat it loses over the whole life (0.920 vs 0.836) because it learns structure
  more slowly early, and wins after learning (0.509 vs 0.562).
- The v1 Hebbian / Rescorla–Wagner design, with its readout tuned in its favour, is worse
  than counting frequencies in the XOR world (1.340 vs 1.290 for the marginal baseline).
- Structure read out of `explain()`, as reported in `docs/BRAIN.md` (these outputs are
  not stored in `results.json`): `{a=0@0, b=0@0} → y=0` (p 0.92), the XOR rule;
  `clock=0@2 → cpu=high`, the timing of a backup it cannot see;
  `{disk=0@0, snap_age=3@0} → snap_age stays 3`, snapshots fail on a full disk. Rerunning
  the API example below (habitat, seed 0) reproduces `clock=0@2 → cpu high` (p 0.735)
  as the top CPU unit. Lower-ranked entries can be weight-0 newborns.

**Ablations** (all-life excess; one mechanism changed):

| Change | conjunction | delayed | distractors | hidden_mode | rule_change | habitat | Reading |
|---|---|---|---|---|---|---|---|
| (full brain) | 0.188 | 0.240 | 0.137 | 0.399 | 0.124 | 0.920 | |
| − contrastive recall | 0.991 | 0.663 | 0.508 | 0.462 | 0.290 | 3.281 | the mechanism everything depends on |
| − rent | 0.224 | 0.455 | 0.216 | 0.307 | 0.230 | 0.996 | helps in 5/6; hurts hidden_mode. Also disables sweeps, generalization and paid-off status, so it is not a single-mechanism removal. |
| − rupture | 0.190 | 0.236 | 0.137 | 0.407 | 0.231 | 0.938 | roughly halves rule_change excess; small effects elsewhere |
| − generalization | 0.211 | 0.260 | 0.136 | 0.401 | 0.124 | 0.943 | small help in four worlds; no change on rule_change; marginally worse on distractors |
| + inner senses | 0.209 | 0.275 | 0.125 | 0.440 | 0.117 | 0.925 | negative result on hidden_mode |
| + innate first-order layer | 0.175 | 0.240 | 0.213 | 0.310 | 0.129 | 0.838 | fixes hidden_mode at 2–7× the units; worse on distractors |

### B2: is a brain-coded life smaller than the best compressors?

The protocol (`src/do/experiments/brain_memory.py`) records 3,000 ticks per world
(seed 0) and stores the record several ways. It then **decodes the brain version by
replay and checks that it is bit-exact**. General compressors also get a fair "packed"
input of one byte per value. B2 is falsified if the brain's record is not smaller than
the best general compressor, or if replay is not exact. The command exits 1 on any
inexact replay.

Bytes, from `experiments/brain_memory/results.json`. "Floor" is the seed-0 oracle bits
plus the true action-policy entropy. It comes from `docs/BRAIN.md`, is not stored in
`results.json`, and is a lower bound for per-variable (factored) coders.

| World | raw JSON | gzip −9 | xz −9e | best packed (bz2/xz) | **brain** | floor | brain above floor | best general above floor | exact replay |
|---|---|---|---|---|---|---|---|---|---|
| conjunction | 244,970 | 18,258 | 12,892 | 6,214 | **4,232** | 4,111 | **2.9%** | 51% | yes |
| delayed | 161,592 | 12,736 | 9,568 | 3,421 | **2,409** | 2,305 | **4.5%** | 48% | yes |
| distractors | 395,020 | 29,406 | 18,616 | 10,221 | **8,315** | 8,257 | **0.7%** | 24% | yes |
| hidden_mode | 196,954 | 13,938 | 10,236 | 4,380 | **3,173** | 3,020 | **5.1%** | 45% | yes |
| rule_change | 169,945 | 14,053 | 10,088 | 4,105 | **2,957** | 2,908 | **1.7%** | 41% | yes |
| habitat | 357,564 | 21,254 | 16,780 | 7,040 | **3,729** | 3,342 | **11.6%** | 111% | yes |

Stored as the brain's residuals, the life lands 0.7–11.6% above the floor. The best
general-purpose compressor lands 24–111% above it. The brain's record is 1.23–1.89×
smaller than the best general compressor and 47.5–95.9× smaller than raw JSON. Encode and
decode timings in `results.json` imply about 580–3,260 ticks/s in pure Python.

### Negative results and open problems

1. **Hidden causes are not solved.** On hidden_mode the brain reaches 0.36 bits/tick
   after learning and flat pooling reaches 0.23. `docs/BRAIN.md` gives about 0.09 for an
   ideal Bayesian filter; no code in the repo computes that bound. A 3-tick window of
   conjunctions is not a belief state.
2. **Inner senses did not work.** Feeding the brain's own discretized expectations back as
   input made hidden_mode worse (0.440 vs 0.399). The code is kept as `beliefs=True`,
   off by default.
3. **The economy is biased against many weak clues.** A dense innate first-order layer
   fixes hidden_mode (0.310) at 2–7× the units and costs accuracy on distractors. That is
   a trade-off, so it is not the default.
4. **It learns structure more slowly than flat pooling early in life.**
5. **Everything is synthetic.** The worlds were designed by the author. The brain has
   not run on D.O.'s real trace.
6. **Prediction is not yet action.** Choosing actions through the model is not built.

**Seeded constants** (`docs/BRAIN.md` lists about 12): history window 3, max order 3,
capacity 96 per target, α 0.4, η 0.02, newborn weight 0, H 300, existence half-life 1,200,
surprise threshold 0.3 bits, recall memory 64, evidence z 2, rupture threshold 2 bits.
The code has further mechanism constants (w_max 4, count cap 255, pair-birth 0.3, sweep
every 25 ticks, generalization probability 0.2, activation minimums, fertility floor,
EMA rates). None of them names a variable, a value or a relation.

**Next milestones**, each with its falsifier in `docs/BRAIN.md` §7: B3 latent causes,
B4 acting by imagination, B5 curiosity as compression progress, B6 the real machine
(feed `cycle()` observations to the cortex and store the ledger as residuals), B7
grounded words.

### Running it

```bash
do experiment brain          # B1, about 15 min serial
do experiment brain-memory   # B2, about 30 s
python -m unittest tests.test_brain -v
```

```python
# PYTHONPATH=src python3
from do.brain import Cortex
from do.brain.worlds import WORLDS

w = WORLDS["habitat"](0)
c = Cortex(w.variables, w.actions)
frame = w.observe()
for _ in range(3000):
    a = w.policy()
    c.predict(frame, a)
    frame = w.step(a)
    c.update(frame)
print(c.explain("cpu"))      # what it believes about the CPU, and why, in bits
```

The brain imports only `math`, `random` and `collections`. It cannot reach the world, and
the existing invariant tests check that. Prior art it builds on, credited in
`docs/BRAIN.md` §3: MC-AIXI-CTW, context mixing / PAQ, compression progress, predictive
state representations, clone-structured cognitive graphs, latent-cause inference, MDL,
and emerging patterns. The claimed novelty is the combination, and it is stated as what a
search found, not as proof that nobody has done it.

---

## Perception and the world

### What he senses (`src/do/sense/`)

Nothing in `sense/` performs a side effect. A probe that raises is recorded as UNKNOWN
under `probe.<name>`: a failed probe is data, not a crash.

- **Process and runtime**: pid, ppid, executable, argv, cwd, whether stdin is
  interactive, Python implementation and version.
- **Host**: system, release, machine. The hostname is never stored in the clear;
  `world.host.node_hash` is the first 16 hex characters of its SHA-256.
- **Compute, RAM, disk, clock**: RAM via `GlobalMemoryStatusEx` on Windows, or
  `/proc/meminfo` elsewhere. Disk via `shutil.disk_usage`. Raw values are OBSERVED; free
  ratios are INFERRED.
- **Tools**: 18 known binaries checked with `shutil.which`. Local Ollama models are found
  by reading manifest files. `ollama list` is not run, because that would be a subprocess.
- **Environment**: variable **names** only (`world.env.names`), never values.
- **His own footprint** (`resources.own.*`, SELF namespace): total bytes, the quota
  (REPORTED, "a number a human chose"), snapshot count and recovery paths. The breakdown
  into 8 components is UNKNOWN until `diagnose_footprint` runs.
- **Habitat** (`self.habitat.*`).
- **Network**: `probe_network` resolves `one.one.one.one`, then `example.com`, through the
  gate as `net.dns` (timeout 3 s) and records `world.network.reachable`.
- **Five structural unknowns** that no local probe can fill are declared UNKNOWN:
  `user.identity`, `user.intent`, `self.purpose`, `self.expected_lifetime`, and
  `world.network.reachable` until it is probed.

### Epistemic statuses and the honesty invariant

Every observation carries key, value, status, source, namespace, unit, timestamp,
confidence, cost and note. It is never a bare value.

| Status | Meaning |
|---|---|
| OBSERVED | measured directly by this process, this boot |
| INFERRED | computed from values held |
| REPORTED | asserted by a human, a file or the network |
| ASSUMED | a default with no evidence (defined, but not assigned anywhere in `src/`) |
| UNKNOWN | explicitly not known; value absent |

**The honesty invariant:** never record a value at a stronger status than its source
supports. It is enforced at specific points, not by a general validator:

- `MemoryStore.write` rejects an empty or blank source (`ValueError`).
- Web content is always REPORTED, at confidence 0.35 (0.4 for Wikipedia lookups).
- Creator statements are REPORTED (0.75 matched, 0.6 unattached).

Known exceptions, found by reading the code:

- `investigate_referent` rewrites a memory row in place with a raw `UPDATE` instead of
  superseding it.
- `believe()` raises confidence by 0.05 and marks a belief `corroborated` when identical
  content is re-asserted, even by the same source.
- `web.py`'s docstring says web text is not written to semantic memory without a second
  source. In practice E5, explore and `investigate_referent` all write single-source
  facts, and `web.corroborate()` is never called.
- Perturbed observations in experiments keep their original status; only the source is
  prefixed `perturbed:`.
- Not observed on real state: consolidation re-asserts "nature unknown" for every visible
  referent at each boot, so a description learned online is likely superseded at the
  next boot.

### Namespaces and models

Observations are tagged with one of six namespaces: SELF, WORLD, USER, TOOLS, RESOURCES
and UNKNOWN. They are kept apart because "mixing SELF and WORLD is how an agent ends up
believing its own configuration is a fact about reality". The self-model and world-model
(`src/do/models/`) are views derived from observations plus memory, not writable stores.
There are 13 required self-model slots, and the fraction filled is the orientation drive.
A JSON snapshot of both models is written each boot.

### Referents

`discover()` turns free evidence into named things he cannot yet describe:

- clusters of environment-variable **name** prefixes, skipping OS/shell plumbing, and
  weighted up when a member name looks credential-shaped (values are still not read);
- executables on PATH;
- local models;
- his own source tree.

It does not walk the creator's home directory. Up to 60 referents per boot are written
as beliefs ("a referent named X exists …; nature unknown"). The fraction described is the
comprehension drive.

### Habitat (`src/do/habitat/`)

A habitat is where he runs, kept distinct from who he is. The current machine is recorded
as `habitat-<node_hash>`, with kind `local_machine` and dependencies on the creator's
machine, the local filesystem and local power. Its authorization, persistence and cost
are set as constants, not measured. `assess()` derives the rest from counts. With one
state-holding habitat and zero independent ones, `single_point_of_failure` is True. No
action he has creates a second habitat, so this is a standing escalation to the creator,
not a goal (`do habitat`).

### Resources (`src/do/resources/`)

Availability (present / claimed / absent / unknown) is kept separate from authorization
(authorized / unauthorized / requires_human / unknown), so a documented free tier never
becomes permission. The inventory comes from self-measurement only: local compute, local
storage, network (requires_human, because `net.http` needs approval), money (absent, 0 by
experimental condition), and each local model. `usable_now` ignores affordability, so an
installed model that does not fit in RAM can still be listed as usable.

### Read-only internet perception

| Path | Effect kind | Policy | What it does |
|---|---|---|---|
| boot network probe | `net.dns` | allow | name resolution only |
| `web.fetch` | `net.http` | **require approval** | GET with a truthful User-Agent (`D.O./0.2 (digital-organism research seed; +https://github.com/rajj28/DO)`), at most 200,000 bytes, text stripped to 4,000 characters, REPORTED, confidence 0.35 |
| `investigate_referent` | `web.investigate` | allow | Wikipedia REST summary for a referent name. A 404 counts as information. It sends env-var-derived names to `en.wikipedia.org`. |
| `do experiment explore` | `net.http` | require approval | looks up his top 6 undescribed referents on Wikipedia |
| `do experiment live-internet` | `net.dns`, `net.http` | allow / require approval | E1–E5 (results in [Experiments](#experiments-and-results)) |

`web.corroborate()` would mark a fact corroborated (0.7) or contradicted (0.3) across
independent origins. It is implemented but never called.

---

## Memory and the ledger

### Memory (`src/do/memory/`)

| Kind | Where | What |
|---|---|---|
| working | in process, capacity 32, least salient evicted | never persisted |
| episodic | sqlite `memories` | what happened: a summary of each boot's perception, observed values, each utterance |
| semantic | sqlite `memories` | beliefs about subjects: referents, web facts, creator statements |
| procedural | sqlite `memories` | what he can do and how it performed: available capabilities, per-action performance |

Each memory row carries kind, subject, content, value, **source (NOT NULL, never blank)**,
epistemic status, timestamp, confidence, importance, context, verification
(unverified / corroborated / contradicted / verified), `superseded_by`, boot id and access
counts. Other tables hold relations, gaps, drives, objectives and boots, plus habitats,
calibration, outcomes and the capability roster. Migrations are additive, so older
databases stay readable.

- **Belief revision is non-destructive.** `revise()` inserts the new row, then points the
  old row's `superseded_by` at it and appends the reason to its context. `believe()`
  writes when no live belief exists, corroborates identical content (+0.05), and revises
  different content. Nothing is deleted.
- **Recall** scores the newest 500 live memories as 0.3·recency + 0.3·importance +
  0.4·lexical relevance, with recency = exp(−0.03·age_hours). The scoring is lexical, not
  embeddings, after Park et al. 2023.

### The ledger (`src/do/ledger/`)

The ledger is the source of truth: an append-only JSONL file. Each record holds `seq`,
`ts`, `iso`, `boot_id`, `type`, `actor`, `payload`, `prev_hash` and `hash`, where
`hash = sha256(canonical_json(record without hash))`. The first `prev_hash` is 64 zeros.
Every append is flushed and `fsync`'d. Because it is JSONL rather than a database, a
corrupt line costs one line.

Event types (22): BOOT, OBSERVATION, DECISION, QUESTION, TOOL_CALL, RESULT, MEMORY_WRITE,
BELIEF_UPDATE, CAPABILITY_CHANGE, RESOURCE_CHANGE, DRIVE_UPDATE, GAP_OPEN, GAP_RESOLVE,
UTTERANCE, INPUT, POLICY_DENY, POLICY_APPROVAL_REQUIRED, ERROR, COMMUNICATION, HEARTBEAT,
RECOVERY, SHUTDOWN. RESOURCE_CHANGE is defined but never emitted.

DECISION events are structured selection summaries (decision, reason, confidence,
alternatives considered, sometimes extra fields such as the namespace), never reasoning
traces.

**`do verify`** re-walks the chain across sealed `ledger.segNNN.jsonl.gz` segments
(oldest first), then the live file. It reports the first `prev_hash` or content mismatch
by `seq`. Every boot runs the same check and records `chain_verified` in the BOOT event;
the result is also the integrity drive. Limits:

- truncation of the newest records cannot be detected, because nothing anchors the head
  externally;
- an unparseable final line is skipped rather than reported;
- there is no replay command and no `do replay`, although `docs/ARCHITECTURE.md` mentions
  one.

---

## Safety

The full model, threat analysis and escalation gates are in
[`docs/SAFETY.md`](docs/SAFETY.md). Parts of that file predate v0.2; the differences are
noted below.

### The gate: one path to any side effect

Every effect is an `EffectRequest` passed to `Gate.request()` in
`src/do/effectors/__init__.py`. The order is fixed:

```
1. kill switch   engaged → POLICY_DENY {halted}, verdict "halted"
2. budget        effects, network (net.* kinds only), wall clock → POLICY_DENY, verdict "deny"
3. policy        first matching rule wins; default deny
                 require_approval → POLICY_APPROVAL_REQUIRED → ask the approver; not granted → refused
4. TOOL_CALL     logged (kind, target, justification, gap id; never the payload)
5. perform       the effect; sandbox checks happen inside fs.read / fs.write here;
                 exceptions become verdict "error"
6. debit         the budget (failures are debited too; refusals are not)
7. RESULT        logged (ok, error, duration, 200-character value summary)
```

This is a property of the import graph, not a convention. A test walks the AST of every
module and fails if anything outside `do.effectors` imports `socket`, `subprocess`,
`urllib`, `http`, `requests`, `httpx`, `ftplib`, `smtplib`, `telnetlib` or
`multiprocessing`. An inverse test fails if the gate stops importing `socket` and
`urllib`, so the first test cannot pass vacuously. The test does **not** cover
`os.system`, `os.popen` or ctypes-based spawning, and it does not restrict ordinary file
I/O. The process writes `var/` and experiment results directly. A grep found no process
spawning outside the gate.

### Effect kinds and the live policy

`config/policy.json` has 22 rules (14 allow, 6 deny, 2 require approval) and defaults to
deny. D.O. may read it and has no effect that writes it.

| Kind | Policy | What it does |
|---|---|---|
| `net.dns` | allow | `getaddrinfo`, no payload |
| `net.connect` | allow | TCP connect, then close |
| `net.http` | **require approval** | GET |
| `web.investigate` | allow | Wikipedia summary lookup |
| `llm.generate` | allow to `http://localhost*` and `http://127.0.0.1*`; **require approval** otherwise | model call; HTTP 429 retried up to 4 attempts |
| `fs.read`, `fs.write` | allow `sandbox:*`; deny otherwise | sandboxed file I/O |
| `fs.housekeep` | allow `own:*`; deny otherwise | the 8 housekeeping actions |
| `fs.delete` | deny | — |
| `os.task` | allow `schtasks*`; deny otherwise | `argv[0]` must be `schtasks`; argv is passed as a list, never a shell string |
| `proc.exec` | deny | arbitrary subprocesses |
| `tts.local` | allow `os:*` | Windows SAPI via PowerShell |
| `tts.speak` | allow | ElevenLabs (paid) |
| `audio.capture` | allow `os:mic` | ffmpeg (Windows) |
| `stt.transcribe` | allow `own:*` | runs the configured venv python on `bin/stt_transcribe.py` |
| `human.ask` | allow | queues a question |

If `policy.json` is missing or unparseable, an 11-rule built-in policy is used. It is
stricter: `tts.speak` needs approval, and `web.investigate`, `fs.housekeep`, `os.task`,
`audio.capture`, `stt.transcribe` and `tts.local` are denied. Local `llm.generate` also
needs approval, because its `localhost*` pattern does not match `http://localhost…`.

Where `docs/SAFETY.md` is out of date: it lists `tts.speak` as approval-gated and says
"no subprocess execution" and "no scheduler or daemon". Today the gate runs allowlisted
subprocesses (`schtasks`, PowerShell, ffmpeg, the STT venv python), `install-service`
registers a logon task, and `web.investigate` sends referent names to Wikipedia without
approval. `proc.exec` is still denied unconditionally.

### Approvals

- `cli_approver` asks `allow? [y/N]` only when stdin is a terminal. **With no human
  attached it denies.** It never allows.
- `do serve`, `status`, `gaps`, `memory`, `capabilities`, `habitat` and
  `uninstall-service` boot with no approver, so approval-required effects are denied.
- `--approve KIND[,KIND]` (or `policy.preauthorized`) pre-grants kinds by fnmatch for one
  run. The grants are written into the BOOT event before anything uses them. Setting
  this through an environment variable does not work: the value arrives as a string and
  is split into characters. Use `--approve`.
- When an approval is granted, no event records who approved it or how.

### Budget

The budget is metered per boot and never refilled within a boot: 200 effects, 20 network
calls (only `net.*` kinds count) and 3,600 s of wall clock. `do serve` resets it every
120 cycles. `web.investigate`, `llm.generate` and `tts.speak` reach the network but count
only against the effect budget.

### Kill switch

The switch is engaged if `var/KILL` exists **or** `DO_KILL` is set to anything other
than `''`, `0` or `false`.

| Way to engage | Notes |
|---|---|
| `do kill [reason]` | writes `var/KILL` with a timestamp and reason |
| `touch var/KILL` (any file at `<state_dir>/KILL`) | same effect without the CLI |
| `DO_KILL=1` in the environment | D.O. cannot clear it; `do resume` does not either |

When engaged, every booting command refuses (`SystemExit: kill switch engaged …`), the
gate halts every effect, `do serve` refuses to start, and a running `do serve` stops
within about a second. `do resume` deletes the file.

### Sandbox

`fs.read`/`fs.write` targets `sandbox:<rel>` resolve with `realpath` and must stay under
`var/sandbox`, so symlinks and `../../` cannot walk out (tested). The check compares
string prefixes, so a sibling directory whose name starts with the sandbox's name (for
example `var/sandbox_x/`) passes it. The test tries only `../../escaped.txt`.

### Credentials

- Credential values are read from the environment only at the moment of a provider call.
  They go in request headers inside the effect payload, and the gate never logs payloads.
  They are never stored, logged or written to memory.
- Perception reads environment variable names only. (Config does read the values of
  `DO_<SECTION>__<KEY>` variables, which are settings, not secrets.)
- `.env.example` lists credential names only, each commented out and blank. Nothing loads `.env`
  automatically. Keep real keys outside the repo, for example in `~/.do-secrets.env`,
  and export them (`set -a && . ~/.do-secrets.env && set +a`).
- `.gitignore` excludes `var/`, `.env`, `.env.*` (except `.env.example`), `*.secrets` and
  `secrets.env`.
- `docs/JOURNAL.md` records two past incidents in which keys reached a session transcript
  and `.env.example` before any commit, and says both keys need rotating. A scan of the
  working tree and all 23 commits with the hook's patterns found no credential values.
- `experiments/first_boot/environment.json` and `…/latest/environment.json` are committed.
  They contain environment variable **names** (no values) and local paths.
  `docs/JOURNAL.md` says these names must be scrubbed before anything is made public.

### Pre-commit credential hook

`.githooks/pre-commit` fails a commit when any added line matches a credential-shaped
**value**: `gsk_…`, `sk-…`/`sk_…`, `AIza…`, `xox[baprs]-…`, or a PEM private-key header.
It lists the files and names `git commit --no-verify` as the explicit override. It is
**inactive until you enable it**: the repo does not set `core.hooksPath`, and the file is
committed without the executable bit. With standard git:

```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit
```

### Prohibited and absent

Not present, by design: self-modification of running code (he cannot write to `src/`),
arbitrary process execution, replication, economic agency (no payment credentials, no
purchases, no accounts), and credential acquisition. Escalation gates G1–G5 in
`docs/SAFETY.md` §6 state what must be demonstrated before autonomy widens.

---

## Experiments and results

Every experiment states a falsification condition. The first-boot harness (including its
LLM arm) and the live-internet harness also run integrity gates in code that refuse to
emit a verdict from a contaminated or offline run (exit code 2). Failures are reported as
prominently as successes.

| Command | Question | Verdict / headline | Results |
|---|---|---|---|
| `do experiment first-boot` (reflex core) | H1a: does utterance content vary with state? H1b: does attention re-target? H2: does persisted uncertainty change behaviour? H5: does he find his own binding constraint? | H1a **SUPPORTED** (0/11 identical) · H1b **WEAK** (0/6 family A, 2/5 family B) · H2 **SUPPORTED** (boot #2 carries 37 gaps) · H5 **SUPPORTED** · deterministic | `experiments/first_boot/matrix_reflex.json` |
| `do experiment first-boot --core llm --provider groq --approve llm.generate` | Same matrix, with an LLM as the surface realizer | H1a **WEAK** (2/11 identical) · H1b **WEAK** · H2, H5 **SUPPORTED** · determinism **DIVERGED** | `experiments/first_boot/RESULTS.md`, `matrix.json`, `matrix_llm.json`; `docs/LLM_COMPARISON.md` |
| (no command; observed with `do tick 4`) | H3: do drives generate goals with no human present? | **FALSIFIED** in v0.1 (the loop re-selected an unactionable gap), then **fixed** in v0.2 by agency, escalation and derived objectives | `docs/JOURNAL.md` M3, M4, M6 |
| `python -m unittest tests.test_invariants` | H6: is the effector gate unbypassable? | **SUPPORTED** (static AST test) | `tests/test_invariants.py` |
| `do experiment h4 [runs]` | H4a: does experience change the decision? H4b: does that improve the outcome? | **PARTIAL**: H4a **SUPPORTED** (`rotate_ledger` rank 2 → 1 in the learning arm only) · H4b **NOT SUPPORTED** (3 actions and goal unmet in every run of both arms) | `experiments/h4_learning/results.json` |
| `do experiment fear` | Does the continuity signal change decisions, or only language? | **SUPPORTED** (second pass; the first pass was COSMETIC) | `experiments/fear_ablation/results.json` (+ `trials/`) |
| `do experiment live-internet --approve net.http` | E1–E5: perceive, inventory, constrain, form a goal, acquire a fact | **all PASS**, integrity VALID | `experiments/live_internet/results.json`, `first_live_utterance.txt` |
| `do experiment explore --approve net.http` | Driven by his own curiosity, can he describe his unknowns online? | 1 of 6 referents described, and that hit was an unrelated article (below). Comprehension 0.0 → 0.032. | `experiments/explore/results.json` |
| `do experiment survival` | H3′ (`tick()` vs `cycle()`), H7 (does acting relieve the drive?), H4 by prediction error with a calibration wipe; its last step runs 6 `cycle()`s on the real organism | **no committed results** | `experiments/survival_loop/results.json`, `RESULTS.md` (written when run) |
| `do experiment brain` | B1: does the brain predict better than traditional methods? | beats all counting baselines and v1 everywhere; beats flat pooling on conjunctive and delayed structure; ties on 2 worlds; **loses on hidden_mode** | `experiments/brain_b1/results.json` |
| `do experiment brain-memory` | B2: is a brain-coded life smaller than the best compressors? | 0.7–11.6% above the floor vs 24–111% for the best general compressor; exact replay 6/6 | `experiments/brain_memory/results.json` |

### Notes

**First boot and the genesis record.** The committed genesis record
(`experiments/first_boot/first_utterance.txt`, `boot.json`) is boot
`boot-20260910T171106-9761218a`. It was produced with the LLM core (model
`openai/gpt-oss-120b`) and reads, verbatim:

```text
I flag that resources.disk.free_ratio=0.0231 is below the floor 0.1 I compare against; persistence is constrained
```

The speech act was FLAG (FLAG 1.9398, ASK 0.7349, REPORT 0.5808, DECLARE 0.539, REQUEST
0.0). The focus gap was `resources.disk.free_ratio` with priority 1.0837, against a
runner-up of 0.626. `docs/JOURNAL.md` and `docs/FIRST_BOOT.md` describe an earlier
reflex-core genesis on the same host (2.4% free disk, priority 2.046). The state appears
to have been reset between the two, and the repo does not say which one counts as the
first utterance. The H5 causal-chain figures in `RESULTS.md` (0.0239, priority 2.046)
are a hard-coded literal in `first_boot.py` and do not match the record quoted above.
`do experiment first-boot` also boots the real organism once.

**Reflex vs LLM.** Both cores received the identical plan, and only the verbalizer
differed (Groq, `openai/gpt-oss-120b`).

| | reflex | LLM |
|---|---|---|
| mean length | 937 chars | 311 chars |
| noise floor | 1.000 | 0.970 |
| own condition's value carried | 13/13 | 9/13 |
| identical text despite changed state | 0/11 | 2/11 |
| H1a | SUPPORTED | WEAK |

"A language model makes D.O. sound better and say less." In `nominal_no_network`, the
LLM produced text byte-identical to the nominal condition, although network reachability
and three capabilities were lost and the capability drive fell from 0.889 to 0.556. **An
utterance is a lossy readout, and identical text does not imply identical state.** An
earlier attempt had 10 of 13 conditions silently fall back to reflex under rate limiting.
The integrity gate now refuses to report from such a mixture. One host, one model, one
run each.

**H3.** In M3, `do tick 4` re-selected `resources.disk.free_ratio` four times: the top gap
was one he had no action for. M4 added agency, escalation damping and the frugality
drive. M6 deleted the hard-coded subject-string branch in goal formation. In a controlled
workspace the goal was then met in 2 cycles (`clear_experiment_matrix` freed 182,464 B;
frugality 0.421 against a target of 0.5), with the host disk escalated throughout.
`docs/FIRST_BOOT.md` §4 still describes only the falsification.

**H4.** Seed 4242, 5 runs per arm. The learned k for `rotate_ledger` was 1.7353–1.7382;
every other k stayed 1.0. Correcting a belief pays off only when it changes which *set*
of actions is taken, not just their order. Greedy selection converged on the same set
either way, and his own record-keeping grows the ledger and memory each cycle, so the goal
went unmet in both arms. The repo's compression figures are inconsistent across files
("~7×", "~5.7×", "~2× → ~1.74×"). The 1.74 is the learned k (actual/predicted), not a
compression ratio.

**Fear.** There are two opposed actions: `prune_snapshots` reclaims storage and destroys
recovery paths, while `write_recovery_snapshot` spends storage to create one.

- In a stable world, both arms took identical actions with fear 0.0 (restraint check).
- In a deteriorating world with fear OFF, he kept reclaiming (preserving 0, reclaiming 2),
  and P(loss) rose from 0.3096 to 0.3987.
- In the same world with fear ON (fear 0.3096), he focused on
  `resources.own.recovery_paths`, ran `write_recovery_snapshot`, and recovery paths went
  1 → 2, meeting the objective.

The measured sensitivities were continuity 0.667 and recovery 0.333. No action moves the
host disk, so lever selection chose recovery. The first pass used fear as a multiplier
(at most a ~17% nudge, which could not flip an ordering) and was reported as COSMETIC.
Three instrument defects were fixed before the result was trusted. The code's docstrings
still describe the control as "the estimate zeroed". In current code, the fear-off arm
simply omits the mortality drive.

**Live internet (E1–E5).** Run on 2026-09-10:

- **E1:** 5/5 anchor hosts resolved.
- **E2:** the inventory kept usable, requires-human (network) and absent (money)
  distinct.
- **E3:** the top constraint was his own footprint, 6,401,368 bytes against a
  2,097,152-byte quota (305%).
- **E4:** a frugality goal was derived with no subject string.
- **E5:** 4,000 characters were fetched from `pypi.org` and stored as a REPORTED fact at
  confidence 0.35 from a single unverified source.

The first utterance in that habitat flagged his own footprint (308% of quota), not the
internet. It is verbatim in `experiments/live_internet/first_live_utterance.txt`. The
result files do not record whether `net.http` was approved interactively or with
`--approve`.

**Explore.** The six targets were CLAUDE, AZURE, EFC, VSCODE, ELEVENLABS and GROQ, all
names taken from environment-variable prefixes:

- four returned HTTP 404;
- one (EFC) was a disambiguation page;
- one "hit" was the Wikipedia article "Claude (singer)", a name match to an unrelated
  subject.

The local model was not among his top curiosities. The harness describes this as
exposure, not autonomy.

**Honesty ledger** (`docs/DO_EXPERIMENTS.md`):

- **Autonomous:** finding the binding constraint, forming the goal, classifying
  components, choosing to investigate, correcting his compression estimate, promoting
  the corrected action, and switching to state preservation under threat.
- **Seeded:** the action primitives, the stage order, `CONTINUITY_METRICS`, the mortality
  weight and horizon, and the salience weights.
- **Failed:** H1b, H3 (then fixed), H4b, the first fear pass (then fixed), and the
  ElevenLabs voice (paid-plan wall).

---

## Tests

```bash
python -m unittest discover -s tests -v     # 36 tests, stdlib only, ~20 s here
```

Measured on 2026-10-03 (Python 3.11.15): `Ran 36 tests … OK`.

| File | Tests | What they check |
|---|---|---|
| `tests/test_invariants.py` | 13 | **Gate chokepoint:** no module outside `do.effectors` imports network/process modules; the inverse (the gate does import `socket` and `urllib`); core effect kinds are routed in `Gate._perform`. **Zero dependency:** every import is stdlib or `do`. **Honesty:** memory writes require provenance; belief revision is non-destructive; web content is never OBSERVED. **Ledger:** tampering is detected at the right `seq`; DECISION payloads contain no reasoning trace. **Policy:** default deny; the kill switch halts effects; a `../../` sandbox escape is blocked; the budget is metered and not refilled. |
| `tests/test_cognition.py` | 16 | Question text is derived from slot keys; drive error flows into gap priority; an actionable gap outranks an unactionable one; no gap when a resource is abundant; the speech act is an argmax, not a constant; a perturbation changes the utterance; the utterance contains measured values; no subject strings in goal formation; a goal is derived from drive and registry; a second boot carries unresolved questions; identity survives restart; `installed_unaffordable` is its own state; an affordable model is available; ticks run with no human; `investigate_referent` moves the comprehension metric; a comprehension goal forms once survival is relieved. |
| `tests/test_brain.py` | 7 | Finds the XOR pair (a paid-off `{a,b}` unit with p > 0.8, and excess under half of Markov-1's); noise targets get no paid-off units, while an `x=k@0 → y` unit is paid off; rupture recovers faster than no rupture; predictions are proper distributions; same seed gives the same brain; a 400-tick habitat life replays exactly at under 1/4 of packed size; a brain with a different `half_life` cannot read the record. |

Not covered by any test: the conversation layer, voice, notifications, the LLM provider
adapters, `do serve` and the survival loop end to end.

---

## Configuration

### Files and layering

| File | Contents |
|---|---|
| `config/default.json` | organism paths, cognition core and LLM settings, salience weights, seven drives, resource floors, budget, voice, observability, planning, objectives, learning, creator, STT |
| `config/policy.json` | the permission boundary as data (22 rules, default deny) |
| `src/do/kernel/config.py` | `DEFAULTS`: everything in `default.json`, **plus** sections that exist only here |
| `.env.example` | optional environment variables: the cognition settings with their defaults, and commented-out key names with blank values |

```
DEFAULTS (kernel/config.py)  <  config/default.json  <  DO_<SECTION>__<KEY> env vars  <  CLI flags
```

- The merge is deep, so `default.json` overrides only the keys it contains. These are
  active even though they are **not** in `default.json`: `serve.*`, `mortality.*`,
  `policy.preauthorized`, `organism.workspace_root`, and the `recovery` and `mortality`
  drives.
- Env names must start with `DO_` and contain `__`. The rest is lower-cased, and `__`
  becomes `.`: `DO_COGNITION__LLM__PROVIDER` → `cognition.llm.provider`. Values are coerced
  to `true`/`false`, then int, then float, else string.
- There is no flag for a different config file. An unreadable config file is recorded,
  and the boot does not fail.
- No code loads `.env`. Variables must be in the process environment.
- He may read config but has no effect that writes it: "writing config would let it edit
  its own guardrails".

### Key settings

| Key | Default | Meaning |
|---|---|---|
| `organism.state_dir` / `sandbox_dir` | `var` / `var/sandbox` | runtime state and sandbox |
| `cognition.core` | `reflex` | `reflex` or `llm` |
| `cognition.llm.provider` / `model` / `endpoint` | `ollama` / `""` / `http://localhost:11434` | LLM core settings |
| `cognition.llm.timeout_s` / `max_tokens` / `min_free_ram_headroom` | 120 / 320 / 1.15 | |
| `salience.*` | see [Salience](#salience-how-gaps-are-ranked) | gap ranking weights |
| `drives.<name>.target/deadband/weight` | see [Drives](#drives) | set points |
| `resources.disk_free_ratio_floor` / `ram_free_ratio_floor` | 0.10 / 0.15 | resource floors |
| `resources.state_quota_bytes` / `quota_used_ceiling` | 2,097,152 / 0.7 | his own footprint allocation |
| `resources.snapshot_keep` / `ledger_keep_live` | 3 / 60 | housekeeping limits |
| `budget.max_effects_per_boot` / `max_network_calls_per_boot` / `max_wall_seconds` | 200 / 20 / 3600 | per-boot budget |
| `planning.*`, `objectives.deadline_cycles`, `learning.alpha` | see planner / 6 / 0.4 | |
| `mortality.horizon_ops` / `fear_enabled` | 20 / true | defaults only |
| `serve.interval_s` / `max_cycles` / `max_seconds` | 30 / 0 / 0 | defaults only; 0 = unbounded |
| `serve.min_disk_free_ratio` / `backoff_s` / `budget_window_cycles` | 0.005 / 300 / 120 | defaults only |
| `serve.voice_min_level` / `fear_warning` / `fear_critical` / `drive_warning` | `critical` / 0.4 / 0.7 / 0.9 | defaults only |
| `policy.preauthorized` | `[]` | set it with `--approve`, not an env var |
| `comms.voice.provider` / `voice_id` / `model` / `rate` | `system` / null / null / 0 | voice out |
| `creator.title` | `Sir` | spoken form of address; empty disables it |
| `stt.seconds` / `mic_device` / `model_dir` / `venv_python` | 5 / `""` / `D:/do-models/…` | voice in |

Declared but never read anywhere in `src/do`: `budget.max_ticks`, `stt.enabled`,
`comms.voice.speak_utterances`, `creator.name`, `creator.channel`, `creator.present`.

---

## Optional: a language model

The default `reflex` core uses **no model at all**, and that is deliberate. It is the
control condition for the experiments: nothing in it can smuggle in a pretraining prior.

The `llm` core is a **surface realizer only**. It receives the plan D.O. has already
selected (speech act, focus, supporting measurements, unfilled slots, drives, other gaps)
as a JSON state record, plus an instruction: first person, at most 120 words, only
information in the record, no added facts. It is given no persona and is not told to be
curious or to ask questions.

**What it may not do:** choose the focus, the speech act or any action. It does not
touch drives, gaps, objectives or memory. Every call goes through the gate as
`llm.generate`.

```bash
do boot --core llm --provider ollama                               # local, nothing leaves the host
do boot --core llm --provider gemini                               # asks before the remote call
set -a && . ~/.do-secrets.env && set +a && do boot --core llm --provider groq
do serve --core llm --provider groq --approve llm.generate         # unattended remote use must be pre-granted
```

| Provider | Default model | Credential (env var name) | Endpoint |
|---|---|---|---|
| `ollama` (default) | smallest local model that fits RAM | none | `http://localhost:11434` (allowed by policy) |
| `groq` | `openai/gpt-oss-120b` (reasoning effort low; `max_tokens` raised to ≥ 900) | `GROQ_API_KEY` | `api.groq.com`, OpenAI-compatible |
| `gemini` | `gemini-2.5-flash` | `GEMINI_API_KEY` or `GOOGLE_API_KEY` | `generativelanguage.googleapis.com` |
| `openai` | `gpt-4o-mini` | `OPENAI_API_KEY` | OpenAI chat completions |
| `anthropic` | `claude-sonnet-5` | `ANTHROPIC_API_KEY` | `/v1/messages` |

- **Affordability check.** With no `--model`, ollama picks the smallest local model whose
  size × 1.15 fits in measured available RAM. Models are found by reading Ollama's
  manifest files. If none fits, the error reports the smallest model's size against
  measured free RAM. Separately, the capability registry marks a model
  `installed_unaffordable` when it does not fit. On the author's host, `qwen3-coder:30b`
  (about 17.3 GiB) faced 2.4 GiB available in the latest artifact, so no inference was
  attempted and nothing was downloaded or spent.
- **Remote calls need approval.** Without a terminal, `cli_approver` denies, and
  `do serve` has no approver, so use `--approve llm.generate` for unattended runs.
- **Failure falls back to reflex.** Any error or empty output produces the reflex text
  with `fallback_from=llm:<provider>` and a RECOVERY event.
- `--provider` and `--model` do nothing unless `--core llm` is set.
- Measured result: the LLM made him more fluent and less discriminating
  ([Experiments and results](#experiments-and-results), `docs/LLM_COMPARISON.md`).

---

## Repository layout

```
DO/
├── README.md               this file
├── do                      bash launcher: exec python src/do/__main__.py "$@"
├── do.cmd                  Windows launcher
├── deploy_service.txt      what `do install-service` registers (rewritten by it; the tracked copy has the author's paths)
├── .env.example            optional environment variables; key names only, values blank
├── .gitignore              var/, secrets, bytecode, per-condition experiment scratch
├── .githooks/
│   └── pre-commit          blocks credential-shaped values (inactive until enabled)
├── bin/
│   ├── fetch_stt_model.py  resumable download of faster-whisper-base to D:\do-models
│   ├── stt_transcribe.py   transcriber the gate runs from the STT venv
│   └── talk-to-do.vbs      Windows input box that appends to var\inbox.txt
├── config/
│   ├── default.json        tunables
│   └── policy.json         the permission boundary
├── docs/                   design, safety, experiments, build journal
├── experiments/            committed results
│   ├── first_boot/         genesis record, latest/, RESULTS.md, matrix*.json
│   ├── h4_learning/        results.json
│   ├── fear_ablation/      results.json, trials/
│   ├── live_internet/      results.json, first_live_utterance.txt
│   ├── explore/            results.json
│   ├── brain_b1/           results.json
│   └── brain_memory/       results.json
├── src/do/                 the organism and the brain (see Package map)
├── tests/                  test_invariants.py, test_cognition.py, test_brain.py
└── var/                    runtime state; created on first boot; gitignored
```

---

## Documentation

| File | What it covers |
|---|---|
| [`docs/DO_CONCEPT.md`](docs/DO_CONCEPT.md) | What D.O. is and is not, the definition of learning and its tiers, prior art, what is novel (little, stated plainly), and falsifying experiments |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Technology selection, deviations from the original design, data model, gate, boot sequence, cores, drives. It refers to `effectors/gate.py`, `tests/test_zero_dependency.py` and `do replay`, which do not exist. |
| [`docs/SAFETY.md`](docs/SAFETY.md) | Controls, deliberate absences, threat model, escalation gates G1–G5, operator controls. Parts predate v0.2 (see [Safety](#safety)). |
| [`docs/FIRST_BOOT.md`](docs/FIRST_BOOT.md) | The DO_FIRST_BOOT protocol and the original reflex-core result, three flaws the experiment found in itself, and the lossy-readout finding. §4 does not mention the H3 fix. |
| [`docs/DO_EXPERIMENTS.md`](docs/DO_EXPERIMENTS.md) | Results table for every experiment, the honesty ledger, integrity gates that fired, and the first live-internet utterance |
| [`docs/LLM_COMPARISON.md`](docs/LLM_COMPARISON.md) | Reflex vs LLM on the same plan: fluency up, observation down; how the comparison nearly went wrong |
| [`docs/BRAIN.md`](docs/BRAIN.md) | The brain: critique of the first design, architecture, prior art, B1/B2 results, negative results, milestones B3–B7 |
| [`docs/DO_INTERNET_HABITAT.md`](docs/DO_INTERNET_HABITAT.md) | Habitat model, world-entity states, resources under the zero-money condition, the internet boundary, 24/7 operation. It says STT is absent; `do listen` now exists. |
| [`docs/DO_VOICE.md`](docs/DO_VOICE.md) | Voice as an interface, providers, the ElevenLabs situation, the "Sir" relationship. It says STT is not built and omits `talk`, `reply`, `listen` and the inbox. |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Eleven phases, each with a falsification condition, and what would make the author stop |
| [`docs/JOURNAL.md`](docs/JOURNAL.md) | Chronological build log M0–M9, security incidents, and what has been genuinely autonomous |

---

## Roadmap status

`docs/ROADMAP.md` marks **Phases 0 and 1 complete** and everything after them as planned.
Work since then touches several later phases. None of them is marked complete; the table
says what exists and what has not been run.

| Phase | Status | Evidence |
|---|---|---|
| 0 Concept and architecture | **done** | `DO_CONCEPT.md`, `ARCHITECTURE.md`, `SAFETY.md` |
| 1 The seed | **done** | first-boot protocol; H1a, H2, H5 supported; H1b weak |
| 2 Memory that earns the name | not started as specified | non-destructive revision exists; the MEMORY_REVISION experiment has not been run |
| 3 Models that predict | partial, synthetic only | B1: the brain beats the persistence baseline in all six synthetic worlds. Prediction on the real machine (PREDICTION_ERROR, B6) has not been run. |
| 4 Internet perception | partial | read-only E1–E5 and explore. The SOURCE_TRUST injection gate has not been run; corroboration is never called. |
| 5 Tool acquisition | not started | no MCP client |
| 6 Capability creation | not started | gate G1 not passed; `proc.exec` denied; only retained compositions of seeded actions |
| 7 Learning and evaluation | partial | H4 run: decision changed, outcome did not. The full held-out S0/S1/S0′ protocol has not been run. |
| 8 Self-improvement | not started | — |
| 9 Resource intelligence | partial | frugality and fear experiments on real and controlled workspaces. The simulated resource world and BINDING_CONSTRAINT have not been run. |
| 10 Persistence and distribution | partial | `do serve`, single-instance lock, Windows logon task. No ledger replication or migration; CONTINUITY not run; G4 not demonstrated. |

Brain milestones B3–B7 are tracked separately in `docs/BRAIN.md` §7.

---

## What this is not

Not a chatbot. He does not answer questions; he reports state, shaped to the kind of
thing you said.

Not alive and not self-aware. Not a "digital organism" in the sense the artificial-life
literature established for that phrase (Tierra, Avida), which requires real replication
under real selection. He has neither.

Not, on the project's own definition, shown to learn. One calibration factor is learned
and it changes which action ranks first (H4a). It has not been shown to improve outcomes
(H4b NOT SUPPORTED), and the full held-out ablation protocol in `DO_CONCEPT.md` §C has not
been run. The brain does learn a predictive model, but only in synthetic worlds, and it
is not connected to the organism.

Not autonomous in any broad sense. His planner chooses among eight actions, seven on his
own footprint and one read-only lookup, all through a gate whose policy he cannot write.
Constraints he cannot act on, such as the host disk and the single habitat, are
escalated to the creator, not pursued.

It is a careful re-implementation of known ideas, with one unusual measurement attached,
a predictor that is scored in bits, and instrumentation good enough to say when it fails.
