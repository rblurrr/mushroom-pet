"""Reminders, timers, pomodoro, and the notification queue the pet speaks from.

Nothing is polled from online accounts -- the pet only ever announces things you
explicitly created here, or things pushed in through the local API.
"""
from __future__ import annotations
import time, uuid
from datetime import datetime, timedelta

KINDS = ("once", "daily", "weekdays", "interval")


def new_id():
    return uuid.uuid4().hex[:8]


class Notification:
    __slots__ = ("title", "text", "mood", "urgent", "ts", "seconds", "source")

    def __init__(self, text, title="", mood="info", urgent=False, seconds=None, source="local"):
        self.text = text
        self.title = title
        self.mood = "urgent" if urgent else mood
        self.urgent = urgent
        self.ts = time.time()
        self.seconds = seconds
        self.source = source

    def when(self):
        return datetime.fromtimestamp(self.ts).strftime("%H:%M")


class Reminder:
    """kind: once (fire_at epoch) | daily | weekdays (at HH:MM) | interval (every N min)."""

    def __init__(self, text, kind="once", fire_at=None, at="09:00", interval_min=30,
                 rid=None, enabled=True, last_fired=0.0, urgent=False):
        self.id = rid or new_id()
        self.text = text
        self.kind = kind if kind in KINDS else "once"
        self.fire_at = fire_at
        self.at = at
        self.interval_min = int(interval_min)
        self.enabled = bool(enabled)
        self.last_fired = float(last_fired)
        self.urgent = bool(urgent)
        if self.kind == "interval" and not self.last_fired:
            self.last_fired = time.time()

    # ---------- serialisation ----------
    def to_dict(self):
        return {"id": self.id, "text": self.text, "kind": self.kind, "fire_at": self.fire_at,
                "at": self.at, "interval_min": self.interval_min, "enabled": self.enabled,
                "last_fired": self.last_fired, "urgent": self.urgent}

    @staticmethod
    def from_dict(d):
        return Reminder(d.get("text", ""), d.get("kind", "once"), d.get("fire_at"),
                        d.get("at", "09:00"), d.get("interval_min", 30), d.get("id"),
                        d.get("enabled", True), d.get("last_fired", 0.0), d.get("urgent", False))

    # ---------- scheduling ----------
    def describe(self):
        if self.kind == "once":
            if not self.fire_at:
                return "unscheduled"
            left = self.fire_at - time.time()
            if left <= 0:
                return "due"
            if left < 3600:
                return f"in {int(left // 60) + 1} min"
            dt = datetime.fromtimestamp(self.fire_at)
            same_day = dt.date() == datetime.now().date()
            return dt.strftime("at %H:%M" if same_day else "%b %d, %H:%M")
        if self.kind == "daily":
            return f"daily at {self.at}"
        if self.kind == "weekdays":
            return f"weekdays at {self.at}"
        return f"every {self.interval_min} min"

    def due(self, now=None):
        if not self.enabled:
            return False
        now = now or time.time()
        if self.kind == "once":
            return bool(self.fire_at) and now >= self.fire_at
        if self.kind == "interval":
            return now - self.last_fired >= self.interval_min * 60
        try:
            hh, mm = [int(x) for x in self.at.split(":")]
        except ValueError:
            return False
        n = datetime.fromtimestamp(now)
        if self.kind == "weekdays" and n.weekday() >= 5:
            return False
        target = n.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if n < target:
            return False
        if now - target.timestamp() > 180:      # missed it by >3 min, skip until tomorrow
            return False
        return datetime.fromtimestamp(self.last_fired).date() != n.date() or self.last_fired == 0


class NotificationCenter:
    def __init__(self, cfg):
        self.cfg = cfg
        self.reminders: list[Reminder] = [Reminder.from_dict(d) for d in cfg.get("reminders", [])]
        self.queue: list[Notification] = []
        self.history: list[Notification] = []
        self.muted = False
        self._last_check = 0.0

    # ---------- persistence ----------
    def save(self):
        self.cfg["reminders"] = [r.to_dict() for r in self.reminders]

    # ---------- creating ----------
    def add_in_minutes(self, text, minutes, urgent=False):
        r = Reminder(text, "once", fire_at=time.time() + minutes * 60, urgent=urgent)
        self.reminders.append(r)
        self.save()
        return r

    def add_daily(self, text, at, weekdays_only=False, urgent=False):
        r = Reminder(text, "weekdays" if weekdays_only else "daily", at=at, urgent=urgent)
        self.reminders.append(r)
        self.save()
        return r

    def add_interval(self, text, minutes, urgent=False):
        r = Reminder(text, "interval", interval_min=minutes, urgent=urgent)
        self.reminders.append(r)
        self.save()
        return r

    def remove(self, rid):
        before = len(self.reminders)
        self.reminders = [r for r in self.reminders if r.id != rid]
        if len(self.reminders) != before:
            self.save()
            return True
        return False

    def clear_all(self):
        self.reminders.clear()
        self.save()

    def pending(self):
        out = []
        for r in self.reminders:
            if r.kind == "once" and r.fire_at and r.fire_at <= time.time():
                continue
            out.append(r)
        return out

    # ---------- pushing ----------
    def push(self, text, title="", urgent=False, mood="info", seconds=None, source="local"):
        n = Notification(text, title, mood, urgent, seconds, source)
        if self.muted and not urgent:
            self.history.insert(0, n)
            del self.history[24:]
            return None
        # collapse an identical message already waiting
        for q in self.queue:
            if q.text == n.text and q.title == n.title:
                return None
        self.queue.append(n)
        self.queue.sort(key=lambda x: (not x.urgent, x.ts))
        self.history.insert(0, n)
        del self.history[24:]
        return n

    def take(self):
        return self.queue.pop(0) if self.queue else None

    # ---------- ticking ----------
    def tick(self):
        now = time.time()
        if now - self._last_check < 2.0:
            return
        self._last_check = now
        changed = False
        still = []
        for r in self.reminders:
            if r.due(now):
                self.push(r.text, title="Reminder", urgent=r.urgent,
                          mood="urgent" if r.urgent else "info")
                r.last_fired = now
                changed = True
                if r.kind == "once":
                    continue        # drop one-shots after firing
            still.append(r)
        if len(still) != len(self.reminders):
            self.reminders = still
        if changed:
            self.save()
        self._tick_pomodoro(now)

    def _tick_pomodoro(self, now):
        p = self.cfg["pomodoro"]
        if not p.get("enabled"):
            return
        if not p.get("next_ts"):
            p["phase"] = "work"
            p["next_ts"] = now + p["work_min"] * 60
            self.cfg.save()
            return
        if now < p["next_ts"]:
            return
        if p["phase"] == "work":
            p["phase"] = "break"
            p["next_ts"] = now + p["break_min"] * 60
            self.push(f"{p['work_min']} min done. Stand up, look away, drink something.",
                      title="Break time", mood="happy")
        else:
            p["phase"] = "work"
            p["next_ts"] = now + p["work_min"] * 60
            self.push(f"Break's over. {p['work_min']} minutes of focus, go.",
                      title="Back to it", mood="info")
        self.cfg.save()

    def pomodoro_status(self):
        p = self.cfg["pomodoro"]
        if not p.get("enabled"):
            return "off"
        left = max(0, int((p.get("next_ts", 0) - time.time()) // 60) + 1)
        return f"{p.get('phase', 'work')} - {left} min left"

    def start_pomodoro(self, work=25, brk=5):
        p = self.cfg["pomodoro"]
        p.update({"enabled": True, "work_min": int(work), "break_min": int(brk),
                  "phase": "work", "next_ts": time.time() + int(work) * 60})
        self.cfg.save()

    def stop_pomodoro(self):
        self.cfg["pomodoro"]["enabled"] = False
        self.cfg["pomodoro"]["next_ts"] = 0
        self.cfg.save()


def parse_time_phrase(s: str):
    """Accepts '25', '25m', '1h30', '14:30', 'in 10 minutes'. Returns ('in', mins) or ('at', 'HH:MM')."""
    s = (s or "").strip().lower().replace("in ", "")
    if not s:
        return None
    if ":" in s and not s.endswith("m"):
        parts = s.split(":")
        try:
            hh, mm = int(parts[0]), int(parts[1][:2])
            if 0 <= hh < 24 and 0 <= mm < 60:
                return ("at", f"{hh:02d}:{mm:02d}")
        except ValueError:
            pass
    total = 0
    num = ""
    matched = False
    for ch in s:
        if ch.isdigit():
            num += ch
        elif ch in "hH" and num:
            total += int(num) * 60
            num = ""
            matched = True
        elif ch in "mM" and num:
            total += int(num)
            num = ""
            matched = True
    if num:
        total += int(num)
        matched = True
    return ("in", max(1, total)) if matched and total else None
