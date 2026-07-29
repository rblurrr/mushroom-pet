"""Platform backend interface plus a generic fallback that works anywhere Qt does.

Everything OS-specific lives behind this class: config location, always-on-top,
click-through hit testing, sounds, opening files, and reading the desktop's open
windows. The generic backend simply reports "not supported" for the exotic parts, so the
pet still runs (walking, dragging, bubbles, menus) on an unrecognised platform.
"""
from __future__ import annotations
import os
import subprocess
import sys


class WindowInfo:
    """One open window, in Qt logical coordinates."""
    __slots__ = ("wid", "title", "x0", "y0", "x1", "y1")

    def __init__(self, wid, title, x0, y0, x1, y1):
        self.wid = wid
        self.title = title
        self.x0, self.y0, self.x1, self.y1 = float(x0), float(y0), float(x1), float(y1)

    @property
    def w(self):
        return self.x1 - self.x0

    @property
    def h(self):
        return self.y1 - self.y0


class Backend:
    name = "generic"

    # ---------------------------------------------------------------- paths
    def app_data_dir(self) -> str:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
        return os.path.join(base, "mushroompet")

    # ------------------------------------------------------- window plumbing
    def prepare_window(self, widget) -> None:
        """Called once the native window exists. Set no-activate / accessory styles."""

    def raise_above_shell(self, widget, over_taskbar=False) -> bool:
        """Re-assert always-on-top. Return True if handled natively."""
        return False

    def is_on_top(self, widget) -> bool:
        return True

    @property
    def supports_native_hittest(self) -> bool:
        """True when the backend can answer per-pixel hit tests via native events."""
        return False

    def hittest_message(self, message) -> bool:
        return False

    @property
    def native_hittest_working(self) -> bool:
        return False

    HIT_SOLID, HIT_THROUGH = 1, -1

    def begin_high_res_timer(self) -> bool:
        """Ask the OS for finer timer granularity, if it has such a knob."""
        return False

    def end_high_res_timer(self) -> None:
        pass

    def refresh_shell_handles(self) -> None:
        pass

    # ---------------------------------------------------------------- extras
    def beep(self, urgent=False) -> None:
        try:
            sys.stdout.write("\a")
            sys.stdout.flush()
        except Exception:
            pass

    def open_path(self, path, args="") -> tuple[bool, str]:
        if not path:
            return False, "nothing to open"
        try:
            opener = "xdg-open"
            subprocess.Popen([opener, path], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True, ""
        except OSError as e:
            return False, str(e)

    def open_terminal(self, command) -> tuple[bool, str]:
        for term in ("x-terminal-emulator", "gnome-terminal", "konsole", "xterm"):
            try:
                subprocess.Popen([term, "-e", command], start_new_session=True)
                return True, ""
            except OSError:
                continue
        return False, "no terminal emulator found"

    def find_app(self, *keywords) -> str:
        """Best-effort search for an installed application. Empty string if not found."""
        return ""

    # --------------------------------------------------------- desktop model
    @property
    def can_read_windows(self) -> bool:
        return False

    def list_windows(self, own_ids=()) -> list[WindowInfo]:
        """Open top-level windows, front-most first, in Qt logical coordinates."""
        return []

    def install_autostart(self, entry_script) -> tuple[bool, str]:
        return False, "autostart isn't implemented for this platform"

    def remove_autostart(self) -> tuple[bool, str]:
        return False, "autostart isn't implemented for this platform"


def get_backend() -> Backend:
    if sys.platform.startswith("win"):
        try:
            from .windows import WindowsBackend
            return WindowsBackend()
        except Exception:
            pass
    elif sys.platform == "darwin":
        try:
            from .macos import MacBackend
            return MacBackend()
        except Exception:
            pass
    return Backend()
