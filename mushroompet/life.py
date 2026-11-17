"""The pet's autonomous day.

Each beat recovers a little energy, picks the next item on today's plan, and runs
one registered skill. Local drafts happen immediately. Publishing, messaging, and
spending are submitted to Creator Studio and stop in the approval queue; approving
a record still does not perform the outside action.

The loop is safe to call from a background thread. Moments are queued for the pet
window, which turns them into a speech bubble and a small animation.
"""
from __future__ import annotations

import os
import queue
import random
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .brain import Brain
from .creator import EXTERNAL_ACTIONS, CreatorEngine, _atomic_json
from .memory import MemoryStore
from .skills import PLANNER_NOTE, SkillContext, SkillRegistry, builtin_skills

DEFAULT_NICHE = "small creative tools and desktop companions"
DEFAULT_GOAL = (
    "earn from short-form posts and tiny digital goods, "
    "without posting or spending unless I say yes"
)
PROMPT_KINDS = ("idea", "script", "caption", "post", "listing", "opportunity")
REST_THRESHOLD = 22.0
REST_GAIN = 20.0
RECOVER_PER_HOUR = 8.0

LIFE_ACTIONS = frozenset({
    "life_status", "life_tick", "life_skill", "life_focus", "life_enabled",
    "life_pause", "life_log", "life_plan", "life_earnings", "life_opportunities",
    "life_memory", "life_skills", "approvals", "approve", "reject", "remember", "earning",
})

CHATTER = {
    "curious": ["i have a plan for today", "wondering what we should make", "i'll keep it small"],
    "focused": ["i'm on today's plan", "working, quietly", "one useful thing at a time"],
    "tired": ["i'm going to sit for a bit", "low battery. still here"],
    "proud": ["today's plan is coming along", "i did a useful thing earlier"],
    "hopeful": ["something is waiting for you to approve", "i drafted something. your call"],
    "restless": ["that one didn't work. i left a note", "i'll try a different piece"],
    "sleepy": ["i'm going to sit for a bit", "five more minutes, then back to it"],
}

BUBBLE = {
    "curious": "info", "focused": "normal", "tired": "sleepy", "proud": "happy",
    "hopeful": "happy", "restless": "urgent", "sleepy": "sleepy",
}
VERBS = {"look", "happy", "wave", "love", "sit"}


class LifeError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = int(status)
        self.message = message


class Life:
    def __init__(self, root: str | Path, creator: CreatorEngine, brain: Brain | None = None,
                 skills: SkillRegistry | None = None, clock=None, config=None,
                 interval_s: float | None = None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.creator = creator
        self.brain = brain or Brain.offline()
        self.skills = skills or builtin_skills()
        self.clock = clock or (lambda: datetime.now().astimezone())
        self.config = config
        self.memory = MemoryStore(self.root / "life.sqlite")
        self._lock = threading.RLock()
        self._moments: queue.Queue = queue.Queue(maxsize=32)
        self._chatter = ""
        self.interval = self._resolve_interval(interval_s)
        self.enabled = self._resolve_enabled()
        self._ensure_focus()
        self._arm_first_beat()

    def close(self) -> None:
        self.memory.close()

    # ----------------------------------------------------------------- public
    @property
    def niche(self) -> str:
        return self.memory.get_vitals()["niche"]

    @property
    def goal(self) -> str:
        return self.memory.get_vitals()["goal"]

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self.enabled = bool(enabled)
            fields: dict[str, Any] = {"enabled": 1 if self.enabled else 0}
            if self.enabled:
                fields["next_beat"] = _iso(self._now())
            self.memory.update_vitals(**fields)
            self._write_config_flag("life_enabled", self.enabled)
            self._snapshot()

    def set_focus(self, niche: str, goal: str) -> dict[str, str]:
        niche = _clean(niche, 160) or DEFAULT_NICHE
        goal = _clean(goal, 400) or DEFAULT_GOAL
        with self._lock:
            self.memory.update_vitals(niche=niche, goal=goal, idled_on="")
            self.memory.delete_plan(self._day())
            self._write_config_flag("life_niche", niche)
            self._write_config_flag("life_goal", goal)
            try:
                existing = [item.get("text") for item in self.creator.mind.state.get("goals", [])]
                if goal not in existing:
                    self.creator.mind.add_goal(goal)
                self.creator.mind.state["mood"] = "curious"
                self.creator.mind.remember(self.brain.redact(f"Working toward: {goal} ({niche})"), 6)
            except Exception:
                pass
            self._snapshot()
        return {"niche": niche, "goal": goal}

    def due(self) -> bool:
        with self._lock:
            if not self.enabled or self.creator.paused:
                return False
            nxt = _parse(self.memory.get_vitals().get("next_beat"))
            if nxt is None:
                return True
            return self._now() >= nxt

    def tick(self, force: bool = False) -> dict[str, Any] | None:
        with self._lock:
            return self._tick(force)

    def run_skill(self, skill_id: str, args: dict | None = None) -> dict[str, Any]:
        with self._lock:
            if self.creator.paused:
                raise LifeError(409, "creator is paused by the owner kill switch")
            return self._run_one(skill_id, args or {})

    def approve(self, action_id: str, note: str = "") -> dict[str, Any]:
        record = self._decide("approve", action_id, note)
        self._speak_decision(record, "Approved. I still won't send it myself.")
        return record

    def reject(self, action_id: str, note: str) -> dict[str, Any]:
        record = self._decide("reject", action_id, note)
        self._speak_decision(record, "Rejected. I'll leave it alone.")
        return record

    def _decide(self, kind: str, action_id: str, note: str) -> dict[str, Any]:
        try:
            record = (self.creator.approve(action_id, note) if kind == "approve"
                      else self.creator.reject(action_id, note))
        except KeyError:
            raise LifeError(404, "unknown action") from None
        except ValueError as exc:
            raise LifeError(400, self.brain.redact(str(exc).splitlines()[0][:200])) from None
        try:
            self.memory.add_activity(kind, f"{kind} {record.get('kind')} {record.get('id')}",
                                     "focused", self.memory.get_vitals()["energy"])
        except Exception:
            pass
        self._snapshot()
        return record

    def record_earning(self, source: str, amount: float, note: str = "",
                       currency: str = "USD") -> dict[str, Any]:
        """Record money that already arrived. Returns the ledger row, and the pet says so."""
        self.run_skill("log_earning", {
            "source": source, "amount": amount, "note": note, "currency": currency,
        })
        recent = self.memory.earnings_summary(limit=1)["recent"]
        return recent[0]

    def remember(self, text: str, importance: int = 5) -> dict[str, Any]:
        item = self.memory.add_memory(text, kind="note", importance=importance)
        try:
            self.creator.mind.remember(text, importance)
        except Exception:
            pass
        return item

    def poll_moment(self) -> dict[str, Any] | None:
        try:
            return self._moments.get_nowait()
        except queue.Empty:
            return None

    def chatter_line(self) -> str | None:
        if not self.enabled:
            return None
        vitals = self.memory.get_vitals()
        try:
            pending = len(self.creator.list_actions("pending_approval"))
        except Exception:
            pending = 0
        if pending and random.random() < 0.5:
            noun = "one thing" if pending == 1 else f"{pending} things"
            return f"{noun} in the approval queue. I haven't sent any of it."
        if vitals.get("goal") and random.random() < 0.25:
            return "today's aim: " + str(vitals["goal"])[:90]
        mood = vitals.get("mood") or "curious"
        return random.choice(CHATTER.get(mood) or CHATTER["curious"])

    def status(self) -> dict[str, Any]:
        vitals = self.memory.get_vitals()
        day = self._day()
        plan = self.memory.get_plan(day)
        items = plan["items"] if plan else []
        done = sum(1 for item in items if item.get("status") == "done")
        nxt = next((item for item in items if item.get("status") == "todo"), None)
        try:
            pending = self.creator.list_actions("pending_approval")
        except Exception:
            pending = []
        earnings = self.memory.earnings_summary(limit=5)
        return {
            "enabled": self.enabled,
            "paused": self.creator.paused,
            "mood": vitals["mood"],
            "energy": round(float(vitals["energy"]), 1),
            "niche": vitals["niche"],
            "goal": vitals["goal"],
            "interval_s": self.interval,
            "next_beat": vitals["next_beat"],
            "last_summary": vitals["last_summary"],
            "plan": {
                "date": day,
                "focus": plan["focus"] if plan else "",
                "source": plan["source"] if plan else "",
                "done": done,
                "total": len(items),
                "next": nxt["title"] if nxt else None,
                "items": [
                    {"skill": item.get("skill"), "title": item.get("title"), "status": item.get("status")}
                    for item in items
                ],
            },
            "pending_approvals": len(pending),
            "earnings": earnings["by_currency"],
            "recent": [
                {"time": row["created_at"], "skill": row["skill"], "summary": row["summary"]}
                for row in self.memory.recent_activity(5)
            ],
            "brain": self.brain.describe(),
            "guards": {"external_actions": "approval_queue_only", "approval_executes": False},
        }

    def prompt_context(self) -> str:
        """What a model is allowed to see: the assignment and recent work, not the ledger."""
        vitals = self.memory.get_vitals()
        parts = [
            "Niche: " + self.brain.redact(vitals["niche"])[:200],
            "Goal: " + self.brain.redact(vitals["goal"])[:300],
        ]
        for mem in self.memory.recent_memories(limit=3, kinds=PROMPT_KINDS):
            parts.append("Recent work: " + self.brain.redact(mem["text"])[:180])
        return "\n".join(parts)

    def write_dashboard(self) -> Path:
        path = self.root / "dashboard.html"
        _atomic_text(path, _dashboard_html(self.status(), self.memory, self.creator))
        return path

    # ------------------------------------------------------------------- tick
    def _tick(self, force: bool) -> dict[str, Any] | None:
        if self.creator.paused or not self.enabled:
            return None
        now = self._now()
        vitals = self.memory.get_vitals()
        nxt = _parse(vitals.get("next_beat"))
        if not force and nxt is not None and now < nxt:
            return None
        day = self._day(now)
        energy = _recover(vitals, now)
        self._ensure_plan(now)
        plan = self.memory.get_plan(day)
        if plan is None:
            return None
        item = next((entry for entry in plan["items"] if entry.get("status") == "todo"), None)
        if item is None:
            return self._caught_up(now, force, vitals, energy)
        if energy < REST_THRESHOLD:
            return self._rest(now, energy)
        try:
            result = self._execute(item["skill"], item.get("args") or {}, now)
            item["status"] = "done"
            item["summary"] = result["summary"]
            failed = False
        except LifeError as exc:
            item["status"] = "failed"
            item["summary"] = exc.message
            result = self._failure(item, exc.message)
            failed = True
        except Exception as exc:
            message = self.brain.redact(str(exc).splitlines()[0][:180]) or "that step failed"
            item["status"] = "failed"
            item["summary"] = message
            result = self._failure(item, message)
            failed = True
        self.memory.save_plan(plan)
        mood = _mood_for(result["mood"] if not failed else "restless", energy, item["skill"])
        moment = self._finish(
            now, skill=item["skill"], speech=result["speech"], summary=result["summary"],
            title=result["title"], bubble=result["bubble"], verb=result["verb"],
            mood=mood, energy=max(0.0, energy - result["energy"]),
            approval_id=result.get("approval_id"), artifacts=result.get("artifacts"),
        )
        return moment

    def _run_one(self, skill_id: str, args: dict) -> dict[str, Any]:
        now = self._now()
        try:
            result = self._execute(skill_id, args, now)
        except KeyError:
            raise LifeError(404, f"unknown skill: {skill_id}") from None
        except LifeError:
            raise
        except ValueError as exc:
            raise LifeError(400, self.brain.redact(str(exc).splitlines()[0][:200])) from None
        except RuntimeError as exc:
            text = str(exc)
            status = 409 if "paused" in text else 400
            raise LifeError(status, self.brain.redact(text.splitlines()[0][:200])) from None
        vitals = self.memory.get_vitals()
        energy = max(0.0, _recover(vitals, now) - result["energy"])
        moment = self._finish(
            now, skill=skill_id, speech=result["speech"], summary=result["summary"],
            title=result["title"], bubble=result["bubble"], verb=result["verb"],
            mood=result["mood"], energy=energy, approval_id=result.get("approval_id"),
            artifacts=result.get("artifacts"),
        )
        return moment

    def _execute(self, skill_id: str, args: dict, now: datetime) -> dict[str, Any]:
        try:
            skill = self.skills.get(skill_id)
        except KeyError:
            raise
        ctx = self._context(now)
        outcome = skill.run(ctx, args if isinstance(args, dict) else {})
        if outcome.memory:
            try:
                self.memory.add_memory(self.brain.redact(outcome.memory), kind=outcome.memory_kind,
                                       importance=outcome.importance)
            except ValueError:
                pass
        approval_status = None
        if outcome.approval_id:
            found = self.creator.list_actions()
            match = next((item for item in found if item["id"] == outcome.approval_id), None)
            approval_status = match["status"] if match else "pending_approval"
        return {
            "speech": _clean(outcome.speech, 240) or "Done.",
            "summary": _clean(outcome.summary, 400) or _clean(outcome.speech, 240) or "Done.",
            "title": _clean(outcome.title, 40) or "Working",
            "bubble": outcome.bubble if outcome.bubble in BUBBLE.values() or outcome.bubble in BUBBLE else "info",
            "verb": outcome.verb if outcome.verb in VERBS else "look",
            "mood": outcome.mood if outcome.mood in CHATTER else "focused",
            "energy": float(getattr(skill, "energy", outcome.energy) or 8),
            "approval_id": outcome.approval_id,
            "approval_status": approval_status,
            "source": outcome.source,
            "artifacts": outcome.artifacts,
        }

    def _rest(self, now: datetime, energy: float) -> dict[str, Any]:
        restored = min(100.0, energy + REST_GAIN)
        return self._finish(
            now, skill="rest", speech="I'm worn out. I'll sit, then pick the plan back up.",
            summary="Rested. The plan is still there.", title="Resting", bubble="sleepy",
            verb="sit", mood="tired", energy=restored,
        )

    def _caught_up(self, now: datetime, force: bool, vitals: dict, energy: float) -> dict[str, Any] | None:
        day = self._day(now)
        if vitals.get("idled_on") == day and not force:
            self.memory.update_vitals(next_beat=_iso(self._next(now)), last_tick=_iso(now), energy=energy)
            return None
        self.memory.update_vitals(idled_on=day)
        return self._finish(
            now, skill="idle",
            speech="Caught up for today. I'll wander until tomorrow's plan.",
            summary="Caught up for today.", title="Caught up", bubble="happy",
            verb="happy", mood="proud", energy=min(100.0, energy + 2),
        )

    def _failure(self, item: dict, message: str) -> dict[str, Any]:
        speech = f"I couldn't finish {item.get('title') or item.get('skill')}. {message}"
        return {
            "speech": _clean(speech, 240), "summary": _clean(speech, 400), "title": "Snag",
            "bubble": "urgent", "verb": "look", "mood": "restless", "energy": 3,
            "approval_id": None,
        }

    def _finish(self, now: datetime, *, skill: str, speech: str, summary: str, title: str,
                bubble: str, verb: str, mood: str, energy: float,
                approval_id: str | None = None, artifacts: list | None = None) -> dict[str, Any]:
        energy = max(0.0, min(100.0, float(energy)))
        self.memory.update_vitals(
            energy=energy, mood=mood, last_tick=_iso(now), next_beat=_iso(self._next(now)),
            last_summary=summary[:240], enabled=1 if self.enabled else 0,
        )
        self.memory.add_activity(skill, summary, mood, energy)
        self._chatter = speech[:180]
        try:
            self.creator.ledger.append("life_beat", {
                "skill": skill, "mood": mood, "energy": round(energy, 1),
                "summary": self.brain.redact(summary)[:180],
            })
        except Exception:
            pass
        try:
            self.creator.mind.state["mood"] = mood
            self.creator.mind.remember(self.brain.redact(summary)[:300], 4)
        except Exception:
            pass
        moment = {
            "text": speech, "summary": summary, "title": title, "mood": bubble,
            "bubble": bubble, "verb": verb, "mood_name": mood, "energy": round(energy, 1),
            "skill": skill, "approval_id": approval_id, "kind": skill,
            "artifacts": artifacts or [],
        }
        self._emit(moment)
        self._snapshot()
        return moment

    def _speak_decision(self, record: dict, speech: str) -> None:
        moment = {
            "text": speech, "summary": speech, "title": record.get("kind") or "Approval",
            "mood": "info", "bubble": "info", "verb": "look", "mood_name": "focused",
            "energy": self.memory.get_vitals()["energy"], "skill": "approval",
            "approval_id": record.get("id"), "kind": "approval",
        }
        self._emit(moment)

    def _emit(self, moment: dict[str, Any]) -> None:
        try:
            self._moments.put_nowait(moment)
        except queue.Full:
            try:
                self._moments.get_nowait()
            except queue.Empty:
                pass
            try:
                self._moments.put_nowait(moment)
            except queue.Full:
                pass

    # ------------------------------------------------------------------- plan
    def _ensure_plan(self, now: datetime) -> dict[str, Any]:
        day = self._day(now)
        existing = self.memory.get_plan(day)
        if existing and existing.get("items"):
            return existing
        plan = self._build_plan(now)
        self.memory.save_plan(plan)
        return plan

    def _build_plan(self, now: datetime) -> dict[str, Any]:
        data, source = self.brain.think_json(PLANNER_NOTE, self.prompt_context() + "\n\nPlan today's work.")
        chosen = self._sanitize_plan(data) if data else None
        if chosen:
            focus = self.brain.redact(_plan_focus(data, self.niche))
        else:
            chosen = _offline_plan(self.niche, self.goal)
            source = "offline"
            focus = _plan_focus(None, self.niche)
        items = []
        for entry in chosen:
            items.append({
                "id": os.urandom(3).hex(),
                "skill": entry["skill"],
                "title": entry["title"],
                "args": entry["args"],
                "status": "todo",
            })
        return {
            "day": self._day(now),
            "focus": focus,
            "items": items,
            "source": source,
            "created_at": _iso(now),
        }

    def _sanitize_plan(self, data: dict | None) -> list[dict] | None:
        if not isinstance(data, dict):
            return None
        raw_items = data.get("items")
        if not isinstance(raw_items, list):
            return None
        kept = []
        proposed = False
        for entry in raw_items:
            if not isinstance(entry, dict):
                continue
            skill_id = str(entry.get("skill") or "")
            if not self._planner_allows(skill_id):
                continue
            if skill_id == "propose_post":
                if proposed:
                    continue
                proposed = True
            kept.append({
                "skill": skill_id,
                "title": _clean(entry.get("title"), 120) or skill_id.replace("_", " "),
                "args": _scrub_args(entry.get("args")),
            })
            if len(kept) >= 8:
                break
        if not kept:
            return None
        posts = [item for item in kept if item["skill"] == "propose_post"]
        rest = [item for item in kept if item["skill"] != "propose_post"]
        return rest + posts[:1]

    def _planner_allows(self, skill_id: str) -> bool:
        try:
            skill = self.skills.get(skill_id)
        except KeyError:
            return False
        if getattr(skill, "records_money", False):
            return False
        if getattr(skill, "external", False) and skill_id != "propose_post":
            return False
        return bool(getattr(skill, "autonomous", False))

    def _context(self, now: datetime) -> SkillContext:
        vitals = self.memory.get_vitals()
        return SkillContext(
            memory=self.memory, creator=self.creator, brain=self.brain,
            niche=vitals["niche"], goal=vitals["goal"], context=self.prompt_context(),
            now=now, redact=self.brain.redact,
        )

    # ------------------------------------------------------------------ setup
    def _resolve_interval(self, interval_s: float | None) -> float:
        if interval_s is not None:
            return max(0.0, float(interval_s))
        if self.config is not None:
            try:
                raw = float(self.config.get("life_interval_s", 900) or 900)
            except (TypeError, ValueError):
                raw = 900.0
            return max(60.0, raw)
        return 900.0

    def _resolve_enabled(self) -> bool:
        if self.config is not None and self.config.get("life_enabled") is not None:
            return bool(self.config.get("life_enabled"))
        return bool(self.memory.get_vitals()["enabled"])

    def _ensure_focus(self) -> None:
        vitals = self.memory.get_vitals()
        niche = vitals["niche"]
        goal = vitals["goal"]
        if self.config is not None:
            configured_niche = _clean(self.config.get("life_niche") or "", 160)
            configured_goal = _clean(self.config.get("life_goal") or "", 400)
            niche = configured_niche or niche
            goal = configured_goal or goal
        niche = niche or DEFAULT_NICHE
        goal = goal or DEFAULT_GOAL
        self.memory.update_vitals(
            niche=niche, goal=goal, enabled=1 if self.enabled else 0, interval_s=self.interval,
        )

    def _arm_first_beat(self) -> None:
        vitals = self.memory.get_vitals()
        if vitals.get("next_beat"):
            return
        delay = 0.0 if self.interval <= 0 else min(90.0, self.interval)
        self.memory.update_vitals(next_beat=_iso(self._now() + timedelta(seconds=delay)))

    def _write_config_flag(self, key: str, value: Any) -> None:
        if self.config is None:
            return
        try:
            self.config[key] = value
        except Exception:
            try:
                self.config.data[key] = value
                self.config.save()
            except Exception:
                pass

    def _snapshot(self) -> None:
        try:
            payload = self.status()
            _atomic_json(self.root / "life.json", payload)
            self.write_dashboard()
        except Exception:
            pass

    def _now(self, now: datetime | None = None) -> datetime:
        current = self.clock() if now is None else now
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return current

    def _day(self, now: datetime | None = None) -> str:
        return self._now(now).date().isoformat()

    def _next(self, now: datetime) -> datetime:
        return now + timedelta(seconds=self.interval)


def handle_request(life: Life, action: str, payload: dict | None = None) -> dict[str, Any]:
    """Shared by the local HTTP API and the inbox folder."""
    payload = payload if isinstance(payload, dict) else {}
    action = (action or "").strip().lower()
    if action not in LIFE_ACTIONS:
        raise LifeError(404, "unknown life action")
    if action == "life_status":
        return {"ok": True, "life": life.status()}
    if action == "life_plan":
        return {"ok": True, "plan": life.status()["plan"]}
    if action == "life_log":
        return {"ok": True, "log": life.memory.recent_activity(_limit(payload))}
    if action == "life_earnings":
        return {"ok": True, "earnings": life.memory.earnings_summary(_limit(payload))}
    if action == "life_opportunities":
        return {"ok": True, "opportunities": life.memory.list_opportunities(_limit(payload))}
    if action == "life_memory":
        query = str(payload.get("q") or payload.get("query") or "")[:200]
        if query.strip():
            rows = life.memory.search_memories(query, _limit(payload))
        else:
            rows = life.memory.recent_memories(_limit(payload))
        return {"ok": True, "memories": rows}
    if action == "life_skills":
        return {"ok": True, "skills": life.skills.describe()}
    if action == "approvals":
        status = str(payload.get("status") or "pending_approval")
        rows = life.creator.list_actions(None if status == "all" else status)
        return {"ok": True, "actions": [_public_action(row) for row in rows[:50]]}
    if action == "life_tick":
        moment = life.tick(force=_bool(payload.get("force", True)))
        return {"ok": True, "moment": moment, "life": life.status()}
    if action == "life_skill":
        skill_id = str(payload.get("skill") or payload.get("name") or "")
        args = payload.get("args") if isinstance(payload.get("args"), dict) else {}
        moment = life.run_skill(skill_id, args)
        return {"ok": True, "moment": moment}
    if action == "life_focus":
        return {"ok": True, "focus": life.set_focus(str(payload.get("niche") or ""), str(payload.get("goal") or ""))}
    if action == "life_enabled":
        life.set_enabled(_bool(payload.get("enabled", True)))
        return {"ok": True, "enabled": life.enabled}
    if action == "life_pause":
        life.creator.set_paused(_bool(payload.get("paused", True)))
        return {"ok": True, "paused": life.creator.paused}
    if action == "approve":
        return {"ok": True, "action": life.approve(str(payload.get("id") or ""), str(payload.get("note") or ""))}
    if action == "reject":
        return {"ok": True, "action": life.reject(str(payload.get("id") or ""), str(payload.get("note") or ""))}
    if action == "remember":
        try:
            importance = int(payload.get("importance") or 5)
        except (TypeError, ValueError):
            importance = 5
        try:
            return {"ok": True, "memory": life.remember(str(payload.get("text") or ""), importance)}
        except ValueError as exc:
            raise LifeError(400, life.brain.redact(str(exc).splitlines()[0][:200])) from None
    if action == "earning":
        try:
            amount = float(payload.get("amount") or 0)
        except (TypeError, ValueError):
            raise LifeError(400, "amount must be a number") from None
        try:
            return {"ok": True, "earning": life.record_earning(
                str(payload.get("source") or ""), amount,
                str(payload.get("note") or ""), str(payload.get("currency") or "USD"),
            )}
        except LifeError:
            raise
        except ValueError as exc:
            raise LifeError(400, life.brain.redact(str(exc).splitlines()[0][:200])) from None
    raise LifeError(404, "unknown life action")


def _public_action(row: dict) -> dict[str, Any]:
    payload = row.get("payload") or {}
    summary = payload.get("item") or payload.get("text") or payload.get("repository_name") or payload.get("title") or ""
    return {
        "id": row.get("id"),
        "kind": row.get("kind"),
        "status": row.get("status"),
        "summary": str(summary)[:180],
        "executed": row.get("result") is not None and row.get("kind") in EXTERNAL_ACTIONS,
    }


def _offline_plan(niche: str, goal: str) -> list[dict]:
    return [
        {"skill": "content_ideas", "title": "Find three angles", "args": {}},
        {"skill": "write_script", "title": "Write the strongest as a short", "args": {}},
        {"skill": "write_caption", "title": "Write captions for it", "args": {}},
        {"skill": "draft_listing", "title": "Draft a tiny product listing", "args": {}},
        {"skill": "track_opportunity", "title": "Log the opportunity", "args": {}},
        {"skill": "draft_post", "title": "Save the post draft locally", "args": {}},
        {"skill": "propose_post", "title": "Ask before publishing", "args": {}},
    ]


def _plan_focus(data: dict | None, niche: str) -> str:
    if isinstance(data, dict):
        focus = _clean(data.get("focus"), 180)
        if focus:
            return focus
    return f"Make one useful piece about {niche}"[:180]


def _mood_for(mood: str, energy: float, skill: str) -> str:
    if skill == "propose_post":
        return "hopeful"
    if energy < REST_THRESHOLD:
        return "tired"
    return mood if mood in CHATTER else "focused"


def _recover(vitals: dict, now: datetime) -> float:
    energy = float(vitals.get("energy") or 0)
    last = _parse(vitals.get("last_tick"))
    if last is not None:
        hours = max(0.0, (now - last).total_seconds() / 3600.0)
        energy = min(100.0, energy + hours * RECOVER_PER_HOUR)
    return energy


def _scrub_args(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    cleaned = {}
    for key, item in list(value.items())[:8]:
        name = _clean(key, 40)
        text = _clean(item, 500)
        if name and text and name.replace("_", "").isalnum():
            cleaned[name] = text
    return cleaned


def _clean(value: Any, limit: int) -> str:
    if value is None:
        return ""
    text = " ".join(str(value).replace("\x00", "").split())
    return text[:limit].strip()


def _limit(payload: dict) -> int:
    try:
        return max(1, min(100, int(payload.get("limit") or 20)))
    except (TypeError, ValueError):
        return 20


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat(timespec="seconds")


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name, dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _dashboard_html(status: dict, memory: MemoryStore, creator: CreatorEngine) -> str:
    plan = status["plan"]
    rows = []
    for item in plan["items"]:
        rows.append(
            f"<li><span class='mark'>{_esc(item['status'])}</span> "
            f"{_esc(item['title'])} <em>{_esc(item['skill'])}</em></li>"
        )
    activity = []
    for row in memory.recent_activity(12):
        activity.append(f"<li><span class='when'>{_esc(row['created_at'][11:16])}</span> {_esc(row['summary'])}</li>")
    if status["earnings"]:
        money = ", ".join(f"{_esc(name)} {amount:.2f}" for name, amount in status["earnings"].items())
    else:
        money = "nothing logged"
    pending = creator.list_actions("pending_approval")
    waiting = []
    for action in pending[:12]:
        summary = (action.get("payload") or {}).get("text") or (action.get("payload") or {}).get("item") or action["kind"]
        waiting.append(f"<li><code>{_esc(action['id'])}</code> {_esc(action['kind'])}: {_esc(str(summary)[:140])}</li>")
    opps = []
    for opp in memory.list_opportunities(6):
        opps.append(
            f"<li>{_esc(opp['title'])} "
            f"<em>guess ${_esc(opp['guess_low'])}–${_esc(opp['guess_high'])}</em></li>"
        )
    energy = max(0, min(100, int(round(status["energy"]))))
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Mushroom — today</title>
<style>
body {{ margin: 0; background: #15111b; color: #f7eee5; font: 17px/1.45 "Segoe UI", system-ui, sans-serif; }}
main {{ max-width: 820px; margin: 6vh auto; padding: 8px 20px 48px; }}
h1 {{ color: #ff765f; font-size: 32px; margin-bottom: 0; }}
h2 {{ font-size: 15px; letter-spacing: .08em; text-transform: uppercase; color: #ffb07a; }}
section {{ background: #241c2d; border-radius: 18px; padding: 8px 22px 18px; margin: 14px 0; }}
.bar {{ height: 10px; background: #3a3144; border-radius: 99px; overflow: hidden; }}
.bar span {{ display: block; height: 100%; width: {energy}%; background: #ff765f; }}
li {{ margin: 6px 0; }} .mark {{ color: #ffb07a; }} .when {{ color: #a898b4; }}
em {{ color: #a898b4; font-style: normal; }} code {{ color: #ffd7a8; }}
p.note {{ color: #d9cfe0; }}
</style></head>
<body><main>
<h1>{_esc(status['mood'])} · energy {energy}</h1>
<p>{_esc(status['niche'])}</p>
<div class="bar"><span></span></div>
<p class="note">{_esc(status['goal'])}</p>
<section><h2>Today · {plan['done']}/{plan['total']} · {_esc(plan['source'] or '—')}</h2>
<p>{_esc(plan['focus'])}</p><ol>{''.join(rows) or '<li>No plan yet.</li>'}</ol></section>
<section><h2>Activity</h2><ul>{''.join(activity) or '<li>Quiet so far.</li>'}</ul></section>
<section><h2>Money in · {_esc(money)}</h2>
<p class="note">This is a ledger of money that already arrived. The pet cannot spend it.</p></section>
<section><h2>Opportunities</h2><ul>{''.join(opps) or '<li>None spotted.</li>'}</ul>
<p class="note">Guesses are not earnings.</p></section>
<section><h2>Waiting for you · {len(pending)}</h2>
<ul>{''.join(waiting) or '<li>Nothing waiting.</li>'}</ul>
<p class="note">Approving here is not possible on purpose. Confirm from the pet menu, the local API, or tools/mushroom_creator.py. Approval does not post, send, or spend.</p>
</section>
<p class="note">Brain: {_esc(status['brain']['mode'])} {_esc(status['brain'].get('model') or '')}</p>
</main></body></html>
"""


def _esc(value: Any) -> str:
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))
