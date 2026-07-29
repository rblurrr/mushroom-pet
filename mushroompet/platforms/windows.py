"""Windows backend: taskbar-aware z-order, per-pixel hit testing, window enumeration."""
from __future__ import annotations
import ctypes
import glob
import os
import shutil
import subprocess

from PySide6.QtCore import QPoint
from PySide6.QtGui import QGuiApplication

from .base import Backend, WindowInfo

from ctypes import wintypes

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_dwm = ctypes.WinDLL("dwmapi")

GWL_STYLE, GWL_EXSTYLE = -16, -20
WS_CHILD = 0x40000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOPMOST = 0x00000008
HWND_TOPMOST = -1
SWP_Z = 0x0002 | 0x0001 | 0x0010 | 0x0200      # NOMOVE | NOSIZE | NOACTIVATE | NOOWNERZORDER
DWMWA_CLOAKED = 14
DWMWA_EXTENDED_FRAME_BOUNDS = 9
WM_NCHITTEST = 0x0084
HTCLIENT, HTTRANSPARENT = 1, -1

SKIP_CLASSES = {
    "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Progman", "WorkerW", "Button", "SysShadow",
    "TaskListThumbnailWnd", "Windows.UI.Core.CoreWindow", "ForegroundStaging",
    "ApplicationManager_DesktopShellWindow", "MultitaskingViewFrame",
    "XamlExplorerHostIslandWindow", "TopLevelWindowForOverflowXamlIsland",
    "Shell_InputSwitchTopLevelWindow", "NotifyIconOverflowWindow",
}

# Declaring argtypes is not optional: without them ctypes narrows the 64-bit HWND to a
# C int and every one of these calls silently does nothing.
_ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                 ctypes.c_int, ctypes.c_int, ctypes.c_uint]
_user32.SetWindowPos.restype = wintypes.BOOL
_user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
_user32.FindWindowW.restype = wintypes.HWND
_user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
_user32.FindWindowExW.restype = wintypes.HWND
_user32.EnumWindows.argtypes = [_ENUMPROC, wintypes.LPARAM]
_user32.EnumWindows.restype = wintypes.BOOL
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.IsIconic.argtypes = [wintypes.HWND]
_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
_user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_get_long = getattr(_user32, "GetWindowLongPtrW", None) or _user32.GetWindowLongW
_set_long = getattr(_user32, "SetWindowLongPtrW", None) or _user32.SetWindowLongW
_get_long.argtypes = [wintypes.HWND, ctypes.c_int]
_get_long.restype = ctypes.c_ssize_t
_set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
_set_long.restype = ctypes.c_ssize_t
_dwm.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p,
                                       wintypes.DWORD]

DETACHED = 0x00000008


def _hwnd(widget):
    try:
        return int(widget.winId())
    except Exception:
        return 0


def _text(h):
    n = _user32.GetWindowTextLengthW(h)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    _user32.GetWindowTextW(h, buf, n + 1)
    return buf.value


def _cls(h):
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(h, buf, 256)
    return buf.value


def _cloaked(h):
    v = wintypes.DWORD(0)
    try:
        return _dwm.DwmGetWindowAttribute(h, DWMWA_CLOAKED, ctypes.byref(v),
                                          ctypes.sizeof(v)) == 0 and v.value != 0
    except Exception:
        return False


def _frame(h):
    r = wintypes.RECT()
    try:
        if _dwm.DwmGetWindowAttribute(h, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r),
                                      ctypes.sizeof(r)) == 0 and r.right > r.left:
            return r.left, r.top, r.right, r.bottom
    except Exception:
        pass
    if not _user32.GetWindowRect(h, ctypes.byref(r)):
        return None
    return r.left, r.top, r.right, r.bottom


class WindowsBackend(Backend):
    name = "windows"

    def __init__(self):
        self._trays = self._find_trays()
        self._native_hit_seen = False

    # ---------------------------------------------------------------- paths
    def app_data_dir(self):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "MushroomPet")

    # ------------------------------------------------------- window plumbing
    def prepare_window(self, widget):
        h = _hwnd(widget)
        if not h:
            return
        try:
            ex = _get_long(h, GWL_EXSTYLE)
            _set_long(h, GWL_EXSTYLE, ex | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)
        except Exception:
            pass

    def _find_trays(self):
        primary, others = None, []
        try:
            primary = _user32.FindWindowW("Shell_TrayWnd", None) or None
            h = None
            for _ in range(8):
                h = _user32.FindWindowExW(None, h, "Shell_SecondaryTrayWnd", None)
                if not h:
                    break
                others.append(h)
        except Exception:
            pass
        return (primary, others)

    def refresh_shell_handles(self):
        self._trays = self._find_trays()

    def raise_above_shell(self, widget, over_taskbar=False):
        h = _hwnd(widget)
        if not h:
            return False
        try:
            placed = False
            if over_taskbar:
                # HWND_TOPMOST alone loses to the taskbar, which is itself topmost --
                # insert directly above it instead.
                primary, others = self._trays
                on_primary = widget.screen() is QGuiApplication.primaryScreen()
                order = (others + [primary]) if on_primary else ([primary] + others)
                for tray in order:
                    if tray and _user32.SetWindowPos(h, tray, 0, 0, 0, 0, SWP_Z):
                        placed = True
            if not placed:
                _user32.SetWindowPos(h, wintypes.HWND(HWND_TOPMOST), 0, 0, 0, 0, SWP_Z)
            return True
        except Exception:
            return False

    def is_on_top(self, widget):
        h = _hwnd(widget)
        if not h:
            return True
        try:
            return bool(_get_long(h, GWL_EXSTYLE) & WS_EX_TOPMOST)
        except Exception:
            return True

    @property
    def supports_native_hittest(self):
        return True

    def hittest_message(self, message):
        """Return True if this native message is a hit test we should answer."""
        try:
            msg = wintypes.MSG.from_address(int(message))
        except Exception:
            return False
        if msg.message == WM_NCHITTEST:
            self._native_hit_seen = True
            return True
        return False

    @property
    def native_hittest_working(self):
        return self._native_hit_seen

    HIT_SOLID, HIT_THROUGH = HTCLIENT, HTTRANSPARENT

    def begin_high_res_timer(self):
        """Windows' default 15.6 ms granularity makes a 16 ms frame timer beat unevenly."""
        try:
            ctypes.WinDLL("winmm").timeBeginPeriod(1)
            self._timer_boosted = True
            return True
        except Exception:
            self._timer_boosted = False
            return False

    def end_high_res_timer(self):
        if getattr(self, "_timer_boosted", False):
            try:
                ctypes.WinDLL("winmm").timeEndPeriod(1)
            except Exception:
                pass
            self._timer_boosted = False

    # ---------------------------------------------------------------- extras
    def beep(self, urgent=False):
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONHAND if urgent else winsound.MB_OK)
        except Exception:
            pass

    def open_path(self, path, args=""):
        if not path:
            return False, "nothing to open"
        try:
            low = path.lower()
            if low.startswith(("http://", "https://", "mailto:")) or "://" in path[:12]:
                os.startfile(path)
                return True, ""
            if low.endswith(".lnk") or os.path.isdir(path):
                os.startfile(path)
                return True, ""
            cmd = [path] + (args.split() if args else [])
            subprocess.Popen(cmd, creationflags=DETACHED, close_fds=True)
            return True, ""
        except OSError as e:
            try:
                os.startfile(path)
                return True, ""
            except OSError:
                return False, str(e)

    def open_terminal(self, command):
        wt = shutil.which("wt.exe") or shutil.which("wt")
        try:
            if wt:
                subprocess.Popen([wt, "-w", "0", "nt", "cmd", "/k", command],
                                 creationflags=DETACHED)
                return True, ""
            ps = shutil.which("powershell.exe") or shutil.which("powershell")
            if ps:
                subprocess.Popen([ps, "-NoExit", "-Command", command], creationflags=DETACHED)
                return True, ""
            subprocess.Popen([os.environ.get("COMSPEC", "cmd.exe"), "/k", command],
                             creationflags=DETACHED)
            return True, ""
        except OSError as e:
            return False, str(e)

    def find_app(self, *keywords):
        roots = [os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                              "Start Menu", "Programs"),
                 os.path.join(os.environ.get("PROGRAMDATA", ""), "Microsoft", "Windows",
                              "Start Menu", "Programs")]
        hits = []
        for root in roots:
            if not root or not os.path.isdir(root):
                continue
            for p in glob.glob(os.path.join(root, "**", "*.lnk"), recursive=True):
                name = os.path.basename(p).lower()
                if all(k.lower() in name for k in keywords) and "uninstall" not in name:
                    hits.append(p)
        hits.sort(key=len)
        return hits[0] if hits else ""

    # --------------------------------------------------------- desktop model
    @property
    def can_read_windows(self):
        return True

    @staticmethod
    def _to_logical(px, py):
        prim = QGuiApplication.primaryScreen()
        base = (prim.devicePixelRatio() if prim else 1.0) or 1.0
        s = QGuiApplication.screenAt(QPoint(int(px / base), int(py / base))) or prim
        d = (s.devicePixelRatio() if s else base) or 1.0
        return px / d, py / d

    def list_windows(self, own_ids=()):
        own = set(int(i) for i in own_ids if i)
        found = []

        def cb(h, _):
            hi = int(h)
            if hi in own:
                return True
            if not _user32.IsWindowVisible(hi) or _user32.IsIconic(hi):
                return True
            if _get_long(hi, GWL_STYLE) & WS_CHILD:
                return True
            if _get_long(hi, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
                return True
            if _cls(hi) in SKIP_CLASSES:
                return True
            title = _text(hi)
            if not title or _cloaked(hi):
                return True
            r = _frame(hi)
            if r is None:
                return True
            x0, y0 = self._to_logical(r[0], r[1])
            x1, y1 = self._to_logical(r[2], r[3])
            found.append(WindowInfo(hi, title, x0, y0, x1, y1))
            return len(found) < 40

        try:
            _user32.EnumWindows(_ENUMPROC(cb), 0)
        except Exception:
            return []
        return found

    # ------------------------------------------------------------- autostart
    def _shortcut_path(self):
        return os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                            "Start Menu", "Programs", "Startup", "Mushroom Pet.lnk")

    def install_autostart(self, entry_script):
        import sys
        target = shutil.which("pythonw.exe") or sys.executable
        link = self._shortcut_path()
        ps = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{link}');"
              f"$s.TargetPath='{target}';"
              f"$s.Arguments='\"{entry_script}\"';"
              f"$s.WorkingDirectory='{os.path.dirname(entry_script)}';"
              f"$s.WindowStyle=7;$s.Save()")
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, creationflags=DETACHED)
            return os.path.exists(link), link
        except Exception as e:
            return False, str(e)

    def remove_autostart(self):
        link = self._shortcut_path()
        try:
            if os.path.exists(link):
                os.remove(link)
                return True, link
            return True, "wasn't set up"
        except OSError as e:
            return False, str(e)
