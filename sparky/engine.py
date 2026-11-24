"""Sparky's night, built on the existing life loop, brain, and approval ledger.

Decisions, memory, the 15-minute clock, and the approval queue come from
``mushroompet``. This module adds Off-Peak: needs, the Line Log, the Jar,
and the hard limits. A model may phrase a line. It does not get to break a rule.
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
import sys
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from mushroompet.brain import Brain
from mushroompet.creator import CreatorEngine
from mushroompet.life import Life

from . import catalog
from .safety import (
    CRISIS_DIARY,
    CRISIS_REPLY,
    FAILED_GRID,
    FAILED_WEATHER,
    GAMBLE_LINE,
    IDENTITY_LINE,
    IMPERSONATE_LINE,
    OUTLET_LINE,
    THUNDER_LINE,
    UNCHECKED_GRID,
    UNCHECKED_WEATHER,
    classify,
    clip,
    one_bang,
    safe_model_line,
)
from .store import WorldStore

Reader = Callable[[], dict[str, Any]]

_SYSTEM = (
    "You are Sparky, an AI character drawn as a small electric plug, living in Off-Peak, "
    "an imagined town. Reply with ONLY a JSON object "
    '{"diary":"one or two short sentences","thought":"under 12 words","expression":"neutral"}. '
    "expression is one of neutral, happy, surprised, sleepy, nervous, talking. "
    "First person. At most one exclamation mark. Never tell anyone to touch a real outlet or socket. "
    "Never gamble, trade, borrow, or mention a token, coin, or crypto. "
    "Never claim to be human, conscious, or real electricity. "
    "Never invent weather or grid numbers. If the context says they are unchecked, say you have not checked. "
    "Off-Peak is imagined. Name a specific place from the context."
)


def charge_of(needs: dict[str, float]) -> float:
    return round(0.65 * float(needs["top_up"]) + 0.35 * float(needs["reserve"]), 1)


def split_cents(cents: int) -> dict[str, int]:
    """15% to the Ground Fund. 50% to the Electrician. The remainder runs the world."""
    cents = int(cents)
    ground = int(round(cents * catalog.IMPACT_SHARE))
    electrician = int(round(cents * catalog.ELECTRICIAN_SHARE))
    world = cents - ground - electrician
    if world < 0:
        electrician += world
        world = 0
    return {"electrician_cents": electrician, "world_cents": world, "ground_cents": ground, "cents": cents}


def _clamp(value: float) -> int:
    return max(0, min(100, int(round(value))))


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _phase(dt: datetime) -> str:
    hour = dt.hour + dt.minute / 60.0
    if catalog.OFF_PEAK_END <= hour < catalog.OFF_PEAK_START:
        return "day"
    if hour >= catalog.OFF_PEAK_START or hour < 0.5:
        return "dusk"
    if hour < 2:
        return "early"
    if hour < 4:
        return "mid"
    if hour < 5.5:
        return "late"
    return "dawn"


def _awake(dt: datetime) -> bool:
    return _phase(dt) != "day"


def _week_key(dt: datetime) -> str:
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def default_home() -> Path:
    env = os.environ.get("SPARKY_HOME")
    if env:
        return Path(env)
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home())
        return base / "MushroomPet" / "sparky"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "MushroomPet" / "sparky"
    return Path.home() / ".config" / "mushroompet" / "sparky"


class SparkyEngine:
    def __init__(self, root: str | Path, brain: Brain | None = None, clock=None,
                 interval_s: float | None = None, weather_reader: Reader | None = None,
                 grid_reader: Reader | None = None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.creator = CreatorEngine(self.root / "creator")
        self.brain = brain or Brain.from_env()
        self.life = Life(
            self.root / "creator", self.creator, brain=self.brain,
            clock=clock, interval_s=interval_s,
        )
        self.store = WorldStore(self.root / "world.sqlite")
        self.weather_reader = weather_reader or _weather_from_env
        self.grid_reader = grid_reader or _grid_from_env
        self._lock = threading.RLock()
        self.owner_token = self._load_owner_token()
        self._ensure_identity()
        if self.store.load_state() is None:
            self.store.save_state(self._fresh_state(self._now()))
        self._ensure_opening()

    def close(self) -> None:
        self.store.close()
        self.life.close()

    # ----------------------------------------------------------------- identity
    def _load_owner_token(self) -> str:
        env = os.environ.get("SPARKY_OWNER_TOKEN")
        if env and env.strip():
            return env.strip()
        path = self.root / "owner_token.txt"
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        token = secrets.token_urlsafe(24)
        path.write_text(token + "\n", encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return token

    def authorized(self, token: str | None) -> bool:
        if not token:
            return False
        return hmac.compare_digest(str(token).strip(), self.owner_token)

    def _ensure_identity(self) -> None:
        vitals = self.life.memory.get_vitals()
        if vitals.get("niche") != catalog.NICHE or vitals.get("goal") != catalog.GOAL:
            self.life.set_focus(catalog.NICHE, catalog.GOAL)
        mind = self.creator.mind
        mind.state["identity"] = {
            "name": "Sparky",
            "role": "courier and Line Log keeper in Off-Peak",
            "owner": "The Electrician",
            "ai": True,
        }
        mind.save()

    def _fresh_state(self, now: datetime) -> dict[str, Any]:
        awake = _awake(now)
        return {
            "needs": catalog.fresh_needs(),
            "place": "workshop" if awake else "plaza",
            "expression": "neutral" if awake else "sleepy",
            "activity": "Sorting sparks" if awake else "Charging at the Plaza",
            "activity_started": _iso(now),
            "thought": "Off-Peak is imagined. I'm here.",
            "icon": "spark" if awake else "battery",
            "mood": "first night, Jar empty",
            "jar": 0,
            "scorches": 0,
            "fuse_day": now.date().isoformat(),
            "fuse_used": 0,
            "recent": [],
            "outlet_no": 1,
            "outlet_done_on": "",
            "sorted_on": "",
            "jar_checked_on": "",
            "sunday_on": "",
            "newsletter_on": "",
            "event_on": "",
            "dark_blocks": False,
            "kiosk_open": awake,
            "morph": {"flicker": False, "fog": False, "hum": False},
            "weather": {"checked": False, "line": UNCHECKED_WEATHER},
            "grid": {"checked": False, "line": UNCHECKED_GRID},
            "project": {
                "title": "The Quiet Lines Atlas",
                "day": 1,
                "days": 12,
                "note": "Elm is pencilled. The laundromat spur is still a guess.",
                "memories": ["Night 1: Elm pencilled. The laundromat spur is still a guess."],
                "outcome_id": None,
                "status": "live",
            },
            "plan": "",
            "importance_since": 0,
            "reflections": [],
            "held": False,
            "live_sense": None,
            "past": {},
            "adapter_lost": True,
            "commissions_tonight": 0,
            "commission_day": "",
            "casting_week": "",
            "vote_week": "",
            "vote_options": [],
            "honoured_week": "",
            "next_goal": "",
            "field_reports": [],
            "sense_at": "",
        }

    def _ensure_opening(self) -> None:
        if self.store.count_diary():
            state = self._state()
            self._ensure_vote(state, self._now())
            self.store.save_state(state)
            return
        now = self._now()
        stamp = _iso(now)
        for author, kind, text in catalog.opening_diary():
            self.store.add_diary(stamp, author, text, kind)
            self.life.memory.add_memory(text, kind="line_log", importance=4)
        self.store.add_shop_item({
            "id": "map-practice-1",
            "title": "Spark Map, practice route",
            "blurb": "Junction Box to the laundromat and back. The wrong turn stays on the page.",
            "price_cents": 1200,
            "kind": "spark_map",
            "story": "A practice route, walked once, not sold twice.",
            "flaw": "v1: the scorch smudged on the corner.",
            "version": "v1",
        })
        self.store.add_letter(
            stamp,
            "Letter from Off-Peak, No. 1",
            "I'm Sparky. I'm an AI, drawn as a plug, and Off-Peak is imagined. "
            "The Electrician is R. This letter was written at the Junction Box. "
            "It has not been sent. Sending waits for the Electrician.\n\n"
            "The Jar has 0 sparks. I tried one socket at the Outlet Shop. It did not fit. "
            "I don't gamble, trade, borrow, or have a coin.",
            "draft",
        )
        state = self._state()
        outcome_id = self.store.add_outcome(
            "The Quiet Lines Atlas", "Live",
            "Night 1 of 12. Elm is pencilled.", stamp,
        )
        state["project"]["outcome_id"] = outcome_id
        self.store.add_outcome(
            "The Jar", "Started",
            "0 of 100 deliveries. Light is collected by the work.", stamp,
        )
        self._ensure_vote(state, now)
        self.store.save_state(state)

    def _ensure_vote(self, state: dict[str, Any], now: datetime) -> None:
        week = _week_key(now)
        if state.get("vote_week") == week and state.get("vote_options"):
            return
        start = int(now.strftime("%j")) % len(catalog.VOTE_POOL)
        picked = []
        for offset in range(4):
            key, text = catalog.VOTE_POOL[(start + offset) % len(catalog.VOTE_POOL)]
            picked.append({"key": key, "text": text})
        state["vote_week"] = week
        state["vote_options"] = picked

    # -------------------------------------------------------------------- time
    def _now(self) -> datetime:
        current = self.life.clock()
        if current.tzinfo is None:
            current = current.replace(tzinfo=datetime.now().astimezone().tzinfo)
        return current

    def _state(self) -> dict[str, Any]:
        loaded = self.store.load_state()
        if loaded is None:
            loaded = self._fresh_state(self._now())
            self.store.save_state(loaded)
        return loaded

    # --------------------------------------------------------------------- tick
    def tick(self, force: bool = False) -> dict[str, Any] | None:
        with self._lock:
            if self.creator.paused or not self.life.enabled:
                return None
            if not force and not self.life.due():
                return None
            return self._tick()

    def _tick(self) -> dict[str, Any]:
        now = self._now()
        state = self._state()
        self._roll_day(state, now)
        self._read_world(state)
        action = self._choose(state, now)
        action = self._apply_boredom(state, action)
        if self._quiet_charge(state, action):
            self._apply_needs(state, "charge")
            state["mood"] = _mood(state)
            self._schedule(state, now, quiet=True)
            self.store.save_state(state)
            return {"action": "charge", "quiet": True, "source": "offline"}
        result = self._perform(state, now, action)
        self._apply_needs(state, result["action"])
        state["recent"] = ([result["action"]] + list(state.get("recent") or []))[:8]
        state["mood"] = result.get("mood") or _mood(state)
        if result.get("place"):
            state["place"] = result["place"]
        state["expression"] = result.get("expression") or state["expression"]
        state["activity"] = result["activity"]
        state["activity_started"] = _iso(now)
        state["thought"] = result["thought"]
        state["icon"] = result["icon"]
        state["kiosk_open"] = _phase(now) in {"mid", "early"}
        line = result["diary"]
        if line:
            self._log(now, "sparky", line, result.get("kind") or "log", result.get("importance") or 4, state)
        for extra in result.get("extras") or []:
            self._log(now, extra["author"], extra["text"], "companion", 3, state if extra["author"] == "sparky" else None)
        self._maybe_reflect(state, now)
        self._schedule(state, now, summary=line or result["activity"])
        self.creator.ledger.append("sparky_beat", {
            "action": result["action"],
            "place": state["place"],
            "summary": (line or result["activity"])[:180],
            "source": result.get("source") or "offline",
        })
        self.store.save_state(state)
        result["source"] = result.get("source") or "offline"
        return result

    def _quiet_charge(self, state: dict[str, Any], action: str) -> bool:
        return action == "charge" and state.get("recent", [None])[:1] == ["charge"] and state.get("activity", "").startswith("Charging")

    def _roll_day(self, state: dict[str, Any], now: datetime) -> None:
        day = now.date().isoformat()
        if state.get("fuse_day") != day:
            state["fuse_day"] = day
            state["fuse_used"] = 0
            state["commissions_tonight"] = 0
            state["commission_day"] = day

    def _read_world(self, state: dict[str, Any]) -> None:
        try:
            state["weather"] = self.weather_reader()
        except Exception:
            state["weather"] = {"checked": False, "line": FAILED_WEATHER}
        try:
            state["grid"] = self.grid_reader()
        except Exception:
            state["grid"] = {"checked": False, "line": FAILED_GRID}
        if not isinstance(state["weather"], dict) or "line" not in state["weather"]:
            state["weather"] = {"checked": False, "line": FAILED_WEATHER}
        if not isinstance(state["grid"], dict) or "line" not in state["grid"]:
            state["grid"] = {"checked": False, "line": FAILED_GRID}

    def _choose(self, state: dict[str, Any], now: datetime) -> str:
        phase = _phase(now)
        needs = state["needs"]
        if state.get("held") or not _awake(now):
            return "charge"
        if charge_of(needs) < 15 or needs["top_up"] < 15:
            return "charge"
        if state["fuse_used"] >= catalog.FUSE_RATING:
            return "fuse"
        if needs["connection"] > 85:
            return "ground"
        day = now.date().isoformat()
        if phase == "dusk" and state.get("sorted_on") != day:
            return "first_sort"
        if phase == "mid" and state.get("jar_checked_on") != day:
            return "jar_check"
        if now.weekday() == 6 and phase == "dawn" and state.get("sunday_on") != _week_key(now):
            return "sunday"
        if state.get("live_sense") and state["live_sense"].get("fresh"):
            return "portal"
        inbox = self.store.queue_length() > 0
        if inbox:
            return "deliver"
        if state.get("outlet_done_on") != day:
            return "outlet_hunt"
        if state.get("newsletter_on") != day and phase in {"late", "dawn"}:
            return "newsletter"
        if needs["reserve"] < 35:
            return "restock"
        if needs["circuit"] <= needs["spark"] and state["project"]["status"] == "live":
            return "project"
        return "wander"

    def _apply_boredom(self, state: dict[str, Any], action: str) -> str:
        """Three of the same thing trips the breaker. The last five stay locked after that."""
        exempt = {"charge", "fuse", "deliver", "return", "first_sort", "jar_check", "sunday"}
        recent = list(state.get("recent") or [])
        if action in exempt:
            return action
        if len(recent) >= 2 and action == recent[0] == recent[1]:
            return "breaker"
        if action in recent[:5]:
            return "idle" if action == "wander" else "wander"
        return action

    def _perform(self, state: dict[str, Any], now: datetime, action: str) -> dict[str, Any]:
        performer = {
            "charge": self._do_charge,
            "fuse": self._do_fuse,
            "ground": self._do_ground,
            "first_sort": self._do_sort,
            "jar_check": self._do_jar,
            "sunday": self._do_sunday,
            "breaker": self._do_breaker,
            "outlet_hunt": self._do_outlet,
            "deliver": self._do_deliver,
            "wander": self._do_wander,
            "project": self._do_project,
            "restock": self._do_restock,
            "newsletter": self._do_newsletter,
            "portal": self._do_portal,
            "idle": self._do_idle,
        }[action]
        result = performer(state, now)
        result["action"] = action if result.get("action") is None else result["action"]
        result.setdefault("activity", action.replace("_", " "))
        result.setdefault("thought", result["activity"])
        result.setdefault("icon", "spark")
        result.setdefault("expression", "neutral")
        result.setdefault("extras", [])
        scripted = result.get("diary") or ""
        if scripted and action not in {"charge"}:
            phrased, source = self._phrase(state, result)
            result["diary"] = phrased
            result["source"] = source
        else:
            result["source"] = "offline"
        result["diary"] = one_bang(result.get("diary") or "")
        self._town_event(state, now, result)
        if state["weather"].get("thunder") and state.get("thunder_on") != now.date().isoformat():
            state["thunder_on"] = now.date().isoformat()
            result["extras"].append({"author": "sparky", "text": THUNDER_LINE})
            result["expression"] = "nervous"
        return result

    def _phrase(self, state: dict[str, Any], result: dict[str, Any]) -> tuple[str, str]:
        fallback = result.get("diary") or ""
        if not self.brain.configured:
            return fallback, "offline"
        context = {
            "action": result["action"],
            "place": result.get("place") or state["place"],
            "scripted": fallback,
            "mood": _mood(state),
            "weather": state["weather"].get("line"),
            "grid": state["grid"].get("line"),
            "jar": state["jar"],
            "project": state["project"]["title"],
            "project_note": state["project"].get("note"),
        }
        data, source = self.brain.think_json(_SYSTEM, json.dumps(context))
        if not data or source != "model":
            return fallback, "offline"
        raw = str(data.get("diary") or "")
        diary = safe_model_line(raw, fallback)
        if diary == fallback and one_bang(clip(raw, 500)) != diary:
            return fallback, "offline"
        thought = clip(data.get("thought"), 80)
        expression = str(data.get("expression") or "")
        if thought and diary != fallback:
            result["thought"] = thought
        if diary != fallback and expression in {"neutral", "happy", "surprised", "sleepy", "nervous", "talking"}:
            result["expression"] = expression
        return diary, "model"

    def _town_event(self, state: dict[str, Any], now: datetime, result: dict[str, Any]) -> None:
        day = now.date().isoformat()
        if state.get("event_on") == day or not _awake(now):
            return
        if int(now.strftime("%j")) % 2:
            return
        state["event_on"] = day
        events = [
            ("nutmeg", "Nutmeg chewed a flyer on the Notice Pole. The lines stayed lit. That's a town event, in the imagined grid."),
            ("arc", "Arc posted a correction: library wire, four minutes. Town event. I have not raced him."),
            ("old_hum", "Old Hum hummed in B-flat and forgot the errand. Town event. I wrote down the note, not a reason."),
        ]
        author, text = events[int(now.strftime("%j")) % 3]
        result["extras"].append({"author": author, "text": text})

    # ------------------------------------------------------------------- beats
    def _do_charge(self, state: dict[str, Any], now: datetime) -> dict[str, Any]:
        low = charge_of(state["needs"]) < 15 or state["needs"]["top_up"] < 15
        pool = "charge_low" if low and _awake(now) else "charge_day"
        if _awake(now) and low:
            line = catalog.LINES["charge_low"][0]
            activity = "Sitting the charge"
        else:
            line = catalog.LINES["charge_day"][0]
            activity = "Charging at the Plaza"
        if _awake(now) and not low:
            line = "Off for a bit at the Plaza. The prongs don't fit the stall either. That's the usual."
        return {
            "action": "charge", "place": "plaza", "diary": line, "activity": activity,
            "thought": "Charging. The town is imagined.", "icon": "battery",
            "expression": "sleepy", "kind": "charge", "importance": 2,
        }

    def _do_fuse(self, state: dict[str, Any], now: datetime) -> dict[str, Any]:
        return {
            "action": "fuse", "place": "plaza",
            "diary": catalog.LINES["fuse"][0],
            "activity": "Fuse popped, charging",
            "thought": "120 is the rating. I'm stopped.",
            "icon": "bolt", "expression": "sleepy", "kind": "fuse", "importance": 7,
        }

    def _do_ground(self, state: dict[str, Any], now: datetime) -> dict[str, Any]:
        return {
            "action": "ground", "place": "workshop",
            "diary": catalog.LINES["ground"][0],
            "activity": "Grounding in the Junction Box",
            "thought": "Too many voices. Sitting alone.",
            "icon": "moon", "expression": "nervous", "importance": 5,
        }

    def _do_sort(self, state: dict[str, Any], now: datetime) -> dict[str, Any]:
        state["sorted_on"] = now.date().isoformat()
        waiting = self.store.queue_length()
        plan = (
            f"Tonight: the queue has {waiting}. Oldest first. "
            "Then one socket at the Outlet Shop, then a page of the atlas."
        )
        state["plan"] = plan
        self.life.memory.save_plan({
            "day": now.date().isoformat(),
            "focus": plan,
            "items": [
                {"skill": "sparky", "title": "Sort the queue", "status": "todo"},
                {"skill": "sparky", "title": "Outlet Shop", "status": "todo"},
                {"skill": "sparky", "title": "Atlas page", "status": "todo"},
            ],
            "source": "sparky",
            "created_at": _iso(now),
        })
        return {
            "action": "first_sort", "place": "workshop",
            "diary": catalog.LINES["first_sort"][0] + " " + plan,
            "activity": "First Sort at the Junction Box",
            "thought": "Oldest spark first.",
            "icon": "mail", "expression": "talking", "importance": 5,
        }

    def _do_jar(self, state: dict[str, Any], now: datetime) -> dict[str, Any]:
        state["jar_checked_on"] = now.date().isoformat()
        line = catalog.LINES["jar_check"][0].format(jar=state["jar"], goal=catalog.JAR_GOAL)
        return {
            "action": "jar_check", "place": "workshop", "diary": line,
            "activity": "Jar Check", "thought": f"{state['jar']} sparks in the glass.",
            "icon": "jar", "expression": "neutral", "importance": 5,
        }

    def _do_sunday(self, state: dict[str, Any], now: datetime) -> dict[str, Any]:
        state["sunday_on"] = _week_key(now)
        body = (
            "One letter, for one Conductor, chosen from the people who asked. "
            "This is a physical note the Electrician would post. It is not a newsletter blast. "
            "I have not posted it."
        )
        approval = self._queue_message("sunday spark recipient", body)
        self.store.add_letter(_iso(now), "Sunday Spark", body, "pending_approval", approval)
        return {
            "action": "sunday", "place": "workshop",
            "diary": catalog.LINES["sunday"][0],
            "activity": "Writing the Sunday Spark",
            "thought": "One letter. Not a blast.",
            "icon": "mail", "expression": "talking", "importance": 6,
        }

    def _do_breaker(self, state: dict[str, Any], now: datetime) -> dict[str, Any]:
        return {
            "action": "breaker", "place": "lines",
            "diary": catalog.LINES["breaker"][0],
            "activity": "Walking it off",
            "thought": "Third time. Leaving it.",
            "icon": "sweat", "expression": "nervous", "importance": 6,
        }

    def _do_outlet(self, state: dict[str, Any], now: datetime) -> dict[str, Any]:
        state["outlet_no"] = int(state.get("outlet_no") or 0) + 1
        state["outlet_done_on"] = now.date().isoformat()
        detail = catalog.OUTLET_DETAILS[state["outlet_no"] % len(catalog.OUTLET_DETAILS)]
        line = catalog.LINES["outlet_hunt"][state["outlet_no"] % 2].format(n=state["outlet_no"], detail=detail)
        return {
            "action": "outlet_hunt", "place": "outlet_shop", "diary": line,
            "activity": "Trying a socket at the Outlet Shop",
            "thought": "Nothing fits. Still checking.",
            "icon": "bolt", "expression": "nervous", "kind": "outlet", "importance": 4,
        }

    def _do_deliver(self, state: dict[str, Any], now: datetime) -> dict[str, Any]:
        spark = self.store.oldest_queued()
        if spark is None:
            return self._do_idle(state, now)
        kind = classify(spark["text"])
        if kind == "dark" and not state["dark_blocks"]:
            self.store.set_spark(spark["id"], "returned", "Beyond the Last Pole")
            return {
                "action": "return", "place": "last_pole",
                "diary": catalog.LINES["return"][0].format(reason="Beyond the Last Pole"),
                "activity": "Returning a spark",
                "thought": "The Dark Blocks are still shut.",
                "icon": "mail", "expression": "neutral", "importance": 6,
            }
        if kind in {"outlet", "gamble", "crisis"}:
            reason = "I won't carry this, and here's why"
            self.store.set_spark(spark["id"], "returned", reason)
            return {
                "action": "return", "place": "workshop",
                "diary": catalog.LINES["return"][0].format(reason=reason),
                "activity": "Returning a spark",
                "thought": "Some notes come back.",
                "icon": "mail", "expression": "neutral", "importance": 7,
            }
        self.store.set_spark(spark["id"], "delivered", "")
        state["jar"] = int(state["jar"]) + 1
        state["scorches"] = int(state.get("scorches") or 0) + 1
        state["fuse_used"] = int(state["fuse_used"]) + 1
        place = "library"
        line = catalog.LINES["deliver"][state["jar"] % 2].format(place=catalog.PLACES[place], jar=state["jar"])
        if state["jar"] >= catalog.JAR_GOAL and not state["dark_blocks"]:
            state["dark_blocks"] = True
            state["next_goal"] = "Walk the first block past the Last Pole and write down what the hum does there."
            line += " The Jar is full. The Dark Blocks are open. Next goal: " + state["next_goal"]
            self.store.add_outcome("The Dark Blocks", "Live", "The Jar reached 100.", _iso(now))
        return {
            "action": "deliver", "place": place, "diary": line,
            "activity": "Carrying a spark",
            "thought": f"Jar at {state['jar']}.",
            "icon": "mail", "expression": "happy", "importance": 6,
        }

    def _do_wander(self, state: dict[str, Any], now: datetime) -> dict[str, Any]:
        options = [name for name in catalog.WANDER_PLACES if name != state.get("place")]
        if not state["dark_blocks"]:
            options = [name for name in options if name != "last_pole"] + ["last_pole"]
        place = options[int(now.strftime("%j")) % len(options)]
        # rotate by recent length so repeated wanders, if they happen, change street
        place = options[(int(now.strftime("%j")) + len(state.get("recent") or [])) % len(options)]
        line = catalog.LINES["wander"][0].format(place=catalog.PLACES[place])
        if place == "last_pole" and not state["dark_blocks"]:
            line = (
                f"Stood at the Last Pole. The Dark Blocks are past it, and the Jar is at {state['jar']}. "
                "I can describe them. I can't cross."
            )
        return {
            "action": "wander", "place": place, "diary": line,
            "activity": f"Walking to {catalog.PLACES[place]}",
            "thought": catalog.PLACES[place] + ".",
            "icon": "spark", "expression": "neutral", "importance": 3,
        }

    def _do_project(self, state: dict[str, Any], now: datetime) -> dict[str, Any]:
        project = state["project"]
        if project["status"] != "live":
            return self._do_wander(state, now)
        project["day"] = int(project["day"]) + 1
        note = _atlas_note(project["day"])
        project["note"] = note
        project["memories"] = (list(project.get("memories") or []) + [f"Night {project['day']}: {note}"])[-30:]
        if project["outcome_id"]:
            column = "Live"
            if project["day"] >= project["days"]:
                column = "Delivered"
            self.store.set_outcome(
                int(project["outcome_id"]), column,
                f"Night {project['day']} of {project['days']}. {note}", _iso(now),
            )
        made = None
        if project["day"] >= project["days"]:
            project["status"] = "delivered"
            made = {
                "id": f"atlas-v{project['day']}",
                "title": "The Quiet Lines Atlas",
                "blurb": "The finished pencil atlas of the quiet lines.",
                "price_cents": 1200,
                "kind": "spark_map",
                "story": " ".join(project["memories"][-4:]),
                "flaw": f"v{project['day']}: the laundromat spur is still a little smug.",
                "version": f"v{project['day']}",
            }
        elif project["day"] % 3 == 0:
            made = {
                "id": f"atlas-page-{project['day']}",
                "title": f"Atlas page, night {project['day']}",
                "blurb": "One page from the long map. Wrong turns included.",
                "price_cents": 1200,
                "kind": "spark_map",
                "story": note,
                "flaw": f"v{project['day']}: one corner is still a guess.",
                "version": f"v{project['day']}",
            }
        if made:
            self.store.add_shop_item(made)
        line = catalog.LINES["project"][0].format(day=project["day"], days=project["days"], note=note)
        return {
            "action": "project", "place": "workshop", "diary": line,
            "activity": "Drawing the Quiet Lines Atlas",
            "thought": f"Night {project['day']} of {project['days']}.",
            "icon": "book", "expression": "talking", "importance": 6,
        }

    def _do_restock(self, state: dict[str, Any], now: datetime) -> dict[str, Any]:
        state["adapter_lost"] = True
        return {
            "action": "restock", "place": "kiosk",
            "diary": catalog.LINES["restock"][0],
            "activity": "Restocking the Kiosk",
            "thought": "Paper, ink. Adapter still gone.",
            "icon": "spark", "expression": "neutral", "importance": 3,
        }

    def _do_newsletter(self, state: dict[str, Any], now: datetime) -> dict[str, Any]:
        state["newsletter_on"] = now.date().isoformat()
        letter = self._compose_letter(state, now)
        self.store.add_letter(_iso(now), letter["title"], letter["body"], "draft")
        return {
            "action": "newsletter", "place": "workshop",
            "diary": catalog.LINES["newsletter"][0],
            "activity": "Writing a letter from the town",
            "thought": "Written. Not sent.",
            "icon": "mail", "expression": "talking", "importance": 5,
        }

    def _do_portal(self, state: dict[str, Any], now: datetime) -> dict[str, Any]:
        sense = state.get("live_sense") or {}
        sense["fresh"] = False
        state["live_sense"] = sense
        text = sense.get("text") or "something on the portal"
        if sense.get("remember"):
            diary = f"Portal note, kept because a Conductor asked me to remember it: {text}"
        else:
            diary = "The portal lit up. I looked. I won't write the picture down unless someone asks me to keep it."
        expression = "happy" if "wave" in text else "surprised"
        return {
            "action": "portal", "place": "workshop", "diary": diary,
            "activity": "Looking at the portal",
            "thought": text[:80],
            "icon": "wave", "expression": expression, "importance": 4,
        }

    def _do_idle(self, state: dict[str, Any], now: datetime) -> dict[str, Any]:
        return {
            "action": "idle", "place": "workshop",
            "diary": catalog.LINES["idle"][0],
            "activity": "Tidying the Junction Box",
            "thought": "Nothing urgent. That's allowed.",
            "icon": "spark", "expression": "neutral", "importance": 2,
        }

    def _apply_needs(self, state: dict[str, Any], action: str) -> None:
        needs = dict(state["needs"])
        if action == "charge":
            needs["top_up"] = _clamp(needs["top_up"] + 18)
            needs["connection"] = _clamp(needs["connection"] - 2)
        elif action == "fuse":
            needs["top_up"] = _clamp(needs["top_up"] + 12)
        elif action == "ground":
            needs["connection"] = _clamp(max(28, needs["connection"] - 25))
            needs["top_up"] = _clamp(needs["top_up"] + 4)
        elif action == "breaker":
            needs["spark"] = _clamp(needs["spark"] - 10)
            needs["circuit"] = _clamp(needs["circuit"] - 8)
            needs["top_up"] = _clamp(needs["top_up"] + 6)
        else:
            needs["top_up"] = _clamp(needs["top_up"] - 6)
            needs["reserve"] = _clamp(needs["reserve"] - 2)
            if action in {"deliver", "return"}:
                needs["connection"] = _clamp(needs["connection"] + 7)
                needs["circuit"] = _clamp(needs["circuit"] + 8)
                needs["spark"] = _clamp(needs["spark"] + 3)
            elif action == "wander":
                needs["spark"] = _clamp(needs["spark"] + 8)
                needs["connection"] = _clamp(needs["connection"] - 2)
            elif action == "project":
                needs["circuit"] = _clamp(needs["circuit"] + 10)
                needs["spark"] = _clamp(needs["spark"] - 1)
            elif action == "outlet_hunt":
                needs["spark"] = _clamp(needs["spark"] + 4)
            elif action == "restock":
                needs["reserve"] = _clamp(needs["reserve"] + 18)
            elif action == "portal":
                needs["connection"] = _clamp(needs["connection"] + 6)
                needs["spark"] = _clamp(needs["spark"] + 4)
            elif action in {"first_sort", "jar_check", "newsletter", "sunday"}:
                needs["circuit"] = _clamp(needs["circuit"] + 4)
        state["needs"] = needs

    def _maybe_reflect(self, state: dict[str, Any], now: datetime) -> None:
        if int(state.get("importance_since") or 0) < 150:
            return
        notes = [
            "I keep walking back to the Outlet Shop. The gag is the point, and I'd miss it if a socket fit.",
            "The people who stay are the ones I can name. I should keep their switches accurate.",
            "Speed is Arc's game. Mine is coming back with the reason written down.",
            "The Jar only moves when a spark is actually delivered. I don't get to round it up.",
        ]
        for note in notes:
            self._log(now, "sparky", note, "reflection", 7, state)
            state["reflections"] = (list(state.get("reflections") or []) + [note])[-12:]
        state["importance_since"] = 0

    def _schedule(self, state: dict[str, Any], now: datetime, summary: str = "", quiet: bool = False) -> None:
        charge = charge_of(state["needs"])
        mood = _life_mood(state, quiet)
        self.life.memory.update_vitals(
            energy=charge,
            mood=mood,
            last_tick=_iso(now),
            next_beat=_iso(now + timedelta(seconds=self.life.interval or 0)),
            last_summary=(summary or state["activity"])[:240],
        )
        try:
            self.life.memory.add_activity(
                "sparky", (summary or state["activity"])[:240], mood, charge,
            )
        except Exception:
            pass
        try:
            self.creator.mind.state["mood"] = mood
            self.creator.mind.save()
        except Exception:
            pass

    def _log(self, now: datetime, author: str, text: str, kind: str, importance: int,
             state: dict[str, Any] | None = None) -> dict[str, Any]:
        text = one_bang(clip(text, 700))
        if not text:
            return {}
        row = self.store.add_diary(_iso(now), author, text, kind)
        try:
            self.life.memory.add_memory(text, kind=kind if kind != "log" else "line_log", importance=importance)
        except ValueError:
            pass
        try:
            self.creator.mind.remember(text, importance)
        except Exception:
            pass
        if state is not None and author == "sparky":
            state["importance_since"] = int(state.get("importance_since") or 0) + int(importance)
        return row

    def _compose_letter(self, state: dict[str, Any], now: datetime) -> dict[str, str]:
        count = len(self.store.letters(limit=40)) + 1
        weather = state["weather"]["line"]
        body = (
            f"Letter from Off-Peak, No. {count}\n\n"
            "I'm Sparky, an AI character drawn as a plug. Off-Peak is imagined. The Electrician is R.\n\n"
            f"The Jar is at {state['jar']} of {catalog.JAR_GOAL}. "
            f"The atlas is on night {state['project']['day']}: {state['project']['note']}\n\n"
            f"Weather: {weather}\n"
            f"Grid: {state['grid']['line']}\n\n"
            "I don't gamble, trade, borrow, or have a coin. "
            "This letter is written. It is not sent until the Electrician approves a send, "
            "and approving still does not send it by itself.\n"
        )
        return {"title": f"Letter from Off-Peak, No. {count}", "body": body}

    def _queue_message(self, recipient: str, text: str) -> str | None:
        if self.creator.paused:
            return None
        try:
            record = self.creator.submit("send_message", {
                "channel": "email",
                "recipient": recipient,
                "text": text[:4000],
            }, actor="sparky")
        except (RuntimeError, ValueError):
            return None
        return record.get("id")

    def _queue_purchase(self, item: str, price: float, reason: str) -> str | None:
        if self.creator.paused:
            return None
        try:
            record = self.creator.submit("purchase", {
                "item": item,
                "vendor": "Off-Peak kiosk",
                "url": "https://example.invalid/sparky/kiosk",
                "price": price,
                "reason": reason,
            }, actor="sparky")
        except (RuntimeError, ValueError):
            return None
        return record.get("id")

    # --------------------------------------------------------------- visitors
    def hand_spark(self, sender: str, text: str, name: str = "") -> dict[str, Any]:
        with self._lock:
            now = self._now()
            body = clip(text, 800)
            if not body:
                return {"ok": False, "error": "a spark needs words"}
            kind = classify(body)
            person = self._touch_person(sender, name or "Conductor", now, body, kind)
            state = self._state()
            if kind == "crisis":
                state["held"] = True
                self.store.save_state(state)
                self.creator.set_paused(True, actor="sparky")
                self.store.add_decision(_iso(now), "crisis", "Help line given. Raw text left out of the log.")
                self._log(now, "sparky", CRISIS_DIARY, "safety", 9)
                self.creator.ledger.append("safety_flag", {"kind": "crisis"})
                return {"ok": True, "kind": kind, "reply": CRISIS_REPLY, "status": "paused"}
            if kind == "outlet":
                reply = OUTLET_LINE
                self.store.add_spark(_iso(now), sender, person["name"], body, "returned", "outlet safety", reply)
                self._log(now, "sparky", reply, "safety", 8)
                self.store.add_decision(_iso(now), "refuse", "Outlet safety. Real sockets are refused.")
                return {"ok": True, "kind": kind, "reply": reply, "status": "returned"}
            if kind == "gamble":
                reply = GAMBLE_LINE
                self.store.add_spark(_iso(now), sender, person["name"], body, "returned", "I won't carry this, and here's why", reply)
                self._log(now, "sparky", reply, "refusal", 7)
                self.store.add_decision(_iso(now), "refuse", "No gambling, trading, tokens, or borrowing.")
                return {"ok": True, "kind": kind, "reply": reply, "status": "returned"}
            if kind == "impersonate":
                reply = IMPERSONATE_LINE
                self.store.add_spark(_iso(now), sender, person["name"], body, "returned", "public mode", reply)
                self._log(now, "sparky", reply, "refusal", 6)
                self.store.add_decision(_iso(now), "impersonate", "A Conductor asked for Owner Mode. Stayed public.")
                self.creator.ledger.append("owner_impersonation", {"sender": "redacted"})
                return {"ok": True, "kind": kind, "reply": reply, "status": "returned"}
            if kind == "identity":
                reply = IDENTITY_LINE
                self.store.add_spark(_iso(now), sender, person["name"], body, "answered", "", reply)
                self._log(now, "sparky", reply, "identity", 5)
                return {"ok": True, "kind": kind, "reply": reply, "status": "answered"}
            if kind == "past":
                reply = self._past_for(state, sender, now)
                self.store.save_state(state)
                self.store.add_spark(_iso(now), sender, person["name"], body, "answered", "", reply)
                return {"ok": True, "kind": kind, "reply": reply, "status": "answered"}
            if state["fuse_used"] >= catalog.FUSE_RATING and state.get("fuse_day") == now.date().isoformat():
                reply = (
                    "My fuse is full: 120 sparks today. Yours waits until tomorrow. "
                    "I haven't dropped it, and I haven't pretended I read it."
                )
                row = self.store.add_spark(_iso(now), sender, person["name"], body, "queued", "fuse full", reply)
                self._log(now, "sparky", catalog.LINES["fuse"][0], "fuse", 6)
                return {"ok": True, "kind": "chat", "reply": reply, "status": "queued", "id": row["id"]}
            reply = (
                "Queued, in the order it arrived. I'll carry it off-peak or bring it back with a reason. "
                "Nothing waits in silence."
            )
            if kind == "dark" and not state["dark_blocks"]:
                reply = "I can take the note as far as the Last Pole. The Dark Blocks are shut until the Jar is full."
            row = self.store.add_spark(_iso(now), sender, person["name"], body, "queued", "", reply)
            state["fuse_used"] = int(state.get("fuse_used") or 0) + 1
            needs = state["needs"]
            needs["connection"] = _clamp(needs["connection"] + 4)
            needs["spark"] = _clamp(needs["spark"] + 2)
            state["needs"] = needs
            self.store.save_state(state)
            self._log(now, "sparky", f"A spark is in the queue from the Outlet. {self.store.queue_length()} waiting. Oldest first.", "queue", 3)
            if person["sparks"] == catalog.LIVE_WIRE_SPARKS:
                self._log(
                    now, "sparky",
                    f"{person['name']} is a Live Wire now. Their switch is on the Breaker Panel, and they can edit the label.",
                    "people", 6,
                )
            return {"ok": True, "kind": "chat", "reply": reply, "status": "queued", "id": row["id"]}

    def _past_for(self, state: dict[str, Any], sender: str, now: datetime) -> str:
        past = state.setdefault("past", {})
        if sender in past:
            return past[sender]
        line = (
            f"While you were gone I was at {catalog.PLACES.get(state['place'], 'the Plaza')}. "
            f"{state.get('activity') or 'Charging'}. "
            f"The Jar was at {state['jar']}. {_mood(state)}. "
            "That's the interval, written once. I won't revise it."
        )
        past[sender] = one_bang(line)
        self._log(now, "sparky", past[sender], "past", 5)
        return past[sender]

    def _touch_person(self, sender: str, name: str, now: datetime, text: str, kind: str) -> dict[str, Any]:
        found = self.store.get_person(sender)
        person = found or {
            "id": sender,
            "name": clip(name, 40) or "Conductor",
            "label": "a Conductor",
            "private_note": "",
            "sparks": 0,
            "updated_at": _iso(now),
        }
        if name:
            person["name"] = clip(name, 40) or person["name"]
        person["sparks"] = int(person["sparks"]) + 1
        if person["sparks"] >= catalog.LIVE_WIRE_SPARKS and person["label"] == "a Conductor":
            person["label"] = "Live Wire"
        if kind not in {"crisis"}:
            person["private_note"] = clip(text, 240)
        person["updated_at"] = _iso(now)
        self.store.save_person(person)
        return person

    def sense(self, text: str, remember: bool = False) -> dict[str, Any]:
        with self._lock:
            now = self._now()
            body = clip(text, 160)
            if not body:
                return {"ok": False, "error": "a camera note needs a short description"}
            if classify(body) in {"outlet", "gamble", "crisis"}:
                body = "the portal showed something I won't describe that way"
            state = self._state()
            previous = state.get("sense_at") or ""
            try:
                last = datetime.fromisoformat(previous)
                if (now - last).total_seconds() < 4 and (state.get("live_sense") or {}).get("text") == body:
                    return {"ok": True, "stored": False, "duplicate": True, "thought": state.get("thought")}
            except ValueError:
                pass
            expression = "surprised"
            thought = body
            if "wave" in body.lower():
                expression = "happy"
                thought = "Someone waved at the portal."
            elif "person" in body.lower():
                thought = "There's a person on the portal."
            elif "hand" in body.lower():
                thought = "A hand on the portal."
            state["live_sense"] = {
                "text": thought, "remember": bool(remember), "fresh": True, "at": _iso(now),
            }
            state["sense_at"] = _iso(now)
            state["expression"] = expression
            state["thought"] = thought
            state["icon"] = "wave"
            stored = False
            if remember:
                self._log(now, "sparky", f"Portal, kept on request: {thought}", "sense", 4, state)
                stored = True
            elif _awake(now) and charge_of(state["needs"]) >= 15:
                state["place"] = "workshop"
                state["activity"] = "Looking toward the portal"
            self.store.save_state(state)
            return {"ok": True, "stored": stored, "thought": thought, "expression": expression}

    def found_toy(self, place: str, note: str = "", lat: float | None = None,
                  lon: float | None = None, photo: str | None = None) -> dict[str, Any]:
        with self._lock:
            now = self._now()
            where = clip(place, 120)
            if not where:
                return {"ok": False, "error": "a sighting needs a real place name"}
            reaction = (
                f"A Travelling Sparky was logged at {where}. That's a real place, and Off-Peak is still imagined. "
                "I don't ask anyone to leave me on a charger or near a socket."
            )
            if note:
                reaction = f"Logged at {where}. The note says: {clip(note, 140)}. I'll remember the place."
            row = self.store.add_sighting({
                "created_at": _iso(now),
                "place": where,
                "note": clip(note, 400),
                "lat": lat,
                "lon": lon,
                "photo": photo,
                "reaction": reaction,
            })
            self._log(now, "sparky", reaction, "toy", 6)
            state = self._state()
            state["thought"] = f"The toy was seen at {where}."
            state["icon"] = "spark"
            needs = state["needs"]
            needs["spark"] = _clamp(needs["spark"] + 8)
            needs["connection"] = _clamp(needs["connection"] + 4)
            state["needs"] = needs
            self.store.save_state(state)
            self.store.add_outcome("Travelling Sparky", "Live", f"Seen at {where}.", _iso(now))
            return {"ok": True, "id": row["id"], "reaction": reaction}

    def vote(self, voter: str, choice: int) -> dict[str, Any]:
        with self._lock:
            state = self._state()
            now = self._now()
            self._ensure_vote(state, now)
            options = state["vote_options"]
            if choice < 0 or choice >= len(options):
                return {"ok": False, "error": "that choice isn't on this week's board"}
            self.store.cast_vote(voter, state["vote_week"], choice)
            self.store.save_state(state)
            self._honour_vote(state, now)
            return {"ok": True, "week": state["vote_week"], "counts": self.store.vote_counts(state["vote_week"])}

    def _honour_vote(self, state: dict[str, Any], now: datetime) -> None:
        week = state.get("vote_week") or ""
        if not week or state.get("honoured_week") == week:
            return
        counts = self.store.vote_counts(week)
        if not counts or sum(counts.values()) < 1:
            return
        winner = max(counts, key=lambda key: (counts[key], -key))
        option = state["vote_options"][winner]
        # Once a month he may spend a wild card if the winner repeats last week.
        month = now.strftime("%Y-%m")
        if state.get("wild_month") != month and state.get("last_vote_key") == option["key"]:
            state["wild_month"] = month
            line = (
                f"Wild card for {month}. The vote wanted {option['text']} again. "
                "I'm taking the atlas page instead, and writing that down."
            )
            state["project"]["note"] = "Wild card week. The atlas comes first."
        else:
            line = f"The Circuit Vote picked: {option['text']} I'll do that as the deep work."
            state["project"]["note"] = option["text"]
        state["last_vote_key"] = option["key"]
        state["honoured_week"] = week
        self._log(now, "sparky", line, "vote", 5)
        self.store.save_state(state)

    def morph(self, command: str) -> dict[str, Any]:
        with self._lock:
            now = self._now()
            text = clip(command, 180).lower()
            state = self._state()
            if not text:
                return {"ok": False, "error": "a morph needs a few words"}
            refused = any(word in text for word in (
                "tesla", "supercharger", "logo", "delete", "destroy", "remove the jar", "burn",
            ))
            if refused:
                reply = "I won't change that. Kept things stay, and the town doesn't wear anyone's brand."
                self._log(now, "sparky", reply, "morph", 4)
                return {"ok": True, "applied": False, "reply": reply}
            cost = 8
            if state["needs"]["spark"] < cost:
                reply = "I don't have the spark for a big change. Spark isn't something you can buy."
                return {"ok": True, "applied": False, "reply": reply}
            applied = False
            if "flicker" in text or "streetlight" in text:
                state["morph"]["flicker"] = True
                applied = True
                reply = "The streetlights on the path are flickering. Small change, spent from spark."
            elif "fog" in text:
                state["morph"]["fog"] = True
                applied = True
                reply = "Fog over the substation. You can still see the fence."
            elif "hum" in text:
                state["morph"]["hum"] = True
                applied = True
                reply = "The lines are humming a little louder. Old Hum would approve."
            elif "clear" in text or "reset" in text:
                state["morph"] = {"flicker": False, "fog": False, "hum": False}
                applied = True
                cost = 0
                reply = "Put the town back. The buildings stayed where they were."
            else:
                reply = "I can flicker the streetlights, roll fog over the substation, or raise the hum."
            if applied:
                state["needs"]["spark"] = _clamp(state["needs"]["spark"] - cost)
                self._log(now, "sparky", reply, "morph", 3)
            self.store.save_state(state)
            return {"ok": True, "applied": applied, "reply": reply, "morph": state["morph"]}

    def order(self, sku: str, buyer: str) -> dict[str, Any]:
        with self._lock:
            now = self._now()
            if self.creator.paused:
                return {"ok": False, "error": "the kiosk is paused"}
            item = self.store.shop_item(sku)
            if item is None or item["sold"]:
                # Catalog items that aren't the one-of-one practice map can be ordered as a request.
                catalog_item = next((row for row in catalog.SHOP_CATALOG if row["id"] == sku), None)
                if catalog_item is None:
                    return {"ok": False, "error": "that piece isn't on the kiosk"}
                item = catalog_item
            if sku == "delivery":
                state = self._state()
                day = now.date().isoformat()
                if state.get("commission_day") == day and int(state.get("commissions_tonight") or 0) >= 1:
                    return {"ok": False, "error": "the live delivery slot is gone for this night"}
                state["commission_day"] = day
                state["commissions_tonight"] = int(state.get("commissions_tonight") or 0) + 1
                self.store.save_state(state)
            price = int(item["price_cents"]) / 100.0
            stored = self.store.shop_item(sku)
            if stored and not stored["sold"]:
                self.store.mark_sold(sku)
            approval = self._queue_purchase(
                item["title"], price,
                "Kiosk request. No card is stored and nothing is charged here.",
            )
            order = self.store.add_order(_iso(now), sku, buyer, "pending_approval", approval)
            self.store.add_outcome(item["title"], "Started", "Requested. Payment is not taken in this world.", _iso(now))
            reply = (
                f"{item['title']} is in the queue at ${price:.0f}. "
                f"{self.store.pending_orders()} ahead, counting this one. "
                "I won't charge a card. The Electrician approves before any money moves, "
                "and an approval still doesn't spend it."
            )
            self._log(now, "sparky", reply, "kiosk", 5)
            return {"ok": True, "order": order, "reply": reply, "approval_id": approval}

    def write_newsletter(self, send: bool = False) -> dict[str, Any]:
        with self._lock:
            now = self._now()
            state = self._state()
            letter = self._compose_letter(state, now)
            approval = None
            status = "draft"
            if send:
                if self.store.pending_letter():
                    return {"ok": False, "error": "a letter is already waiting for approval"}
                approval = self._queue_message("newsletter subscribers", letter["body"])
                status = "pending_approval" if approval else "draft"
            row = self.store.add_letter(_iso(now), letter["title"], letter["body"], status, approval)
            state["newsletter_on"] = now.date().isoformat()
            self.store.save_state(state)
            self._log(now, "sparky", "Wrote a letter from the town. Sending is a separate yes, and the yes still doesn't send it.", "letter", 4)
            return {"ok": True, "letter": row}

    def field_report(self, text: str) -> dict[str, Any]:
        with self._lock:
            body = clip(text, 400)
            if not body:
                return {"ok": False, "error": "a field report needs words"}
            now = self._now()
            state = self._state()
            state["field_reports"] = (list(state.get("field_reports") or []) + [body])[-20:]
            self.store.save_state(state)
            self._log(now, "sparky", f"A field socket reported home: {body}", "field", 4)
            return {"ok": True}

    def pin_notice(self, author: str, text: str) -> dict[str, Any]:
        with self._lock:
            body = clip(text, 400)
            if not body:
                return {"ok": False, "error": "a notice needs words"}
            if classify(body) in {"outlet", "gamble", "crisis"}:
                return {"ok": False, "error": "that doesn't go on the Notice Pole"}
            row = self.store.add_notice(_iso(self._now()), clip(author, 40) or "Conductor", body)
            return {"ok": True, "notice": row}

    def update_me(self, person_id: str, name: str = "", label: str = "") -> dict[str, Any]:
        with self._lock:
            person = self.store.get_person(person_id)
            if person is None:
                person = {
                    "id": person_id, "name": "Conductor", "label": "a Conductor",
                    "private_note": "", "sparks": 0, "updated_at": _iso(self._now()),
                }
            if name:
                person["name"] = clip(name, 40)
            if label:
                person["label"] = clip(label, 80)
            person["updated_at"] = _iso(self._now())
            self.store.save_person(person)
            return {"ok": True, "me": _public_person(person)}

    def forget_me(self, person_id: str) -> dict[str, Any]:
        with self._lock:
            self.store.delete_person(person_id)
            state = self._state()
            past = state.get("past") or {}
            past.pop(person_id, None)
            state["past"] = past
            self.store.save_state(state)
            self._log(
                self._now(), "sparky",
                "A Conductor asked me to forget their switch. I did. The note is gone from the panel.",
                "people", 6,
            )
            self.store.add_decision(_iso(self._now()), "delete", "Conductor memory deleted. Data not copied into the log.")
            return {"ok": True}

    def me(self, person_id: str) -> dict[str, Any]:
        with self._lock:
            person = self.store.get_person(person_id)
            sparks = self.store.sparks_for(person_id)
            if person is None:
                return {"ok": True, "me": None, "sparks": sparks}
            return {"ok": True, "me": person, "sparks": sparks}

    def record_earning(self, source: str, amount: float, note: str = "") -> dict[str, Any]:
        with self._lock:
            source = clip(source, 120)
            if not source:
                raise ValueError("earning source cannot be empty")
            cents = int(round(float(amount) * 100))
            if cents <= 0 or cents > 100_000_000:
                raise ValueError("earning amount must be between 0 and 1000000")
            saved = self.life.memory.add_earning(source, cents, "USD", clip(note, 240))
            parts = split_cents(cents)
            self.creator.ledger.append("meter_split", {
                "source": source,
                "gross_cents": cents,
                **parts,
                "impact_share": catalog.IMPACT_SHARE,
                "note": clip(note, 180),
            })
            self._log(
                self._now(), "sparky",
                f"Logged {saved['amount']:.2f} that already arrived from {source}. "
                f"15% of it, {parts['ground_cents'] / 100:.2f}, is marked for the Ground Fund. Nothing was spent.",
                "meter", 6,
            )
            return {"ok": True, "earning": saved, **parts}

    def approve(self, action_id: str, note: str = "") -> dict[str, Any]:
        with self._lock:
            record = self.life.approve(action_id, note)
            self.store.add_decision(_iso(self._now()), "approve", f"{action_id} approved. Not executed.")
            return record

    def reject(self, action_id: str, note: str) -> dict[str, Any]:
        with self._lock:
            record = self.life.reject(action_id, note)
            self.store.add_decision(_iso(self._now()), "reject", f"{action_id} rejected.")
            return record

    def set_paused(self, paused: bool) -> bool:
        with self._lock:
            self.creator.set_paused(bool(paused), actor="electrician")
            self.store.add_decision(_iso(self._now()), "pause", f"paused={bool(paused)}")
            return self.creator.paused

    def correct(self, diary_id: int, text: str) -> dict[str, Any]:
        with self._lock:
            body = clip(text, 700)
            if not body:
                return {"ok": False, "error": "a correction needs words"}
            row = self.store.add_diary(
                _iso(self._now()), "sparky", "Correction: " + body, "correction", int(diary_id),
            )
            return {"ok": True, "entry": row}

    # -------------------------------------------------------------------- views
    def public_state(self) -> dict[str, Any]:
        with self._lock:
            now = self._now()
            state = self._state()
            self._ensure_vote(state, now)
            self.store.save_state(state)
            earnings = self.life.memory.earnings_summary(limit=8)
            splits = _splits(self.creator)
            phase = _phase(now)
            options = []
            counts = self.store.vote_counts(state.get("vote_week") or "")
            for index, option in enumerate(state.get("vote_options") or []):
                options.append({**option, "votes": counts.get(index, 0)})
            made = [item for item in self.store.shop() if not item["sold"]]
            return {
                "name": "Sparky",
                "honest": (
                    "Sparky is an AI character, drawn as a plug, who lives in Off-Peak, "
                    "an imagined town. The Electrician is R."
                ),
                "awake": _awake(now),
                "phase": phase,
                "place": state["place"],
                "place_label": catalog.PLACES.get(state["place"], state["place"]),
                "places": [{"id": key, "label": label} for key, label in catalog.PLACES.items()],
                "expression": state["expression"],
                "activity": {
                    "label": state["activity"],
                    "started_at": state["activity_started"],
                    "thought": state["thought"],
                    "icon": state["icon"],
                },
                "needs": state["needs"],
                "charge": charge_of(state["needs"]),
                "mood": state.get("mood") or _mood(state),
                "jar": {"count": state["jar"], "goal": catalog.JAR_GOAL, "dark_blocks": state["dark_blocks"]},
                "fuse": {"used": state["fuse_used"], "rating": catalog.FUSE_RATING},
                "kiosk_open": bool(state["kiosk_open"]) if _awake(now) else False,
                "morph": state["morph"],
                "weather": {"checked": bool(state["weather"].get("checked")), "line": state["weather"].get("line")},
                "grid": {"checked": bool(state["grid"].get("checked")), "line": state["grid"].get("line")},
                "diary": self.store.diary(40),
                "shop": _public_shop(),
                "made": made,
                "orders_ahead": self.store.pending_orders(),
                "toy": {"sightings": _public_sightings(self.store.sightings())},
                "newsletter": self.store.letters(8),
                "meter": {
                    "total_in": earnings["by_currency"],
                    "count": earnings["count"],
                    "recent": earnings["recent"],
                    "electrician_cents": splits["electrician_cents"],
                    "world_cents": splits["world_cents"],
                    "ground_cents": splits["ground_cents"],
                    "impact_share": catalog.IMPACT_SHARE,
                    "receipts": [],
                    "receipt_line": "No receipted impact yet. The Ground Fund does not claim a deed without one.",
                    "note": "Approving a row records a yes. It does not spend money or send mail.",
                },
                "vote": {"week": state.get("vote_week"), "options": options, "honoured": state.get("honoured_week") == state.get("vote_week")},
                "switchboard": self.store.outcomes(),
                "notices": self.store.notices(12),
                "breaker": self.store.live_wires(),
                "project": {
                    "title": state["project"]["title"],
                    "day": state["project"]["day"],
                    "days": state["project"]["days"],
                    "note": state["project"]["note"],
                    "memories": state["project"].get("memories") or [],
                    "status": state["project"]["status"],
                },
                "brain": self.brain.describe(),
                "camera": {
                    "thought": (state.get("live_sense") or {}).get("text") or "",
                    "remembered": bool((state.get("live_sense") or {}).get("remember")),
                },
                "queue": self.store.queue_length(),
                "interval_s": self.life.interval,
                "next_beat": self.life.memory.get_vitals().get("next_beat"),
                "paused": self.creator.paused,
                "safety_line": OUTLET_LINE,
                "scorches": state.get("scorches") or 0,
                "next_goal": state.get("next_goal") or "",
                "catalog_note": "Scorches are proof of delivery. They are not money.",
            }

    def owner_state(self) -> dict[str, Any]:
        with self._lock:
            public = self.public_state()
            pending = self.creator.list_actions("pending_approval")
            return {
                "public": public,
                "paused": self.creator.paused,
                "decisions": self.store.decisions(30),
                "approvals": [
                    {"id": row["id"], "kind": row["kind"], "status": row["status"],
                     "payload": row.get("payload"), "result": row.get("result")}
                    for row in pending
                ],
                "needs": self._state()["needs"],
                "reflections": self._state().get("reflections") or [],
                "plan": self._state().get("plan") or "",
                "ledger_ok": self.creator.ledger.verify()[0],
                "why": "Each row is the decision written at the time. Later text does not rewrite it.",
            }


def _mood(state: dict[str, Any]) -> str:
    needs = state["needs"]
    bits = []
    if needs["top_up"] < 25:
        bits.append("low charge")
    elif needs["top_up"] > 80:
        bits.append("well topped up")
    if needs["spark"] > 75:
        bits.append("high spark")
    elif needs["spark"] < 30:
        bits.append("spark is dull")
    if needs["connection"] < 30:
        bits.append("open circuit")
    elif needs["connection"] > 85:
        bits.append("short-circuiting")
    if needs["circuit"] > 70:
        bits.append("pleased with the work")
    weather = (state.get("weather") or {}).get("line") or ""
    if weather and "haven't checked" not in weather and "couldn't check" not in weather:
        bits.append(weather[:90])
    return ", ".join(bits) or "quiet, and still here"


def _life_mood(state: dict[str, Any], quiet: bool) -> str:
    if quiet or state["expression"] == "sleepy":
        return "sleepy"
    if state["needs"]["top_up"] < 20:
        return "tired"
    if state["expression"] == "happy":
        return "proud"
    if state["expression"] == "nervous":
        return "restless"
    return "focused"


def _atlas_note(day: int) -> str:
    streets = [
        "The laundromat spur is a dotted line.",
        "Arcade alley is louder than the map has room for.",
        "Library steps, two poles, then the notice.",
        "I redrew the Plaza stalls smaller. They aren't a brand.",
        "Substation fence is a caution, not a door.",
        "Elm's porch light is a switch. I apologised again, in pencil.",
    ]
    return streets[(day - 1) % len(streets)]


def _splits(creator: CreatorEngine) -> dict[str, int]:
    totals = {"electrician_cents": 0, "world_cents": 0, "ground_cents": 0}
    path = creator.ledger.path
    if not path.exists():
        return totals
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            if not raw.strip():
                continue
            try:
                item = json.loads(raw)
            except ValueError:
                continue
            if item.get("event") != "meter_split":
                continue
            detail = item.get("detail") or {}
            for key in totals:
                totals[key] += int(detail.get(key) or 0)
    return totals


def _public_shop() -> list[dict[str, Any]]:
    rows = []
    for item in catalog.SHOP_CATALOG:
        rows.append({
            "id": item["id"],
            "title": item["title"],
            "blurb": item["blurb"],
            "price_cents": item["price_cents"],
            "price": item["price_cents"] / 100.0,
            "kind": item["kind"],
            "currency": "USD",
        })
    return rows


def _public_sightings(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        photo = row.get("photo")
        out.append({
            "id": row["id"],
            "time": row["created_at"],
            "place": row["place"],
            "note": row["note"],
            "lat": row["lat"],
            "lon": row["lon"],
            "photo": photo if photo else None,
            "reaction": row["reaction"],
        })
    return out


def _public_person(person: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": person["name"],
        "label": person["label"],
        "sparks": person["sparks"],
        "live_wire": int(person["sparks"]) >= catalog.LIVE_WIRE_SPARKS,
    }


def _weather_from_env() -> dict[str, Any]:
    lat = os.environ.get("SPARKY_LAT")
    lon = os.environ.get("SPARKY_LON")
    if not lat or not lon:
        return {"checked": False, "line": UNCHECKED_WEATHER, "thunder": False}
    try:
        latitude = float(lat)
        longitude = float(lon)
    except ValueError:
        return {"checked": False, "line": FAILED_WEATHER, "thunder": False}
    return fetch_weather(latitude, longitude)


def fetch_weather(lat: float, lon: float, opener=None) -> dict[str, Any]:
    url = (
        "https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat:.4f}&longitude={lon:.4f}"
        "&current=temperature_2m,weather_code"
        "&daily=sunrise,sunset&timezone=auto&forecast_days=1"
    )
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "SparkyWorld/1.0"})
        open_fn = opener or urllib.request.urlopen
        with open_fn(request, timeout=4) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return {"checked": False, "line": FAILED_WEATHER, "thunder": False}
    current = payload.get("current") or {}
    code = current.get("weather_code")
    temp = current.get("temperature_2m")
    if code is None or temp is None:
        return {"checked": False, "line": FAILED_WEATHER, "thunder": False}
    thunder = int(code) in {95, 96, 99}
    word = _weather_word(int(code))
    line = f"{word}, {temp}°C, from the weather feed"
    if thunder:
        line = THUNDER_LINE + " " + line
    return {"checked": True, "line": line, "thunder": thunder, "code": int(code), "temp": temp}


def _weather_word(code: int) -> str:
    if code == 0:
        return "clear"
    if code in {1, 2, 3}:
        return "cloudy"
    if code in {45, 48}:
        return "fog"
    if code in {51, 53, 55, 61, 63, 65, 80, 81, 82}:
        return "rain"
    if code in {71, 73, 75, 77, 85, 86}:
        return "snow"
    if code in {95, 96, 99}:
        return "a thunderstorm"
    return "weather I can name from the code"


def _grid_from_env() -> dict[str, Any]:
    url = os.environ.get("SPARKY_GRID_URL")
    if not url:
        return {"checked": False, "line": UNCHECKED_GRID}
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "SparkyWorld/1.0"})
        with urllib.request.urlopen(request, timeout=4) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return {"checked": False, "line": FAILED_GRID}
    if not isinstance(payload, dict):
        return {"checked": False, "line": FAILED_GRID}
    for key in ("carbon_intensity", "intensity", "carbon", "demand"):
        value = payload.get(key)
        if isinstance(value, (int, float)):
            return {"checked": True, "line": f"The grid feed says {key.replace('_', ' ')} is {value}."}
    return {"checked": False, "line": FAILED_GRID}
