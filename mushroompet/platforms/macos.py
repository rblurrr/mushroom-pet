"""macOS backend.

Window enumeration needs Quartz, which ships with pyobjc:

    pip install pyobjc-framework-Quartz

Without it the pet still works fully -- it just walks the bottom of the screen instead of
climbing your windows. Quartz reports bounds in points, which already match Qt's logical
coordinates, so no DPI conversion is needed here.
"""
from __future__ import annotations
import os
import subprocess
import plistlib

from .base import Backend, WindowInfo

try:
    from Quartz import (CGWindowListCopyWindowInfo, kCGWindowListOptionOnScreenOnly,
                        kCGWindowListExcludeDesktopElements, kCGNullWindowID)
    _HAVE_QUARTZ = True
except Exception:                                      # pragma: no cover
    _HAVE_QUARTZ = False

try:
    from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
    _HAVE_APPKIT = True
except Exception:                                      # pragma: no cover
    _HAVE_APPKIT = False

SKIP_OWNERS = {"Window Server", "Dock", "Control Center", "Notification Center",
               "Spotlight", "SystemUIServer", "Wallpaper"}

SOUND_OK = "/System/Library/Sounds/Pop.aiff"
SOUND_ALERT = "/System/Library/Sounds/Sosumi.aiff"


class MacBackend(Backend):
    name = "macos"

    def __init__(self):
        self._accessory_done = False

    # ---------------------------------------------------------------- paths
    def app_data_dir(self):
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support",
                            "MushroomPet")

    # ------------------------------------------------------- window plumbing
    def prepare_window(self, widget):
        """Hide the Dock tile so he behaves like a menu-bar accessory, not an app."""
        if self._accessory_done or not _HAVE_APPKIT:
            return
        try:
            NSApplication.sharedApplication().setActivationPolicy_(
                NSApplicationActivationPolicyAccessory)
            self._accessory_done = True
        except Exception:
            pass

    def raise_above_shell(self, widget, over_taskbar=False):
        return False        # Qt's WindowStaysOnTopHint is enough on macOS

    @property
    def supports_native_hittest(self):
        return False        # falls back to the input mask, which works well here

    # ---------------------------------------------------------------- extras
    def beep(self, urgent=False):
        path = SOUND_ALERT if urgent else SOUND_OK
        try:
            if os.path.exists(path):
                subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError:
            pass

    def open_path(self, path, args=""):
        if not path:
            return False, "nothing to open"
        try:
            cmd = ["open"]
            if path.endswith(".app") or os.path.isdir(path):
                cmd += ["-a", path] if path.endswith(".app") else [path]
            else:
                cmd += [path]
            if args:
                cmd += ["--args"] + args.split()
            subprocess.Popen(cmd, start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True, ""
        except OSError as e:
            return False, str(e)

    def open_terminal(self, command):
        safe = command.replace("\\", "\\\\").replace('"', '\\"')
        script = f'tell application "Terminal" to do script "{safe}"\n' \
                 'tell application "Terminal" to activate'
        try:
            subprocess.Popen(["osascript", "-e", script], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True, ""
        except OSError as e:
            return False, str(e)

    def find_app(self, *keywords):
        roots = ["/Applications", os.path.expanduser("~/Applications"),
                 "/System/Applications"]
        for root in roots:
            if not os.path.isdir(root):
                continue
            try:
                for name in sorted(os.listdir(root)):
                    low = name.lower()
                    if name.endswith(".app") and all(k.lower() in low for k in keywords):
                        return os.path.join(root, name)
            except OSError:
                continue
        return ""

    # --------------------------------------------------------- desktop model
    @property
    def can_read_windows(self):
        return _HAVE_QUARTZ

    def list_windows(self, own_ids=()):
        if not _HAVE_QUARTZ:
            return []
        try:
            info = CGWindowListCopyWindowInfo(
                kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
                kCGNullWindowID)
        except Exception:
            return []
        me = os.getpid()
        out = []
        for w in info or []:                       # already front-most first
            try:
                if int(w.get("kCGWindowLayer", 0)) != 0:
                    continue
                if int(w.get("kCGWindowOwnerPID", -1)) == me:
                    continue
                owner = str(w.get("kCGWindowOwnerName", "") or "")
                if owner in SKIP_OWNERS:
                    continue
                b = w.get("kCGWindowBounds") or {}
                x, y = float(b.get("X", 0)), float(b.get("Y", 0))
                ww, hh = float(b.get("Width", 0)), float(b.get("Height", 0))
                if ww < 120 or hh < 80:
                    continue
                title = str(w.get("kCGWindowName", "") or "") or owner
                out.append(WindowInfo(int(w.get("kCGWindowNumber", 0)), title,
                                      x, y, x + ww, y + hh))
            except Exception:
                continue
            if len(out) >= 40:
                break
        return out

    # ------------------------------------------------------------- autostart
    def _plist_path(self):
        return os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents",
                            "com.mushroompet.plist")

    def install_autostart(self, entry_script):
        import sys
        path = self._plist_path()
        plist = {"Label": "com.mushroompet", "ProgramArguments":
                 [sys.executable, entry_script], "RunAtLoad": True, "KeepAlive": False}
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as fh:
                plistlib.dump(plist, fh, fmt=plistlib.FMT_XML, sort_keys=False)
            subprocess.run(["launchctl", "unload", path],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            subprocess.run(["launchctl", "load", path], check=False)
            return True, path
        except OSError as e:
            return False, str(e)

    def remove_autostart(self):
        path = self._plist_path()
        try:
            subprocess.run(["launchctl", "unload", path],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            if os.path.exists(path):
                os.remove(path)
            return True, path
        except OSError as e:
            return False, str(e)
