"""Persistent long-term memory with a deterministic write policy.

* Memory is NON-authoritative: it is never used as proof of identity or permission.
* What may be stored is decided by regex rules in this module, not by the LLM.
* Only a small allow-list of non-sensitive keys can ever be stored.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import delete, select

from database.connection import Database
from database.models import MemoryItem
from services.privacy import contains_sensitive

ALLOWED_KEYS = {"programme", "preferred_language", "contact_preference", "preferred_name"}
MAX_VALUE_LEN = 120

_LANGS = r"(english|hindi|marathi|tamil|telugu|bengali|gujarati|kannada|malayalam|punjabi|urdu)"
_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("programme", re.compile(
        r"\bmy (?:programme|program|specialization|specialisation) is\s+(.+?)(?=\s+and\s+(?:i|please)\b|[.!?;]|$)", re.I)),
    ("programme", re.compile(
        r"\bi(?:'m| am) (?:enrolled in|studying|pursuing)\s+(?:the\s+)?(.+?)(?=\s+and\s+(?:i|please)\b|[.!?;]|$)", re.I)),
    ("preferred_language", re.compile(
        rf"\b(?:i prefer|please (?:reply|respond|answer|talk)(?: to me)? in|reply in|respond in)\s+{_LANGS}\b", re.I)),
    ("contact_preference", re.compile(
        r"\b(?:contact|reach|message|notify) me (?:via|by|on|through)\s+(email|e-mail|phone|sms|whatsapp)\b", re.I)),
    ("preferred_name", re.compile(r"\bcall me\s+([A-Za-z][A-Za-z'\-]{1,29})\b", re.I)),
]

_RELEVANCE_TERMS = {
    "programme": {"programme", "program", "specialization", "specialisation", "enrolled", "studying", "course", "degree"},
    "contact_preference": {"contact", "reach", "notify", "notification", "message", "email", "phone", "update"},
}
_ALWAYS_RELEVANT = {"preferred_language", "preferred_name"}   # style hints, tiny and harmless


@dataclass(frozen=True)
class MemoryCandidate:
    key: str
    value: str


@dataclass
class MemoryWriteResult:
    stored: list[str]
    blocked_reason: str = ""      # e.g. "sensitive_content"


def _naive_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class MemoryService:
    def __init__(self, db: Database, clock: Callable[[], datetime] = _naive_utc):
        self.db = db
        self.clock = clock

    # ---- write policy -------------------------------------------------------
    def extract_candidates(self, message: str) -> list[MemoryCandidate]:
        """Deterministically extract allow-listed facts from a user message."""
        found: dict[str, str] = {}
        for key, pat in _PATTERNS:
            m = pat.search(message or "")
            if m and key not in found:
                val = m.group(1).strip().strip("\"'")
                if key in ("preferred_language", "contact_preference"):
                    val = val.lower().replace("e-mail", "email")
                if 0 < len(val) <= MAX_VALUE_LEN:
                    found[key] = val
        return [MemoryCandidate(k, v) for k, v in found.items()]

    def remember_from_message(self, student_id: str, message: str, session_id: str = "") -> MemoryWriteResult:
        """Apply the write policy to a message; store only what passes."""
        if contains_sensitive(message):
            return MemoryWriteResult(stored=[], blocked_reason="sensitive_content")
        stored = []
        for cand in self.extract_candidates(message):
            if cand.key in ALLOWED_KEYS and not contains_sensitive(cand.value):
                self.upsert(student_id, cand.key, cand.value, session_id)
                stored.append(cand.key)
        return MemoryWriteResult(stored=stored)

    # ---- CRUD -----------------------------------------------------------------
    def upsert(self, student_id: str, key: str, value: str, session_id: str = "") -> MemoryItem:
        if key not in ALLOWED_KEYS:
            raise ValueError(f"memory key not allowed: {key}")
        if contains_sensitive(value):
            raise ValueError("sensitive value refused by memory policy")
        now = self.clock()
        with self.db.session() as s:
            item = s.scalar(select(MemoryItem).where(MemoryItem.student_id == student_id, MemoryItem.key == key))
            if item is None:
                item = MemoryItem(student_id=student_id, key=key, value=value, source_session=session_id,
                                  created_at=now, updated_at=now)
                s.add(item)
            else:
                item.value, item.updated_at, item.source_session = value, now, session_id
            s.flush()
            return item

    def list_items(self, student_id: str) -> list[MemoryItem]:
        with self.db.session() as s:
            return list(s.scalars(select(MemoryItem).where(MemoryItem.student_id == student_id)
                                  .order_by(MemoryItem.key)))

    def delete(self, student_id: str, key: str) -> bool:
        with self.db.session() as s:
            res = s.execute(delete(MemoryItem).where(MemoryItem.student_id == student_id, MemoryItem.key == key))
            return res.rowcount > 0

    # ---- retrieval for context selection -------------------------------------
    def get_relevant(self, student_id: str, query: str) -> list[MemoryItem]:
        """Return only memory items relevant to this query (not the whole memory)."""
        words = set(re.findall(r"[a-z]+", (query or "").lower()))
        out = []
        for item in self.list_items(student_id):
            if item.key in _ALWAYS_RELEVANT or words & _RELEVANCE_TERMS.get(item.key, set()):
                out.append(item)
        return out
