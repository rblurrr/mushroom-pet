"""Local control bridge so your own scripts can drive the pet.

Disabled by default. Turn it on from the menu (Control API -> Enable local API).

Two equivalent ways in, both loopback-only:

  1. HTTP   POST http://127.0.0.1:7477/say   {"text": "build finished"}
  2. Inbox  drop a .json file into the inbox folder in your config directory

Commands are queued and drained on the Qt thread, so nothing here touches widgets.
"""
from __future__ import annotations
import hmac
import json, os, queue, threading, time, glob
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import INBOX_DIR

MAX_BODY = 64 * 1024

ACTIONS = ("say", "notify", "do", "reminder_add", "reminder_list", "reminder_clear",
           "state", "config", "health")

DO_VERBS = ("react", "wave", "happy", "love", "sit", "sleep", "wake", "come", "jump",
            "hop", "climb", "getdown", "rampage", "fire_on", "fire_off",
            "hide", "show", "quit", "look")


class Bridge:
    """Thread-safe command inbox drained by the pet each tick."""

    def __init__(self):
        self.q: queue.Queue = queue.Queue(maxsize=256)
        self.state_provider = lambda: {}

    def submit(self, cmd: dict):
        try:
            self.q.put_nowait(cmd)
            return True
        except queue.Full:
            return False

    def drain(self, limit=16):
        out = []
        for _ in range(limit):
            try:
                out.append(self.q.get_nowait())
            except queue.Empty:
                break
        return out

    def state(self):
        try:
            return self.state_provider()
        except Exception as e:                      # pragma: no cover - defensive
            return {"error": str(e)}


def normalise(payload: dict, default_action=None) -> dict | None:
    """Accept a few shapes so callers can be sloppy."""
    if not isinstance(payload, dict):
        return None
    action = (payload.get("action") or default_action or "").strip().lower()
    if not action:
        if "text" in payload and "what" not in payload:
            action = "say"
        elif "what" in payload:
            action = "do"
    if action not in ACTIONS:
        return None
    cmd = {"action": action}
    if action == "say":
        cmd["text"] = str(payload.get("text", ""))[:600]
        cmd["seconds"] = float(payload.get("seconds", payload.get("duration", 8)) or 8)
        cmd["mood"] = str(payload.get("mood", "normal"))
        cmd["title"] = str(payload.get("title", ""))[:80]
    elif action == "notify":
        cmd["text"] = str(payload.get("text", payload.get("message", "")))[:600]
        cmd["title"] = str(payload.get("title", "Script"))[:80]
        cmd["urgent"] = bool(payload.get("urgent", False))
        cmd["seconds"] = payload.get("seconds")
    elif action == "do":
        what = str(payload.get("what", payload.get("verb", ""))).strip().lower()
        if what not in DO_VERBS:
            return None
        cmd["what"] = what
        cmd["arg"] = payload.get("arg")
    elif action == "reminder_add":
        cmd["text"] = str(payload.get("text", ""))[:300]
        cmd["in_minutes"] = payload.get("in_minutes")
        cmd["at"] = payload.get("at")
        cmd["repeat"] = str(payload.get("repeat", "once")).lower()
        cmd["urgent"] = bool(payload.get("urgent", False))
    return cmd


class _Handler(BaseHTTPRequestHandler):
    server_version = "MushroomPet/1.0"
    bridge: Bridge = None
    token: str = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *a):       # keep the console quiet
        pass

    # ---- helpers ----
    def _json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1")
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def _authed(self):
        if not self.token:
            return True
        supplied = self.headers.get("X-Token")
        if supplied is None:
            auth = self.headers.get("Authorization", "")
            scheme, separator, value = auth.partition(" ")
            supplied = value.strip() if separator and scheme.lower() == "bearer" else ""
        return hmac.compare_digest(str(supplied).strip(), self.token)

    def _read(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return {}
        if n <= 0 or n > MAX_BODY:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, OSError, UnicodeDecodeError):
            return {}

    # ---- routes ----
    def do_GET(self):
        route = (self.path.split("?")[0] or "/").rstrip("/") or "/"
        if route in ("/", "/health"):
            return self._json(200, {"ok": True, "app": "mushroom-pet", "ts": time.time()})
        if not self._authed():
            return self._json(401, {"ok": False, "error": "bad token"})
        if route == "/state":
            return self._json(200, {"ok": True, "state": self.bridge.state()})
        if route == "/reminders":
            self.bridge.submit({"action": "reminder_list"})
            return self._json(200, {"ok": True, "state": self.bridge.state()})
        return self._json(404, {"ok": False, "error": "unknown route"})

    def do_POST(self):
        if not self._authed():
            return self._json(401, {"ok": False, "error": "bad token"})
        route = (self.path.split("?")[0] or "/").strip("/").lower()
        payload = self._read()
        cmd = normalise(payload, default_action=route if route in ACTIONS else None)
        if cmd is None:
            return self._json(400, {"ok": False, "error": "bad command",
                                    "actions": list(ACTIONS), "verbs": list(DO_VERBS)})
        ok = self.bridge.submit(cmd)
        return self._json(200 if ok else 503, {"ok": ok})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Token, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()


class ApiServer:
    def __init__(self, bridge: Bridge, port: int, token: str):
        self.bridge = bridge
        self.port = port
        self.token = token
        self.httpd = None
        self.thread = None

    def start(self):
        handler = type("H", (_Handler,), {"bridge": self.bridge, "token": self.token})
        try:
            self.httpd = ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        except OSError:
            return False
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       kwargs={"poll_interval": 0.4}, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        if self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except OSError:
                pass
            self.httpd = None


class InboxWatcher:
    """Any .json dropped into the inbox folder is executed then deleted."""

    def __init__(self, bridge: Bridge):
        self.bridge = bridge
        os.makedirs(INBOX_DIR, exist_ok=True)
        self._last = 0.0

    def tick(self):
        now = time.time()
        if now - self._last < 0.8:
            return
        self._last = now
        for path in sorted(glob.glob(os.path.join(INBOX_DIR, "*.json")))[:12]:
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    payload = json.load(fh)
            except (OSError, ValueError):
                payload = None
            if isinstance(payload, list):
                for item in payload[:20]:
                    cmd = normalise(item)
                    if cmd:
                        self.bridge.submit(cmd)
            elif isinstance(payload, dict):
                cmd = normalise(payload)
                if cmd:
                    self.bridge.submit(cmd)
            try:
                os.remove(path)
            except OSError:
                pass
