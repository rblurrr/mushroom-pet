"""Local memory for the autonomous pet.

SQLite holds the things that grow: notes, the daily plan, the activity log,
opportunities, and the earnings ledger. One row of vitals (mood, energy, focus)
is the pet's current state. The database lives under the app data directory,
never in the repository.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def _iso(dt: datetime | None = None) -> str:
    current = dt or datetime.now().astimezone()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.isoformat(timespec="seconds")


class MemoryStore:
    """Thread-safe SQLite memory. Call close() before deleting the directory."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(self.path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA busy_timeout=3000")
        try:
            self._db.execute("PRAGMA journal_mode=WAL")
        except sqlite3.DatabaseError:
            pass
        self._migrate()

    def close(self) -> None:
        with self._lock:
            db = getattr(self, "_db", None)
            self._db = None
            if db is not None:
                db.close()

    def _migrate(self) -> None:
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                text TEXT NOT NULL,
                importance INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                skill TEXT NOT NULL,
                summary TEXT NOT NULL,
                mood TEXT NOT NULL,
                energy REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS plans (
                day TEXT PRIMARY KEY,
                focus TEXT NOT NULL,
                items TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS opportunities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                title TEXT NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                guess_low REAL NOT NULL,
                guess_high REAL NOT NULL,
                notes TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS earnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                source TEXT NOT NULL,
                cents INTEGER NOT NULL,
                currency TEXT NOT NULL,
                note TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS vitals (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                energy REAL NOT NULL,
                mood TEXT NOT NULL,
                niche TEXT NOT NULL,
                goal TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                interval_s REAL NOT NULL,
                last_tick TEXT,
                next_beat TEXT,
                last_summary TEXT NOT NULL DEFAULT '',
                idled_on TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind, id DESC);
            """
        )
        self._db.commit()

    # ----------------------------------------------------------------- vitals
    def get_vitals(self) -> dict[str, Any]:
        with self._lock:
            row = self._db.execute("SELECT * FROM vitals WHERE id = 1").fetchone()
            if row is None:
                self._db.execute(
                    """INSERT INTO vitals
                       (id, energy, mood, niche, goal, enabled, interval_s, last_summary, idled_on)
                       VALUES (1, 80, 'curious', '', '', 1, 900, '', '')"""
                )
                self._db.commit()
                row = self._db.execute("SELECT * FROM vitals WHERE id = 1").fetchone()
            return self._vital_dict(row)

    def update_vitals(self, **fields: Any) -> dict[str, Any]:
        allowed = {
            "energy", "mood", "niche", "goal", "enabled", "interval_s",
            "last_tick", "next_beat", "last_summary", "idled_on",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unknown vitals: {', '.join(sorted(unknown))}")
        if not fields:
            return self.get_vitals()
        cols = ", ".join(f"{name} = ?" for name in fields)
        with self._lock:
            self.get_vitals()
            self._db.execute(
                f"UPDATE vitals SET {cols} WHERE id = 1",
                tuple(fields.values()),
            )
            self._db.commit()
            row = self._db.execute("SELECT * FROM vitals WHERE id = 1").fetchone()
            return self._vital_dict(row)

    def _vital_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "energy": float(row["energy"]),
            "mood": row["mood"],
            "niche": row["niche"] or "",
            "goal": row["goal"] or "",
            "enabled": bool(row["enabled"]),
            "interval_s": float(row["interval_s"]),
            "last_tick": row["last_tick"],
            "next_beat": row["next_beat"],
            "last_summary": row["last_summary"] or "",
            "idled_on": row["idled_on"] or "",
        }

    # ---------------------------------------------------------------- memories
    def add_memory(self, text: str, *, kind: str = "note", importance: int = 5) -> dict[str, Any]:
        kind = (kind or "note").strip().lower()[:40] or "note"
        importance = max(1, min(10, int(importance)))
        text = str(text).strip()
        if not text:
            raise ValueError("memory text cannot be empty")
        if len(text) > 4000:
            text = text[:4000]
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO memories (created_at, kind, text, importance) VALUES (?, ?, ?, ?)",
                (_iso(), kind, text, importance),
            )
            self._db.execute(
                """DELETE FROM memories WHERE id NOT IN
                   (SELECT id FROM memories ORDER BY id DESC LIMIT 2000)"""
            )
            self._db.commit()
            memory_id = int(cur.lastrowid)
        return {"id": memory_id, "kind": kind, "text": text, "importance": importance}

    def recent_memories(self, limit: int = 10, kind: str | None = None,
                        kinds: Iterable[str] | None = None) -> list[dict[str, Any]]:
        limit = max(1, min(100, int(limit)))
        query = "SELECT id, created_at, kind, text, importance FROM memories"
        args: list[Any] = []
        if kind:
            query += " WHERE kind = ?"
            args.append(kind)
        elif kinds:
            names = [str(k) for k in kinds]
            if not names:
                return []
            marks = ",".join("?" for _ in names)
            query += f" WHERE kind IN ({marks})"
            args.extend(names)
        query += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        with self._lock:
            rows = self._db.execute(query, args).fetchall()
        return [dict(row) for row in rows]

    def search_memories(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        cleaned = (query or "").replace("%", "").replace("_", "").strip()
        if not cleaned:
            return []
        limit = max(1, min(50, int(limit)))
        with self._lock:
            rows = self._db.execute(
                """SELECT id, created_at, kind, text, importance FROM memories
                   WHERE text LIKE ? ORDER BY importance DESC, id DESC LIMIT ?""",
                (f"%{cleaned}%", limit),
            ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------- plans
    def get_plan(self, day: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM plans WHERE day = ?", (day,)).fetchone()
        if row is None:
            return None
        try:
            items = json.loads(row["items"])
        except ValueError:
            items = []
        if not isinstance(items, list):
            items = []
        return {
            "day": row["day"],
            "focus": row["focus"],
            "items": items,
            "source": row["source"],
            "created_at": row["created_at"],
        }

    def save_plan(self, plan: dict[str, Any]) -> None:
        with self._lock:
            self._db.execute(
                """INSERT INTO plans (day, focus, items, source, created_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(day) DO UPDATE SET
                     focus = excluded.focus,
                     items = excluded.items,
                     source = excluded.source""",
                (
                    plan["day"],
                    plan["focus"],
                    json.dumps(plan["items"], ensure_ascii=False),
                    plan["source"],
                    plan.get("created_at") or _iso(),
                ),
            )
            self._db.commit()

    def delete_plan(self, day: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM plans WHERE day = ?", (day,))
            self._db.commit()

    # ---------------------------------------------------------------- activity
    def add_activity(self, skill: str, summary: str, mood: str, energy: float) -> None:
        with self._lock:
            self._db.execute(
                """INSERT INTO activity (created_at, skill, summary, mood, energy)
                   VALUES (?, ?, ?, ?, ?)""",
                (_iso(), skill[:80], summary[:500], mood[:40], float(energy)),
            )
            self._db.execute(
                """DELETE FROM activity WHERE id NOT IN
                   (SELECT id FROM activity ORDER BY id DESC LIMIT 2000)"""
            )
            self._db.commit()

    def recent_activity(self, limit: int = 20) -> list[dict[str, Any]]:
        limit = max(1, min(100, int(limit)))
        with self._lock:
            rows = self._db.execute(
                """SELECT id, created_at, skill, summary, mood, energy
                   FROM activity ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    # ---------------------------------------------------------- opportunities
    def add_opportunity(self, title: str, kind: str, notes: str,
                        guess_low: float, guess_high: float) -> dict[str, Any]:
        now = _iso()
        low = max(0.0, float(guess_low))
        high = max(low, float(guess_high))
        with self._lock:
            cur = self._db.execute(
                """INSERT INTO opportunities
                   (created_at, updated_at, title, kind, status, guess_low, guess_high, notes)
                   VALUES (?, ?, ?, ?, 'spotted', ?, ?, ?)""",
                (now, now, title[:200], (kind or "idea")[:40], low, high, notes[:2000]),
            )
            self._db.commit()
            opp_id = int(cur.lastrowid)
        return {
            "id": opp_id, "title": title[:200], "kind": kind, "status": "spotted",
            "guess_low": low, "guess_high": high, "notes": notes[:2000],
        }

    def list_opportunities(self, limit: int = 20) -> list[dict[str, Any]]:
        limit = max(1, min(100, int(limit)))
        with self._lock:
            rows = self._db.execute(
                """SELECT id, created_at, title, kind, status, guess_low, guess_high, notes
                   FROM opportunities ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    # -------------------------------------------------------------- earnings
    def add_earning(self, source: str, cents: int, currency: str = "USD",
                    note: str = "") -> dict[str, Any]:
        cents = int(cents)
        if cents == 0 or abs(cents) > 100_000_000:
            raise ValueError("amount must be between 0 and 1000000, and not zero")
        currency = (currency or "USD").strip().upper()[:8] or "USD"
        source = str(source).strip()
        if not source:
            raise ValueError("earning source cannot be empty")
        with self._lock:
            cur = self._db.execute(
                """INSERT INTO earnings (created_at, source, cents, currency, note)
                   VALUES (?, ?, ?, ?, ?)""",
                (_iso(), source[:200], cents, currency, (note or "")[:500]),
            )
            self._db.commit()
            earning_id = int(cur.lastrowid)
        return {
            "id": earning_id,
            "source": source[:200],
            "amount": cents / 100.0,
            "currency": currency,
            "note": (note or "")[:500],
        }

    def earnings_summary(self, limit: int = 10) -> dict[str, Any]:
        limit = max(1, min(50, int(limit)))
        with self._lock:
            totals = self._db.execute(
                "SELECT currency, SUM(cents) AS cents, COUNT(*) AS n FROM earnings GROUP BY currency"
            ).fetchall()
            recent = self._db.execute(
                """SELECT id, created_at, source, cents, currency, note
                   FROM earnings ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        by_currency = {row["currency"]: row["cents"] / 100.0 for row in totals}
        count = sum(int(row["n"]) for row in totals)
        recent_rows = []
        for row in recent:
            item = dict(row)
            item["amount"] = item.pop("cents") / 100.0
            recent_rows.append(item)
        return {"by_currency": by_currency, "count": count, "recent": recent_rows}
