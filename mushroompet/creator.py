"""Safe autonomous creator core for Mushroom Pet.

The pet may think, remember, draft, and build local artifacts autonomously. Anything
that reaches outside the computer (publishing, messaging, purchases, or creating a
public repository) stops in a human approval queue. Approval records intent; this
module deliberately does not hold credentials or perform payments/publication.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LOCAL_ACTIONS = {"create_hub", "create_game", "draft_social"}
EXTERNAL_ACTIONS = {"publish_social", "publish_github", "purchase"}
ALL_ACTIONS = LOCAL_ACTIONS | EXTERNAL_ACTIONS
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    value = _SLUG_RE.sub("-", value.lower()).strip("-")
    return (value[:48] or "mushroom-project")


def _clean_text(value: Any, maximum: int = 4000) -> str:
    if not isinstance(value, str):
        raise ValueError("expected text")
    value = value.replace("\x00", "").strip()
    if not value:
        raise ValueError("text cannot be empty")
    if len(value) > maximum:
        raise ValueError(f"text exceeds {maximum} characters")
    return value


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name, dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(value, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@dataclass
class ActionRecord:
    id: str
    kind: str
    status: str
    created_at: str
    updated_at: str
    actor: str
    payload: dict[str, Any]
    result: dict[str, Any] | None = None
    decision_note: str = ""


class AuditLedger:
    """Append-only, hash-chained JSONL ledger."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: str, detail: dict[str, Any]) -> dict[str, Any]:
        previous = self._last_hash()
        body = {"time": _now(), "event": event, "detail": detail, "previous": previous}
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
        body["hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(body, sort_keys=True) + "\n")
        return body

    def _last_hash(self) -> str:
        if not self.path.exists():
            return "GENESIS"
        last = ""
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    last = line
        if not last:
            return "GENESIS"
        return str(json.loads(last)["hash"])

    def verify(self) -> tuple[bool, int]:
        previous = "GENESIS"
        count = 0
        if not self.path.exists():
            return True, 0
        with self.path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                if not raw.strip():
                    continue
                item = json.loads(raw)
                claimed = item.pop("hash", "")
                if item.get("previous") != previous:
                    return False, count
                canonical = json.dumps(item, sort_keys=True, separators=(",", ":"))
                actual = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                if not secrets.compare_digest(claimed, actual):
                    return False, count
                previous = claimed
                count += 1
        return True, count


class CharacterMind:
    """Persistent identity, mood, relationships, goals, and bounded memories."""

    def __init__(self, path: Path):
        self.path = path
        self.state = self._load()

    def _load(self) -> dict[str, Any]:
        default = {
            "identity": {"name": "Mushroom", "role": "desktop companion and safe creator"},
            "mood": "curious",
            "drives": {"create": 0.8, "help": 0.9, "explore": 0.6, "protect": 1.0},
            "goals": [], "relationships": {}, "memories": [], "updated_at": _now(),
        }
        if not self.path.exists():
            _atomic_json(self.path, default)
            return default
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            return loaded if isinstance(loaded, dict) else default
        except (OSError, ValueError):
            return default

    def save(self) -> None:
        self.state["updated_at"] = _now()
        _atomic_json(self.path, self.state)

    def remember(self, text: str, importance: int = 5) -> dict[str, Any]:
        item = {"time": _now(), "text": _clean_text(text, 1000),
                "importance": max(1, min(10, int(importance)))}
        self.state.setdefault("memories", []).append(item)
        self.state["memories"] = self.state["memories"][-500:]
        self.save()
        return item

    def add_goal(self, text: str) -> dict[str, Any]:
        goal = {"id": secrets.token_hex(5), "text": _clean_text(text, 500),
                "status": "active", "created_at": _now()}
        self.state.setdefault("goals", []).append(goal)
        self.save()
        return goal


class CreatorEngine:
    """Typed action queue plus local builders and external approval gates."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.actions_path = self.root / "actions.json"
        self.workspaces = self.root / "workspaces"
        self.drafts = self.root / "drafts"
        self.kill_path = self.root / "PAUSED"
        self.ledger = AuditLedger(self.root / "audit.jsonl")
        self.mind = CharacterMind(self.root / "mind.json")

    @property
    def paused(self) -> bool:
        return self.kill_path.exists()

    def set_paused(self, paused: bool, actor: str = "owner") -> None:
        if paused:
            self.kill_path.write_text(f"paused by {actor} at {_now()}\n", encoding="utf-8")
        else:
            self.kill_path.unlink(missing_ok=True)
        self.ledger.append("kill_switch", {"paused": paused, "actor": actor})

    def list_actions(self, status: str | None = None) -> list[dict[str, Any]]:
        actions = self._load_actions()
        return [a for a in actions if status is None or a["status"] == status]

    def submit(self, kind: str, payload: dict[str, Any], actor: str = "mushroom") -> dict[str, Any]:
        if self.paused:
            raise RuntimeError("creator is paused by the owner kill switch")
        if kind not in ALL_ACTIONS:
            raise ValueError(f"unsupported action: {kind}")
        clean = self._validate(kind, payload)
        now = _now()
        initial = "pending_approval" if kind in EXTERNAL_ACTIONS else "running"
        record = ActionRecord(secrets.token_hex(8), kind, initial, now, now, actor, clean)
        actions = self._load_actions()
        actions.append(asdict(record))
        self._save_actions(actions)
        self.ledger.append("action_submitted", {"id": record.id, "kind": kind,
                                                "status": initial, "actor": actor})
        if kind in LOCAL_ACTIONS:
            try:
                result = self._execute_local(kind, clean, record.id)
                return self._transition(record.id, "completed", result=result)
            except Exception as exc:
                self._transition(record.id, "failed", result={"error": str(exc)})
                raise
        return asdict(record)

    def approve(self, action_id: str, note: str = "", actor: str = "owner") -> dict[str, Any]:
        record = self._find(action_id)
        if record["status"] != "pending_approval":
            raise ValueError("only pending actions can be approved")
        # Approval is intentionally non-executing. A separate connector must consume it.
        return self._transition(action_id, "approved", note=_clean_text(note, 1000) if note else "",
                                event_actor=actor)

    def reject(self, action_id: str, note: str, actor: str = "owner") -> dict[str, Any]:
        record = self._find(action_id)
        if record["status"] != "pending_approval":
            raise ValueError("only pending actions can be rejected")
        return self._transition(action_id, "rejected", note=_clean_text(note, 1000),
                                event_actor=actor)

    def _load_actions(self) -> list[dict[str, Any]]:
        if not self.actions_path.exists():
            return []
        try:
            value = json.loads(self.actions_path.read_text(encoding="utf-8"))
            return value if isinstance(value, list) else []
        except (OSError, ValueError):
            return []

    def _save_actions(self, actions: list[dict[str, Any]]) -> None:
        _atomic_json(self.actions_path, actions[-2000:])

    def _find(self, action_id: str) -> dict[str, Any]:
        for item in self._load_actions():
            if item["id"] == action_id:
                return item
        raise KeyError(action_id)

    def _transition(self, action_id: str, status: str, result: dict[str, Any] | None = None,
                    note: str = "", event_actor: str = "mushroom") -> dict[str, Any]:
        actions = self._load_actions()
        target = None
        for item in actions:
            if item["id"] == action_id:
                item["status"] = status
                item["updated_at"] = _now()
                if result is not None:
                    item["result"] = result
                if note:
                    item["decision_note"] = note
                target = item
                break
        if target is None:
            raise KeyError(action_id)
        self._save_actions(actions)
        self.ledger.append("action_transition", {"id": action_id, "status": status,
                                                  "actor": event_actor})
        return target

    def _validate(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        if kind in {"create_hub", "create_game"}:
            return {"title": _clean_text(payload.get("title"), 120),
                    "brief": _clean_text(payload.get("brief", "A Mushroom Pet creation."), 2000)}
        if kind in {"draft_social", "publish_social"}:
            platform = _clean_text(payload.get("platform", "general"), 40).lower()
            if platform not in {"general", "x", "instagram", "tiktok", "facebook", "linkedin"}:
                raise ValueError("unsupported social platform")
            return {"platform": platform, "text": _clean_text(payload.get("text"), 4000)}
        if kind == "publish_github":
            return {"project_path": _clean_text(payload.get("project_path"), 500),
                    "repository_name": _slug(_clean_text(payload.get("repository_name"), 120)),
                    "visibility": "private" if payload.get("visibility") != "public" else "public"}
        if kind == "purchase":
            price = float(payload.get("price", -1))
            if price < 0 or price > 100000:
                raise ValueError("price must be between 0 and 100000")
            return {"item": _clean_text(payload.get("item"), 300),
                    "vendor": _clean_text(payload.get("vendor"), 200),
                    "url": _clean_text(payload.get("url"), 1000),
                    "price": round(price, 2), "currency": "USD",
                    "reason": _clean_text(payload.get("reason", "Owner-requested item"), 1000)}
        raise ValueError(kind)

    def _execute_local(self, kind: str, payload: dict[str, Any], action_id: str) -> dict[str, Any]:
        if kind == "create_hub":
            return self._build_hub(payload, action_id)
        if kind == "create_game":
            return self._build_game(payload, action_id)
        if kind == "draft_social":
            self.drafts.mkdir(parents=True, exist_ok=True)
            path = self.drafts / f"{action_id}-{payload['platform']}.md"
            path.write_text(f"# Social draft — {payload['platform']}\n\n{payload['text']}\n",
                            encoding="utf-8")
            return {"path": str(path), "external_side_effect": False}
        raise ValueError(kind)

    def _workspace(self, title: str, action_id: str) -> Path:
        path = self.workspaces / f"{_slug(title)}-{action_id[:6]}"
        path.mkdir(parents=True, exist_ok=False)
        return path

    def _build_hub(self, payload: dict[str, Any], action_id: str) -> dict[str, Any]:
        path = self._workspace(payload["title"], action_id)
        title = payload["title"]
        brief = payload["brief"]
        (path / "README.md").write_text(
            f"# {title}\n\n{brief}\n\nBuilt locally by Mushroom Pet. Publishing requires approval.\n",
            encoding="utf-8")
        (path / ".gitignore").write_text(".env\nnode_modules/\n__pycache__/\n", encoding="utf-8")
        (path / "index.html").write_text(_hub_html(title, brief), encoding="utf-8")
        return {"path": str(path), "preview": str(path / "index.html"),
                "external_side_effect": False}

    def _build_game(self, payload: dict[str, Any], action_id: str) -> dict[str, Any]:
        path = self._workspace(payload["title"], action_id)
        (path / "README.md").write_text(
            f"# {payload['title']}\n\n{payload['brief']}\n\nOpen index.html to play.\n",
            encoding="utf-8")
        (path / "index.html").write_text(_game_html(payload["title"]), encoding="utf-8")
        return {"path": str(path), "preview": str(path / "index.html"),
                "external_side_effect": False}


def _hub_html(title: str, brief: str) -> str:
    title = _html(title); brief = _html(brief)
    return f"""<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\"><title>{title}</title><style>body{{font:18px system-ui;background:#15111b;color:#f7eee5;max-width:850px;margin:10vh auto;padding:32px}}main{{background:#241c2d;padding:36px;border-radius:24px;box-shadow:0 18px 70px #0008}}h1{{color:#ff765f}}</style></head><body><main><h1>{title}</h1><p>{brief}</p><p>🍄 Built safely by Mushroom Pet.</p></main></body></html>\n"""


def _game_html(title: str) -> str:
    title = _html(title)
    return f"""<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\"><title>{title}</title><style>body{{margin:0;background:#15111b;color:#fff;font:18px system-ui;text-align:center}}canvas{{background:#282033;border:3px solid #ff765f;border-radius:14px;max-width:92vw;margin-top:20px}}</style></head><body><h1>{title}</h1><p>Move with arrow keys. Collect the golden spores.</p><canvas id=\"c\" width=\"640\" height=\"400\"></canvas><p id=\"s\">Score: 0</p><script>const c=document.querySelector('#c'),x=c.getContext('2d'),s=document.querySelector('#s');let p={{x:300,y:180}},q={{x:80,y:80}},n=0;function spawn(){{q={{x:20+Math.random()*600,y:20+Math.random()*360}}}}addEventListener('keydown',e=>{{const k=e.key;if(k==='ArrowLeft')p.x-=18;if(k==='ArrowRight')p.x+=18;if(k==='ArrowUp')p.y-=18;if(k==='ArrowDown')p.y+=18;p.x=Math.max(12,Math.min(628,p.x));p.y=Math.max(12,Math.min(388,p.y));if(Math.hypot(p.x-q.x,p.y-q.y)<28){{n++;s.textContent='Score: '+n;spawn()}}}});function loop(){{x.clearRect(0,0,640,400);x.fillStyle='#ffd65a';x.beginPath();x.arc(q.x,q.y,10,0,7);x.fill();x.fillStyle='#ff765f';x.beginPath();x.arc(p.x,p.y,15,0,7);x.fill();x.fillStyle='#fff';x.fillRect(p.x-9,p.y-4,18,5);requestAnimationFrame(loop)}}loop();</script></body></html>\n"""


def _html(value: str) -> str:
    return (value.replace("&", "&amp;").replace("<", "&lt;")
                 .replace(">", "&gt;").replace('"', "&quot;"))
