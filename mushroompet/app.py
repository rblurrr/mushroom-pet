"""Application wiring: single instance, tray icon, optional control API, pet window."""
from __future__ import annotations
import os
import socket
import sys
import traceback

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu

from .config import Config, ASSET_DIR, LOG_PATH, APP_DIR
from .assets import Assets
from .notify import NotificationCenter
from .api import Bridge, ApiServer, InboxWatcher
from .pet import PetWindow
from .menu import MenuFactory, MENU_QSS
from .platforms import backend

SINGLETON_PORT = 7476       # not the API port; used purely as an instance lock


def _log(msg):
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(msg.rstrip() + "\n")
    except OSError:
        pass


class SingleInstance:
    def __init__(self, port=SINGLETON_PORT):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sock.bind(("127.0.0.1", port))
            self.sock.listen(1)
            self.acquired = True
        except OSError:
            self.acquired = False


class MushroomApp:
    def __init__(self, argv):
        QApplication.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings, True)
        self.qapp = QApplication(argv)
        self.qapp.setQuitOnLastWindowClosed(False)
        self.qapp.setApplicationName("Mushroom Pet")

        self.cfg = Config()
        self.assets = Assets(ASSET_DIR)
        self.qapp.setWindowIcon(self.assets.icon())

        self.notifier = NotificationCenter(self.cfg)
        self.bridge = Bridge()

        self.pet = PetWindow(self.cfg, self.assets, self.notifier, self.bridge)
        self.pet.quit_requested.connect(self.quit)

        self.menus = MenuFactory(self.pet, self.cfg, self.notifier, self.quit)
        self.pet.menu_builder = self.menus.build

        self._build_tray()
        self._start_api()

        self.inbox = InboxWatcher(self.bridge)
        self._inbox_timer = QTimer()
        self._inbox_timer.timeout.connect(self.inbox.tick)
        self._inbox_timer.start(900)

        app = QGuiApplication.instance()
        app.screenAdded.connect(lambda *_: self.pet.handle_screens_changed())
        app.screenRemoved.connect(lambda *_: self.pet.handle_screens_changed())
        for s in QGuiApplication.screens():
            s.geometryChanged.connect(lambda *_: self.pet.handle_screens_changed())

        dpr = QGuiApplication.primaryScreen().devicePixelRatio()
        self.assets.warm(["idle", "walk", "run", "look", "fire_walk"], self.cfg.scale, dpr)

        self.pet.show()
        self.pet._assert_topmost()
        if self.cfg["greet_on_start"]:
            QTimer.singleShot(900, self._greet)

    # ------------------------------------------------------------------
    def _greet(self):
        msg = "Hi! Click me, triple-click to go fiery, right-click for the menu."
        if len(QGuiApplication.screens()) > 1:
            msg = ("Hi! Move your mouse to another monitor and I'll hop over. "
                   "Triple-click me to go fiery.")
        self.pet.speak(msg, 9.5, "happy")
        self.pet.effects.sparkles(self.pet.x, self.pet.y - self.pet.sprite_h * 0.6, 10)

    def _build_tray(self):
        self.tray = QSystemTrayIcon(self.assets.icon())
        self.tray.setToolTip("Mushroom Pet")
        holder = QMenu()
        holder.setStyleSheet(MENU_QSS)
        self.tray.setContextMenu(holder)
        self.tray.activated.connect(self._tray_activated)
        holder.aboutToShow.connect(lambda: self._fill_tray_menu(holder))
        self.tray.show()

    def _fill_tray_menu(self, holder: QMenu):
        holder.clear()
        fresh = self.menus.build()
        for act in fresh.actions():
            holder.addAction(act)
        holder.setStyleSheet(MENU_QSS)
        self._tray_keepalive = fresh          # keeps the submenus alive

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if not self.pet.isVisible():
                self.pet.show()
            self.pet._assert_topmost()
            self.pet.come_here()

    def _start_api(self):
        self.api = None
        if not self.cfg["api_enabled"]:
            return
        token = self.cfg.ensure_token()
        self.api = ApiServer(self.bridge, int(self.cfg["api_port"]), token)
        if not self.api.start():
            _log(f"API port {self.cfg['api_port']} busy; control API disabled this run.")
            self.api = None

    # ------------------------------------------------------------------
    def quit(self):
        try:
            self.cfg.save()
            if self.api:
                self.api.stop()
            self.pet.release_timer_resolution()
            self.pet.effects.clear()
            self.tray.hide()
        finally:
            self.qapp.quit()

    def run(self):
        return self.qapp.exec()


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv)
    lock = SingleInstance()
    if not lock.acquired:
        print("Mushroom Pet is already running.")
        return 0
    try:
        app = MushroomApp(argv)
    except Exception:
        _log("STARTUP FAILURE\n" + traceback.format_exc())
        raise
    return app.run()
