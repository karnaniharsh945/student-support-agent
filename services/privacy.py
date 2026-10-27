"""Deterministic detection and redaction of sensitive text.

Used by: persistent memory policy, trace recording, and the text sent to the LLM.
These rules live in application code on purpose: the LLM never decides what is stored.
"""
from __future__ import annotations

import re

REDACTED = "[REDACTED]"

# keyword followed (optionally) by "is"/":"/"=" and a value
_KEYWORD_VALUE = re.compile(
    r"\b(otp|one[- ]?time[- ]?(?:password|code|pin)|password|passcode|passwd|pwd|pin|cvv|cvc|secret|"
    r"api[ _-]?key|access[ _-]?token|auth(?:entication)?[ _-]?token|token)\b"
    r"(\s*(?:is|are|was|:|=|-)?\s*)(\S+)",
    re.IGNORECASE,
)
_SENSITIVE_KEYWORD = re.compile(
    r"\b(otp|one[- ]?time[- ]?(?:password|code|pin)|password|passcode|passwd|pwd|pin|cvv|cvc|secret|"
    r"api[ _-]?key|access[ _-]?token|auth(?:entication)?[ _-]?token|token)\b",
    re.IGNORECASE,
)
_CARD_NUMBER = re.compile(r"\b(?:\d[ -]?){13,19}\b")

SENSITIVE_PATTERNS = [_SENSITIVE_KEYWORD, _CARD_NUMBER]


def contains_sensitive(text: str) -> bool:
    """True if the text appears to contain a credential or payment secret."""
    return any(p.search(text or "") for p in SENSITIVE_PATTERNS)


def redact(text: str) -> str:
    """Replace credential values with a placeholder, keeping the surrounding sentence."""
    if not text:
        return text
    out = _KEYWORD_VALUE.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)
    out = _CARD_NUMBER.sub(REDACTED, out)
    return out


_SENSITIVE_KEYS = re.compile(r"(password|otp|token|secret|api[_-]?key|pin|cvv)", re.IGNORECASE)


def redact_mapping(obj):
    """Recursively redact a dict/list structure (tool arguments, trace payloads)."""
    if isinstance(obj, dict):
        return {k: (REDACTED if _SENSITIVE_KEYS.search(str(k)) else redact_mapping(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_mapping(v) for v in obj]
    if isinstance(obj, str):
        return redact(obj)
    return obj
