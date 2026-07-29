"""Speech / notification bubble painted inside the pet window."""
from __future__ import annotations
import time
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainterPath, QPen, QLinearGradient

MOOD_STYLES = {
    "normal":  ((32, 30, 40, 240), (255, 176, 92), (245, 240, 236)),
    "happy":   ((30, 38, 34, 240), (126, 226, 150), (240, 250, 242)),
    "urgent":  ((44, 22, 22, 244), (255, 92, 66), (255, 236, 230)),
    "fire":    ((40, 20, 12, 244), (255, 132, 32), (255, 232, 200)),
    "sleepy":  ((26, 28, 44, 236), (146, 158, 224), (226, 230, 250)),
    "info":    ((26, 32, 44, 240), (120, 180, 255), (230, 240, 252)),
}


class Bubble:
    """Fades in, holds, fades out. Renders with a tail pointing down at the pet."""

    FADE = 0.18

    def __init__(self):
        self.text = ""
        self.title = ""
        self.mood = "normal"
        self.shown_at = 0.0
        self.duration = 0.0
        self.visible = False
        self.rect = QRectF()
        self._font = QFont("Segoe UI", 10)
        self._font.setWeight(QFont.Medium)
        self._title_font = QFont("Segoe UI Semibold", 10)
        self._wrap_cache = None

    def show(self, text, seconds=6.0, mood="normal", title=""):
        self.text = str(text or "").strip()
        self.title = str(title or "").strip()
        self.mood = mood if mood in MOOD_STYLES else "normal"
        self.shown_at = time.monotonic()
        self.duration = max(1.2, float(seconds))
        self.visible = bool(self.text or self.title)
        self._wrap_cache = None

    def hide(self):
        self.visible = False
        self.text = self.title = ""
        self.rect = QRectF()

    @property
    def active(self):
        return self.visible and (time.monotonic() - self.shown_at) < self.duration

    def opacity(self):
        if not self.visible:
            return 0.0
        el = time.monotonic() - self.shown_at
        if el < 0:
            return 0.0
        if el < self.FADE:
            return el / self.FADE
        left = self.duration - el
        if left <= 0:
            return 0.0
        if left < self.FADE:
            return left / self.FADE
        return 1.0

    def needs_repaint(self):
        """Only the fade in/out actually changes pixels; the hold phase is static."""
        if not self.visible:
            return False
        el = time.monotonic() - self.shown_at
        return el < self.FADE + 0.05 or (self.duration - el) < self.FADE + 0.05

    def step(self):
        if self.visible and not self.active and self.opacity() <= 0.0:
            self.hide()

    # ------------------------------------------------------------------
    def _wrap(self, fm_body, fm_title, max_w):
        if self._wrap_cache and self._wrap_cache[0] == max_w:
            return self._wrap_cache[1]
        lines = []
        if self.title:
            lines.append(("title", self.title))
        for para in self.text.split("\n"):
            words, cur = para.split(), ""
            if not words:
                lines.append(("body", ""))
                continue
            for w in words:
                trial = (cur + " " + w).strip()
                if fm_body.horizontalAdvance(trial) <= max_w or not cur:
                    cur = trial
                else:
                    lines.append(("body", cur))
                    cur = w
            if cur:
                lines.append(("body", cur))
        lines = lines[:7]
        self._wrap_cache = (max_w, lines)
        return lines

    def paint(self, p, anchor: QPointF, win_w, win_h, scale=1.0):
        """anchor = point just above the pet's cap, in window coords."""
        op = self.opacity()
        if op <= 0.001 or not (self.text or self.title):
            return
        bg, accent, fg = MOOD_STYLES[self.mood]
        body_font = QFont(self._font)
        title_font = QFont(self._title_font)
        body_font.setPointSizeF(max(8.0, 10.0 * min(1.25, max(0.85, scale))))
        title_font.setPointSizeF(body_font.pointSizeF())
        fm_b = QFontMetrics(body_font)
        fm_t = QFontMetrics(title_font)

        pad_x, pad_y, tail = 13.0, 9.0, 11.0
        max_w = min(320.0, win_w - 2 * pad_x - 18)
        lines = self._wrap(fm_b, fm_t, max_w)
        line_h = fm_b.height() + 2
        text_w = 0.0
        for kind, s in lines:
            fm = fm_t if kind == "title" else fm_b
            text_w = max(text_w, fm.horizontalAdvance(s))
        w = min(max_w, max(56.0, text_w)) + 2 * pad_x
        h = len(lines) * line_h + 2 * pad_y

        cx = anchor.x()
        left = min(max(6.0, cx - w / 2), win_w - w - 6.0)
        bottom = max(h + tail + 4.0, anchor.y())
        top = bottom - h - tail
        if top < 4.0:
            top = 4.0
            bottom = top + h + tail
        r = QRectF(left, top, w, h)
        self.rect = QRectF(r.left(), r.top(), r.width(), r.height() + tail)

        p.save()
        p.setOpacity(op)
        path = QPainterPath()
        path.addRoundedRect(r, 11, 11)
        tip_x = min(max(r.left() + 16, cx), r.right() - 16)
        tri = QPainterPath()
        tri.moveTo(tip_x - 8, r.bottom() - 1)
        tri.lineTo(tip_x + 8, r.bottom() - 1)
        tri.lineTo(tip_x + 1, r.bottom() + tail)
        tri.closeSubpath()
        path = path.united(tri)

        grad = QLinearGradient(r.topLeft(), r.bottomLeft())
        c0 = QColor(*bg)
        c1 = QColor(max(0, bg[0] - 8), max(0, bg[1] - 8), max(0, bg[2] - 8), bg[3])
        grad.setColorAt(0.0, c0)
        grad.setColorAt(1.0, c1)

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 70))
        p.translate(0, 2)
        p.drawPath(path)
        p.translate(0, -2)

        p.setBrush(grad)
        p.setPen(QPen(QColor(*accent, 205), 1.6))
        p.drawPath(path)

        p.setPen(QColor(*fg))
        y = r.top() + pad_y
        for kind, s in lines:
            if kind == "title":
                p.setFont(title_font)
                p.setPen(QColor(*accent))
            else:
                p.setFont(body_font)
                p.setPen(QColor(*fg))
            p.drawText(QRectF(r.left() + pad_x, y, r.width() - 2 * pad_x, line_h),
                       Qt.AlignLeft | Qt.AlignVCenter, s)
            y += line_h
        p.restore()
