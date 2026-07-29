"""Full-screen click-through overlays used for fire trails, dust and sparkles.

One overlay per physical screen. Overlays are hidden whenever they hold no live
particles, so in the common case nothing extra is composited at all.
"""
from __future__ import annotations
import math, random
from PySide6.QtCore import Qt, QRect, QPointF
from PySide6.QtGui import QPainter, QColor, QRadialGradient, QPen
from PySide6.QtWidgets import QWidget

EMBER = "ember"
SMOKE = "smoke"
DUST = "dust"
SPARK = "spark"
HEART = "heart"
NOTE = "note"


class Particle:
    __slots__ = ("kind", "x", "y", "vx", "vy", "life", "max_life", "size", "hue", "rot", "spin")

    def __init__(self, kind, x, y, vx, vy, life, size, hue=0.0, spin=0.0):
        self.kind = kind
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.life = self.max_life = life
        self.size = size
        self.hue = hue
        self.rot = random.uniform(0, math.tau)
        self.spin = spin

    def step(self, dt):
        self.life -= dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.rot += self.spin * dt
        if self.kind == EMBER:
            self.vy += 42 * dt          # embers float up then get pulled a bit
            self.vx *= (1 - 1.5 * dt)
        elif self.kind == SMOKE:
            self.vy -= 26 * dt
            self.vx *= (1 - 0.9 * dt)
            self.size += 34 * dt
        elif self.kind == DUST:
            self.vy += 340 * dt
            self.vx *= (1 - 2.2 * dt)
        elif self.kind in (SPARK, HEART, NOTE):
            self.vy += 90 * dt
            self.vx *= (1 - 1.1 * dt)
        return self.life > 0

    @property
    def t(self):
        return max(0.0, min(1.0, self.life / self.max_life))


class EffectOverlay(QWidget):
    """Transparent, input-transparent, always-on-top canvas covering one screen.

    Only the rectangle that actually contains particles is repainted; repainting a whole
    1080p translucent window at 60 fps is what made the old build stutter.
    """

    def __init__(self, screen):
        super().__init__(None)
        self.screen_obj = screen
        self.particles: list[Particle] = []
        self._prev_dirty = None
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
            | Qt.WindowTransparentForInput | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.sync_geometry()

    def sync_geometry(self):
        g: QRect = self.screen_obj.geometry()
        self.setGeometry(g)
        self._origin = g.topLeft()

    # ---- emission (global logical coords) ----
    def add(self, p: Particle):
        p.x -= self._origin.x()
        p.y -= self._origin.y()
        self.particles.append(p)
        if not self.isVisible():
            self.show()

    def _dirty_rect(self):
        if not self.particles:
            return None
        xs0 = xs1 = ys0 = ys1 = None
        for p in self.particles:
            r = p.size * 2.4 + 6
            a, b, c, d = p.x - r, p.x + r, p.y - r, p.y + r
            if xs0 is None:
                xs0, xs1, ys0, ys1 = a, b, c, d
            else:
                if a < xs0: xs0 = a
                if b > xs1: xs1 = b
                if c < ys0: ys0 = c
                if d > ys1: ys1 = d
        return QRect(int(xs0) - 2, int(ys0) - 2,
                     int(xs1 - xs0) + 4, int(ys1 - ys0) + 4)

    def step(self, dt):
        if not self.particles:
            if self.isVisible():
                self.hide()
                self._prev_dirty = None
            return
        self.particles = [p for p in self.particles if p.step(dt)]
        if len(self.particles) > 700:
            del self.particles[:-700]
        cur = self._dirty_rect()
        area = cur
        if area is not None and self._prev_dirty is not None:
            area = area.united(self._prev_dirty)
        self._prev_dirty = cur
        if area is not None:
            self.update(area)
        elif self.isVisible():
            self.update()

    def clear(self):
        self.particles.clear()
        self._prev_dirty = None
        self.hide()

    # ---- painting ----
    def paintEvent(self, _):
        if not self.particles:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        add_mode = QPainter.CompositionMode_Plus
        for pt in self.particles:
            t = pt.t
            if pt.kind == EMBER:
                p.setCompositionMode(add_mode)
                r = pt.size * (0.35 + 0.65 * t)
                g = QRadialGradient(QPointF(pt.x, pt.y), max(1.0, r))
                hot = QColor.fromHsvF(0.09 - 0.06 * (1 - t) + pt.hue * 0.03, 0.95, 1.0)
                hot.setAlphaF(0.85 * t)
                mid = QColor(hot)
                mid.setAlphaF(0.35 * t)
                edge = QColor(255, 90, 20, 0)
                g.setColorAt(0.0, hot)
                g.setColorAt(0.45, mid)
                g.setColorAt(1.0, edge)
                p.setBrush(g)
                p.drawEllipse(QPointF(pt.x, pt.y), r, r)
            elif pt.kind == SMOKE:
                p.setCompositionMode(QPainter.CompositionMode_SourceOver)
                r = pt.size
                g = QRadialGradient(QPointF(pt.x, pt.y), max(1.0, r))
                c = QColor(206, 200, 196)
                c.setAlphaF(0.30 * t)
                g.setColorAt(0.0, c)
                c2 = QColor(190, 184, 180, 0)
                g.setColorAt(1.0, c2)
                p.setBrush(g)
                p.drawEllipse(QPointF(pt.x, pt.y), r, r * 0.8)
            elif pt.kind == DUST:
                p.setCompositionMode(QPainter.CompositionMode_SourceOver)
                c = QColor(228, 214, 190)
                c.setAlphaF(0.55 * t)
                p.setBrush(c)
                r = pt.size * (0.4 + 0.6 * t)
                p.drawEllipse(QPointF(pt.x, pt.y), r, r * 0.85)
            elif pt.kind == SPARK:
                p.setCompositionMode(add_mode)
                c = QColor(255, 236, 150)
                c.setAlphaF(0.9 * t)
                p.setPen(QPen(c, max(1.0, pt.size * 0.28)))
                d = pt.size * (0.6 + 0.8 * t)
                for k in range(2):
                    a = pt.rot + k * math.pi / 2
                    p.drawLine(QPointF(pt.x - math.cos(a) * d, pt.y - math.sin(a) * d),
                               QPointF(pt.x + math.cos(a) * d, pt.y + math.sin(a) * d))
                p.setPen(Qt.NoPen)
            elif pt.kind in (HEART, NOTE):
                p.setCompositionMode(QPainter.CompositionMode_SourceOver)
                col = QColor(255, 96, 122) if pt.kind == HEART else QColor(150, 205, 255)
                col.setAlphaF(0.9 * min(1.0, t * 1.6))
                p.setBrush(col)
                s = pt.size
                if pt.kind == HEART:
                    p.save()
                    p.translate(pt.x, pt.y)
                    p.rotate(math.degrees(math.sin(pt.rot) * 0.25))
                    p.drawEllipse(QPointF(-s * 0.32, -s * 0.18), s * 0.42, s * 0.42)
                    p.drawEllipse(QPointF(s * 0.32, -s * 0.18), s * 0.42, s * 0.42)
                    from PySide6.QtGui import QPolygonF
                    p.drawPolygon(QPolygonF([QPointF(-s * 0.72, 0.0), QPointF(s * 0.72, 0.0),
                                             QPointF(0.0, s * 0.95)]))
                    p.restore()
                else:
                    p.drawEllipse(QPointF(pt.x, pt.y), s * 0.42, s * 0.34)
                    p.setPen(QPen(col, max(1.0, s * 0.20)))
                    p.drawLine(QPointF(pt.x + s * 0.40, pt.y), QPointF(pt.x + s * 0.40, pt.y - s * 1.15))
                    p.setPen(Qt.NoPen)
        p.end()


class EffectManager:
    """Routes particle emission to whichever screen the point is on.

    Every preset is scaled by the user's effects level, so "light" genuinely means fewer
    particles rather than the same load drawn fainter.
    """

    def __init__(self, app):
        self.app = app
        self.overlays: dict[str, EffectOverlay] = {}
        self.rebuild()

    @property
    def density(self) -> float:
        try:
            return float(self.app.cfg.fx)
        except Exception:
            return 1.0

    def _n(self, base, power=1.0):
        return max(0, int(round(base * power * self.density)))

    def rebuild(self):
        from PySide6.QtGui import QGuiApplication
        wanted = {s.name(): s for s in QGuiApplication.screens()}
        for name in list(self.overlays):
            if name not in wanted:
                self.overlays.pop(name).deleteLater()
        for name, s in wanted.items():
            if name in self.overlays:
                self.overlays[name].screen_obj = s
                self.overlays[name].sync_geometry()
            else:
                self.overlays[name] = EffectOverlay(s)

    def _overlay_at(self, x, y):
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QGuiApplication
        s = QGuiApplication.screenAt(QPoint(int(x), int(y)))
        if s is None:
            s = QGuiApplication.primaryScreen()
        ov = self.overlays.get(s.name())
        if ov is None:
            self.rebuild()
            ov = self.overlays.get(s.name())
        return ov

    def emit(self, p: Particle):
        ov = self._overlay_at(p.x, p.y)
        if ov:
            ov.add(p)

    def step(self, dt):
        for ov in self.overlays.values():
            ov.step(dt)

    def clear(self):
        for ov in self.overlays.values():
            ov.clear()

    def raise_all(self):
        for ov in self.overlays.values():
            if ov.isVisible():
                ov.raise_()

    # ---------- presets ----------
    def fire_trail(self, x, y, facing, intensity=1.0):
        if self.density <= 0:
            return
        for _ in range(self._n(3, intensity) + 1):
            self.emit(Particle(
                EMBER,
                x - facing * random.uniform(2, 26) + random.uniform(-8, 8),
                y - random.uniform(2, 30),
                -facing * random.uniform(30, 140) + random.uniform(-25, 25),
                -random.uniform(40, 130),
                random.uniform(0.45, 1.05),
                random.uniform(5, 13),
                hue=random.random(),
            ))
        if random.random() < 0.35 * intensity * self.density:
            self.emit(Particle(SMOKE, x + random.uniform(-14, 14), y - random.uniform(6, 26),
                               random.uniform(-16, 16), -random.uniform(12, 34),
                               random.uniform(0.9, 1.7), random.uniform(9, 18)))

    def roar_burst(self, x, y, power=1.0):
        for _ in range(self._n(46, power)):
            a = random.uniform(-math.pi, 0.35)
            sp = random.uniform(90, 430) * power
            self.emit(Particle(EMBER, x + random.uniform(-16, 16), y - random.uniform(6, 44),
                               math.cos(a) * sp, math.sin(a) * sp,
                               random.uniform(0.5, 1.4), random.uniform(6, 17), hue=random.random()))
        for _ in range(self._n(9, power)):
            self.emit(Particle(SMOKE, x + random.uniform(-26, 26), y - random.uniform(10, 40),
                               random.uniform(-46, 46), -random.uniform(20, 70),
                               random.uniform(1.1, 2.2), random.uniform(12, 26)))

    def land_puff(self, x, y, power=1.0):
        n = self._n(13, power)
        if n == 0 and self.density > 0:
            n = 2
        for _ in range(n):
            side = random.choice((-1, 1))
            self.emit(Particle(DUST, x + random.uniform(-10, 10), y - random.uniform(0, 6),
                               side * random.uniform(35, 190) * power, -random.uniform(20, 130) * power,
                               random.uniform(0.35, 0.8), random.uniform(3, 9)))

    def sparkles(self, x, y, n=10):
        for _ in range(self._n(n)):
            self.emit(Particle(SPARK, x + random.uniform(-26, 26), y - random.uniform(10, 60),
                               random.uniform(-55, 55), -random.uniform(40, 130),
                               random.uniform(0.5, 1.1), random.uniform(4, 9),
                               spin=random.uniform(-6, 6)))

    def hearts(self, x, y, n=5):
        for _ in range(max(1, self._n(n)) if self.density > 0 else 0):
            self.emit(Particle(HEART, x + random.uniform(-18, 18), y - random.uniform(20, 50),
                               random.uniform(-26, 26), -random.uniform(45, 95),
                               random.uniform(0.9, 1.6), random.uniform(9, 15),
                               spin=random.uniform(-3, 3)))

    def notes(self, x, y, n=4):
        for _ in range(max(1, self._n(n)) if self.density > 0 else 0):
            self.emit(Particle(NOTE, x + random.uniform(-18, 18), y - random.uniform(20, 50),
                               random.uniform(-30, 30), -random.uniform(40, 90),
                               random.uniform(0.9, 1.5), random.uniform(9, 14),
                               spin=random.uniform(-3, 3)))
