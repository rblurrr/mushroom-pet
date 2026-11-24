"""SQLite world memory for Sparky. The life loop's own database stays separate."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=3000")
    try:
        db.execute("PRAGMA journal_mode=WAL")
    except sqlite3.DatabaseError:
        pass
    return db


class WorldStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._db = _connect(self.path)
        self._migrate()

    def close(self) -> None:
        with self._lock:
            db = self._db
            self._db = None
            if db is not None:
                db.close()

    def _migrate(self) -> None:
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS kv (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS diary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                author TEXT NOT NULL,
                text TEXT NOT NULL,
                kind TEXT NOT NULL,
                correction_of INTEGER
            );
            CREATE TABLE IF NOT EXISTS sparks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                sender TEXT NOT NULL,
                sender_name TEXT NOT NULL,
                text TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                reply TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS people (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                label TEXT NOT NULL,
                private_note TEXT NOT NULL DEFAULT '',
                sparks INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS shop (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                blurb TEXT NOT NULL,
                price_cents INTEGER NOT NULL,
                kind TEXT NOT NULL,
                story TEXT NOT NULL,
                flaw TEXT NOT NULL,
                version TEXT NOT NULL,
                sold INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                sku TEXT NOT NULL,
                buyer TEXT NOT NULL,
                status TEXT NOT NULL,
                approval_id TEXT
            );
            CREATE TABLE IF NOT EXISTS sightings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                place TEXT NOT NULL,
                note TEXT NOT NULL,
                lat REAL,
                lon REAL,
                photo TEXT,
                reaction TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS letters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL,
                approval_id TEXT
            );
            CREATE TABLE IF NOT EXISTS outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                column_name TEXT NOT NULL,
                detail TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                action TEXT NOT NULL,
                reason TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS notices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                author TEXT NOT NULL,
                text TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS votes (
                voter TEXT NOT NULL,
                week TEXT NOT NULL,
                choice INTEGER NOT NULL,
                PRIMARY KEY (voter, week)
            );
            """
        )
        self._db.commit()

    # ------------------------------------------------------------------- state
    def load_state(self) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT value FROM kv WHERE key = 'state'").fetchone()
        if row is None:
            return None
        try:
            value = json.loads(row["value"])
        except ValueError:
            return None
        return value if isinstance(value, dict) else None

    def save_state(self, state: dict[str, Any]) -> None:
        payload = json.dumps(state, ensure_ascii=False)
        with self._lock:
            self._db.execute(
                "INSERT INTO kv (key, value) VALUES ('state', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (payload,),
            )
            self._db.commit()

    # ------------------------------------------------------------------- diary
    def add_diary(self, created_at: str, author: str, text: str, kind: str = "log",
                  correction_of: int | None = None) -> dict[str, Any]:
        with self._lock:
            cur = self._db.execute(
                """INSERT INTO diary (created_at, author, text, kind, correction_of)
                   VALUES (?, ?, ?, ?, ?)""",
                (created_at, author[:40], text[:2000], kind[:40], correction_of),
            )
            self._db.commit()
            diary_id = int(cur.lastrowid)
        return {
            "id": diary_id, "time": created_at, "author": author[:40],
            "text": text[:2000], "kind": kind[:40], "correction_of": correction_of,
        }

    def diary(self, limit: int = 40) -> list[dict[str, Any]]:
        limit = max(1, min(200, int(limit)))
        with self._lock:
            rows = self._db.execute(
                """SELECT id, created_at, author, text, kind, correction_of
                   FROM diary ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [_diary_row(row) for row in rows]

    def count_diary(self, kind: str | None = None) -> int:
        with self._lock:
            if kind:
                row = self._db.execute(
                    "SELECT COUNT(*) AS n FROM diary WHERE kind = ?", (kind,)
                ).fetchone()
            else:
                row = self._db.execute("SELECT COUNT(*) AS n FROM diary").fetchone()
        return int(row["n"])

    # ------------------------------------------------------------------ sparks
    def add_spark(self, created_at: str, sender: str, sender_name: str, text: str,
                  status: str, reason: str = "", reply: str = "") -> dict[str, Any]:
        with self._lock:
            cur = self._db.execute(
                """INSERT INTO sparks
                   (created_at, sender, sender_name, text, status, reason, reply)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (created_at, sender[:80], sender_name[:80], text[:2000],
                 status[:40], reason[:400], reply[:2000]),
            )
            self._db.commit()
            spark_id = int(cur.lastrowid)
        return {"id": spark_id, "status": status, "reason": reason, "reply": reply}

    def oldest_queued(self) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(
                """SELECT * FROM sparks WHERE status = 'queued' ORDER BY id ASC LIMIT 1"""
            ).fetchone()
        return dict(row) if row else None

    def set_spark(self, spark_id: int, status: str, reason: str = "") -> None:
        with self._lock:
            self._db.execute(
                "UPDATE sparks SET status = ?, reason = ? WHERE id = ?",
                (status[:40], reason[:400], int(spark_id)),
            )
            self._db.commit()

    def queue_length(self) -> int:
        with self._lock:
            row = self._db.execute(
                "SELECT COUNT(*) AS n FROM sparks WHERE status = 'queued'"
            ).fetchone()
        return int(row["n"])

    def sparks_for(self, sender: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                """SELECT id, created_at, text, status, reason, reply
                   FROM sparks WHERE sender = ? ORDER BY id DESC LIMIT ?""",
                (sender, max(1, min(50, limit))),
            ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------ people
    def get_person(self, person_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone()
        return dict(row) if row else None

    def save_person(self, person: dict[str, Any]) -> None:
        with self._lock:
            self._db.execute(
                """INSERT INTO people (id, name, label, private_note, sparks, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     name = excluded.name,
                     label = excluded.label,
                     private_note = excluded.private_note,
                     sparks = excluded.sparks,
                     updated_at = excluded.updated_at""",
                (
                    person["id"], person["name"][:80], person["label"][:160],
                    person.get("private_note", "")[:1000], int(person["sparks"]),
                    person["updated_at"],
                ),
            )
            self._db.commit()

    def delete_person(self, person_id: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM people WHERE id = ?", (person_id,))
            self._db.commit()

    def live_wires(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                """SELECT name, label, sparks FROM people
                   WHERE sparks >= 5 ORDER BY sparks DESC, name ASC LIMIT 40"""
            ).fetchall()
        return [
            {"name": row["name"], "label": row["label"], "sparks": int(row["sparks"])}
            for row in rows
        ]

    # -------------------------------------------------------------------- shop
    def add_shop_item(self, item: dict[str, Any]) -> None:
        with self._lock:
            self._db.execute(
                """INSERT OR REPLACE INTO shop
                   (id, title, blurb, price_cents, kind, story, flaw, version, sold)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item["id"], item["title"][:160], item.get("blurb", "")[:400],
                    int(item["price_cents"]), item["kind"][:40], item.get("story", "")[:800],
                    item.get("flaw", "")[:240], item.get("version", "v1")[:20],
                    1 if item.get("sold") else 0,
                ),
            )
            self._db.commit()

    def shop(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM shop ORDER BY sold ASC, title ASC"
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["sold"] = bool(item["sold"])
            item["price"] = item["price_cents"] / 100.0
            items.append(item)
        return items

    def shop_item(self, sku: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM shop WHERE id = ?", (sku,)).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["sold"] = bool(item["sold"])
        return item

    def mark_sold(self, sku: str) -> None:
        with self._lock:
            self._db.execute("UPDATE shop SET sold = 1 WHERE id = ?", (sku,))
            self._db.commit()

    def add_order(self, created_at: str, sku: str, buyer: str, status: str,
                  approval_id: str | None) -> dict[str, Any]:
        with self._lock:
            cur = self._db.execute(
                """INSERT INTO orders (created_at, sku, buyer, status, approval_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (created_at, sku, buyer[:80], status[:40], approval_id),
            )
            self._db.commit()
            order_id = int(cur.lastrowid)
        return {"id": order_id, "sku": sku, "status": status, "approval_id": approval_id}

    def pending_orders(self) -> int:
        with self._lock:
            row = self._db.execute(
                "SELECT COUNT(*) AS n FROM orders WHERE status = 'pending_approval'"
            ).fetchone()
        return int(row["n"])

    # -------------------------------------------------------------------- toy
    def add_sighting(self, row: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            cur = self._db.execute(
                """INSERT INTO sightings (created_at, place, note, lat, lon, photo, reaction)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    row["created_at"], row["place"][:160], row["note"][:500],
                    row.get("lat"), row.get("lon"), row.get("photo"), row["reaction"][:500],
                ),
            )
            self._db.commit()
            row = dict(row)
            row["id"] = int(cur.lastrowid)
        return row

    def sightings(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                """SELECT id, created_at, place, note, lat, lon, photo, reaction
                   FROM sightings ORDER BY id DESC LIMIT ?""",
                (max(1, min(100, limit)),),
            ).fetchall()
        return [dict(row) for row in rows]

    # -------------------------------------------------------------- newsletter
    def add_letter(self, created_at: str, title: str, body: str, status: str,
                   approval_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            cur = self._db.execute(
                """INSERT INTO letters (created_at, title, body, status, approval_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (created_at, title[:160], body[:8000], status[:40], approval_id),
            )
            self._db.commit()
            letter_id = int(cur.lastrowid)
        return {
            "id": letter_id, "time": created_at, "title": title[:160],
            "body": body[:8000], "status": status, "approval_id": approval_id,
        }

    def letters(self, limit: int = 12) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                """SELECT id, created_at, title, body, status, approval_id
                   FROM letters ORDER BY id DESC LIMIT ?""",
                (max(1, min(40, limit)),),
            ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["time"] = item.pop("created_at")
            out.append(item)
        return out

    def set_letter_status(self, letter_id: int, status: str, approval_id: str | None) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE letters SET status = ?, approval_id = ? WHERE id = ?",
                (status[:40], approval_id, int(letter_id)),
            )
            self._db.commit()

    def pending_letter(self) -> bool:
        with self._lock:
            row = self._db.execute(
                "SELECT COUNT(*) AS n FROM letters WHERE status = 'pending_approval'"
            ).fetchone()
        return int(row["n"]) > 0

    # ---------------------------------------------------------------- outcomes
    def add_outcome(self, title: str, column: str, detail: str, updated_at: str) -> int:
        with self._lock:
            cur = self._db.execute(
                """INSERT INTO outcomes (title, column_name, detail, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (title[:160], column[:40], detail[:500], updated_at),
            )
            self._db.commit()
            return int(cur.lastrowid)

    def outcomes(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, title, column_name, detail, updated_at FROM outcomes ORDER BY id ASC"
            ).fetchall()
        return [
            {
                "id": row["id"], "title": row["title"], "column": row["column_name"],
                "detail": row["detail"], "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def set_outcome(self, outcome_id: int, column: str, detail: str, updated_at: str) -> None:
        with self._lock:
            self._db.execute(
                """UPDATE outcomes SET column_name = ?, detail = ?, updated_at = ?
                   WHERE id = ?""",
                (column[:40], detail[:500], updated_at, int(outcome_id)),
            )
            self._db.commit()

    # --------------------------------------------------------------- decisions
    def add_decision(self, created_at: str, action: str, reason: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO decisions (created_at, action, reason) VALUES (?, ?, ?)",
                (created_at, action[:80], reason[:1000]),
            )
            self._db.commit()

    def decisions(self, limit: int = 40) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                """SELECT id, created_at, action, reason FROM decisions
                   ORDER BY id DESC LIMIT ?""",
                (max(1, min(100, limit)),),
            ).fetchall()
        return [dict(row) for row in rows]

    # ----------------------------------------------------------------- notices
    def add_notice(self, created_at: str, author: str, text: str) -> dict[str, Any]:
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO notices (created_at, author, text) VALUES (?, ?, ?)",
                (created_at, author[:80], text[:500]),
            )
            self._db.commit()
            return {"id": int(cur.lastrowid), "time": created_at, "author": author[:80], "text": text[:500]}

    def notices(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, created_at, author, text FROM notices ORDER BY id DESC LIMIT ?",
                (max(1, min(50, limit)),),
            ).fetchall()
        return [
            {"id": row["id"], "time": row["created_at"], "author": row["author"], "text": row["text"]}
            for row in rows
        ]

    # -------------------------------------------------------------------- votes
    def cast_vote(self, voter: str, week: str, choice: int) -> None:
        with self._lock:
            self._db.execute(
                """INSERT INTO votes (voter, week, choice) VALUES (?, ?, ?)
                   ON CONFLICT(voter, week) DO UPDATE SET choice = excluded.choice""",
                (voter[:80], week, int(choice)),
            )
            self._db.commit()

    def vote_counts(self, week: str) -> dict[int, int]:
        with self._lock:
            rows = self._db.execute(
                "SELECT choice, COUNT(*) AS n FROM votes WHERE week = ? GROUP BY choice",
                (week,),
            ).fetchall()
        return {int(row["choice"]): int(row["n"]) for row in rows}


def _diary_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "time": row["created_at"],
        "author": row["author"],
        "text": row["text"],
        "kind": row["kind"],
        "correction_of": row["correction_of"],
    }
