"""Settings. Nothing here is machine-specific -- the API token is generated on first run
into the user's own config directory and is never part of the repository.
"""
from __future__ import annotations
import copy
import json
import os
import secrets
import sys

from .platforms import backend

APP_NAME = "MushroomPet"
APP_DIR = backend.app_data_dir()
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
INBOX_DIR = os.path.join(APP_DIR, "inbox")
TOKEN_PATH = os.path.join(APP_DIR, "api_token.txt")
LOG_PATH = os.path.join(APP_DIR, "mushroompet.log")

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(PKG_DIR)


def _find_assets() -> str:
    candidates = [os.path.join(ROOT_DIR, "assets")]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.insert(0, os.path.join(meipass, "assets"))
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    candidates += [os.path.join(exe_dir, "assets"),
                   os.path.join(exe_dir, "_internal", "assets")]
    for c in candidates:
        if os.path.exists(os.path.join(c, "manifest.json")):
            return c
    return candidates[0]


ASSET_DIR = _find_assets()

SIZES = {"tiny": 0.55, "small": 0.72, "medium": 0.92, "large": 1.20, "huge": 1.60}
SPEEDS = {"snail": 0.45, "calm": 0.75, "normal": 1.0, "brisk": 1.45, "hyper": 2.2}

ACTIVITY = {
    "still":  {"wander": 0.00, "idle": (10.0, 22.0), "trip": 0.10, "hop_delay": 1100},
    "chill":  {"wander": 0.26, "idle": (6.5, 15.0),  "trip": 0.30, "hop_delay": 800},
    "calm":   {"wander": 0.48, "idle": (4.5, 10.0),  "trip": 0.55, "hop_delay": 620},
    "lively": {"wander": 0.74, "idle": (2.2, 5.5),   "trip": 1.00, "hop_delay": 450},
}
CHATTINESS = {
    "quiet":  {"idle_gap": (0.0, 0.0),    "click": 0.20},
    "normal": {"idle_gap": (55.0, 130.0), "click": 0.85},
    "chatty": {"idle_gap": (25.0, 60.0),  "click": 1.00},
}
EFFECTS = {"off": 0.0, "light": 0.45, "normal": 1.0}

# Optional launchers. Set "enabled": true on any of these, or add your own to custom_apps.
EXAMPLE_PRESETS = [
    {"id": "editor", "label": "VS Code", "enabled": False,
     "search": ["visual", "studio", "code"], "mac_app": "Visual Studio Code"},
    {"id": "browser", "label": "Firefox", "enabled": False,
     "search": ["firefox"], "mac_app": "Firefox"},
    {"id": "terminal", "label": "Terminal here", "enabled": False,
     "command": ""},
]

DEFAULTS = {
    "config_version": 1,

    # appearance / behaviour
    "size": "medium",
    "speed": "calm",
    "activity": "calm",             # still | chill | calm | lively
    "chattiness": "normal",         # quiet | normal | chatty
    "effects_level": "light",       # off | light | normal
    "shadow": True,
    "click_reactions": True,
    "sounds": True,
    "greet_on_start": True,
    "sleep_after_s": 300,

    # where he walks. "above" stands on the top edge of the taskbar/Dock and is always
    # visible; "taskbar" overlaps the bar itself (Windows only, can lose the z-order fight)
    "walk_layer": "above",
    "auto_fix_layer": True,
    "always_on_top": True,
    "topmost_interval_ms": 300,
    "high_res_timer": True,

    # monitors
    "follow_mouse_monitors": True,
    "locked_screen": None,
    "hop_cooldown_ms": 2600,

    # desktop interaction
    "window_walking": True,
    "climbing": True,

    # fire costume
    "fire_seconds": 30,
    "fire_persistent": False,

    # notifications
    "notify_sound": True,
    "notify_seconds": 11,
    "reminders": [],
    "pomodoro": {"enabled": False, "work_min": 25, "break_min": 5,
                 "phase": "work", "next_ts": 0},

    # local control API -- off by default; turn it on from the menu if you want it
    "api_enabled": False,
    "api_port": 7477,
    "api_token": "",

    # your own menu entries, e.g.
    #   {"label": "Notes", "target": "C:/notes.exe", "args": "", "kind": "app"}
    #   {"label": "Docs",  "target": "https://example.com", "kind": "url"}
    "custom_apps": [],
    "presets": EXAMPLE_PRESETS,
    "terminal_command": "",
}


def _deep_fill(dst: dict, src: dict) -> dict:
    for k, v in src.items():
        if k not in dst:
            dst[k] = copy.deepcopy(v)
        elif isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_fill(dst[k], v)
    return dst


class Config:
    def __init__(self):
        os.makedirs(APP_DIR, exist_ok=True)
        os.makedirs(INBOX_DIR, exist_ok=True)
        self.data = copy.deepcopy(DEFAULTS)
        self.file_version = None
        self.load()
        if self.data.get("api_enabled") and not self.data.get("api_token"):
            self.data["api_token"] = secrets.token_urlsafe(18)
            self._write_token()
        if self.file_version is None:
            self.save()          # first run: write the file so it's there to edit

    def _write_token(self):
        try:
            value = self.data.get("api_token", "").encode("utf-8")
            fd = os.open(TOKEN_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                try:
                    os.fchmod(fd, 0o600)
                except AttributeError:
                    pass
                with os.fdopen(fd, "wb") as fh:
                    fd = -1
                    fh.write(value)
            finally:
                if fd != -1:
                    os.close(fd)
            try:
                os.chmod(TOKEN_PATH, 0o600)
            except OSError:
                pass
        except OSError:
            pass

    def ensure_token(self):
        if not self.data.get("api_token"):
            self.data["api_token"] = secrets.token_urlsafe(18)
            self.save()
        self._write_token()
        return self.data["api_token"]

    # dict-ish access
    def __getitem__(self, k):
        return self.data[k]

    def __setitem__(self, k, v):
        self.data[k] = v
        self.save()

    def get(self, k, default=None):
        return self.data.get(k, default)

    def load(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if isinstance(raw, dict):
                # read the version from the file before defaults are merged in, otherwise
                # a new default masks the old value and migrations silently never run
                self.file_version = int(raw.get("config_version", 1))
                self.data = _deep_fill(raw, DEFAULTS)
        except (OSError, ValueError, TypeError):
            pass

    def save(self):
        try:
            os.makedirs(APP_DIR, exist_ok=True)
            tmp = CONFIG_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, indent=2)
            os.replace(tmp, CONFIG_PATH)
        except OSError:
            pass

    # convenience
    @property
    def scale(self) -> float:
        return SIZES.get(self.data.get("size"), 0.92)

    @property
    def speed_mult(self) -> float:
        return SPEEDS.get(self.data.get("speed"), 1.0)

    @property
    def activity(self) -> dict:
        return ACTIVITY.get(self.data.get("activity"), ACTIVITY["calm"])

    @property
    def chatter(self) -> dict:
        return CHATTINESS.get(self.data.get("chattiness"), CHATTINESS["normal"])

    @property
    def fx(self) -> float:
        return EFFECTS.get(self.data.get("effects_level"), 0.45)

    @property
    def over_taskbar(self) -> bool:
        return self.data.get("walk_layer") == "taskbar"
