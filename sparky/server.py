"""Local HTTP server for Sparky's World. Loopback by default."""
from __future__ import annotations

import json
import mimetypes
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .engine import SparkyEngine, default_home
from .safety import clip

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
MAX_BODY = 64 * 1024
MAX_PHOTO_BODY = 400_000

_OPEN = {"/", "/index.html", "/api/state", "/api/health"}


class SparkyHandler(BaseHTTPRequestHandler):
    server_version = "SparkyWorld/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._send(200, {"ok": True, "service": "sparky"})
            return
        if parsed.path == "/api/state":
            self._send(200, {"ok": True, "state": self._engine().public_state()}, cookie=True)
            return
        if parsed.path == "/api/me":
            self._send(200, self._engine().me(self._person()))
            return
        if parsed.path == "/api/owner/state":
            if not self._owner():
                self._send(401, {"ok": False, "error": "owner token required"})
                return
            self._send(200, {"ok": True, "owner": self._engine().owner_state()})
            return
        if parsed.path.startswith("/photos/"):
            self._photo(parsed.path.rsplit("/", 1)[-1])
            return
        if parsed.path.startswith("/api/"):
            self._send(404, {"ok": False, "error": "unknown route"})
            return
        self._file(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            limit = MAX_PHOTO_BODY if path == "/api/found" else MAX_BODY
            payload = _read_json(self, limit)
        except ValueError as exc:
            self._send(400, {"ok": False, "error": str(exc)})
            return
        engine = self._engine()
        person = self._person()
        try:
            if path == "/api/spark":
                result = engine.hand_spark(person, str(payload.get("text") or ""), str(payload.get("name") or ""))
            elif path == "/api/sense":
                if _has_frame(payload):
                    self._send(400, {"ok": False, "error": "camera frames are not accepted"})
                    return
                result = engine.sense(str(payload.get("text") or ""), bool(payload.get("remember")))
            elif path == "/api/found":
                result = self._found(engine, payload)
            elif path == "/api/vote":
                result = engine.vote(person, int(payload.get("choice")))
            elif path == "/api/morph":
                result = engine.morph(str(payload.get("command") or ""))
            elif path == "/api/order":
                result = engine.order(str(payload.get("sku") or ""), person)
            elif path == "/api/newsletter":
                result = engine.write_newsletter(bool(payload.get("send")))
            elif path == "/api/field":
                result = engine.field_report(str(payload.get("text") or ""))
            elif path == "/api/notice":
                result = engine.pin_notice(str(payload.get("name") or "Conductor"), str(payload.get("text") or ""))
            elif path == "/api/me":
                result = engine.update_me(person, str(payload.get("name") or ""), str(payload.get("label") or ""))
            elif path == "/api/me/forget":
                result = engine.forget_me(person)
            elif path == "/api/owner/pause":
                if not self._owner():
                    self._send(401, {"ok": False, "error": "owner token required"})
                    return
                paused = engine.set_paused(bool(payload.get("paused", True)))
                result = {"ok": True, "paused": paused}
            elif path == "/api/owner/approve":
                if not self._owner():
                    self._send(401, {"ok": False, "error": "owner token required"})
                    return
                record = engine.approve(str(payload.get("id") or ""), str(payload.get("note") or ""))
                result = {"ok": True, "action": record, "executed": False}
            elif path == "/api/owner/reject":
                if not self._owner():
                    self._send(401, {"ok": False, "error": "owner token required"})
                    return
                record = engine.reject(str(payload.get("id") or ""), str(payload.get("note") or ""))
                result = {"ok": True, "action": record}
            elif path == "/api/owner/tick":
                if not self._owner():
                    self._send(401, {"ok": False, "error": "owner token required"})
                    return
                result = {"ok": True, "moment": engine.tick(force=True)}
            elif path == "/api/owner/earning":
                if not self._owner():
                    self._send(401, {"ok": False, "error": "owner token required"})
                    return
                result = engine.record_earning(
                    str(payload.get("source") or ""),
                    float(payload.get("amount") or 0),
                    str(payload.get("note") or ""),
                )
            elif path == "/api/owner/correction":
                if not self._owner():
                    self._send(401, {"ok": False, "error": "owner token required"})
                    return
                result = engine.correct(int(payload.get("id") or 0), str(payload.get("text") or ""))
            else:
                self._send(404, {"ok": False, "error": "unknown route"})
                return
        except (ValueError, TypeError) as exc:
            self._send(400, {"ok": False, "error": clip(exc, 180)})
            return
        except Exception as exc:
            message = str(exc).splitlines()[0][:180]
            status = 404 if "unknown action" in message else 400
            self._send(status, {"ok": False, "error": message or "that didn't work"})
            return
        code = 200 if result.get("ok", True) else 400
        self._send(code, result)

    def _found(self, engine: SparkyEngine, payload: dict) -> dict:
        if payload.get("save_photo") and payload.get("photo"):
            photo = _store_photo(engine.root, str(payload.get("photo")))
        elif payload.get("photo") and not payload.get("save_photo"):
            return {"ok": False, "error": "photos are stored only when save_photo is true"}
        else:
            photo = None
        lat = _float_or_none(payload.get("lat"))
        lon = _float_or_none(payload.get("lon"))
        return engine.found_toy(
            str(payload.get("place") or ""),
            str(payload.get("note") or ""),
            lat, lon, photo,
        )

    def _photo(self, name: str) -> None:
        import re
        if not re.fullmatch(r"[a-f0-9]{16}\.(?:jpg|png)", name or ""):
            self._send(404, {"ok": False, "error": "not found"})
            return
        path = self._engine().root / "photos" / name
        if not path.is_file():
            self._send(404, {"ok": False, "error": "not found"})
            return
        data = path.read_bytes()
        mime = "image/jpeg" if name.endswith(".jpg") else "image/png"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _file(self, path: str) -> None:
        rel = "index.html" if path in {"", "/"} else path.lstrip("/")
        root = WEB_ROOT.resolve()
        target = (root / rel).resolve()
        if root not in target.parents and target != root:
            self._send(404, {"ok": False, "error": "not found"})
            return
        if not target.is_file():
            self._send(404, {"ok": False, "error": "not found"})
            return
        data = target.read_bytes()
        mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix == ".js":
            mime = "text/javascript"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self._cookie_header()
        self.end_headers()
        self.wfile.write(data)

    def _send(self, code: int, payload: dict, cookie: bool = False) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if cookie or code < 500:
            self._cookie_header()
        self.end_headers()
        self.wfile.write(body)

    def _cookie_header(self) -> None:
        if self._existing_person():
            return
        person = self._person()
        self.send_header(
            "Set-Cookie",
            f"sparky_cid={person}; Path=/; SameSite=Lax; HttpOnly",
        )

    def _existing_person(self) -> str:
        raw = self.headers.get("Cookie") or ""
        for part in raw.split(";"):
            key, _, value = part.strip().partition("=")
            if key == "sparky_cid" and value:
                return value[:80]
        return ""

    def _person(self) -> str:
        found = self._existing_person()
        if found:
            return found
        if not hasattr(self, "_minted"):
            self._minted = secrets.token_hex(8)
        return self._minted

    def _owner(self) -> bool:
        header = self.headers.get("Authorization") or ""
        token = ""
        if header.lower().startswith("bearer "):
            token = header[7:].strip()
        token = token or (self.headers.get("X-Owner-Token") or "")
        return self._engine().authorized(token)

    def _engine(self) -> SparkyEngine:
        return self.server.engine  # type: ignore[attr-defined]


def _has_frame(payload: dict) -> bool:
    for key in payload:
        if key.lower() in {"image", "frame", "photo", "pixels", "jpeg", "png", "data", "dataurl", "blob"}:
            return True
    return False


def _read_json(handler: BaseHTTPRequestHandler, limit: int) -> dict:
    length = int(handler.headers.get("Content-Length") or 0)
    if length < 0 or length > limit:
        raise ValueError("request is too large")
    raw = handler.rfile.read(length) if length else b""
    if not raw:
        return {}
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("expected json") from None
    if not isinstance(value, dict):
        raise ValueError("expected an object")
    return value


def _float_or_none(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("lat and lon need to be numbers") from None
    if number != number or number in {float("inf"), float("-inf")}:
        raise ValueError("lat and lon need to be numbers")
    return number


def _store_photo(root: Path, data_url: str) -> str:
    raw = data_url.strip()
    if raw.startswith("data:"):
        raw = raw.split(",", 1)[-1]
    import base64
    try:
        blob = base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise ValueError("photo could not be read") from exc
    if len(blob) > 180_000:
        raise ValueError("photo is too large")
    if not (blob.startswith(b"\xff\xd8") or blob.startswith(b"\x89PNG")):
        raise ValueError("photo needs to be a jpeg or png")
    folder = root / "photos"
    folder.mkdir(parents=True, exist_ok=True)
    name = secrets.token_hex(8) + (".jpg" if blob.startswith(b"\xff\xd8") else ".png")
    (folder / name).write_bytes(blob)
    return name


class SparkyServer:
    def __init__(self, engine: SparkyEngine, host: str = "127.0.0.1", port: int = 8765):
        self.engine = engine
        self.httpd = ThreadingHTTPServer((host, port), SparkyHandler)
        self.httpd.engine = engine
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return int(self.httpd.server_address[1])

    def serve(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="sparky-life", daemon=True)
        self._thread.start()
        self.httpd.serve_forever()

    def start_background(self) -> None:
        self._thread = threading.Thread(target=self.httpd.serve_forever, name="sparky-http", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.engine.tick(force=False)
            except Exception:
                pass
            self._stop.wait(1.0)

    def close(self) -> None:
        self._stop.set()
        self.httpd.shutdown()
        self.httpd.server_close()


def main() -> None:
    import os
    home = default_home()
    engine = SparkyEngine(home)
    host = os.environ.get("SPARKY_HOST", "127.0.0.1")
    port = int(os.environ.get("SPARKY_PORT", "8765"))
    server = SparkyServer(engine, host, port)
    token_path = home / "owner_token.txt"
    print(f"Sparky is awake at http://{host}:{server.port}")
    print(f"Owner token file: {token_path}")
    print("No model configured." if not engine.brain.configured else "A model is configured.")
    try:
        server.serve()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        server.close()
        engine.close()
