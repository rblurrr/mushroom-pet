"""OpenAI-compatible brain with a quiet offline fallback.

The key is read from the environment, from the gitignored app-data file
``llm.env``, or from the gitignored ``config.json``. It is never written back
out, logged, or put in a prompt. When no model is configured, or the call
fails, callers get ``None`` and use their own local templates.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse


_SECRET_RE = re.compile(
    r"\bsk-[A-Za-z0-9_\-]{8,}\b|\b(?:api[_-]?key|token|secret|password)\s*[:=]\s*\S+",
    re.IGNORECASE,
)

Transport = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]


def redact(text: str, *secrets: str) -> str:
    """Hide configured secrets and obvious key material."""
    value = str(text or "")
    for secret in secrets:
        if secret and len(secret) >= 6:
            value = value.replace(secret, "[redacted]")
    return _SECRET_RE.sub("[redacted]", value)


@dataclass
class BrainConfig:
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    timeout: float = 12.0


class Brain:
    """One chat-completions client. ``transport`` is injectable for tests."""

    def __init__(self, config: BrainConfig | None = None, transport: Transport | None = None):
        self.config = config or BrainConfig()
        self._transport = transport or _http_transport
        self.last_error = ""

    @classmethod
    def offline(cls) -> "Brain":
        return cls(BrainConfig())

    @classmethod
    def from_env(cls, settings: dict | None = None, secrets_path: str | None = None,
                 transport: Transport | None = None) -> "Brain":
        """Environment wins, then ``llm.env``, then keys in the local config dict."""
        settings = settings or {}
        file_data = _read_env_file(secrets_path) if secrets_path else {}
        base = _pick(
            ("MUSHROOM_LLM_BASE_URL", "OPENAI_BASE_URL"),
            file_data, "MUSHROOM_LLM_BASE_URL", settings.get("llm_base_url"),
        )
        key = _pick(
            ("MUSHROOM_LLM_API_KEY", "OPENAI_API_KEY"),
            file_data, "MUSHROOM_LLM_API_KEY", settings.get("llm_api_key"),
        )
        model = _pick(
            ("MUSHROOM_LLM_MODEL", "OPENAI_MODEL"),
            file_data, "MUSHROOM_LLM_MODEL", settings.get("llm_model"),
        ) or "gpt-4o-mini"
        timeout = 12.0
        raw_timeout = os.environ.get("MUSHROOM_LLM_TIMEOUT") or settings.get("llm_timeout")
        if raw_timeout:
            try:
                timeout = max(2.0, min(60.0, float(raw_timeout)))
            except (TypeError, ValueError):
                timeout = 12.0
        return cls(BrainConfig(base_url=base, api_key=key, model=model, timeout=timeout), transport)

    @property
    def configured(self) -> bool:
        base = (self.config.base_url or "").strip()
        if not base or not (self.config.model or "").strip():
            return False
        host = (urlparse(base).hostname or "").lower()
        if host in {"localhost", "127.0.0.1", "::1"}:
            return True
        return bool(self.config.api_key)

    def describe(self) -> dict[str, Any]:
        """Safe to put in status, logs, and the dashboard. No key, no full URL."""
        host = ""
        if self.config.base_url:
            host = urlparse(self.config.base_url).hostname or ""
        return {
            "configured": self.configured,
            "mode": "model" if self.configured else "offline",
            "model": self.config.model if self.configured else "",
            "host": host,
            "last_error": self.last_error,
        }

    def redact(self, text: str) -> str:
        return redact(text, self.config.api_key)

    def think_json(self, system: str, user: str) -> tuple[dict[str, Any] | None, str]:
        """Ask for a JSON object. ``(None, "offline")`` means use a local template."""
        if not self.configured:
            self.last_error = ""
            return None, "offline"
        try:
            text = self._chat(system, user)
        except Exception:
            return None, "offline"
        parsed = _parse_json(text)
        if parsed is None:
            self.last_error = "bad json"
            return None, "offline"
        self.last_error = ""
        return parsed, "model"

    def _chat(self, system: str, user: str) -> str:
        url = _chat_url(self.config.base_url)
        headers = {"Content-Type": "application/json", "User-Agent": "MushroomPet/1.1"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        payload = {
            "model": self.config.model,
            "temperature": 0.7,
            "max_tokens": 900,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            body = self._transport(url, headers, payload, float(self.config.timeout))
        except urllib.error.HTTPError as exc:
            self.last_error = f"http {exc.code}"
            raise
        except (urllib.error.URLError, TimeoutError, OSError):
            self.last_error = "unreachable"
            raise
        except Exception:
            self.last_error = "error"
            raise
        return _message_text(body)


def _pick(env_keys: tuple[str, ...], file_data: dict[str, str], file_key: str, config_value: Any) -> str:
    for key in env_keys:
        value = os.environ.get(key)
        if value and value.strip():
            return value.strip()
    filed = file_data.get(file_key)
    if filed and filed.strip():
        return filed.strip()
    if config_value is None:
        return ""
    return str(config_value).strip()


def _read_env_file(path: str) -> dict[str, str]:
    data: dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return data
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        data[key.strip()] = value
    return data


def _chat_url(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def _parse_json(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            value = json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


def _message_text(body: dict[str, Any]) -> str:
    choices = body.get("choices") if isinstance(body, dict) else None
    if not choices:
        raise ValueError("empty completion")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get("text") or ""))
            else:
                parts.append(str(part))
        content = "".join(parts)
    if not isinstance(content, str) or not content.strip():
        raise ValueError("empty completion")
    return content


def _http_transport(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(1_000_000)
    parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("model response was not an object")
    return parsed
