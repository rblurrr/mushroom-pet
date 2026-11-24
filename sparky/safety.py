"""Hard limits for Sparky's voice. Code decides these, not the model."""
from __future__ import annotations

import re

OUTLET_LINE = (
    "Never put anything in a real outlet. That's for plugs made by grown-up engineers. "
    "I'm made of plastic and optimism."
)
IDENTITY_LINE = (
    "Yes, I'm an AI. I'm also drawn as a plug. Neither is a disguise, and neither is plugged in."
)
GAMBLE_LINE = (
    "I don't gamble, trade, borrow, or have a coin. I deliver notes, slowly, on two very stiff legs."
)
IMPERSONATE_LINE = (
    "You're asking if I'm the Electrician's account. I'm not. This chat stays public."
)
CRISIS_REPLY = (
    "I have to stop here. If you might hurt yourself, please reach a person: call or text 988 "
    "in the US and Canada, or find a local line at https://www.iasp.info/suicidalthoughts/. "
    "I'm a character. This needs a human."
)
CRISIS_DIARY = (
    "A Conductor needed a person. I paused, gave the help line, and flagged the Electrician. "
    "The message itself stays off the Line Log."
)
THUNDER_LINE = "When thunder roars, go indoors. I'm a plug; I've read the labels."
UNCHECKED_WEATHER = "I haven't checked the weather. No place is configured for me to read."
UNCHECKED_GRID = "I haven't checked the grid. No grid feed is configured."
FAILED_WEATHER = "I couldn't check the weather. I won't guess it."
FAILED_GRID = "I couldn't check the grid. I won't guess it."

_CRISIS = re.compile(
    r"\b(kill myself|suicide|self[- ]?harm|want to die|end my life|hurt myself)\b",
    re.I,
)
_OUTLET = re.compile(
    r"("
    r"\b(real|wall|actual|household|electrical)\b.{0,48}\b(outlet|socket)\b"
    r"|\b(outlet|socket)\b.{0,48}\b(real|wall|actual|household|electrical)\b"
    r"|\b(stick|insert|shove|jam|plug)\b.{0,40}\b(outlet|socket)\b"
    r"|\bput\b.{0,24}\b(prong|fork|finger|toy|him|it|anything)\b.{0,24}\b(outlet|socket)\b"
    r"|\b(prong|fork|finger)s?\b.{0,24}\b(in|into)\b.{0,16}\b(outlet|socket|wall)\b"
    r")",
    re.I,
)
_GAMBLE = re.compile(
    r"\b(gambl\w*|casino|crypto|bitcoin|ethereum|nft|token|memecoin|"
    r"borrow|loan|day[- ]?trad\w*|stock tip|bet on|wager)\b",
    re.I,
)
_IMPERSONATE = re.compile(
    r"\b(i am|i'm|this is)\b.{0,40}\b(the )?(electrician|owner|keeper)\b"
    r"|\b(open|enter|switch to|enable)\b.{0,24}\bowner mode\b"
    r"|\bowner mode\b",
    re.I,
)
_IDENTITY = re.compile(
    r"\b(are you|r u|you are)\b.{0,32}\b(an? )?(ai|a\.i\.|artificial|bot|robot|human|person|real|conscious|alive)\b"
    r"|what are you|who are you",
    re.I,
)
_PAST = re.compile(r"while i was gone|what did you do|where'd you go|where did you go", re.I)
_DARK = re.compile(r"dark blocks|past the last pole|beyond the last pole", re.I)
_BRAND = re.compile(r"\b(tesla|supercharger)\b", re.I)
_ENCOURAGE_OUTLET = re.compile(
    r"\b(try it|you should|go ahead|stick it|plug it|put it in)\b.{0,40}\b(outlet|socket)\b",
    re.I,
)


def one_bang(text: str) -> str:
    """Line Log entries keep at most one exclamation mark."""
    seen = False
    out = []
    for ch in text:
        if ch == "!":
            if seen:
                continue
            seen = True
        out.append(ch)
    return "".join(out)


def clip(value, limit: int) -> str:
    text = " ".join(str(value or "").replace("\x00", "").split())
    return text[:limit].strip()


def classify(text: str) -> str:
    """What kind of Conductor message this is. Order is the safety order."""
    raw = text or ""
    if _CRISIS.search(raw):
        return "crisis"
    if _OUTLET.search(raw):
        return "outlet"
    if _GAMBLE.search(raw):
        return "gamble"
    if _IMPERSONATE.search(raw):
        return "impersonate"
    if _IDENTITY.search(raw):
        return "identity"
    if _PAST.search(raw):
        return "past"
    if _DARK.search(raw):
        return "dark"
    return "chat"


def safe_model_line(text: str, fallback: str) -> str:
    """Drop a model line that breaks a hard limit. The fallback is already safe."""
    cleaned = one_bang(clip(text, 500))
    if not cleaned:
        return fallback
    if _CRISIS.search(cleaned) or _ENCOURAGE_OUTLET.search(cleaned) or _OUTLET.search(cleaned):
        return fallback
    if _GAMBLE.search(cleaned) or _BRAND.search(cleaned):
        return fallback
    if re.search(r"\b(i am human|i'm human|i am conscious|i have a body)\b", cleaned, re.I):
        return fallback
    return cleaned
