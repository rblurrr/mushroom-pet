"""The right-click menu (also used as the tray menu)."""
from __future__ import annotations
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QActionGroup, QGuiApplication
from PySide6.QtWidgets import QMenu, QFileDialog, QInputDialog, QMessageBox

from . import launchers
from .config import SIZES, SPEEDS, APP_DIR
from .notify import parse_time_phrase
from .platforms import backend

MENU_QSS = """
QMenu {
    background-color: #1d1b24;
    color: #ece8f0;
    border: 1px solid #3a3446;
    border-radius: 10px;
    padding: 6px;
}
QMenu::item { padding: 6px 26px 6px 22px; border-radius: 6px; margin: 1px 2px; }
QMenu::item:selected { background-color: #d8462f; color: #fff8f2; }
QMenu::item:disabled { color: #7d7789; }
QMenu::separator { height: 1px; background: #332e3f; margin: 5px 8px; }
QMenu::indicator { width: 14px; height: 14px; left: 6px; }
"""


class MenuFactory:
    def __init__(self, pet, cfg, notifier, on_quit):
        self.pet = pet
        self.cfg = cfg
        self.notifier = notifier
        self.on_quit = on_quit

    def build(self) -> QMenu:
        m = QMenu()
        m.setStyleSheet(MENU_QSS)
        self._apps(m)
        m.addSeparator()
        self._actions(m)
        m.addSeparator()
        self._notifications(m)
        m.addSeparator()
        self._prefs(m)
        m.addSeparator()
        self._system(m)
        return m

    # ------------------------------------------------------------------ apps
    def _apps(self, m: QMenu):
        head = m.addAction("Open")
        head.setEnabled(False)
        any_entry = False

        for preset in self.cfg["presets"]:
            if not preset.get("enabled"):
                continue
            any_entry = True
            act = m.addAction(preset.get("label") or preset.get("id", "?"))
            act.triggered.connect(lambda _=False, p=preset: self._run(launchers.launch_preset, p))

        for entry in self.cfg["custom_apps"]:
            any_entry = True
            act = m.addAction(entry.get("label") or entry.get("target", "?"))
            act.triggered.connect(lambda _=False, e=entry: self._run(launchers.launch_custom, e))

        if self.cfg["terminal_command"]:
            any_entry = True
            m.addAction("Terminal").triggered.connect(
                lambda: self._run(launchers.launch_terminal, self.cfg))

        if not any_entry:
            a = m.addAction("nothing added yet — use More… below")
            a.setEnabled(False)

        more = m.addMenu("More…")
        more.setStyleSheet(MENU_QSS)
        more.addAction("Add an app…").triggered.connect(self._add_app)
        more.addAction("Add a link…").triggered.connect(self._add_link)
        if self.cfg["custom_apps"]:
            rm = more.addMenu("Remove")
            rm.setStyleSheet(MENU_QSS)
            for entry in list(self.cfg["custom_apps"]):
                rm.addAction(entry.get("label") or entry.get("target", "?")).triggered.connect(
                    lambda _=False, e=entry: self._remove_custom(e))
        if self.cfg["presets"]:
            ex = more.addMenu("Example launchers")
            ex.setStyleSheet(MENU_QSS)
            for preset in self.cfg["presets"]:
                a = ex.addAction(preset.get("label") or preset.get("id", "?"))
                a.setCheckable(True)
                a.setChecked(bool(preset.get("enabled")))
                a.toggled.connect(lambda v, p=preset: self._toggle_preset(p, v))
        more.addSeparator()
        more.addAction("Set terminal command…").triggered.connect(self._set_terminal_cmd)

    # --------------------------------------------------------------- actions
    def _actions(self, m: QMenu):
        head = m.addAction("Mushroom")
        head.setEnabled(False)
        m.addAction("Come here").triggered.connect(self.pet.come_here)
        m.addAction("Wave at me").triggered.connect(lambda: self.pet.do_verb("wave"))
        m.addAction("Jump").triggered.connect(lambda: self.pet.do_verb("jump"))
        if len(QGuiApplication.screens()) > 1:
            m.addAction("Hop to other monitor").triggered.connect(
                lambda: self.pet.do_verb("hop"))

        on_window = self.pet.ledge is not None and self.pet.ledge.kind == "window"
        if on_window or self.pet.wall is not None:
            here = self.pet.ledge.title[:38] if on_window else "a window edge"
            m.addAction(f"Get down from “{here}”").triggered.connect(
                lambda: self.pet.do_verb("getdown"))
        else:
            a = m.addAction("Climb a window")
            a.setEnabled(bool(self.cfg["window_walking"] and self.cfg["climbing"]
                              and backend.can_read_windows))
            a.triggered.connect(lambda: self.pet.do_verb("climb"))

        if self.pet.state == "sleep":
            m.addAction("Wake up").triggered.connect(lambda: self.pet.do_verb("wake"))
        else:
            m.addAction("Go to sleep").triggered.connect(lambda: self.pet.do_verb("sleep"))
            m.addAction("Sit still").triggered.connect(lambda: self.pet.do_verb("sit"))

        fire = m.addMenu("Fire mode")
        fire.setStyleSheet(MENU_QSS)
        secs = self.cfg["fire_seconds"]
        fire.addAction(f"Go fiery for {secs}s  (or triple-click me)").triggered.connect(
            lambda: self.pet.light_up())
        stay = fire.addAction("Stay fiery")
        stay.setCheckable(True)
        stay.setChecked(bool(self.cfg["fire_persistent"]))
        stay.toggled.connect(self.pet.set_fire_persistent)
        if self.pet.fire:
            fire.addAction("Cool down now").triggered.connect(self.pet.stop_fire)
        fire.addSeparator()
        dur = fire.addMenu(f"Lasts: {secs}s")
        dur.setStyleSheet(MENU_QSS)
        for s in (10, 30, 60, 120):
            a = dur.addAction(f"{s} seconds")
            a.setCheckable(True)
            a.setChecked(secs == s)
            a.triggered.connect(lambda _=False, v=s: self.cfg.__setitem__("fire_seconds", v))
        fire.addSeparator()
        fire.addAction("Run wild  (he sprints around)").triggered.connect(
            lambda: self.pet.rampage_run())

    # --------------------------------------------------------- notifications
    def _notifications(self, m: QMenu):
        pending = self.notifier.pending()
        n = m.addMenu(f"Notifications ({len(pending)})" if pending else "Notifications")
        n.setStyleSheet(MENU_QSS)
        n.addAction("Remind me in…").triggered.connect(self._add_timer)
        n.addAction("Remind me daily at…").triggered.connect(self._add_daily)
        n.addAction("Nag me every…").triggered.connect(self._add_interval)
        n.addSeparator()
        pom = n.addMenu(f"Pomodoro: {self.notifier.pomodoro_status()}")
        pom.setStyleSheet(MENU_QSS)
        for w, b in ((25, 5), (50, 10), (90, 15)):
            pom.addAction(f"{w} / {b} min").triggered.connect(
                lambda _=False, w=w, b=b: self._start_pom(w, b))
        if self.cfg["pomodoro"]["enabled"]:
            pom.addSeparator()
            pom.addAction("Stop pomodoro").triggered.connect(self.notifier.stop_pomodoro)
        n.addSeparator()
        if pending:
            cur = n.addMenu("Scheduled")
            cur.setStyleSheet(MENU_QSS)
            for r in pending[:15]:
                cur.addAction(f"{r.text[:44]}  —  {r.describe()}").triggered.connect(
                    lambda _=False, rid=r.id: self._drop_reminder(rid))
            cur.addSeparator()
            cur.addAction("Clear all").triggered.connect(self._clear_reminders)
        else:
            a = n.addAction("Nothing scheduled")
            a.setEnabled(False)
        if self.notifier.history:
            hist = n.addMenu("Recent")
            hist.setStyleSheet(MENU_QSS)
            for item in self.notifier.history[:10]:
                label = f"{item.when()}  {(item.title + ': ') if item.title else ''}{item.text[:48]}"
                hist.addAction(label).triggered.connect(
                    lambda _=False, it=item: self.pet.speak(it.text, 8, it.mood, it.title))
        n.addSeparator()
        mute = n.addAction("Mute non-urgent")
        mute.setCheckable(True)
        mute.setChecked(self.notifier.muted)
        mute.toggled.connect(self._set_muted)
        snd = n.addAction("Notification sound")
        snd.setCheckable(True)
        snd.setChecked(bool(self.cfg["notify_sound"]))
        snd.toggled.connect(lambda v: self.cfg.__setitem__("notify_sound", bool(v)))

    # ----------------------------------------------------------------- prefs
    def _prefs(self, m: QMenu):
        self._radio(m, f"Size: {self.cfg['size']}", list(SIZES),
                    self.cfg["size"], self._set_size)
        self._radio(m, f"Speed: {self.cfg['speed']}", list(SPEEDS),
                    self.cfg["speed"], self._set_speed)
        self._radio(m, f"How busy: {self.cfg['activity']}",
                    [("still", "still — parks in one spot"),
                     ("chill", "chill — rarely wanders"),
                     ("calm", "calm — wanders now and then"),
                     ("lively", "lively — always moving")],
                    self.cfg["activity"], self._set_activity)
        self._radio(m, f"How chatty: {self.cfg['chattiness']}",
                    [("quiet", "quiet — only when spoken to"),
                     ("normal", "normal — a line every minute or two"),
                     ("chatty", "chatty — talks a lot")],
                    self.cfg["chattiness"], self._set_chattiness)
        self._radio(m, f"Sparkles & embers: {self.cfg['effects_level']}",
                    [("off", "off"), ("light", "light"), ("normal", "full")],
                    self.cfg["effects_level"],
                    lambda k: self.cfg.__setitem__("effects_level", k))

        screens = QGuiApplication.screens()
        if len(screens) > 1:
            mon = m.addMenu("Monitors")
            mon.setStyleSheet(MENU_QSS)
            follow = mon.addAction("Follow my mouse between monitors")
            follow.setCheckable(True)
            follow.setChecked(bool(self.cfg["follow_mouse_monitors"]))
            follow.toggled.connect(self._set_follow)
            mon.addSeparator()
            g = QActionGroup(mon)
            g.setExclusive(True)
            for s in screens:
                geo = s.geometry()
                a = mon.addAction(f"Stay on {s.name().strip()} ({geo.width()}x{geo.height()})")
                a.setCheckable(True)
                a.setChecked((not self.cfg["follow_mouse_monitors"])
                             and self.cfg.get("locked_screen") == s.name())
                g.addAction(a)
                a.triggered.connect(lambda _=False, nm=s.name(): self._lock_screen(nm))

        lane = m.addMenu("Walking lane")
        lane.setStyleSheet(MENU_QSS)
        g4 = QActionGroup(lane)
        g4.setExclusive(True)
        bar = "taskbar" if backend.name == "windows" else "Dock"
        options = [("above", f"On top of the {bar}  (always visible)")]
        if backend.name == "windows":
            options.append(("taskbar", "Overlapping the taskbar  (can hide behind it)"))
        for key, label in options:
            a = lane.addAction(label)
            a.setCheckable(True)
            a.setChecked(self.cfg["walk_layer"] == key)
            g4.addAction(a)
            a.triggered.connect(lambda _=False, k=key: self._set_lane(k))
        if backend.name == "windows":
            lane.addSeparator()
            fix = lane.addAction("Rescue me if I get stuck behind it")
            fix.setCheckable(True)
            fix.setChecked(bool(self.cfg["auto_fix_layer"]))
            fix.toggled.connect(lambda v: self.cfg.__setitem__("auto_fix_layer", bool(v)))

        n_ledges = len(self.pet.scanner.window_ledges())
        win = m.addMenu(f"Windows ({n_ledges} to stand on)" if backend.can_read_windows
                        else "Windows (unavailable)")
        win.setStyleSheet(MENU_QSS)
        if not backend.can_read_windows:
            a = win.addAction("needs pyobjc-framework-Quartz on macOS")
            a.setEnabled(False)
        else:
            ww = win.addAction("Walk on top of open windows")
            ww.setCheckable(True)
            ww.setChecked(bool(self.cfg["window_walking"]))
            ww.toggled.connect(self._set_window_walking)
            cl = win.addAction("Climb up their sides")
            cl.setCheckable(True)
            cl.setChecked(bool(self.cfg["climbing"]))
            cl.setEnabled(bool(self.cfg["window_walking"]))
            cl.toggled.connect(lambda v: self.cfg.__setitem__("climbing", bool(v)))
            win.addSeparator()
            if n_ledges:
                lst = win.addMenu("Send me to…")
                lst.setStyleSheet(MENU_QSS)
                seen = set()
                for lg in self.pet.scanner.window_ledges():
                    if lg.title in seen:
                        continue
                    seen.add(lg.title)
                    lst.addAction(lg.title[:52]).triggered.connect(
                        lambda _=False, l=lg: self.pet.go_to_ledge(l))
                    if len(seen) >= 14:
                        break
            else:
                a = win.addAction("no standable window edges right now")
                a.setEnabled(False)

        look = m.addMenu("Behaviour")
        look.setStyleSheet(MENU_QSS)
        toggles = [("click_reactions", "React when clicked"), ("shadow", "Drop shadow"),
                   ("sounds", "Sounds"), ("always_on_top", "Always on top")]
        if backend.name == "windows":
            toggles.append(("high_res_timer", "Smooth motion (1 ms timer)"))
        for key, label in toggles:
            a = look.addAction(label)
            a.setCheckable(True)
            a.setChecked(bool(self.cfg[key]))
            a.toggled.connect(lambda v, k=key: self._toggle_cfg(k, v))
        look.addSeparator()
        sl = look.addMenu(f"Falls asleep after: {self.cfg['sleep_after_s']}s")
        sl.setStyleSheet(MENU_QSS)
        for s in (60, 150, 300, 900, 99999):
            label = "never" if s > 90000 else (f"{s // 60} min" if s >= 60 else f"{s}s")
            a = sl.addAction(label)
            a.setCheckable(True)
            a.setChecked(self.cfg["sleep_after_s"] == s)
            a.triggered.connect(lambda _=False, v=s: self.cfg.__setitem__("sleep_after_s", v))

    def _radio(self, parent, title, options, current, on_pick):
        sub = parent.addMenu(title)
        sub.setStyleSheet(MENU_QSS)
        g = QActionGroup(sub)
        g.setExclusive(True)
        for opt in options:
            key, label = opt if isinstance(opt, tuple) else (opt, opt)
            a = sub.addAction(label)
            a.setCheckable(True)
            a.setChecked(current == key)
            g.addAction(a)
            a.triggered.connect(lambda _=False, k=key: on_pick(k))
        return sub

    # ---------------------------------------------------------------- system
    def _system(self, m: QMenu):
        api = m.addMenu("Control API")
        api.setStyleSheet(MENU_QSS)
        state = f"127.0.0.1:{self.cfg['api_port']} — " + \
                ("listening" if self.cfg["api_enabled"] else "off")
        a = api.addAction(state)
        a.setEnabled(False)
        en = api.addAction("Enable local API")
        en.setCheckable(True)
        en.setChecked(bool(self.cfg["api_enabled"]))
        en.toggled.connect(self._toggle_api)
        api.addSeparator()
        api.addAction("Copy token").triggered.connect(self._copy_token)
        api.addAction("Copy example command").triggered.connect(self._copy_curl)
        api.addAction("Open inbox folder").triggered.connect(
            lambda: backend.open_path(os.path.join(APP_DIR, "inbox")))

        start = m.addMenu("Start with my computer")
        start.setStyleSheet(MENU_QSS)
        start.addAction("Enable").triggered.connect(self._autostart_on)
        start.addAction("Disable").triggered.connect(self._autostart_off)

        m.addAction("Open settings folder").triggered.connect(launchers.open_config_folder)
        if self.pet.isVisible():
            m.addAction("Hide (tray icon stays)").triggered.connect(
                lambda: self.pet.do_verb("hide"))
        else:
            m.addAction("Show").triggered.connect(lambda: self.pet.do_verb("show"))
        m.addSeparator()
        m.addAction("Quit").triggered.connect(self.on_quit)

    # =============================================================== helpers
    def _run(self, fn, arg):
        ok, err = fn(arg)
        if ok:
            self.pet.do_verb("happy")
        else:
            self.pet.speak(err, 10, "urgent", "Hmm")

    def _toggle_cfg(self, key, value):
        self.cfg[key] = bool(value)
        if key in ("always_on_top", "high_res_timer"):
            self.pet.speak("Restart me for that one to fully apply.", 5, "info")

    def _set_size(self, name):
        self.cfg["size"] = name
        self.pet.resize_for_scale()
        self.pet.speak(name, 1.6, "info")

    def _set_speed(self, name):
        self.cfg["speed"] = name
        self.pet.speak(name, 1.6, "info")

    def _set_activity(self, key):
        self.cfg["activity"] = key
        self.pet.target_x = None
        self.pet._pick_idle()
        self.pet.speak(key, 1.8, "info")

    def _set_chattiness(self, key):
        import time
        self.cfg["chattiness"] = key
        lo, hi = self.cfg.chatter["idle_gap"]
        self.pet.next_chatter = time.monotonic() + (max(6.0, lo * 0.4) if hi else 1e9)
        self.pet.speak(key, 1.8, "info")

    def _set_follow(self, value):
        self.cfg["follow_mouse_monitors"] = bool(value)
        if value:
            self.cfg["locked_screen"] = None
            self.cfg.save()

    def _lock_screen(self, name):
        self.cfg["follow_mouse_monitors"] = False
        self.cfg["locked_screen"] = name
        self.cfg.save()
        for s in QGuiApplication.screens():
            if s.name() == name:
                self.pet.start_hop(s, None)
                break

    def _set_lane(self, key):
        self.cfg["walk_layer"] = key
        self.pet.refresh_tray_cache()
        self.pet.y = self.pet.lane_y()
        self.pet.sync_window()
        self.pet._assert_topmost()

    def _set_window_walking(self, value):
        self.cfg["window_walking"] = bool(value)
        if not value and self.pet.ledge is not None:
            self.pet.wall = None
            self.pet._drop_off_ledge()

    def _set_muted(self, value):
        self.notifier.muted = bool(value)
        self.pet.speak("Muted. Urgent things still get through." if value else "Listening again.",
                       4, "info")

    def _toggle_preset(self, preset, value):
        presets = list(self.cfg["presets"])
        for p in presets:
            if p.get("id") == preset.get("id"):
                p["enabled"] = bool(value)
        self.cfg["presets"] = presets

    # ---- entries ----
    def _add_app(self):
        start = "/Applications" if backend.name == "macos" else os.environ.get("PROGRAMFILES", "")
        filt = ("Applications (*.app);;All files (*)" if backend.name == "macos"
                else "Programs and shortcuts (*.exe *.lnk *.bat *.cmd);;All files (*)")
        path, _ = QFileDialog.getOpenFileName(None, "Pick a program for my menu", start, filt)
        if not path:
            return
        default = os.path.splitext(os.path.basename(path))[0]
        label, ok = QInputDialog.getText(None, "Menu label", "Show it as:", text=default)
        if not ok or not label.strip():
            return
        apps = list(self.cfg["custom_apps"])
        apps.append({"label": label.strip(), "target": path, "args": "", "kind": "app"})
        self.cfg["custom_apps"] = apps
        self.pet.speak(f"Added {label.strip()}", 3.5, "happy")

    def _add_link(self):
        url, ok = QInputDialog.getText(None, "Add a link", "URL:", text="https://")
        if not ok or url.strip() in ("", "https://"):
            return
        default = url.split("//")[-1].split("/")[0]
        label, ok2 = QInputDialog.getText(None, "Menu label", "Show it as:", text=default)
        if not ok2 or not label.strip():
            return
        apps = list(self.cfg["custom_apps"])
        apps.append({"label": label.strip(), "target": url.strip(), "kind": "url"})
        self.cfg["custom_apps"] = apps
        self.pet.speak(f"Added {label.strip()}", 3.5, "happy")

    def _remove_custom(self, entry):
        self.cfg["custom_apps"] = [e for e in self.cfg["custom_apps"] if e is not entry]
        self.pet.speak("Removed.", 2.5, "info")

    def _set_terminal_cmd(self):
        cur = self.cfg["terminal_command"]
        cmd, ok = QInputDialog.getText(None, "Terminal command",
                                       "Command to run in a new terminal window:", text=cur)
        if ok:
            self.cfg["terminal_command"] = cmd.strip()
            self.pet.speak("Saved.", 2.5, "happy")

    # ---- reminders ----
    def _add_timer(self):
        text, ok = QInputDialog.getText(None, "Remind me", "What should I say?")
        if not ok or not text.strip():
            return
        when, ok2 = QInputDialog.getText(None, "When?", "In how long?  (e.g. 10m, 1h30, 45)",
                                         text="10m")
        if not ok2:
            return
        parsed = parse_time_phrase(when)
        if not parsed:
            self.pet.speak("I couldn't read that. Try 10m or 1h30.", 7, "urgent")
            return
        kind, val = parsed
        r = (self.notifier.add_in_minutes(text.strip(), val) if kind == "in"
             else self.notifier.add_daily(text.strip(), val))
        self.pet.speak(f"Okay — {r.describe()}", 4.5, "happy", "Reminder set")

    def _add_daily(self):
        text, ok = QInputDialog.getText(None, "Daily reminder", "What should I say?")
        if not ok or not text.strip():
            return
        when, ok2 = QInputDialog.getText(None, "Time of day", "HH:MM (24h)", text="09:30")
        if not ok2:
            return
        parsed = parse_time_phrase(when)
        if not parsed or parsed[0] != "at":
            self.pet.speak("Give me a time like 09:30.", 6, "urgent")
            return
        weekdays = QMessageBox.question(
            None, "Weekdays only?", "Only on weekdays (Mon–Fri)?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes
        r = self.notifier.add_daily(text.strip(), parsed[1], weekdays)
        self.pet.speak(f"Okay — {r.describe()}", 4.5, "happy", "Reminder set")

    def _add_interval(self):
        text, ok = QInputDialog.getText(None, "Recurring nag", "What should I say?",
                                        text="Stand up and stretch")
        if not ok or not text.strip():
            return
        mins, ok2 = QInputDialog.getInt(None, "How often?", "Every N minutes:", 45, 1, 1440, 5)
        if not ok2:
            return
        r = self.notifier.add_interval(text.strip(), mins)
        self.pet.speak(f"Okay — {r.describe()}", 4.5, "happy", "Reminder set")

    def _drop_reminder(self, rid):
        if QMessageBox.question(None, "Remove reminder?", "Delete this reminder?",
                                QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.No) == QMessageBox.Yes:
            self.notifier.remove(rid)
            self.pet.speak("Deleted.", 2.5, "info")

    def _clear_reminders(self):
        if QMessageBox.question(None, "Clear all?", "Delete every scheduled reminder?",
                                QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.No) == QMessageBox.Yes:
            self.notifier.clear_all()
            self.pet.speak("All clear.", 2.5, "info")

    def _start_pom(self, w, b):
        self.notifier.start_pomodoro(w, b)
        self.pet.speak(f"{w} minutes of focus. Go.", 5, "happy", "Pomodoro")

    # ---- api / autostart ----
    def _toggle_api(self, value):
        self.cfg["api_enabled"] = bool(value)
        if value:
            self.cfg.ensure_token()
        self.pet.speak("Restart me to apply that.", 5.5, "info")

    def _copy_token(self):
        token = self.cfg.ensure_token()
        QGuiApplication.clipboard().setText(token)
        self.pet.speak("Token copied to your clipboard.", 4, "info")

    def _copy_curl(self):
        token = self.cfg.ensure_token()
        cmd = (f"curl -s -X POST http://127.0.0.1:{self.cfg['api_port']}/say "
               f"-H 'X-Token: {token}' -H 'Content-Type: application/json' "
               "-d '{\"text\":\"hello\"}'")
        QGuiApplication.clipboard().setText(cmd)
        self.pet.speak("Example copied. Paste it in a terminal to test.", 6, "info")

    def _autostart_on(self):
        ok, info = launchers.install_autostart()
        self.pet.speak("I'll start with your computer now." if ok else f"Couldn't set that up ({info})",
                       6, "happy" if ok else "urgent")

    def _autostart_off(self):
        ok, info = launchers.remove_autostart()
        self.pet.speak("Autostart removed." if ok else f"Couldn't remove it ({info})",
                       5, "info" if ok else "urgent")
