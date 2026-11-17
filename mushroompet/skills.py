"""Income skills for the autonomous pet.

A skill is a small object with ``id``, ``title``, ``blurb``, and ``run(ctx, args)``.
Register it on a :class:`SkillRegistry`. The HTTP API can only run ids that were
registered; it cannot import or execute code from a request.

Contract: ``run`` may write local files and may submit an external Creator Studio
action, which stops in the approval queue. ``run`` must not post, send a message,
open a checkout, or spend money. ``records_money`` is only for writing down money
that already arrived. The daily planner will schedule a skill when ``autonomous``
is true, and the only external skill it is allowed to schedule is ``propose_post``.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable


PLANNER_NOTE = (
    "You are the planning brain of a desktop pet that helps its owner earn money "
    "by drafting locally. Reply with ONLY a JSON object: "
    '{"focus":"one sentence","items":[{"skill":"id","title":"short","args":{}}]}. '
    "Prefer content_ideas, write_script, write_caption, draft_listing, "
    "track_opportunity, draft_post, and at most one propose_post as the last item. "
    "Never schedule purchases, messages, or earnings. Never ask for credentials."
)


@dataclass
class SkillContext:
    memory: Any
    creator: Any
    brain: Any
    niche: str
    goal: str
    context: str
    now: datetime
    redact: Callable[[str], str]


@dataclass
class SkillResult:
    speech: str
    summary: str
    title: str = "Working"
    bubble: str = "info"
    verb: str = "look"
    mood: str = "focused"
    energy: float = 8.0
    memory: str | None = None
    memory_kind: str = "note"
    importance: int = 5
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    approval_id: str | None = None
    source: str = "offline"


class SkillRegistry:
    def __init__(self):
        self._skills: dict[str, Any] = {}

    def register(self, skill: Any) -> None:
        skill_id = str(getattr(skill, "id", "") or "")
        if not skill_id.isidentifier() or skill_id.startswith("_"):
            raise ValueError("skill id must be a plain identifier")
        for flag in ("external", "autonomous", "records_money"):
            if not isinstance(getattr(skill, flag, False), bool):
                raise ValueError(f"{skill_id}.{flag} must be a bool")
        self._skills[skill_id] = skill

    def get(self, skill_id: str) -> Any:
        try:
            return self._skills[skill_id]
        except KeyError:
            raise KeyError(skill_id) from None

    def __contains__(self, skill_id: str) -> bool:
        return skill_id in self._skills

    def all(self) -> list[Any]:
        return list(self._skills.values())

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "id": skill.id,
                "title": skill.title,
                "blurb": skill.blurb,
                "external": skill.external,
                "autonomous": skill.autonomous,
                "records_money": skill.records_money,
            }
            for skill in self._skills.values()
        ]


def builtin_skills() -> SkillRegistry:
    registry = SkillRegistry()
    for skill in (
        ContentIdeas(), WriteScript(), WriteCaption(), DraftListing(),
        TrackOpportunity(), DraftPost(), ProposePost(), ProposeMessage(),
        ProposePurchase(), LogEarning(),
    ):
        registry.register(skill)
    return registry


# ----------------------------------------------------------------- helpers
def _clip(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").replace("\x00", "").split())
    return text[:limit].strip()


def _rng(ctx: SkillContext, salt: str) -> random.Random:
    return random.Random(f"{ctx.now.date().isoformat()}:{ctx.niche}:{salt}")


def _latest(ctx: SkillContext, kind: str) -> str:
    rows = ctx.memory.recent_memories(limit=1, kind=kind)
    return rows[0]["text"] if rows else ""


def _draft(ctx: SkillContext, kind: str, title: str, text: str) -> dict[str, Any]:
    action = ctx.creator.submit(kind, {"title": ctx.redact(title), "text": ctx.redact(text)})
    return action


def _from_model(data: dict | None, key: str) -> Any:
    if not isinstance(data, dict):
        return None
    return data.get(key)


# ------------------------------------------------------------------- skills
class ContentIdeas:
    id = "content_ideas"
    title = "Content ideas"
    blurb = "Three local angles for a thing people might pay for. Nothing is posted."
    external = False
    autonomous = True
    records_money = False
    energy = 10
    verb = "look"

    def run(self, ctx: SkillContext, args: dict) -> SkillResult:
        data, source = ctx.brain.think_json(
            "Reply with ONLY JSON {\"ideas\":[{\"title\",\"format\",\"hook\",\"angle\",\"earn\"}]} "
            "of exactly 3 ideas. Drafts only. No prices to charge automatically.",
            ctx.context + "\n\nGive me three content ideas.",
        )
        ideas = _clean_ideas(data)
        if not ideas:
            ideas = _offline_ideas(ctx)
            source = "offline"
        lines = [f"# Ideas — {ctx.niche}", "", f"Source: {source}", ""]
        for index, idea in enumerate(ideas, 1):
            lines += [
                f"## {index}. {idea['title']}",
                f"- Format: {idea['format']}",
                f"- Hook: {idea['hook']}",
                f"- Angle: {idea['angle']}",
                f"- How it could earn: {idea['earn']}",
                "",
            ]
        lines.append("Drafts only. Nothing has been posted.")
        text = "\n".join(lines)
        action = _draft(ctx, "draft_ideas", f"Ideas: {ctx.niche}"[:160], text)
        memory = " | ".join(idea["title"] for idea in ideas)
        speech = f"Idea: {_clip(ideas[0]['title'], 140)}. It's in today's folder. Nothing posted."
        return SkillResult(
            speech=speech, summary=speech, title="Ideas", bubble="info", verb=self.verb,
            mood="curious", energy=self.energy, memory=memory, memory_kind="idea",
            source=source, artifacts=_artifacts(action),
        )


class WriteScript:
    id = "write_script"
    title = "Short script"
    blurb = "A 20-second script from the latest idea. Saved locally."
    external = False
    autonomous = True
    records_money = False
    energy = 14
    verb = "look"

    def run(self, ctx: SkillContext, args: dict) -> SkillResult:
        seed = _clip(args.get("seed"), 500) or _latest(ctx, "idea") or ctx.niche
        data, source = ctx.brain.think_json(
            "Reply with ONLY JSON {\"title\",\"hook\",\"beats\":[3 strings],\"cta\",\"on_screen\",\"caption\"}. "
            "A 20 second short. The CTA must say the post is not published yet.",
            ctx.context + "\n\nWrite a short script from:\n" + ctx.redact(seed)[:500],
        )
        script = _clean_script(data)
        if script is None:
            script = _offline_script(ctx, seed)
            source = "offline"
        beats = "\n".join(f"{i}. {beat}" for i, beat in enumerate(script["beats"], 1))
        text = (
            f"# {script['title']}\n\nSource: {source}\n\n"
            f"**Hook:** {script['hook']}\n\n{beats}\n\n"
            f"**On screen:** {script['on_screen']}\n\n**CTA:** {script['cta']}\n\n"
            f"**Caption seed:** {script['caption']}\n\nNot published.\n"
        )
        action = _draft(ctx, "draft_script", script["title"], text)
        memory = json_line(script)
        speech = f"Script drafted: {_clip(script['title'], 120)}. About 20 seconds. Not posted."
        return SkillResult(
            speech=speech, summary=speech, title="Script", bubble="normal", verb=self.verb,
            mood="focused", energy=self.energy, memory=memory, memory_kind="script",
            source=source, artifacts=_artifacts(action),
        )


class WriteCaption:
    id = "write_caption"
    title = "Captions"
    blurb = "Three caption variants for the latest script. Saved locally."
    external = False
    autonomous = True
    records_money = False
    energy = 8
    verb = "look"

    def run(self, ctx: SkillContext, args: dict) -> SkillResult:
        seed = _clip(args.get("seed"), 500) or _latest(ctx, "script") or _latest(ctx, "idea") or ctx.niche
        data, source = ctx.brain.think_json(
            "Reply with ONLY JSON {\"variants\":[\"caption\",\"caption\",\"caption\"]}. "
            "No hashtag spam. Do not claim the post is already live.",
            ctx.context + "\n\nWrite three captions for:\n" + ctx.redact(seed)[:500],
        )
        variants = _clean_variants(data)
        if not variants:
            variants = _offline_captions(ctx, seed)
            source = "offline"
        body = "\n\n".join(f"{i}. {line}" for i, line in enumerate(variants, 1))
        text = f"# Captions\n\nSource: {source}\n\n{body}\n\nNot published.\n"
        # A caption pack is a local draft. The chosen line is what a later post uses.
        action = _draft(ctx, "draft_caption", "Captions", text)
        speech = f"Caption: {_clip(variants[0], 150)}"
        return SkillResult(
            speech=speech, summary=speech, title="Caption", bubble="info", verb=self.verb,
            mood="focused", energy=self.energy, memory=variants[0], memory_kind="caption",
            source=source, artifacts=_artifacts(action),
        )


class DraftListing:
    id = "draft_listing"
    title = "Product listing"
    blurb = "A listing draft with a suggested price band. Does not put anything on sale."
    external = False
    autonomous = True
    records_money = False
    energy = 12
    verb = "look"

    def run(self, ctx: SkillContext, args: dict) -> SkillResult:
        data, source = ctx.brain.think_json(
            "Reply with ONLY JSON {\"title\",\"tagline\",\"for_whom\",\"bullets\":[3 strings],"
            "\"price_band\",\"faq\"}. price_band is a suggestion like $7-$19, not a charge.",
            ctx.context + "\n\nDraft a tiny digital product listing.",
        )
        listing = _clean_listing(data)
        if listing is None:
            listing = _offline_listing(ctx)
            source = "offline"
        bullets = "\n".join(f"- {item}" for item in listing["bullets"])
        text = (
            f"# {listing['title']}\n\n{listing['tagline']}\n\n"
            f"For: {listing['for_whom']}\n\n{bullets}\n\n"
            f"**Suggested price (not a charge):** {listing['price_band']}\n\n"
            f"{listing['faq']}\n\nSource: {source}. This is not listed for sale.\n"
        )
        action = _draft(ctx, "draft_listing", listing["title"], text)
        speech = (
            f"Listing drafted: {_clip(listing['title'], 80)} "
            f"({listing['price_band']}). Not for sale until you list it."
        )
        return SkillResult(
            speech=speech, summary=speech, title="Listing", bubble="info", verb=self.verb,
            mood="focused", energy=self.energy, memory=f"{listing['title']} — {listing['price_band']}",
            memory_kind="listing", source=source, artifacts=_artifacts(action),
        )


class TrackOpportunity:
    id = "track_opportunity"
    title = "Track an opportunity"
    blurb = "Write down a way this could earn. The guess is not money received."
    external = False
    autonomous = True
    records_money = False
    energy = 6
    verb = "look"

    def run(self, ctx: SkillContext, args: dict) -> SkillResult:
        title = _clip(args.get("title"), 200)
        data = None
        source = "offline"
        if not title:
            data, source = ctx.brain.think_json(
                "Reply with ONLY JSON {\"title\",\"kind\",\"notes\",\"guess_low\",\"guess_high\"}. "
                "kind is one of product, content, service. Guesses are dollars, not a sale.",
                ctx.context + "\n\nName one concrete way this work could earn.",
            )
        opp = _clean_opportunity(data) if data else None
        if title and opp is None:
            opp = {
                "title": title,
                "kind": _clip(args.get("kind"), 40) or "idea",
                "notes": _clip(args.get("notes"), 500) or "Noted by hand.",
                "guess_low": _money(args.get("guess_low"), 0),
                "guess_high": _money(args.get("guess_high"), 0),
            }
            source = "offline"
        if opp is None:
            opp = _offline_opportunity(ctx)
            source = "offline"
        if opp["guess_high"] < opp["guess_low"]:
            opp["guess_high"] = opp["guess_low"]
        opp["title"] = ctx.redact(opp["title"])
        opp["notes"] = ctx.redact(opp["notes"])
        saved = ctx.memory.add_opportunity(
            opp["title"], opp["kind"], opp["notes"], opp["guess_low"], opp["guess_high"])
        ctx.creator.ledger.append("opportunity", {"id": saved["id"], "title": saved["title"]})
        speech = (
            f"Spotted: {_clip(opp['title'], 100)}. "
            f"A guess of ${opp['guess_low']:.0f}–${opp['guess_high']:.0f}, not money in the bank."
        )
        return SkillResult(
            speech=speech, summary=speech, title="Opportunity", bubble="info", verb=self.verb,
            mood="curious", energy=self.energy,
            memory=f"{opp['title']} ({opp['kind']})", memory_kind="opportunity",
            source=source,
        )


class DraftPost:
    id = "draft_post"
    title = "Post draft"
    blurb = "Save a short-form post locally. Does not publish it."
    external = False
    autonomous = True
    records_money = False
    energy = 8
    verb = "wave"

    def run(self, ctx: SkillContext, args: dict) -> SkillResult:
        platform = _platform(args.get("platform"))
        text = _clip(args.get("text"), 1000) or _latest(ctx, "caption") or _caption_from_script(ctx) or (
            f"A small useful thing about {ctx.niche}. Still a draft."
        )
        text = ctx.redact(text)[:1000]
        action = ctx.creator.submit("draft_social", {"platform": platform, "text": text})
        speech = f"Post draft saved for {platform}. I will not publish it."
        return SkillResult(
            speech=speech, summary=speech, title="Draft", bubble="happy", verb=self.verb,
            mood="focused", energy=self.energy, memory=text, memory_kind="post",
            source="offline", artifacts=_artifacts(action),
        )


class ProposePost:
    id = "propose_post"
    title = "Ask to publish"
    blurb = "Put a post in the approval queue. Does not publish it."
    external = True
    autonomous = True
    records_money = False
    energy = 4
    verb = "wave"

    def run(self, ctx: SkillContext, args: dict) -> SkillResult:
        platform = _platform(args.get("platform"))
        text = _clip(args.get("text"), 1000) or _latest(ctx, "post") or _latest(ctx, "caption")
        text = ctx.redact(text)
        if not text:
            text = f"Draft about {ctx.redact(ctx.niche)[:80]}."
        action = ctx.creator.submit("publish_social", {"platform": platform, "text": text[:4000]})
        speech = "I put a post in your approval queue. I will not publish it."
        return SkillResult(
            speech=speech, summary=speech, title="Approval", bubble="happy", verb=self.verb,
            mood="hopeful", energy=self.energy, memory=f"Queued post {action['id']} for approval",
            memory_kind="note", importance=6, source="offline", approval_id=action["id"],
        )


class ProposeMessage:
    id = "propose_message"
    title = "Ask to send a message"
    blurb = "Queue an email or DM for approval. Does not send it."
    external = True
    autonomous = False
    records_money = False
    energy = 4
    verb = "look"

    def run(self, ctx: SkillContext, args: dict) -> SkillResult:
        channel = _clip(args.get("channel"), 40).lower() or "other"
        if channel not in {"email", "dm", "sms", "other"}:
            channel = "other"
        recipient = _clip(args.get("recipient"), 200)
        text = ctx.redact(_clip(args.get("text"), 4000))
        if not recipient or not text:
            raise ValueError("a message needs a recipient and text")
        action = ctx.creator.submit("send_message", {
            "channel": channel, "recipient": recipient, "text": text,
        })
        speech = f"Message to {_clip(recipient, 60)} is waiting for approval. I did not send it."
        return SkillResult(
            speech=speech, summary=speech, title="Approval", bubble="info", verb=self.verb,
            mood="hopeful", energy=self.energy, approval_id=action["id"], source="offline",
        )


class ProposePurchase:
    id = "propose_purchase"
    title = "Ask to buy"
    blurb = "Queue a purchase for approval. Does not spend money."
    external = True
    autonomous = False
    records_money = False
    energy = 4
    verb = "look"

    def run(self, ctx: SkillContext, args: dict) -> SkillResult:
        action = ctx.creator.submit("purchase", {
            "item": args.get("item"),
            "vendor": args.get("vendor"),
            "url": args.get("url"),
            "price": args.get("price"),
            "reason": args.get("reason") or "Queued by the pet for approval",
        })
        price = action["payload"]["price"]
        speech = f"Purchase request for ${price:.2f} is in the queue. I will not buy it."
        return SkillResult(
            speech=speech, summary=speech, title="Approval", bubble="info", verb=self.verb,
            mood="hopeful", energy=self.energy, approval_id=action["id"], source="offline",
        )


class LogEarning:
    id = "log_earning"
    title = "Log money in"
    blurb = "Record money that already arrived. Never invents income and never spends."
    external = False
    autonomous = False
    records_money = True
    energy = 2
    verb = "happy"

    def run(self, ctx: SkillContext, args: dict) -> SkillResult:
        source = _clip(args.get("source"), 200)
        if not source:
            raise ValueError("earning source cannot be empty")
        amount = float(args.get("amount", 0) or 0)
        if amount <= 0 or amount > 1_000_000:
            raise ValueError("earning amount must be between 0 and 1000000")
        cents = int(round(amount * 100))
        note = _clip(args.get("note"), 500)
        currency = _clip(args.get("currency"), 8).upper() or "USD"
        saved = ctx.memory.add_earning(source, cents, currency, note)
        speech = f"Logged {saved['amount']:.2f} {saved['currency']} from {_clip(source, 60)}. That's money in, not a purchase."
        return SkillResult(
            speech=speech, summary=speech, title="Ledger", bubble="happy", verb="happy",
            mood="proud", energy=self.energy, source="offline",
        )


# ----------------------------------------------------------------- offline
def _niche(ctx: SkillContext) -> str:
    return _clip(ctx.niche, 80) or "this project"


def _offline_ideas(ctx: SkillContext) -> list[dict[str, str]]:
    niche = _niche(ctx)
    goal = _clip(ctx.goal, 140) or "make something small people pay for"
    angles = [
        ("The mistake that stalls " + niche,
         "a 20-second vertical video",
         "Open on the mistake, then the two-step fix. No intro.",
         "Saves and follows, then a small paid template."),
        ("I made one useful thing for " + niche,
         "a screen recording with one sentence on screen",
         "Before, the making, the result. Hold the result still.",
         "The thing itself can be a $7–$19 download."),
        ("What I would charge for " + niche,
         "a 5-frame carousel",
         "Three price bands and one thing you refuse to sell.",
         "Trust first, then a single clear offer."),
    ]
    rng = _rng(ctx, "ideas")
    rng.shuffle(angles)
    ideas = []
    for title, fmt, hook, earn in angles:
        ideas.append({
            "title": title,
            "format": fmt,
            "hook": hook,
            "angle": f"In service of: {goal}",
            "earn": earn,
        })
    return ideas


def _offline_script(ctx: SkillContext, seed: str) -> dict[str, Any]:
    niche = _niche(ctx)
    title = _clip(seed.split("|")[0], 100) or f"A useful minute on {niche}"
    return {
        "title": title,
        "hook": f"Stop if you care about {niche}.",
        "beats": [
            "Name the problem in one sentence.",
            "Do the fix on screen. No throat-clearing.",
            "Hold the result so someone can screenshot it.",
        ],
        "cta": "The template is in the caption. This is not posted until you approve it.",
        "on_screen": niche[:40],
        "caption": f"{title}. A small useful thing for {niche}.",
    }


def _offline_captions(ctx: SkillContext, seed: str) -> list[str]:
    niche = _niche(ctx)
    title = _clip(seed.split("\n")[0], 90) or niche
    return [
        f"{title}. Made it small on purpose.",
        f"The useful version of {niche}, in one sitting. Draft, not posted.",
        f"If this saved you the blank page, the template is the next thing I make.",
    ]


def _offline_listing(ctx: SkillContext) -> dict[str, Any]:
    niche = _niche(ctx)
    return {
        "title": f"{niche} starter kit"[:120],
        "tagline": "One small download that saves the blank-page hour.",
        "for_whom": f"Someone already trying to earn from {niche}.",
        "bullets": [
            "A one-page template you can fill in today.",
            "The 20-second script that goes with it.",
            "A price band so you are not guessing in public.",
        ],
        "price_band": "$7–$19",
        "faq": "This is a draft. Nothing is for sale until you list it yourself.",
    }


def _offline_opportunity(ctx: SkillContext) -> dict[str, Any]:
    niche = _niche(ctx)
    return {
        "title": f"{niche} starter kit",
        "kind": "product",
        "notes": "Digital good. The dollar range is a guess, not money received.",
        "guess_low": 7.0,
        "guess_high": 19.0,
    }


def _clean_ideas(data: dict | None) -> list[dict[str, str]] | None:
    raw = _from_model(data, "ideas")
    if not isinstance(raw, list):
        return None
    ideas = []
    for item in raw[:5]:
        if not isinstance(item, dict):
            continue
        title = _clip(item.get("title"), 140)
        if not title:
            continue
        ideas.append({
            "title": title,
            "format": _clip(item.get("format"), 80) or "short post",
            "hook": _clip(item.get("hook"), 240) or title,
            "angle": _clip(item.get("angle"), 240) or "",
            "earn": _clip(item.get("earn"), 240) or "A small paid follow-up.",
        })
    return ideas or None


def _clean_script(data: dict | None) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    title = _clip(data.get("title"), 140)
    beats_raw = data.get("beats")
    if not title or not isinstance(beats_raw, list):
        return None
    beats = [_clip(beat, 200) for beat in beats_raw if _clip(beat, 200)]
    if not beats:
        return None
    return {
        "title": title,
        "hook": _clip(data.get("hook"), 200) or title,
        "beats": beats[:4],
        "cta": _clip(data.get("cta"), 240) or "Not posted until you approve it.",
        "on_screen": _clip(data.get("on_screen"), 80) or title[:40],
        "caption": _clip(data.get("caption"), 300) or title,
    }


def _clean_variants(data: dict | None) -> list[str] | None:
    raw = _from_model(data, "variants")
    if not isinstance(raw, list):
        return None
    variants = [_clip(item, 300) for item in raw if _clip(item, 300)]
    return variants[:4] or None


def _clean_listing(data: dict | None) -> dict[str, Any] | None:
    if not isinstance(data, dict) or not _clip(data.get("title"), 120):
        return None
    bullets_raw = data.get("bullets")
    bullets = []
    if isinstance(bullets_raw, list):
        bullets = [_clip(item, 160) for item in bullets_raw if _clip(item, 160)]
    if not bullets:
        return None
    return {
        "title": _clip(data.get("title"), 120),
        "tagline": _clip(data.get("tagline"), 160) or "A small download.",
        "for_whom": _clip(data.get("for_whom"), 160) or "The person already doing the work.",
        "bullets": bullets[:5],
        "price_band": _clip(data.get("price_band"), 40) or "$7–$19",
        "faq": _clip(data.get("faq"), 300) or "Draft only. Not listed for sale.",
    }


def _clean_opportunity(data: dict | None) -> dict[str, Any] | None:
    if not isinstance(data, dict) or not _clip(data.get("title"), 200):
        return None
    kind = _clip(data.get("kind"), 40).lower() or "product"
    if kind not in {"product", "content", "service", "idea"}:
        kind = "idea"
    return {
        "title": _clip(data.get("title"), 200),
        "kind": kind,
        "notes": _clip(data.get("notes"), 500) or "Model suggestion. Guess only.",
        "guess_low": _money(data.get("guess_low"), 0),
        "guess_high": _money(data.get("guess_high"), 0),
    }


def _money(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number < 0 or number > 1_000_000:
        return default
    return round(number, 2)


def _platform(value: Any) -> str:
    platform = _clip(value, 40).lower() or "general"
    if platform not in {"general", "x", "instagram", "tiktok", "facebook", "linkedin"}:
        return "general"
    return platform


def _caption_from_script(ctx: SkillContext) -> str:
    raw = _latest(ctx, "script")
    if not raw:
        return ""
    try:
        import json
        data = json.loads(raw)
    except (ValueError, TypeError):
        return ""
    if isinstance(data, dict):
        return _clip(data.get("caption"), 300)
    return ""


def json_line(script: dict) -> str:
    import json
    return json.dumps(script, ensure_ascii=False)


def _artifacts(action: dict) -> list[dict[str, Any]]:
    result = action.get("result") or {}
    path = result.get("path")
    if not path:
        return []
    return [{"path": path}]
