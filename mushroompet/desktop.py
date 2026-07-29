"""Turns the list of open windows into surfaces the pet can use.

  Ledge -- a horizontal surface he can stand and walk on: a window's top edge, or the
           bottom of a screen. Ledges are trimmed to the part that isn't covered by a
           window in front of them.
  Wall  -- a vertical surface he can climb: the left or right side of a window.

The platform backend supplies the raw window list already converted to Qt logical
coordinates, so this module is entirely OS-agnostic.
"""
from __future__ import annotations

from PySide6.QtGui import QGuiApplication

from .platforms import backend


class Ledge:
    __slots__ = ("x0", "x1", "y", "wid", "title", "kind")

    def __init__(self, x0, x1, y, wid=0, title="", kind="window"):
        self.x0, self.x1, self.y = float(x0), float(x1), float(y)
        self.wid, self.title, self.kind = wid, title, kind

    @property
    def width(self):
        return self.x1 - self.x0

    def holds(self, x, margin=0.0):
        return (self.x0 - margin) <= x <= (self.x1 + margin)

    def __repr__(self):
        return f"<Ledge {self.kind} y={self.y:.0f} {self.x0:.0f}..{self.x1:.0f} {self.title[:20]!r}>"


class Wall:
    __slots__ = ("x", "y0", "y1", "side", "wid", "title")

    def __init__(self, x, y0, y1, side, wid=0, title=""):
        self.x, self.y0, self.y1 = float(x), float(y0), float(y1)
        self.side, self.wid, self.title = side, wid, title

    @property
    def height(self):
        return self.y1 - self.y0

    def __repr__(self):
        return f"<Wall x={self.x:.0f} y={self.y0:.0f}..{self.y1:.0f} side={self.side}>"


class DesktopModel:
    def __init__(self):
        self.ledges: list[Ledge] = []
        self.walls: list[Wall] = []
        self.own_ids: set[int] = set()

    @property
    def available(self):
        return backend.can_read_windows

    def set_own(self, ids):
        self.own_ids = set(int(i) for i in ids if i)

    # ------------------------------------------------------------------
    def refresh(self, floor_for_screen, min_h=120, pet_w=90):
        """Rebuild the surface lists. `floor_for_screen(screen)` gives the walking floor."""
        self.ledges = []
        self.walls = []

        for s in QGuiApplication.screens():
            g = s.geometry()
            self.ledges.append(Ledge(g.x(), g.x() + g.width(),
                                     floor_for_screen(s), 0, s.name(), "floor"))

        if not backend.can_read_windows:
            return

        try:
            wins = backend.list_windows(self.own_ids)
        except Exception:
            return

        for i, w in enumerate(wins):
            covering = []
            for prev in wins[:i]:              # anything in front of this window
                if prev.y0 - 2 <= w.y0 <= prev.y1 and prev.x1 > w.x0 and prev.x0 < w.x1:
                    covering.append((max(w.x0, prev.x0), min(w.x1, prev.x1)))
            for (a, b) in self._subtract(w.x0, w.x1, covering):
                if b - a >= pet_w:
                    self.ledges.append(Ledge(a, b, w.y0, w.wid, w.title, "window"))
            if w.h >= min_h:
                for side, wx in ((-1, w.x0), (1, w.x1)):
                    self.walls.append(Wall(wx, w.y0, min(w.y1, w.y0 + 1400),
                                           side, w.wid, w.title))

    @staticmethod
    def _subtract(x0, x1, spans):
        """x0..x1 with the covered spans removed."""
        if not spans:
            return [(x0, x1)]
        out, cur = [], x0
        for (a, b) in sorted(spans):
            if b <= cur:
                continue
            if a > cur:
                out.append((cur, min(a, x1)))
            cur = max(cur, b)
            if cur >= x1:
                break
        if cur < x1:
            out.append((cur, x1))
        return [(a, b) for (a, b) in out if b > a]

    # ---------------------------------------------------------- queries
    def ledge_below(self, x, y, exclude=None, slack=4.0):
        best = None
        for lg in self.ledges:
            if lg is exclude or not lg.holds(x):
                continue
            if lg.y >= y - slack and (best is None or lg.y < best.y):
                best = lg
        return best

    def ledge_at(self, x, y, tol=6.0):
        for lg in self.ledges:
            if lg.holds(x) and abs(lg.y - y) <= tol:
                return lg
        return None

    def wall_near(self, x, y, reach=34.0, min_rise=90.0):
        best, best_d = None, 1e9
        for w in self.walls:
            if not (w.y0 <= y <= w.y1 + 40) or (y - w.y0) < min_rise:
                continue
            d = abs(w.x - x)
            if d <= reach and d < best_d:
                best, best_d = w, d
        return best

    def walls_on_screen(self, screen):
        g = screen.geometry()
        return [w for w in self.walls if g.x() <= w.x <= g.x() + g.width()]

    def window_ledges(self):
        return [l for l in self.ledges if l.kind == "window"]
