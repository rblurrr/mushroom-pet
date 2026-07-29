# Mushroom Pet

A desktop companion that walks along the bottom of your screen, hops between monitors when
you move your mouse, climbs your open windows, reacts when you click it, and launches
whatever apps you point it at.

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

**Mushroom** — Come here · Wave · Jump · Hop to other monitor · Climb a window / Get down
· Sleep / Wake · Sit still · Fire mode (go fiery, stay fiery, duration, *Run wild*)

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
`jump`, `hop`, `climb`, `getdown`, `rampage`, `fire_on`, `fire_off`, `hide`, `show`, `quit`.

**No-network alternative:** drop a JSON file into the `inbox` folder inside your config
directory, e.g. `{"action": "say", "text": "hello"}`. It's executed within a second and
deleted. Works whether or not the HTTP server is enabled.

**Privacy and trust:** window titles and geometry are read locally into memory only; they are not transmitted and there is no telemetry. The API is loopback-only and `/health` is intentionally unauthenticated; every other route requires the generated token via `X-Token` or `Authorization: Bearer <token>`. Anyone who can read the inbox or obtain the token can send commands. Terminal commands, configured launchers, and app entries execute locally; only add trusted commands and applications.

## Where settings live

| | |
|---|---|
| Windows | `%APPDATA%\MushroomPet\` |
| macOS | `~/Library/Application Support/MushroomPet/` |
| Linux | `~/.config/mushroompet/` |

Contains `config.json`, the generated `api_token.txt`, a log, and the `inbox` folder.
Delete `config.json` to reset. Nothing is written inside the repository.

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
