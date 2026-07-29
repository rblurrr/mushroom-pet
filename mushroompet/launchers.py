"""Opening apps, files and links, through the platform backend.

Nothing is hard-coded to a particular application. Users add entries via the menu
("Add an app…" / "Add a link…") which land in `custom_apps`, or enable one of the example
presets in the config file.
"""
from __future__ import annotations
import os
import sys
from urllib.parse import urlparse

from .platforms import backend

_cache: dict[str, str] = {}


def resolve_preset(preset) -> str:
    """Find the executable/app bundle for a preset, caching the result."""
    pid = preset.get("id") or preset.get("label", "")
    if pid in _cache:
        return _cache[pid]
    found = ""
    explicit = preset.get("target", "")
    if explicit and os.path.exists(explicit):
        found = explicit
    elif backend.name == "macos" and preset.get("mac_app"):
        found = backend.find_app(*preset["mac_app"].split())
    if not found and preset.get("search"):
        found = backend.find_app(*preset["search"])
    _cache[pid] = found
    return found


def launch_preset(preset) -> tuple[bool, str]:
    if preset.get("command"):
        return backend.open_terminal(preset["command"])
    path = resolve_preset(preset)
    if not path:
        label = preset.get("label", "that app")
        return False, (f"Couldn't find {label} on this computer. "
                       "Right-click me -> Open -> More... -> Add an app to point me at it.")
    return backend.open_path(path)


def launch_custom(entry) -> tuple[bool, str]:
    target = entry.get("target", "")
    parsed = urlparse(target)
    if entry.get("kind") == "url" or parsed.scheme:
        if parsed.scheme.lower() not in ("http", "https"):
            return False, "only http and https URLs are allowed"
        ok, err = backend.open_path(target)
    else:
        ok, err = backend.open_path(target, entry.get("args", ""))
    if ok:
        return True, ""
    return False, f"Couldn't open {entry.get('label') or target} ({err})"


def launch_terminal(cfg) -> tuple[bool, str]:
    cmd = (cfg.get("terminal_command") or "").strip()
    if not cmd:
        return False, ("No terminal command set. Right-click me -> Open -> More... -> "
                       "Set terminal command.")
    return backend.open_terminal(cmd)


def open_config_folder():
    from .config import APP_DIR
    backend.open_path(APP_DIR)


def entry_script() -> str:
    from .config import ROOT_DIR
    return os.path.join(ROOT_DIR, "run.py")


def install_autostart():
    return backend.install_autostart(entry_script())


def remove_autostart():
    return backend.remove_autostart()
