#!/usr/bin/env python
"""Command-line Creator Studio for Mushroom Pet."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mushroompet.config import APP_DIR  # noqa: E402
from mushroompet.creator import CreatorEngine  # noqa: E402


def _print(value):
    print(json.dumps(value, indent=2, ensure_ascii=False))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Mushroom Pet safe creator and approval queue")
    p.add_argument("--root", default=os.path.join(APP_DIR, "creator"))
    p.add_argument("--offline", action="store_true",
                   help="use local templates instead of a configured model")
    sub = p.add_subparsers(dest="command", required=True)

    for command in ("hub", "game"):
        q = sub.add_parser(command)
        q.add_argument("title")
        q.add_argument("--brief", default="A Mushroom Pet creation.")

    q = sub.add_parser("post-draft")
    q.add_argument("text")
    q.add_argument("--platform", default="general")
    q = sub.add_parser("post-request")
    q.add_argument("text")
    q.add_argument("--platform", default="general")
    q = sub.add_parser("github-request")
    q.add_argument("project_path")
    q.add_argument("repository_name")
    q.add_argument("--visibility", choices=("private", "public"), default="private")
    q = sub.add_parser("purchase-request")
    q.add_argument("item"); q.add_argument("vendor"); q.add_argument("url")
    q.add_argument("price", type=float); q.add_argument("--reason", default="Owner-requested item")
    q = sub.add_parser("message-request")
    q.add_argument("channel", choices=("email", "dm", "sms", "other"))
    q.add_argument("recipient")
    q.add_argument("text")

    q = sub.add_parser("approve"); q.add_argument("id"); q.add_argument("--note", default="Approved")
    q = sub.add_parser("reject"); q.add_argument("id"); q.add_argument("note")
    q = sub.add_parser("list"); q.add_argument("--status")
    q = sub.add_parser("remember"); q.add_argument("text"); q.add_argument("--importance", type=int, default=5)
    q = sub.add_parser("goal"); q.add_argument("text")
    sub.add_parser("mind")
    sub.add_parser("verify")
    sub.add_parser("pause")
    sub.add_parser("resume")

    sub.add_parser("status")
    sub.add_parser("tick")
    sub.add_parser("plan")
    q = sub.add_parser("log"); q.add_argument("--limit", type=int, default=20)
    q = sub.add_parser("focus"); q.add_argument("niche"); q.add_argument("goal")
    q = sub.add_parser("skill"); q.add_argument("name"); q.add_argument("--args", default="{}")
    q = sub.add_parser("earn")
    q.add_argument("source"); q.add_argument("amount", type=float); q.add_argument("--note", default="")
    sub.add_parser("life-on")
    sub.add_parser("life-off")
    sub.add_parser("dashboard")

    a = p.parse_args(argv)
    engine = CreatorEngine(a.root)
    if a.command == "hub":
        out = engine.submit("create_hub", {"title": a.title, "brief": a.brief})
    elif a.command == "game":
        out = engine.submit("create_game", {"title": a.title, "brief": a.brief})
    elif a.command == "post-draft":
        out = engine.submit("draft_social", {"platform": a.platform, "text": a.text})
    elif a.command == "post-request":
        out = engine.submit("publish_social", {"platform": a.platform, "text": a.text})
    elif a.command == "github-request":
        out = engine.submit("publish_github", vars(a))
    elif a.command == "purchase-request":
        out = engine.submit("purchase", vars(a))
    elif a.command == "message-request":
        out = engine.submit("send_message", {
            "channel": a.channel, "recipient": a.recipient, "text": a.text})
    elif a.command == "approve":
        out = engine.approve(a.id, a.note)
    elif a.command == "reject":
        out = engine.reject(a.id, a.note)
    elif a.command == "list":
        out = engine.list_actions(a.status)
    elif a.command == "remember":
        out = engine.mind.remember(a.text, a.importance)
    elif a.command == "goal":
        out = engine.mind.add_goal(a.text)
    elif a.command == "mind":
        out = engine.mind.state
    elif a.command == "verify":
        ok, count = engine.ledger.verify(); out = {"ok": ok, "events": count}
    elif a.command in {"pause", "resume"}:
        engine.set_paused(a.command == "pause"); out = {"paused": engine.paused}
    elif a.command in {"status", "tick", "plan", "log", "focus", "skill", "earn",
                       "life-on", "life-off", "dashboard"}:
        out = _life_command(engine, a)
    else:
        p.error("unknown command"); return 2
    _print(out)
    return 0


def _life_command(engine, args):
    from mushroompet.brain import Brain
    from mushroompet.life import Life
    secrets_path = os.path.join(os.path.dirname(os.path.abspath(args.root)), "llm.env")
    brain = Brain.offline() if args.offline else Brain.from_env({}, secrets_path)
    life = Life(engine.root, engine, brain=brain)
    try:
        if args.command == "status":
            return life.status()
        if args.command == "tick":
            return {"moment": life.tick(force=True), "life": life.status()}
        if args.command == "plan":
            return life.status()["plan"]
        if args.command == "log":
            return life.memory.recent_activity(args.limit)
        if args.command == "focus":
            return life.set_focus(args.niche, args.goal)
        if args.command == "skill":
            try:
                skill_args = json.loads(args.args or "{}")
            except json.JSONDecodeError as exc:
                raise SystemExit(f"args must be a JSON object ({exc})") from exc
            if not isinstance(skill_args, dict):
                raise SystemExit("args must be a JSON object")
            return life.run_skill(args.name, skill_args)
        if args.command == "earn":
            return life.record_earning(args.source, args.amount, args.note)
        if args.command == "life-on":
            life.set_enabled(True)
            return {"enabled": True}
        if args.command == "life-off":
            life.set_enabled(False)
            return {"enabled": False}
        if args.command == "dashboard":
            return {"path": str(life.write_dashboard())}
        raise SystemExit("unknown life command")
    finally:
        life.close()


if __name__ == "__main__":
    raise SystemExit(main())
