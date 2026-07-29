"""Sprite loading with a scaled/flipped pixmap cache.

Frames are pre-scaled once per (animation, size, facing) so nothing is resized during
the 60 fps paint loop -- that's what keeps the motion smooth.
"""
from __future__ import annotations
import json, os
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QImage, QIcon


class Anim:
    __slots__ = ("name", "fps", "loop", "count", "_paths")

    def __init__(self, name, fps, loop, paths):
        self.name = name
        self.fps = float(fps)
        self.loop = bool(loop)
        self._paths = paths
        self.count = len(paths)

    def path(self, i):
        return self._paths[i % self.count] if self.count else None

    @property
    def duration(self):
        return self.count / self.fps if self.fps else 0.0


class Assets:
    def __init__(self, root):
        self.root = root
        man_path = os.path.join(root, "manifest.json")
        with open(man_path, "r", encoding="utf-8") as fh:
            man = json.load(fh)
        c = man["canvas"]
        self.canvas_w, self.canvas_h, self.baseline = c["w"], c["h"], c["baseline"]
        self.anims: dict[str, Anim] = {}
        for name, meta in man["anims"].items():
            d = os.path.join(root, meta["dir"])
            if not os.path.isdir(d):
                continue
            paths = [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".png")]
            if paths:
                self.anims[name] = Anim(name, meta["fps"], meta["loop"], paths)
        if not self.anims:
            raise RuntimeError(f"No sprite animations found under {root}")
        self._orig: dict[str, QPixmap] = {}
        self._cache: dict[tuple, QPixmap] = {}
        self._mask: dict[tuple, QImage] = {}

    # ---------- lookup ----------
    def has(self, name):
        return name in self.anims

    def anim(self, name) -> Anim:
        return self.anims.get(name) or self.anims.get("idle") or next(iter(self.anims.values()))

    def icon(self) -> QIcon:
        p = os.path.join(self.root, "icon.png")
        return QIcon(p) if os.path.exists(p) else QIcon()

    # ---------- pixmaps ----------
    def _original(self, path) -> QPixmap:
        pm = self._orig.get(path)
        if pm is None:
            pm = QPixmap(path)
            self._orig[path] = pm
        return pm

    def frame(self, anim_name, index, scale, flip=False, dpr=1.0) -> QPixmap:
        """Pixmap sized for `scale` logical px, rendered at `dpr` device pixels."""
        a = self.anim(anim_name)
        path = a.path(index)
        if path is None:
            return QPixmap()
        bucket = round(scale * 200)                      # 0.5% granularity
        dbucket = max(1, round(dpr * 4))                 # 0.25 dpr granularity
        key = (path, bucket, flip, dbucket)
        pm = self._cache.get(key)
        if pm is None:
            src = self._original(path)
            eff = (bucket / 200.0) * (dbucket / 4.0)
            w = max(1, round(self.canvas_w * eff))
            h = max(1, round(self.canvas_h * eff))
            pm = src.scaled(QSize(w, h), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            if flip:
                pm = pm.transformed(_flip_transform(), Qt.SmoothTransformation)
            pm.setDevicePixelRatio(dbucket / 4.0)
            if len(self._cache) > 3000:
                self._cache.clear()
                self._mask.clear()
            self._cache[key] = pm
        return pm

    def alpha_mask(self, anim_name, index, scale, flip=False) -> QImage | None:
        """Low-cost alpha image used for click-through hit testing (always dpr 1)."""
        a = self.anim(anim_name)
        path = a.path(index)
        if path is None:
            return None
        bucket = round(scale * 200)
        key = (path, bucket, flip)
        img = self._mask.get(key)
        if img is None:
            img = self.frame(anim_name, index, scale, flip, 1.0).toImage()
            if img.format() != QImage.Format_ARGB32:
                img = img.convertToFormat(QImage.Format_ARGB32)
            self._mask[key] = img
        return img

    def warm(self, names, scale, dpr=1.0):
        for n in names:
            a = self.anim(n)
            for i in range(a.count):
                self.frame(n, i, scale, False, dpr)
                self.frame(n, i, scale, True, dpr)


_T = None


def _flip_transform():
    global _T
    if _T is None:
        from PySide6.QtGui import QTransform
        _T = QTransform().scale(-1, 1)
    return _T
