"""The mushroom itself: window, physics, animation state machine, input handling.

Design notes
------------
* The window is deliberately larger than the sprite so speech bubbles and props have
  room. Clicks on the empty area pass through to whatever is underneath -- primarily via
  WM_NCHITTEST, with an input-mask fallback if that ever misfires.
* Position is kept as float "feet" coordinates in Qt's virtual-desktop logical space, so
  walking across monitors with different DPI/height just works. The window snaps to whole
  pixels but the sprite is drawn at the sub-pixel remainder, which is what makes slow
  walking look fluid instead of steppy.
* Repaints are driven by a dirty flag and the timer slows to 30 Hz when he's just standing
  around, so an idle mushroom costs almost nothing.
* Fire mode is a *costume*, not a behaviour: the same state machine runs, but animation
  names are remapped to their flaming equivalents.
"""
from __future__ import annotations
import math
import random
import time

from PySide6.QtCore import Qt, QTimer, QPoint, QPointF, QRectF, QSize, Signal
from PySide6.QtGui import QPainter, QColor, QCursor, QGuiApplication, QRadialGradient, QRegion
from PySide6.QtWidgets import QWidget

from .bubble import Bubble
from .effects import EffectManager
from .desktop import DesktopModel
from .platforms import backend

# ---------------------------------------------------------------- states
IDLE, WANDER, DRAG, FALL, HOP, REACT, SLEEP, COME = (
    "idle", "wander", "drag", "fall", "hop", "react", "sleep", "come")
FIRE_INTRO, FIRE_OUTRO, RAMPAGE = "fire_intro", "fire_outro", "rampage"
CLIMB, SEEK_WALL = "climb", "seek_wall"

CLIMB_SPEED = 92.0
LEDGE_MARGIN = 6.0       # how close to a ledge edge he'll walk before deciding

SIDE_SPACE = 96          # logical px of head-room each side for bubbles/props
BUBBLE_SPACE = 134       # logical px above the sprite reserved for bubbles

BASE_WALK = 74.0
BASE_RUN = 205.0
BASE_RAMPAGE = 415.0
GRAVITY = 2350.0
HOLD_TO_DRAG_MS = 165
TRIPLE_WINDOW_MS = 780
CLICK_RESOLVE_MS = 300

# Fire mode reuses the normal state machine with swapped sprites.
FIRE_SKIN = {
    "idle": "fire_idle", "look": "fire_glare", "walk": "fire_walk", "run": "fire_walk",
    "sit": "fire_idle", "lie": "fire_down", "sleep": "fire_down", "happy": "fire_glare",
    "wave": "fire_glare", "love": "fire_glare", "eat": "fire_idle", "startle": "fire_wake",
    "fish": "fire_idle",
}

IDLE_POOL = [("idle", 6), ("look", 3), ("sit", 4), ("eat", 1), ("happy", 1),
             ("lie", 1), ("wave", 1), ("fish", 1)]
REACT_POOL = ["happy", "wave", "love", "startle"]

IDLE_LINES = [
    "just vibing down here", "your taskbar is comfy", "i live here now",
    "nothing to report", "keeping watch", "spore-adically productive",
    "this is a nice corner", "i counted your windows. it's a lot",
    "you've got tabs, huh", "quiet down here", "still damp. still happy",
    "i'd offer to help but i have no hands", "fungi, not fun-guy. big difference",
    "day 1 of living on your screen", "i saw what you typed. no judgement",
    "mushroom status: nominal", "i'm not procrastinating, i'm mycelium-ing",
    "if you drag me i will squeak", "the desktop is warm today",
    "found a crumb. keeping it", "just here if you need me",
    "i grew half a millimetre today", "brb photosynthesising. wait, wrong kingdom",
    "your wallpaper is doing numbers", "moss would be jealous",
    "i've been thinking about soil", "no notifications. suspicious",
    "am i a widget? philosophically", "guarding the corner",
    "consider stretching. or don't", "i don't need much. maybe damp",
    "you're doing better than you think", "this is my rock now",
    "triple click me if you want to see something", "right click me, i know things",
    "scroll on me and i change size. wild",
    "i have opinions about your folder structure",
    "the bottom of the screen is underrated", "occupying negative space",
    "i could sit here forever, and might",
    "hey. no reason", "clock's ticking. no pressure though",
    "sometimes i just look at the pixels",
    "have you drunk water recently? i'm 90% water, so",
    "you have my full attention", "small mushroom, big dreams",
    "i'd get up but the view is fine",
]
CLICK_LINES = [
    "boop", "hi!", "yes?", "you rang?", "oh! hello", "present",
    "that tickles", "again? okay", "at your service", "mush appreciated",
    "i felt that", "reporting for duty", "what's up", "hey you",
    "still here", "always", "hmm?", "acknowledged",
    "careful, i'm delicate", "poke received", "i'm awake i'm awake",
]
DRAG_LINES = ["wheeee", "put me down. gently", "ohhh we're flying",
              "no thoughts, just air", "i trust you. mostly", "weee"]
WAKE_LINES = ["oh — hi", "was i asleep?", "i wasn't sleeping", "five more minutes",
              "i'm up, i'm up"]
CLIMB_LINES = ["made it", "nice up here", "the view!", "i climbed that",
               "peak reached", "king of the window", "don't close this one"]
FIRE_LINES = ["ANGRY", "do not perceive me", "spicy", "i contain heat",
              "this is my final form", "temporarily furious"]


def _weighted(pool):
    total = sum(w for _, w in pool)
    r = random.uniform(0, total)
    for name, w in pool:
        r -= w
        if r <= 0:
            return name
    return pool[0][0]


class PetWindow(QWidget):
    quit_requested = Signal()

    def __init__(self, cfg, assets, notifier, bridge):
        super().__init__(None)
        self.cfg = cfg
        self.assets = assets
        self.notifier = notifier
        self.bridge = bridge
        self.bridge.state_provider = self.state_snapshot
        self.effects = EffectManager(self)
        self.bubble = Bubble()
        self.menu_builder = None          # set by app.py

        # ---- window chrome ----
        flags = Qt.FramelessWindowHint | Qt.Tool | Qt.NoDropShadowWindowHint
        if cfg["always_on_top"]:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)
        self.setWindowTitle("Mushroom Pet")
        self.setCursor(Qt.ArrowCursor)

        # ---- animation ----
        self.scale = cfg.scale
        self.logical_anim = "idle"
        self.anim_name = "idle"
        self.frame = 0
        self.frame_t = 0.0
        self.anim_done = False
        self.facing = 1
        self.flip = False

        # ---- physics ----
        self.screen = QGuiApplication.primaryScreen()
        self.x = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.target_x = None
        self._wander_run = False
        self.state = IDLE
        self.state_t = 0.0
        self.state_dur = 2.0
        self.squash_t = 0.0
        self.bob = 0.0
        self.tilt = 0.0
        self.shake = 0.0

        # ---- interaction ----
        self.press_pos = None
        self.press_time = 0.0
        self.dragging = False
        self.drag_prev = None
        self.drag_prev_t = 0.0
        self.click_times: list[float] = []
        self.last_interaction = time.monotonic()
        self.next_chatter = time.monotonic() + random.uniform(20.0, 50.0)
        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.timeout.connect(self._begin_drag)
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._resolve_clicks)

        # ---- monitor hopping ----
        self.cursor_screen = self.screen
        self.cursor_screen_since = time.monotonic()
        self.last_hop = 0.0
        self.hop_from = (0.0, 0.0)
        self.hop_to = (0.0, 0.0)
        self.hop_peak = 0.0
        self.hop_dur = 0.6
        self.hop_target_screen = None

        # ---- fire costume ----
        self.fire = False
        self.fire_until = 0.0
        self.next_ember = 0.0

        # ---- desktop awareness (walking on windows, climbing their sides) ----
        self.scanner = DesktopModel()
        self.ledge = None                 # None -> the screen floor / taskbar lane
        self.wall = None                  # the wall currently being climbed
        self.climb_dir = -1               # -1 up, +1 down
        self.next_climb_urge = time.monotonic() + random.uniform(25.0, 70.0)
        self._skip_wid = 0               # ledge we just let go of, briefly ignored
        self._skip_until = 0.0
        self._pending_come = None

        # ---- rendering bookkeeping ----
        self._hit_native_ok = False
        self._mask_mode = False
        self._last_mask_key = None
        self._last_move = None
        self._dirty = True
        self._paint_key = None
        self._interval = 16
        backend.refresh_shell_handles()
        self._sleep_bubble_done = False

        self.resize_for_scale()
        self.place_on_screen(self.screen, 0.5)
        self._apply_window_style()
        self._boost_timer_resolution()

        self._tick = QTimer(self)
        self._tick.setTimerType(Qt.PreciseTimer)
        self._tick.timeout.connect(self._on_tick)
        self._last_t = time.monotonic()
        self._tick.start(self._interval)

        self._z_timer = QTimer(self)
        self._z_timer.timeout.connect(self._assert_topmost)
        self._z_timer.start(max(120, int(cfg["topmost_interval_ms"])))

        # the taskbar handles change when Explorer restarts or a monitor is added
        self._tray_timer = QTimer(self)
        self._tray_timer.timeout.connect(self.refresh_tray_cache)
        self._tray_timer.start(8000)

        # rescan open windows a few times a second so ledges track windows being moved
        self._scan_timer = QTimer(self)
        self._scan_timer.timeout.connect(self._rescan_desktop)
        self._scan_timer.start(450)
        QTimer.singleShot(400, self._rescan_desktop)

        QTimer.singleShot(2500, self._check_hit_mode)
        QTimer.singleShot(3200, self._verify_layer)

    # ==================================================== platform plumbing
    def _apply_window_style(self):
        backend.prepare_window(self)

    def _boost_timer_resolution(self):
        if self.cfg["high_res_timer"]:
            backend.begin_high_res_timer()

    def release_timer_resolution(self):
        backend.end_high_res_timer()

    def _assert_topmost(self):
        """Re-assert always-on-top.

        Some platforms demote a floating window whenever the shell (taskbar, Dock, a
        notification) activates, so this runs on a short timer. It's a no-op when we're
        already on top, which keeps it cheap and flicker-free.
        """
        if not self.cfg["always_on_top"] or not self.isVisible():
            return
        handled = backend.raise_above_shell(self, over_taskbar=self.over_taskbar)
        if not handled:
            self.raise_()
        for ov in self.effects.overlays.values():
            if ov.isVisible():
                if not backend.raise_above_shell(ov, over_taskbar=False):
                    ov.raise_()

    def refresh_tray_cache(self):
        backend.refresh_shell_handles()

    def _own_id(self):
        try:
            return int(self.winId())
        except Exception:
            return 0

    def _verify_layer(self):
        """If we can't actually get above the bar, stand on top of it instead.

        Better a visible mushroom on the bar's upper edge than one buried behind it.
        """
        if not (self.cfg.get("auto_fix_layer", True) and self.over_taskbar):
            return
        if backend.is_on_top(self):
            return
        self.cfg["walk_layer"] = "above"
        self.y = self.floor_y()
        self.sync_window()
        self.speak("Couldn't stand on the bar, so I'm on top of it instead. "
                   "Right-click me -> Walking lane to change it.", 11, "info")

    @property
    def over_taskbar(self):
        """Only Windows can put him inside the bar; elsewhere he stands on its edge."""
        return self.cfg["walk_layer"] == "taskbar" and backend.name == "windows"

    # ==================================================== geometry helpers
    @property
    def sprite_w(self):
        return max(1, round(self.assets.canvas_w * self.scale))

    @property
    def sprite_h(self):
        return max(1, round(self.assets.canvas_h * self.scale))

    @property
    def baseline_off(self):
        return round(self.assets.baseline * self.scale)

    def resize_for_scale(self):
        self.scale = self.cfg.scale
        w = self.sprite_w + 2 * SIDE_SPACE
        h = self.sprite_h + BUBBLE_SPACE
        self.setFixedSize(QSize(w, h))
        self._last_mask_key = None
        self._last_move = None
        self._dirty = True
        self.sync_window()

    def lane_y(self, screen=None) -> float:
        """The surface he's standing on: a window ledge if he's on one, else the floor."""
        if self.ledge is not None and self.ledge.kind == "window":
            return self.ledge.y
        return self.floor_y(screen)

    def floor_y(self, screen=None) -> float:
        s = screen or self.screen
        g, a = s.geometry(), s.availableGeometry()
        if self.over_taskbar:
            return float(g.y() + g.height() - 1)
        return float(a.y() + a.height() - 1)      # top edge of the taskbar / Dock

    # ---------------------------------------------------- desktop awareness
    def _rescan_desktop(self):
        if not self.cfg.get("window_walking", True):
            if self.ledge is not None:
                self._drop_off_ledge()
            return
        own = [self._own_id()] + [int(o.winId()) for o in self.effects.overlays.values()]
        self.scanner.set_own(own)
        try:
            self.scanner.refresh(self.floor_y, pet_w=max(60, int(self.sprite_w * 0.55)))
        except Exception:
            return
        if self.ledge is None or self.state in (DRAG, HOP, FALL, CLIMB):
            return
        # the window he was standing on may have moved, resized, or closed
        found = None
        for lg in self.scanner.ledges:
            if lg.wid == self.ledge.wid and lg.kind == "window" and lg.holds(self.x, 40):
                if found is None or abs(lg.y - self.y) < abs(found.y - self.y):
                    found = lg
        if found is None:
            self._drop_off_ledge()
            return
        self.ledge = found
        if abs(found.y - self.y) > 1.0:
            self.y = found.y                     # ride the window as it's dragged
            self._dirty = True
        if not found.holds(self.x, -LEDGE_MARGIN):
            self.x = max(found.x0 + LEDGE_MARGIN, min(found.x1 - LEDGE_MARGIN, self.x))

    def _drop_off_ledge(self):
        self._release_ledge()
        self.vx, self.vy = 0.0, 40.0
        self.set_state(FALL, None, "startle", restart=True)

    def _release_ledge(self):
        """Let go, and don't immediately re-land on the same window we just left."""
        old = self.ledge
        self.ledge = None
        self.wall = None
        if old is not None and old.kind == "window":
            self._skip_wid = old.wid
            self._skip_until = time.monotonic() + 0.6
        else:
            self._skip_wid = 0
            self._skip_until = 0.0

    def x_limits(self):
        """Horizontal range he may walk within, honouring the current ledge."""
        if self.ledge is not None and self.ledge.kind == "window":
            return self.ledge.x0 + LEDGE_MARGIN, self.ledge.x1 - LEDGE_MARGIN
        return self.x_bounds()

    def x_bounds(self, screen=None):
        s = screen or self.screen
        g = s.geometry()
        m = self.sprite_w * 0.42
        return g.x() + m, g.x() + g.width() - m

    def screen_at(self, x, y):
        return QGuiApplication.screenAt(QPoint(int(x), int(y)))

    def place_on_screen(self, screen, frac=0.5):
        self.screen = screen or QGuiApplication.primaryScreen()
        lo, hi = self.x_bounds(self.screen)
        self.x = lo + (hi - lo) * frac
        self.y = self.lane_y(self.screen)
        self.sync_window()

    def sync_window(self):
        """Window on whole pixels; the fractional remainder is applied when painting."""
        left = math.floor(self.x) - SIDE_SPACE - self.sprite_w // 2
        top = math.floor(self.y) - BUBBLE_SPACE - self.baseline_off
        pos = (left, top)
        if pos != self._last_move:
            self._last_move = pos
            self.move(left, top)
            self._dirty = True

    def feet_in_window(self) -> QPointF:
        return QPointF(SIDE_SPACE + self.sprite_w / 2.0 + (self.x - math.floor(self.x)),
                       BUBBLE_SPACE + self.baseline_off + (self.y - math.floor(self.y)))

    # ==================================================== animation
    def _resolve(self, name):
        if self.fire:
            return FIRE_SKIN.get(name, name)
        return name

    def set_anim(self, name, restart=False):
        self.logical_anim = name
        actual = self._resolve(name)
        if not self.assets.has(actual):
            actual = "fire_idle" if (self.fire and self.assets.has("fire_idle")) else "idle"
        if actual == self.anim_name and not restart:
            return
        self.anim_name = actual
        self.frame = 0
        self.frame_t = 0.0
        self.anim_done = False
        self._dirty = True

    def _reskin(self):
        """Re-resolve the current animation when the fire costume goes on or off."""
        self.set_anim(self.logical_anim, restart=True)

    def _force_sprite(self, sprite):
        """Play one specific sprite set without disturbing the logical pose."""
        if not self.assets.has(sprite):
            return
        self.anim_name = sprite
        self.frame = 0
        self.frame_t = 0.0
        self.anim_done = False
        self._dirty = True

    def _advance_anim(self, dt):
        a = self.assets.anim(self.anim_name)
        if a.count <= 1 or a.fps <= 0:
            self.anim_done = True
            return
        self.frame_t += dt
        step = 1.0 / a.fps
        while self.frame_t >= step:
            self.frame_t -= step
            if self.frame + 1 >= a.count:
                if a.loop:
                    self.frame = 0
                    self._dirty = True
                else:
                    self.anim_done = True
                    break
            else:
                self.frame += 1
                self._dirty = True

    # ==================================================== state machine
    def set_state(self, state, duration=None, anim=None, restart=False):
        self.state = state
        self.state_t = 0.0
        self.state_dur = duration if duration is not None else 2.0
        if anim:
            self.set_anim(anim, restart=restart)
        self._dirty = True

    def _speed(self, base):
        return base * self.cfg.speed_mult * (0.72 + 0.28 * self.scale)

    def _pick_idle(self):
        s = self.screen_at(self.x, self.y - 6)
        if s is not None:
            self.screen = s
        lo, hi = self.x_limits()
        self.x = max(lo, min(hi, self.x))
        self.y = self.lane_y()
        lo_d, hi_d = self.cfg.activity["idle"]
        name = _weighted(IDLE_POOL)
        dur = random.uniform(lo_d, hi_d)
        if name in ("sit", "lie", "fish", "eat"):
            dur *= 1.6
        self.set_state(IDLE, dur, name, restart=True)

    def _start_wander(self):
        lo, hi = self.x_limits()
        span = (hi - lo) * self.cfg.activity["trip"]
        tx = max(lo, min(hi, self.x + random.uniform(-span, span)))
        if abs(tx - self.x) < 40:
            self._pick_idle()
            return
        self.target_x = tx
        self._wander_run = random.random() < 0.10
        self.set_state(WANDER, None, "run" if self._wander_run else "walk")

    # ---------------------------------------------------- climbing
    def _maybe_climb(self, now):
        """Every so often, go find a window edge and climb it."""
        if not (self.cfg.get("window_walking", True) and self.cfg.get("climbing", True)):
            return False
        if now < self.next_climb_urge or self.ledge is not None:
            return False
        walls = [w for w in self.scanner.walls_on_screen(self.screen)
                 if abs(w.x - self.x) < 900 and (self.y - w.y0) > 110]
        if not walls:
            self.next_climb_urge = now + random.uniform(12.0, 30.0)
            return False
        w = min(walls, key=lambda k: abs(k.x - self.x))
        self.next_climb_urge = now + random.uniform(45.0, 130.0)
        self.wall = w
        self.target_x = w.x
        self.set_state(SEEK_WALL, 12.0, "run")
        return True

    def _start_climb(self, wall, direction=-1):
        self.wall = wall
        self.climb_dir = direction
        self.x = wall.x
        self.facing = -wall.side
        self.flip = self.facing < 0
        self.vx = self.vy = 0.0
        self.ledge = None
        self.set_state(CLIMB, 30.0, "walk", restart=True)
        self.effects.land_puff(self.x, self.y, 0.35)

    def _step_climb(self, dt, now):
        w = self.wall
        if w is None:
            return self._drop_off_ledge()
        self.x = w.x
        self.y += CLIMB_SPEED * self.climb_dir * dt * max(0.6, self.cfg.speed_mult)
        self._dirty = True

        if self.climb_dir < 0 and self.y <= w.y0 + 1:
            # over the lip: step onto the window's top edge
            self.y = w.y0
            step_in = 1 if w.side < 0 else -1
            self.x = w.x + step_in * (self.sprite_w * 0.35)
            lg = self.scanner.ledge_at(self.x, self.y, tol=10.0)
            if lg is None:
                lg = next((l for l in self.scanner.ledges
                           if l.wid == w.wid and l.kind == "window" and l.holds(self.x, 30)), None)
            self.wall = None
            if lg is None:
                return self._drop_off_ledge()
            self.ledge = lg
            self.x = max(lg.x0 + LEDGE_MARGIN, min(lg.x1 - LEDGE_MARGIN, self.x))
            self.y = lg.y
            self.squash_t = 0.22
            self.effects.land_puff(self.x, self.y, 0.5)
            self.facing = step_in
            self.flip = self.facing < 0
            self.set_state(REACT, 1.0, "happy", restart=True)
            if random.random() < self.cfg.chatter["click"] * 0.5:
                self.bubble.show(random.choice(CLIMB_LINES), 4.0, "happy")
            return

        if self.climb_dir > 0 and self.y >= min(w.y1, self.floor_y()) - 1:
            self.wall = None
            self.y = self.floor_y()
            self.squash_t = 0.24
            self.effects.land_puff(self.x, self.y, 0.6)
            return self._pick_idle()

        if self.state_t > 26.0:                  # safety net
            self.wall = None
            self._drop_off_ledge()

    def _on_tick(self):
        now = time.monotonic()
        dt = min(0.05, max(0.0005, now - self._last_t))
        self._last_t = now

        self._pump_bridge()
        self.notifier.tick()
        self._maybe_speak_notification()
        was_bubble = self.bubble.visible
        if self.bubble.needs_repaint():
            self._dirty = True
        self.bubble.step()
        if was_bubble and not self.bubble.visible:
            self._dirty = True

        self._update_cursor_screen(now)
        self._step_fire(now, dt)
        self._step_state(dt, now)
        self._advance_anim(dt)
        self._step_visuals(dt)
        self.effects.step(dt)
        self.sync_window()
        self._retune_timer()

        if self._mask_mode:
            self._refresh_mask()
        if self._dirty:
            self._dirty = False
            self.update()

    def _retune_timer(self):
        """30 Hz when he's standing still, 60 Hz when anything is moving."""
        busy = (self.state not in (IDLE, SLEEP)
                or self.bubble.needs_repaint()
                or self.shake > 0.02 or self.squash_t > 0
                or any(o.particles for o in self.effects.overlays.values()))
        want = 16 if busy else 33
        if want != self._interval:
            self._interval = want
            self._tick.setInterval(want)

    # ---------------------------------------------------- per-state logic
    def _step_state(self, dt, now):
        self.state_t += dt
        st = self.state

        if st == DRAG:
            return self._step_drag(dt)
        if st == FALL:
            return self._step_fall(dt)
        if st == HOP:
            return self._step_hop(dt)
        if st == CLIMB:
            return self._step_climb(dt, now)

        if st == SEEK_WALL:
            w = self.wall
            if w is None or self.state_t > self.state_dur:
                self.wall = None
                return self._pick_idle()
            self._walk_towards(w.x, dt, self._speed(BASE_RUN))
            if abs(self.x - w.x) < 8:
                fresh = self.scanner.wall_near(w.x, self.y, reach=40.0) or w
                self._start_climb(fresh, -1)
            return

        if st == FIRE_INTRO:
            self.shake = max(self.shake, 2.6)
            if self.anim_name == "fire_wake" and self.anim_done:
                self._force_sprite("fire_roar")
                self.effects.roar_burst(self.x, self.y - self.sprite_h * 0.45, 1.0)
            elif self.anim_name == "fire_roar" and (self.anim_done or self.state_t > 1.6):
                self._pick_idle()
            elif self.state_t > 2.6:                 # safety net
                self._pick_idle()
            return

        if st == FIRE_OUTRO:
            if self.anim_name == "fire_calm" and self.state_t > 0.9:
                self._force_sprite("fire_smoke")
            elif self.anim_name == "fire_smoke" and self.anim_done:
                self.fire = False
                self._pick_idle()
            elif self.state_t > 4.0:                 # safety net
                self.fire = False
                self._pick_idle()
            return

        if st == RAMPAGE:
            return self._step_rampage(dt, now)

        if st == SLEEP:
            if random.random() < 0.004:
                self.set_anim("sleep", restart=True)
            return

        if st == REACT:
            if self.anim_done or self.state_t > self.state_dur:
                self._pick_idle()
            return

        if st == COME:
            if self.target_x is None:
                return self._pick_idle()
            self._walk_towards(self.target_x, dt, self._speed(BASE_RUN))
            lo, hi = self.x_limits()
            if self.ledge is not None and (self.x <= lo + 0.5 or self.x >= hi - 0.5) \
                    and not (lo <= self.target_x <= hi):
                self._pending_come = self.target_x       # hop off and carry on below
                self._release_ledge()
                self.vx = self.facing * 60.0
                self.vy = 20.0
                return self.set_state(FALL, None, "startle", restart=True)
            if abs(self.x - self.target_x) < 6:
                self.target_x = None
                self.set_state(REACT, 1.4, "wave", restart=True)
                self.effects.sparkles(self.x, self.y - self.sprite_h * 0.55, 8)
            return

        if st == WANDER:
            if self.target_x is None:
                return self._pick_idle()
            spd = self._speed(BASE_RUN if self._wander_run else BASE_WALK)
            self._walk_towards(self.target_x, dt, spd)
            lo, hi = self.x_limits()
            if self.ledge is not None and (self.x <= lo + 0.5 or self.x >= hi - 0.5):
                return self._at_ledge_edge()
            if abs(self.x - self.target_x) < 4:
                self.target_x = None
                self._pick_idle()
            return

        # ---- IDLE ----
        self._maybe_look_at_cursor()
        self._maybe_chatter(now)
        if self.state_t >= self.state_dur:
            if now - self.last_interaction > self.cfg["sleep_after_s"]:
                self._sleep_bubble_done = False
                self.set_state(SLEEP, 9e9, "sleep", restart=True)
            elif self._maybe_climb(now):
                return
            elif random.random() < self.cfg.activity["wander"]:
                self._start_wander()
            else:
                self._pick_idle()

    def _at_ledge_edge(self):
        """Reached the end of a window's top edge: hop down, or turn around."""
        self.target_x = None
        if random.random() < 0.45:
            below = self.scanner.ledge_below(self.x, self.y + 2, exclude=self.ledge)
            self._release_ledge()
            self.vx = self.facing * random.uniform(25.0, 70.0)
            self.vy = 30.0
            self.set_state(FALL, None, "startle", restart=True)
            if below is not None and random.random() < 0.4:
                self.bubble.show(random.choice(["geronimo", "wheee", "down we go"]), 2.6, "happy")
        else:
            self.facing = -self.facing
            self.flip = self.facing < 0
            self._pick_idle()

    def _walk_towards(self, tx, dt, speed):
        d = tx - self.x
        if abs(d) < 0.5:
            return
        f = 1 if d > 0 else -1
        if f != self.facing:
            self.facing = f
            self.flip = f < 0
            self._dirty = True
        step = speed * dt
        self.x = tx if step >= abs(d) else self.x + math.copysign(step, d)
        self.y = self.lane_y()
        self.bob = -abs(math.sin(time.monotonic() * speed * 0.14)) * 2.2 * self.scale
        self._dirty = True

    def _step_drag(self, dt):
        c = QCursor.pos()
        nx, ny = float(c.x()), float(c.y()) + self.sprite_h * 0.32
        now = time.monotonic()
        if self.drag_prev is not None:
            span = max(1e-3, now - self.drag_prev_t)
            self.vx = 0.72 * self.vx + 0.28 * ((nx - self.drag_prev[0]) / span)
            self.vy = 0.72 * self.vy + 0.28 * ((ny - self.drag_prev[1]) / span)
        self.drag_prev = (nx, ny)
        self.drag_prev_t = now
        self.x, self.y = nx, ny
        s = self.screen_at(self.x, self.y)
        if s is not None:
            self.screen = s
        self.tilt = max(-16.0, min(16.0, -self.vx * 0.035))
        if abs(self.vx) > 40:
            self.facing = 1 if self.vx > 0 else -1
            self.flip = self.facing < 0
        self._dirty = True

    def _step_fall(self, dt):
        y_before = self.y
        self.vy += GRAVITY * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vx *= (1 - 0.9 * dt)
        s = self.screen_at(self.x, self.y) or self.screen
        self.screen = s
        lo, hi = self.x_bounds(s)
        if self.x < lo:
            self.x, self.vx = lo, abs(self.vx) * 0.4
        elif self.x > hi:
            self.x, self.vx = hi, -abs(self.vx) * 0.4

        surface, landed_on = self.floor_y(s), None
        if self.cfg.get("window_walking", True) and self.vy > 0:
            skip = self._skip_wid if time.monotonic() < self._skip_until else 0
            for lg in self.scanner.ledges:      # catch a ledge crossed during this step
                if lg.kind != "window" or lg.wid == skip:
                    continue
                if not lg.holds(self.x, -LEDGE_MARGIN):
                    continue
                if y_before <= lg.y + 2 <= self.y and lg.y < surface:
                    surface, landed_on = lg.y, lg

        if self.y >= surface:
            self.y = surface
            self.ledge = landed_on
            self.effects.land_puff(self.x, self.y, min(1.6, abs(self.vy) / 700.0 + 0.35))
            self.squash_t = 0.30
            if abs(self.vy) > 260 and landed_on is None:
                self.vy = -abs(self.vy) * 0.28
                self.set_anim("startle", restart=True)
            else:
                self.vy = 0.0
                self.tilt = 0.0
                pending = getattr(self, "_pending_come", None)
                if pending is not None:
                    self._pending_come = None
                    lo, hi = self.x_limits()
                    self.target_x = max(lo, min(hi, pending))
                    self.set_state(COME, None, "run")
                else:
                    self.set_state(REACT, 1.1, "startle", restart=True)
        self.tilt *= (1 - 3.0 * dt)
        self._dirty = True

    def _step_hop(self, dt):
        u = min(1.0, self.state_t / self.hop_dur)
        x0, y0 = self.hop_from
        x1, y1 = self.hop_to
        self.x = x0 + (x1 - x0) * u
        self.y = y0 + (y1 - y0) * u - 4.0 * self.hop_peak * u * (1.0 - u)
        self.tilt = math.sin(u * math.pi) * 9.0 * (1 if x1 > x0 else -1)
        s = self.screen_at(self.x, max(y0, y1) - 4)
        if s is not None:
            self.screen = s
        self._dirty = True
        if u >= 1.0:
            if self.hop_target_screen is not None:
                self.screen = self.hop_target_screen
            self.ledge = None
            self.y = self.floor_y()
            lo, hi = self.x_bounds()
            self.x = max(lo, min(hi, self.x))
            self.tilt = 0.0
            self.squash_t = 0.26
            self.effects.land_puff(self.x, self.y, 0.9)
            self.set_state(REACT, 0.8, "happy", restart=True)

    def _step_rampage(self, dt, now):
        """Opt-in menu extra: actually run around. Not what triple-click does."""
        if now >= self.fire_until:
            self.set_state(FIRE_OUTRO, 3.0, "fire_calm", restart=True)
            return
        spd = self._speed(BASE_RAMPAGE)
        self.vx = math.copysign(spd, self.vx or 1.0)
        self.x += self.vx * dt
        self.facing = 1 if self.vx > 0 else -1
        self.flip = self.facing < 0
        lo, hi = self.x_bounds()
        if self.x <= lo or self.x >= hi:
            nxt = self.screen_at(self.x + math.copysign(self.sprite_w, self.vx), self.y - 6)
            if nxt is not None and nxt is not self.screen:
                self.screen = nxt
            else:
                self.x = max(lo, min(hi, self.x))
                self.vx = -self.vx
                self.shake = 4.0
        self.y += (self.lane_y() - self.y) * min(1.0, 9.0 * dt)
        self.bob = -abs(math.sin(time.monotonic() * 22.0)) * 3.0 * self.scale
        self.effects.fire_trail(self.x, self.y - self.sprite_h * 0.28, self.facing, 1.0)
        self._dirty = True

    def _step_fire(self, now, dt):
        if not self.fire:
            return
        if self.state in (FIRE_OUTRO,):
            return
        if not self.cfg["fire_persistent"] and now >= self.fire_until:
            self.set_state(FIRE_OUTRO, 3.0)
            self._force_sprite("fire_calm")
            return
        if self.state in (FIRE_INTRO, RAMPAGE):
            return
        # gentle embers so the costume reads as hot without being a light show
        if now >= self.next_ember:
            self.next_ember = now + random.uniform(0.16, 0.34)
            self.effects.fire_trail(self.x, self.y - self.sprite_h * 0.34, self.facing, 0.30)

    def _step_visuals(self, dt):
        if self.squash_t > 0:
            self.squash_t = max(0.0, self.squash_t - dt)
            self._dirty = True
        if self.shake > 0:
            self.shake = max(0.0, self.shake - dt * 9.0)
            self._dirty = True
        if self.state not in (WANDER, COME, RAMPAGE, SEEK_WALL) and abs(self.bob) > 0.01:
            self.bob += (0.0 - self.bob) * min(1.0, 8.0 * dt)
            self._dirty = True
        if self.state == CLIMB and self.wall is not None:
            self.tilt = 90.0 * self.wall.side        # cling sideways to the window edge
        elif self.state not in (DRAG, HOP, FALL) and abs(self.tilt) > 0.05:
            self.tilt += (0.0 - self.tilt) * min(1.0, 8.0 * dt)
            self._dirty = True

    # ---------------------------------------------------- cursor / hopping
    def _update_cursor_screen(self, now):
        c = QCursor.pos()
        s = QGuiApplication.screenAt(c)
        if s is None:
            return
        if s is not self.cursor_screen:
            self.cursor_screen = s
            self.cursor_screen_since = now
        if not self.cfg["follow_mouse_monitors"]:
            locked = self.cfg.get("locked_screen")
            if locked and self.state in (IDLE, WANDER, SLEEP):
                for sc in QGuiApplication.screens():
                    if sc.name() == locked and sc is not self.screen:
                        self.start_hop(sc, None)
                        break
            return
        if s is self.screen or self.state in (DRAG, HOP, FALL, FIRE_INTRO, FIRE_OUTRO, RAMPAGE):
            return
        if (now - self.cursor_screen_since) * 1000 < self.cfg.activity["hop_delay"]:
            return
        if (now - self.last_hop) * 1000 < self.cfg["hop_cooldown_ms"]:
            return
        self.start_hop(s, c.x())

    def start_hop(self, screen, target_x=None):
        if screen is None or screen is self.screen:
            return
        self.last_hop = time.monotonic()
        self.ledge = None                      # a cross-screen leap always lands on the floor
        self.wall = None
        lo, hi = self.x_bounds(screen)
        tx = max(lo, min(hi, float(target_x) if target_x is not None else (lo + hi) / 2.0))
        ty = self.floor_y(screen)
        self.hop_from = (self.x, self.y)
        self.hop_to = (tx, ty)
        dist = math.hypot(tx - self.x, ty - self.y)
        self.hop_dur = max(0.42, min(1.25, dist / 1500.0 + 0.42))
        self.hop_peak = max(130.0, min(420.0, dist * 0.28)) * (0.75 + 0.25 * self.scale)
        self.hop_target_screen = screen
        self.facing = 1 if tx > self.x else -1
        self.flip = self.facing < 0
        self.effects.land_puff(self.x, self.y, 0.6)
        self.set_state(HOP, self.hop_dur, "run", restart=True)

    def _maybe_look_at_cursor(self):
        c = QCursor.pos()
        if QGuiApplication.screenAt(c) is not self.screen:
            return
        dx = c.x() - self.x
        if abs(dx) < 190 and abs(c.y() - self.y) < 260:
            f = 1 if dx > 0 else -1
            if f != self.facing:
                self.facing = f
                self.flip = f < 0
                self._dirty = True
            if self.logical_anim in ("idle", "sit") and random.random() < 0.008:
                self.set_anim("look", restart=True)

    def _maybe_chatter(self, now):
        lo, hi = self.cfg.chatter["idle_gap"]
        if hi <= 0:
            return
        if self.bubble.visible or now < self.next_chatter:
            return
        self.next_chatter = now + random.uniform(lo, hi)
        pool = FIRE_LINES if self.fire else IDLE_LINES
        self.bubble.show(random.choice(pool), random.uniform(4.5, 7.0),
                         "fire" if self.fire else "normal")
        self._dirty = True

    # ==================================================== fire costume
    def light_up(self, seconds=None):
        """Triple-click: put the fire costume on for a while. He keeps behaving normally."""
        self.last_interaction = time.monotonic()
        self.wake()
        dur = float(seconds if seconds is not None else self.cfg["fire_seconds"])
        already = self.fire
        self.fire = True
        self.fire_until = time.monotonic() + dur
        self.next_chatter = min(self.next_chatter, time.monotonic() + 2.0)
        self.target_x = None
        if not already:
            self.shake = 4.0
            self.effects.roar_burst(self.x, self.y - self.sprite_h * 0.45, 0.9)
            self.set_state(FIRE_INTRO, 3.0)
            self._force_sprite("fire_wake")
            self._beep()
        else:
            self._reskin()
        self._dirty = True

    # kept for the API / older callers
    def start_rampage(self, seconds=None):
        self.light_up(seconds)

    def rampage_run(self, seconds=None):
        """Menu extra: the full running-around version."""
        self.last_interaction = time.monotonic()
        self.wake()
        self.fire = True
        self.fire_until = time.monotonic() + float(
            seconds if seconds is not None else self.cfg["fire_seconds"])
        self.vx = self._speed(BASE_RAMPAGE) * self.facing
        self.shake = 6.0
        self.effects.roar_burst(self.x, self.y - self.sprite_h * 0.45, 1.4)
        self.set_state(RAMPAGE, None, "walk", restart=True)
        self._beep()

    def set_fire_persistent(self, on):
        self.cfg["fire_persistent"] = bool(on)
        if on:
            if not self.fire:
                self.light_up(9e8)
            else:
                self.fire_until = time.monotonic() + 9e8
        elif self.fire:
            self.fire_until = time.monotonic()

    def stop_fire(self):
        self.cfg["fire_persistent"] = False
        if self.fire:
            self.fire_until = time.monotonic()

    # ==================================================== speaking
    def speak(self, text, seconds=None, mood="normal", title=""):
        if seconds is None:
            seconds = max(4.0, min(18.0, 2.6 + len(str(text)) * 0.055))
        self.bubble.show(text, seconds, mood, title)
        self.last_interaction = time.monotonic()
        self.next_chatter = time.monotonic() + max(20.0, self.cfg.chatter["idle_gap"][0])
        if self.state == SLEEP:
            self.wake()
        self._dirty = True
        self._refresh_mask(force=True)

    def _maybe_speak_notification(self):
        if self.bubble.active or self.state in (DRAG, HOP, FALL, FIRE_INTRO):
            return
        n = self.notifier.take()
        if n is None:
            return
        secs = n.seconds or self.cfg["notify_seconds"]
        self.wake()
        self.target_x = None
        if n.urgent:
            self.set_state(REACT, 1.6, "startle", restart=True)
            self.effects.sparkles(self.x, self.y - self.sprite_h * 0.5, 8)
        else:
            self.set_state(REACT, 1.4, "happy", restart=True)
            self.effects.sparkles(self.x, self.y - self.sprite_h * 0.55, 8)
        self.bubble.show(n.text, secs, "urgent" if n.urgent else n.mood, n.title)
        if self.cfg["notify_sound"] and self.cfg["sounds"]:
            self._beep(urgent=n.urgent)
        self._dirty = True
        self._refresh_mask(force=True)

    def _beep(self, urgent=False):
        if self.cfg["sounds"]:
            backend.beep(urgent)

    def wake(self):
        self.last_interaction = time.monotonic()
        if self.state == SLEEP:
            self.set_state(REACT, 1.2, "startle", restart=True)
            if random.random() < 0.7:
                self.bubble.show(random.choice(WAKE_LINES), 3.2, "sleepy")

    # ==================================================== bridge commands
    def _pump_bridge(self):
        for cmd in self.bridge.drain():
            try:
                self.handle_command(cmd)
            except Exception:
                pass

    def handle_command(self, cmd):
        a = cmd.get("action")
        if a == "say":
            self.speak(cmd.get("text", ""), cmd.get("seconds"), cmd.get("mood", "normal"),
                       cmd.get("title", ""))
        elif a == "notify":
            self.notifier.push(cmd.get("text", ""), cmd.get("title", "Script"),
                               urgent=cmd.get("urgent", False), seconds=cmd.get("seconds"),
                               source="api")
        elif a == "do":
            self.do_verb(cmd.get("what"), cmd.get("arg"))
        elif a == "reminder_add":
            text = cmd.get("text") or "Reminder"
            if cmd.get("in_minutes"):
                r = self.notifier.add_in_minutes(text, int(cmd["in_minutes"]), cmd.get("urgent", False))
            elif cmd.get("at"):
                rep = cmd.get("repeat", "once")
                r = self.notifier.add_daily(text, cmd["at"], rep == "weekdays",
                                            cmd.get("urgent", False))
            else:
                return
            self.speak(f"Got it - {r.describe()}", 4.5, "info", "Reminder set")
        elif a == "reminder_clear":
            self.notifier.clear_all()

    def do_verb(self, what, arg=None):
        self.last_interaction = time.monotonic()
        if what in ("react", "happy", "wave", "love", "look"):
            name = "happy" if what == "react" else what
            self.wake()
            self.set_state(REACT, 1.6, name, restart=True)
            if name == "love":
                self.effects.hearts(self.x, self.y - self.sprite_h * 0.7, 5)
            elif name == "wave":
                self.effects.notes(self.x, self.y - self.sprite_h * 0.7, 3)
            else:
                self.effects.sparkles(self.x, self.y - self.sprite_h * 0.6, 8)
        elif what == "sit":
            self.set_state(IDLE, 14.0, "sit", restart=True)
        elif what == "sleep":
            self._sleep_bubble_done = False
            self.set_state(SLEEP, 9e9, "sleep", restart=True)
        elif what == "wake":
            self.wake()
        elif what == "come":
            self.come_here()
        elif what == "jump":
            self.wake()
            self.vy, self.vx = -720.0, 0.0
            self.set_state(FALL, None, "startle", restart=True)
        elif what == "hop":
            others = [s for s in QGuiApplication.screens() if s is not self.screen]
            if others:
                self.start_hop(random.choice(others), None)
        elif what == "climb":
            self.next_climb_urge = 0.0
            if not self._maybe_climb(time.monotonic()):
                self.speak("no window tall enough near me to climb", 4.5, "info")
        elif what == "getdown":
            if self.ledge is not None or self.wall is not None:
                self.wall = None
                self._drop_off_ledge()
        elif what == "rampage":
            self.light_up(arg if isinstance(arg, (int, float)) else None)
        elif what == "fire_on":
            self.set_fire_persistent(True)
        elif what == "fire_off":
            self.set_fire_persistent(False)
        elif what == "hide":
            self.hide()
        elif what == "show":
            self.show()
            self._assert_topmost()
        elif what == "quit":
            self.quit_requested.emit()

    def go_to_ledge(self, ledge):
        """Send him to a specific window: walk under it, then climb its nearest side."""
        self.wake()
        self.target_x = None
        target = max(ledge.x0 + LEDGE_MARGIN, min(ledge.x1 - LEDGE_MARGIN, self.x))
        if self.ledge is ledge:
            self.target_x = target
            return self.set_state(WANDER, None, "walk")
        wall = None
        best = 1e9
        for w in self.scanner.walls:
            if w.wid != ledge.wid:
                continue
            d = abs(w.x - self.x)
            if d < best:
                wall, best = w, d
        if wall is None:
            self.speak("i can't reach that one", 4.0, "info")
            return
        if self.ledge is not None:
            self._release_ledge()
            self.vy = 20.0
            self.set_state(FALL, None, "startle", restart=True)
        self.wall = wall
        self.target_x = wall.x
        self.set_state(SEEK_WALL, 14.0, "run")

    def come_here(self):
        self.wake()
        c = QCursor.pos()
        s = QGuiApplication.screenAt(c)
        if s is not None and s is not self.screen:
            self.start_hop(s, c.x())
            return
        lo, hi = self.x_bounds()
        self.target_x = max(lo, min(hi, float(c.x())))
        self.set_state(COME, None, "run")

    def state_snapshot(self):
        return {
            "state": self.state, "anim": self.anim_name, "pose": self.logical_anim,
            "fire": self.fire, "x": round(self.x, 1), "y": round(self.y, 1),
            "screen": self.screen.name() if self.screen else None,
            "screens": [s.name() for s in QGuiApplication.screens()],
            "visible": self.isVisible(), "asleep": self.state == SLEEP,
            "speaking": bool(self.bubble.active),
            "standing_on": (self.ledge.title[:60] if self.ledge is not None
                            and self.ledge.kind == "window" else "desktop"),
            "climbing": self.wall is not None,
            "ledges": len([l for l in self.scanner.ledges if l.kind == "window"]),
            "size": self.cfg["size"], "speed": self.cfg["speed"],
            "activity": self.cfg["activity"], "muted": self.notifier.muted,
            "reminders": [{"id": r.id, "text": r.text, "when": r.describe()}
                          for r in self.notifier.pending()],
            "pomodoro": self.notifier.pomodoro_status(),
        }

    # ==================================================== hit testing
    def _opaque_at(self, gx, gy) -> bool:
        g = self.geometry()
        lx, ly = gx - g.x(), gy - g.y()
        if self.bubble.visible and self.bubble.rect.isValid():
            if self.bubble.rect.adjusted(-2, -2, 2, 2).contains(QPointF(lx, ly)):
                return True
        sx, sy = lx - SIDE_SPACE, ly - BUBBLE_SPACE
        if sx < 0 or sy < 0 or sx >= self.sprite_w or sy >= self.sprite_h:
            return False
        img = self.assets.alpha_mask(self.anim_name, self.frame, self.scale, self.flip)
        if img is None or img.isNull():
            return False
        ix = int(sx * img.width() / self.sprite_w)
        iy = int(sy * img.height() / self.sprite_h)
        if ix < 0 or iy < 0 or ix >= img.width() or iy >= img.height():
            return False
        return (img.pixel(ix, iy) >> 24) > 24

    def nativeEvent(self, eventType, message):
        if backend.supports_native_hittest and backend.hittest_message(message):
            c = QCursor.pos()
            solid = self._opaque_at(c.x(), c.y())
            return True, (backend.HIT_SOLID if solid else backend.HIT_THROUGH)
        return False, 0

    def _check_hit_mode(self):
        """Fall back to an input mask wherever native hit testing isn't available."""
        if not (backend.supports_native_hittest and backend.native_hittest_working):
            self._mask_mode = True
            self._refresh_mask(force=True)

    def _refresh_mask(self, force=False):
        """Fallback click-through: clip input to a slightly grown sprite region."""
        if not self._mask_mode:
            return
        key = (self.anim_name, self.frame, self.flip, round(self.scale * 200),
               self.bubble.visible, round(self.bubble.rect.width()), round(self.bubble.rect.top()))
        if key == self._last_mask_key and not force:
            return
        self._last_mask_key = key
        pm = self.assets.frame(self.anim_name, self.frame, self.scale, self.flip, 1.0)
        if pm.isNull():
            return
        region = QRegion(pm.createMaskFromColor(Qt.transparent, Qt.MaskInColor))
        region.translate(SIDE_SPACE, BUBBLE_SPACE)
        grown = QRegion()
        for dx, dy in ((0, 0), (2, 0), (-2, 0), (0, 2), (0, -2)):
            r = QRegion(region)
            r.translate(dx, dy)
            grown = grown.united(r)
        if self.bubble.visible and self.bubble.rect.isValid():
            grown = grown.united(QRegion(self.bubble.rect.adjusted(-4, -4, 4, 4).toRect()))
        self.setMask(grown)

    # ==================================================== input
    def mousePressEvent(self, ev):
        self.last_interaction = time.monotonic()
        if ev.button() == Qt.LeftButton:
            self.press_pos = ev.globalPosition().toPoint()
            self.press_time = time.monotonic()
            self._hold_timer.start(HOLD_TO_DRAG_MS)
            ev.accept()
        elif ev.button() == Qt.RightButton:
            self._show_menu(ev.globalPosition().toPoint())
            ev.accept()
        elif ev.button() == Qt.MiddleButton:
            self.come_here()
            ev.accept()

    def mouseMoveEvent(self, ev):
        if self.press_pos is not None and not self.dragging:
            if (ev.globalPosition().toPoint() - self.press_pos).manhattanLength() > 12:
                self._begin_drag()
        ev.accept()

    def mouseReleaseEvent(self, ev):
        if ev.button() != Qt.LeftButton:
            return
        self._hold_timer.stop()
        self.last_interaction = time.monotonic()
        if self.dragging:
            self._end_drag()
            self.press_pos = None
            return
        self.press_pos = None
        now = time.monotonic()
        self.click_times = [t for t in self.click_times if now - t < TRIPLE_WINDOW_MS / 1000.0]
        self.click_times.append(now)
        if len(self.click_times) >= 3:
            self.click_times.clear()
            self._click_timer.stop()
            self.light_up()
            return
        self._click_timer.start(CLICK_RESOLVE_MS)
        ev.accept()

    def _resolve_clicks(self):
        n = len(self.click_times)
        self.click_times.clear()
        if not self.cfg["click_reactions"]:
            return
        self.wake()
        say_odds = self.cfg.chatter["click"]
        if n >= 2:
            self.set_state(REACT, 1.5, "love", restart=True)
            self.effects.hearts(self.x, self.y - self.sprite_h * 0.72, 5)
            if random.random() < say_odds:
                self.speak(random.choice(["<3", "aww", "you again!", "i like you too"]), 3.0, "happy")
        else:
            name = random.choice(REACT_POOL)
            self.set_state(REACT, 1.4, name, restart=True)
            if name == "wave":
                self.effects.notes(self.x, self.y - self.sprite_h * 0.7, 3)
            else:
                self.effects.sparkles(self.x, self.y - self.sprite_h * 0.6, 7)
            if random.random() < say_odds:
                pool = FIRE_LINES if self.fire else CLICK_LINES
                self.speak(random.choice(pool), 3.0, "fire" if self.fire else "happy")

    def _begin_drag(self):
        if self.press_pos is None or self.dragging:
            return
        self._hold_timer.stop()
        self.dragging = True
        self.wake()
        self.vx = self.vy = 0.0
        self.drag_prev = None
        self.setCursor(Qt.ClosedHandCursor)
        self.set_state(DRAG, 9e9, "startle", restart=True)
        if random.random() < self.cfg.chatter["click"]:
            self.bubble.show(random.choice(DRAG_LINES), 3.4, "happy")
        QTimer.singleShot(300, lambda: self.set_anim("lie") if self.dragging else None)

    def _end_drag(self):
        self.dragging = False
        self.setCursor(Qt.ArrowCursor)
        self.drag_prev = None
        self.vx = max(-1400.0, min(1400.0, self.vx * 0.55))
        self.vy = max(-1400.0, min(1400.0, self.vy * 0.45))
        self.set_state(FALL, None, "startle", restart=True)

    def mouseDoubleClickEvent(self, ev):
        ev.accept()          # handled by the click resolver

    def wheelEvent(self, ev):
        from .config import SIZES
        order = list(SIZES.keys())
        try:
            i = order.index(self.cfg["size"])
        except ValueError:
            i = 2
        i = max(0, min(len(order) - 1, i + (1 if ev.angleDelta().y() > 0 else -1)))
        if order[i] != self.cfg["size"]:
            self.cfg["size"] = order[i]
            self.resize_for_scale()
            self.speak(order[i], 1.6, "info")
        ev.accept()

    def contextMenuEvent(self, ev):
        self._show_menu(ev.globalPos())
        ev.accept()

    def _show_menu(self, pos):
        if self.menu_builder is None:
            return
        menu = self.menu_builder()
        if menu is not None:
            menu.exec(pos)

    # ==================================================== painting
    def showEvent(self, ev):
        super().showEvent(ev)
        QTimer.singleShot(0, self._apply_window_style)
        QTimer.singleShot(30, self._assert_topmost)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)

        pm = self.assets.frame(self.anim_name, self.frame, self.scale, self.flip,
                               self.devicePixelRatioF())
        if pm.isNull():
            p.end()
            return

        feet = self.feet_in_window()
        air = max(0.0, self.lane_y() - self.y) if self.state in (HOP, FALL, DRAG) else 0.0

        if self.cfg["shadow"]:
            t = max(0.0, min(1.0, 1.0 - air / 420.0))
            rw = self.sprite_w * (0.30 + 0.10 * t)
            rh = max(3.0, rw * 0.20)
            g = QRadialGradient(QPointF(feet.x(), feet.y() - 2), max(4.0, rw))
            g.setColorAt(0.0, QColor(0, 0, 0, int(96 * t)))
            g.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.save()
            p.translate(feet.x(), feet.y() - 2)
            p.scale(1.0, rh / max(4.0, rw))
            p.drawEllipse(QPointF(0, 0), rw, rw)
            p.restore()

        sx = sy = 1.0
        if self.squash_t > 0:
            k = math.sin((self.squash_t / 0.30) * math.pi) * 0.24
            sx, sy = 1.0 + k, 1.0 - k
        jx = jy = 0.0
        if self.shake > 0.02:
            jx = random.uniform(-self.shake, self.shake)
            jy = random.uniform(-self.shake, self.shake) * 0.5

        p.save()
        p.translate(feet.x() + jx, feet.y() + self.bob + jy)
        if abs(self.tilt) > 0.05:
            p.rotate(self.tilt)
        if sx != 1.0 or sy != 1.0:
            p.scale(sx, sy)
        p.drawPixmap(QPointF(-self.sprite_w / 2.0, -float(self.baseline_off)), pm)
        p.restore()

        cap_top = feet.y() + self.bob - self.baseline_off + self.sprite_h * 0.06
        self.bubble.paint(p, QPointF(feet.x(), cap_top), self.width(), self.height(), self.scale)
        p.end()

    # ==================================================== screen changes
    def handle_screens_changed(self):
        self.effects.rebuild()
        names = {s.name() for s in QGuiApplication.screens()}
        if self.screen is None or self.screen.name() not in names:
            self.place_on_screen(QGuiApplication.primaryScreen(), 0.5)
        else:
            self.y = self.lane_y()
            lo, hi = self.x_bounds()
            self.x = max(lo, min(hi, self.x))
        self._dirty = True
        self.sync_window()
