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

# Milestone 2: broader secret detection (credential-shaped strings even without a keyword)
_SECRET_SHAPES = re.compile(
    r"\b(?:gsk_[A-Za-z0-9]{16,}|sk-[A-Za-z0-9_\-]{16,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|"
    r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,})\b")      # API keys, GitHub PAT, JWT
_AADHAAR = re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b")
_PAN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
_BEARER = re.compile(r"\bbearer\s+[A-Za-z0-9._\-]{12,}", re.IGNORECASE)
_NATIONAL_ID_WORDS = re.compile(r"\b(aadhaar|aadhar|pan card|passport number|ssn)\b", re.IGNORECASE)

SENSITIVE_PATTERNS = [_SENSITIVE_KEYWORD, _CARD_NUMBER, _SECRET_SHAPES, _AADHAAR, _PAN, _BEARER, _NATIONAL_ID_WORDS]
_VALUE_PATTERNS = [_CARD_NUMBER, _SECRET_SHAPES, _AADHAAR, _PAN, _BEARER]


def contains_sensitive(text: str) -> bool:
    """True if the text appears to contain a credential or payment secret."""
    return any(p.search(text or "") for p in SENSITIVE_PATTERNS)


def redact(text: str) -> str:
    """Replace credential values with a placeholder, keeping the surrounding sentence."""
    if not text:
        return text
    out = _KEYWORD_VALUE.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)
    for pat in _VALUE_PATTERNS:
        out = pat.sub(REDACTED, out)
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
