# Mushroom Pet

A desktop companion that walks along the bottom of your screen, hops between monitors when
you move your mouse, climbs your open windows, reacts when you click it, and launches
whatever apps you point it at. Left on his own he also keeps a small daily plan and drafts
ways to earn. Anything that would post, send a message, or spend money waits until you say yes.

Windows and macOS. Python + PySide6, no build step.

```
┌─ he lives here ────────────────────────────────────────────┐
│                                        ╭──────────────╮    │
│                                        │ nothing to    │   │
│                                        │ report        │   │
│                                        ╰───────╮╭─────╯    │
│                                            🍄            │
└─────────────────────────── taskbar ────────────────────────┘
```

## Install

```bash
git clone https://github.com/rblurrr/mushroom-pet.git mushroom-pet
cd mushroom-pet
pip install -r requirements.txt
python run.py
```

Or double-click a launcher, which installs the dependency for you on first run:

| | |
|---|---|
| Windows | `scripts\run_windows.bat` |
| macOS | `scripts/run_macos.command` |
| Linux | `scripts/run_linux.sh` (works, but untested) |

**macOS extra, optional:** `pip install pyobjc-framework-Quartz pyobjc-framework-Cocoa`.
Quartz lets him read your open windows so he can walk on and climb them; Cocoa hides his
Dock tile. Without them everything else still works — he just stays on the screen edge.

## Sparky's World

Sparky is an AI character, drawn as a plug, who lives in Off-Peak, an imagined town. The
Electrician is R. The town is a browser page on top of the same autonomy brain as the
desktop pet: the 15-minute loop, the approval queue, the hash-chained ledger, and the
optional model. It does not keep a second copy of that machinery.

From the repo:

```bash
python -m sparky
```

Then open http://127.0.0.1:8765 . One process serves the page and the API. It binds to
`127.0.0.1` unless `SPARKY_HOST` is set. `SPARKY_PORT` changes the port (default `8765`).

No model key is required. With nothing configured he still walks, writes the Line Log,
and refuses the things he is supposed to refuse. To let him phrase lines through an
OpenAI-compatible server, use the same variables as the desktop pet:

```bash
MUSHROOM_LLM_BASE_URL=http://127.0.0.1:11434/v1 \
MUSHROOM_LLM_MODEL=llama3.2 \
python -m sparky
```

A failed or missing model call falls back to the scripted voice. The key is not written
into the Line Log.

Weather is real only when you set `SPARKY_LAT` and `SPARKY_LON` (Open-Meteo, no key).
A grid number is read only from `SPARKY_GRID_URL`. If either feed is missing or down,
he says he has not checked. He does not invent the reading.

State lives in `SPARKY_HOME`, or else beside the desktop pet's settings
(`~/.config/mushroompet/sparky` on Linux). The Electrician's token is
`owner_token.txt` in that folder. Owner mode in the page asks for that token.
Saying "I am the Electrician" in the Outlet does not open it.

The camera button asks before it connects. Frames stay in the browser. A short text
description can be sent to him. Nothing is stored unless you tick remember. The green
pill is the on/off indicator. "Step through" puts the camera behind him as an overlay.

```bash
python -m unittest discover -s tests -v
```

Menu → *Start with my computer → Enable* registers a Startup shortcut on Windows or a
LaunchAgent on macOS.

## Controls

| Input | What happens |
|---|---|
| **Single click** | Stops, reacts — a jump, a wave, hearts or a startle — and usually says something |
| **Click and hold** | Pick him up and drag him anywhere, any monitor. Throw him and he arcs, lands and puffs dust |
| **Double click** | Hearts |
| **Triple click** | Fire costume for 30 s: a short roar, then he carries on as normal but flaming. He does *not* run around |
| **Right click** | The menu |
| **Middle click** | Runs to your cursor |
| **Right click → Cursor tricks** | Bounce on the cursor, hang beneath it while it moves, or orbit around it |
| **Scroll wheel on him** | Resize, tiny → huge |
| **Mouse to another monitor** | After ~0.6 s he crouches and leaps across, landing near your cursor |
| **Leave him alone** | Idles, sits, eats, fishes, wanders a little, drops the occasional one-liner, eventually sleeps |

Clicks only register on his actual pixels — empty space around him passes through to
whatever is underneath, and he never takes keyboard focus, so clicking him won't pull you
out of what you're typing.

## He uses your real windows

He reads the open window list a few times a second and treats it as scenery:

- **Walks the top edge** of any window, like a ledge
- **Climbs the sides** of tall windows, clinging sideways to the edge
- **Rides them** — move or resize a window and he stays on it; close it and he falls
- **Lands on lower windows** on the way down instead of always hitting the taskbar
- Only stands on the part of an edge that isn't covered by a window in front of it

Menu → *Windows* toggles walking and climbing, and *Send me to…* picks a window by name.

Window rectangles come back from the OS in physical pixels and are converted to Qt's
logical coordinates. That's exact when every monitor shares one scaling factor; on a
mixed-scaling setup his footing on the non-primary screen can be off by a few pixels.

## Menu

**Open** — starts empty. *More… → Add an app* / *Add a link* adds permanent entries.
*More… → Example launchers* has a few opt-in presets (editor, browser, terminal) that
search your Start Menu or `/Applications` by name.

**Mushroom** — Come here · Wave · Jump · Cursor tricks · Hop to other monitor · Climb a
window / Get down · Sleep / Wake · Sit still · Creator Studio (build locally, approve
anything public, the autonomous plan) · Fire mode (go fiery, stay fiery, duration, *Run wild*)

**Notifications** — see below

**Preferences**

- **Size**, **Speed**
- **How busy** — `still` · `chill` · `calm` (default) · `lively`
- **How chatty** — `quiet` · `normal` (default) · `chatty`
- **Sparkles & embers** — `off` · `light` (default) · `full`
- **Monitors** — follow the mouse, or lock him to one screen
- **Walking lane** — on top of the taskbar/Dock (default), or overlapping the taskbar (Windows)
- **Windows** — walk on window edges, climb their sides, send him somewhere
- **Behaviour** — click reactions, shadow, sounds, always-on-top, smooth motion, sleep timer

## Notifications

He only announces things you set up. Nothing is polled from any online account.

- **Remind me in…** — `10m`, `1h30`, `45`, or `14:30`
- **Remind me daily at…** — every day, or weekdays only
- **Nag me every…** — recurring, e.g. stand up every 45 minutes
- **Pomodoro** — 25/5, 50/10, 90/15
- **Mute non-urgent**, and a **Recent** list of the last 20

When one fires he stops, reacts, beeps and shows it in a speech bubble. Urgent ones make
him jump and turn the bubble red.

## Control API (optional, off by default)

Turn it on under *Control API → Enable local API*. It binds `127.0.0.1` only and requires
a token that's generated on your machine at first use — never in this repo.

```python
import json, os, urllib.request

TOKEN = open(os.path.expanduser("~/.config/mushroompet/api_token.txt")).read().strip()

def send(route, body):
    req = urllib.request.Request(
        f"http://127.0.0.1:7477/{route}", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Token": TOKEN})
    return json.load(urllib.request.urlopen(req))

send("say",    {"text": "build finished in 41s", "mood": "happy"})
send("notify", {"text": "deploy failed", "title": "CI", "urgent": True})
send("do",     {"what": "climb"})
send("reminder_add", {"text": "stand up", "in_minutes": 45})
```

Routes: `POST /say`, `/notify`, `/do`, `/reminder_add` · `GET /state`, `/health`.
Bubble moods: `normal`, `happy`, `urgent`, `fire`, `sleepy`, `info`.
`do` verbs: `react`, `wave`, `happy`, `love`, `look`, `sit`, `sleep`, `wake`, `come`,
`jump`, `hop`, `climb`, `getdown`, `cursor_bounce`, `cursor_hang`, `cursor_orbit`,
`rampage`, `fire_on`, `fire_off`, `hide`, `show`, `quit`.

The same server can drive the autonomous life. These routes need the token too.
`/health` stays open. A token in the query string is ignored.

| | |
|---|---|
| `GET /life` | mood, energy, today's plan, earnings totals, whether a model is configured |
| `GET /life/log` | recent beats |
| `GET /life/plan` | today's plan only |
| `GET /life/earnings` | ledger |
| `GET /life/opportunities` | guessed ways to earn (not money received) |
| `GET /life/memory?q=` | search what he remembers |
| `GET /life/skills` | registered skills |
| `GET /approvals` | the queue. `executed` is false for all of them |
| `POST /life/tick` | run one beat now |
| `POST /life/skill` | `{"skill": "content_ideas", "args": {}}` |
| `POST /life/focus` | `{"niche": "...", "goal": "..."}` |
| `POST /life/enabled` | `{"enabled": false}` turns the loop off |
| `POST /life/pause` | `{"paused": true}` is the emergency stop |
| `POST /approve` | `{"id": "...", "note": "looks fine"}` — records yes, does not publish or spend |
| `POST /reject` | `{"id": "...", "note": "not this"}` — a note is required |
| `POST /remember` | `{"text": "...", "importance": 5}` |
| `POST /earning` | `{"source": "market", "amount": 12.5}` — money that already arrived |

`GET /state` includes a `life` object when the pet is running. The inbox folder accepts
the same life actions (`{"action": "life_tick"}`, `{"action": "remember", "text": "..."}`)
with no HTTP server.

**No-network alternative:** drop a JSON file into the `inbox` folder inside your config
directory, e.g. `{"action": "say", "text": "hello"}`. It's executed within a second and
deleted. Works whether or not the HTTP server is enabled.

**Privacy and trust:** window titles and geometry are read locally into memory only; they are not transmitted and there is no telemetry. The API is loopback-only and `/health` is intentionally unauthenticated; every other route requires the generated token via `X-Token` or `Authorization: Bearer <token>`. Anyone who can read the inbox or obtain the token can send commands. Terminal commands, configured launchers, and app entries execute locally; only add trusted commands and applications.

## Autonomous life

He keeps a day for himself. On a timer (every 15 minutes by default, first beat about
90 seconds after launch) he recovers a little energy, looks at today's plan, and does
one piece of it. You see that as a speech bubble and a small animation, and again in
**Creator Studio → Autonomous life** (today's plan, the activity log, the earnings
ledger, and a local dashboard).

The plan is ordinary local work: three content ideas, a 20-second script, captions, a
product-listing draft, an opportunity to track, a post draft, then one request to
publish. The publish request goes into the approval queue. He does not post it, send
it, or buy anything. Approving a row only records that you said yes. A separate
connector, which this project does not include, would have to perform the outside
action later. He also never invents income. **Log money that came in** is a ledger
you write in yourself.

Turn the loop off under **Autonomous life → Work on its own**, or set
`"life_enabled": false` in `config.json`. **Emergency pause** stops every new creator
action, including the ones you start by hand. **Do the next thing now** runs a beat
immediately. **Set what I'm working toward** is the niche and the goal the plan is
built around. Until you set one, he uses a small default: short creative tools and
desktop companions, earned from drafts you approve.

Energy falls as he works and comes back while he waits (faster if you leave him long
enough that he sits). Under about 22 he rests instead of starting the next item, and
says so.

### A model, if you want one

With no model configured he writes from local templates. That is a complete mode, not
an error. To use an OpenAI-compatible server (OpenAI, Ollama, LM Studio, anything else
that speaks `/v1/chat/completions`), set:

| Variable | Meaning |
|---|---|
| `MUSHROOM_LLM_BASE_URL` | e.g. `https://api.openai.com/v1` or `http://127.0.0.1:11434/v1` |
| `MUSHROOM_LLM_API_KEY` | sent as a bearer token. A local server may omit it |
| `MUSHROOM_LLM_MODEL` | e.g. `gpt-4o-mini` or the name your local server loaded |
| `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` | used only when the `MUSHROOM_*` ones are unset |

Environment variables win. Otherwise he reads `llm.env` in the settings folder
(`KEY=value` lines), then `llm_base_url`, `llm_model`, and `llm_api_key` in
`config.json`. The key is never written into the plan, the dashboard, the audit log,
or a prompt. A public host with no key is left offline. If a call fails, that beat
uses the local templates.

What a model is allowed to see is the niche, the goal, and the last few pieces of
work (ideas, scripts, captions, drafts). Notes you asked him to remember, the
earnings ledger, the approval queue, and the API token are not sent.

`config.json` and `llm.env` live in the settings folder below, which is outside the
repository. Don't put a key in the repo. `.env` files are gitignored in case one
lands in a working copy.

### Skills

A skill is a small object with an `id`, a `title`, a `blurb`, and `run(ctx, args)`.
Register it on the `SkillRegistry` the life loop is holding. The HTTP API can only
run ids that were registered. It will not import or execute code from a request.

```python
from mushroompet.skills import SkillResult

class AffiliateBlurb:
    id = "affiliate_blurb"
    title = "Affiliate blurb"
    blurb = "Draft a disclosure-friendly blurb. Never posts it."
    external = False       # True means the skill only queues an approval
    autonomous = True      # the daily planner may pick it
    records_money = False  # True keeps it out of the planner; money-in is manual

    def run(self, ctx, args):
        text = "Draft only. Not posted."
        return SkillResult(speech=text, summary=text, memory=text, memory_kind="note")
```

`run` may write local files and may `ctx.creator.submit(...)` an external action
(`publish_social`, `publish_github`, `send_message`, `purchase`). Those stop in the
queue. `run` must not post, send, open a checkout, or spend. The planner may schedule
any registered autonomous skill that does not record money, and the only external one
it will schedule is `propose_post`. Purchases, messages, and the earnings skill stay
manual: menu, API, or CLI.

Built in: `content_ideas`, `write_script`, `write_caption`, `draft_listing`,
`track_opportunity`, `draft_post`, `propose_post`, `propose_message`,
`propose_purchase`, `log_earning`.

### Creator Studio

The same core still builds things when you ask. Local creation runs immediately.
Publishing, messages, repositories, and purchases are held for approval, from the
pet menu, the API, or the CLI. Approval does not perform the outside action, and
this module never stores a social token, a GitHub credential, a shipping address,
or a payment method.

```bash
python tools/mushroom_creator.py hub "My project" --brief "A local project hub"
python tools/mushroom_creator.py game "Spore Sprint" --brief "Collect golden spores"
python tools/mushroom_creator.py post-draft "I made a game" --platform x
python tools/mushroom_creator.py post-request "Ready to publish" --platform x
python tools/mushroom_creator.py message-request dm "a friend" "the draft is ready"
python tools/mushroom_creator.py github-request PATH REPO --visibility private
python tools/mushroom_creator.py purchase-request ITEM VENDOR URL 24.99 --reason "Why"
python tools/mushroom_creator.py list --status pending_approval
python tools/mushroom_creator.py approve ACTION_ID --note "Owner reviewed"
python tools/mushroom_creator.py pause       # emergency stop
python tools/mushroom_creator.py verify      # verify the hash-chained audit ledger
python tools/mushroom_creator.py status      # mood, energy, plan
python tools/mushroom_creator.py tick        # one beat, right now
python tools/mushroom_creator.py focus "desk pets" "one useful download"
python tools/mushroom_creator.py --offline tick   # force the local templates
```

Data lives under the settings folder in `creator/`: `mind.json` (identity, mood,
goals), `actions.json`, `audit.jsonl` (append-only hash chain), `life.sqlite`
(memory, plan, activity, opportunities, earnings), `life.json`, `dashboard.html`,
`drafts/`, and `workspaces/`. Generated files are previews. They get no shell and
no automatic network access. The model call, when you configure one, is the only
network the life loop makes, and a failure falls back to the templates.

## Where settings live

| | |
|---|---|
| Windows | `%APPDATA%\MushroomPet\` |
| macOS | `~/Library/Application Support/MushroomPet/` |
| Linux | `~/.config/mushroompet/` |

Contains `config.json`, the generated `api_token.txt`, an optional `llm.env`, a log,
the `inbox` folder, and `creator/` once he has done any work. Delete `config.json`
to reset the settings. Delete `creator/` to reset his memory and the approval queue.
Nothing is written inside the repository.

## Layout

```
run.py                     entry point
mushroompet/
  app.py                   wiring, single-instance lock, tray icon
  pet.py                   window, physics, state machine, input, painting
  desktop.py               open windows -> standable ledges and climbable walls
  effects.py               per-monitor click-through particle overlays
  bubble.py                speech bubbles
  menu.py                  the right-click / tray menu
  launchers.py             opening apps, files and links
  notify.py                reminders, timers, pomodoro, queue
  api.py                   optional local HTTP bridge + inbox watcher
  creator.py               local drafts, approval queue, hash-chained audit log
  life.py                  daily plan, energy, the autonomous beat
  brain.py                 OpenAI-compatible model client, offline when it can't
  memory.py                SQLite memory, plan, ledger, opportunities
  skills.py                income skills and the registry new ones plug into
  assets.py                sprite loading and scaled-pixmap cache
  config.py                settings
  platforms/
    base.py                backend interface + generic fallback
    windows.py             taskbar z-order, native hit testing, EnumWindows
    macos.py               Quartz window list, LaunchAgent, accessory app policy
assets/                    22 animations + icon
tools/                     sprite extraction pipeline (see tools/README.md)
```

Everything OS-specific lives behind `platforms/`. An unrecognised platform gets the
generic backend and still runs — walking, dragging, bubbles, menus, reminders — minus
window climbing and taskbar-layer tricks.

## Notes for anyone reading the code

Three details that took the longest to get right:

**`ctypes` needs `argtypes` on 64-bit Windows.** Without them, ctypes narrows an `HWND` to
a C `int` and calls like `SetWindowPos` silently do nothing. Every binding in
`platforms/windows.py` declares them.

**`HWND_TOPMOST` can't beat the Windows 11 taskbar,** because the taskbar is itself
topmost and within that band whoever was inserted last wins. To overlap the bar he inserts
himself directly above `Shell_TrayWnd` and re-asserts on a short timer. Because the
default lane sits on *top* of the bar, this is only needed for the opt-in overlap mode.

**Repaint cost is what makes a desktop pet feel bad.** Repaints are driven by a dirty
flag, the tick drops to 30 Hz when he's standing still (an idle pet repaints well under
once per second), the particle overlays only invalidate the rectangle holding live
particles instead of the whole screen, and the window snaps to whole pixels while the
sprite is drawn at the sub-pixel remainder so slow walking glides rather than steps.

## Credit and licence

Code is MIT — see `LICENSE`.

The mushroom sprites were AI-generated and cut from those renders with the scripts in
`tools/`. They ship so the app runs out of the box, but AI-generated images sit in an
unsettled area of copyright law, so no warranty is made about their status. If you're
building something you intend to distribute, bring your own art — the extraction pipeline
takes any sprite sheet.
