# D.O. Voice & Interaction

How to talk to D.O., how it talks back, and the one rule the whole design turns on.

---

## The rule: voice is an interface, never the organism

`M5` (the reflex-vs-LLM comparison) established this empirically, not as a preference:
a language model made D.O. *sound* sharper while carrying measurably less of its state.
So everything here renders an utterance cognition has **already produced**. Nothing in
the voice or chat layer decides anything, and nothing in it can change what D.O. would
have said. This matters for a future experiment: when a stronger model is plugged in,
we can ask *"did D.O. become more capable, or only better at explaining itself?"* — and
the answer is meaningful only because speech sits strictly on top of state.

```
state  →  goal  →  action  →  outcome  →  learning        (the organism; canonical)
                                              │
                                        utterance           (chosen by cognition)
                                              │
                                    text / voice / chat      (interface; this doc)
```

---

## Talking to him

All commands run from the project root:

```bash
cd ~/DO
```

### Text conversation — `do chat`

```bash
python src/do/__main__.py chat
```

Opens an interactive session. Type anything; `/commands` are special:

| you type | what happens |
|---|---|
| any statement | recorded with your authorship as a `reported` belief; attached to an open question if it matches one; he replies from his state |
| `/status` | drives, capabilities, budget, memory |
| `/gaps` | what he does not know, ranked |
| `/why` | why he chose what he did this boot |
| `/tick [n]` | run n metabolic cycles |
| `/quit` | leave — his state persists; you are not ending him |

The session **only opens on a real terminal**. Piped or redirected input has no human
attached, so — by the same rule the unattended loop follows — he declines to converse
rather than talk to no one. This is deliberate, not a limitation.

His replies address you as **Sir** (see the relationship model below).

### Voice — `do say`

```bash
python src/do/__main__.py say "what are you tracking?"
python src/do/__main__.py say          # speaks his current utterance
```

He renders the line through a synthesiser and plays it aloud. Verified working on this
host via the local system voice.

### Unprompted — while serving

When run 24/7 (`do serve`), he speaks aloud **only** at CRITICAL level, so he does not
chatter, and logs everything else to the outbox (`do outbox`). See `DO_INTERNET_HABITAT.md`.

---

## Providers, and why the free one is the default

Voice is provider-independent: a `VoiceInterface`, with concrete implementations behind
it. The credential is read from the environment at call time and **never stored, logged,
or written to memory**.

| provider | status | cost | notes |
|---|---|---|---|
| `system` | **working, default** | free | the host OS synthesiser (Windows SAPI via a gated `tts.local` effect); nothing leaves the machine |
| `elevenlabs` | implemented, blocked | paid | see below |
| `null` | — | — | says explicitly that nothing was spoken |

### The ElevenLabs situation, stated honestly

The ElevenLabs path is fully implemented and the request is well-formed — but on a
**free account** it returns:

> `HTTP 402: Free users cannot use library voices via the API.`

Every premade voice (including the default) now requires a paid plan to use through the
API, and a free-tier key additionally lacks the `voices_read` permission needed to
enumerate which voices *are* allowed. This is the project's own **`money = 0`** condition
biting on its first outward-facing capability — recorded, not worked around.

Two ways to get the ElevenLabs voice specifically:
1. a paid plan (against the zero-money condition; the creator's call), or
2. a custom/cloned `voice_id` the free tier permits — set `comms.voice.voice_id` and
   `comms.voice.provider = elevenlabs`.

Until then, `system` is the default and works today. The choice of a nicer voice is not
a working-vs-not difference.

### Adding a provider

Implement `speak(text, gate, config) -> Spoken`, route audio through the gate as a
`tts.*` effect, and register it in `voice.build()`. No caller changes.

---

## Speech recognition (STT) — not built, and why

The brief specifies a full `you speak → STT → D.O.` loop. STT is **not implemented**.
The honest reasons: the only local option is Whisper (~1.5 GB of weights) and the disk
is at ~2.3% free; a cloud STT needs another paid account. So input is text today, output
is text and voice. This is a real gap, stated rather than stubbed with something that
does not work.

---

## The creator relationship — "Sir"

`creator.title` lives in the relationship model (`config`), **not** in a template.
Change it there and D.O. addresses the creator differently everywhere; set it to null
and he uses no title at all. The only templated part is *placement* — the title is
applied once at the front of a direct address, never sprinkled through every sentence
(a title on every line reads as a tic, not a relationship), and it is skipped when the
opening clause already contains it.

```
"I have completed the experiment."      →  "Sir, I have completed the experiment."
"Hello, Sir. I am operational."         →  unchanged (already addressed)
"resources.disk.free_ratio is low."     →  "Sir, resources.disk.free_ratio is low."
```

Both bugs in this path — a scope crash in `do say` and a doubled title — were found by
*running it*, not reading it. The voice path had never been exercised end to end until
then.

---

## One state, every channel

CLI, text, voice, and the serve loop all operate on the **same** persistent D.O. —
one identity, one ledger, one memory. The interface never forks the organism. Closing a
chat, or the machine, does not end him; the next boot resumes the same history.
