"""Narration script loader (data/narration.md) - the single source of the spoken project tour."""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

NARRATION_PATH = Path(__file__).resolve().parent.parent / "data" / "narration.md"


@dataclass(frozen=True)
class Section:
    title: str
    text: str


@lru_cache(maxsize=4)
def load_sections(path: str = str(NARRATION_PATH)) -> tuple[Section, ...]:
    """Parse `## Title` sections; HTML comments and the `# H1` heading are not spoken."""
    raw = re.sub(r"<!--.*?-->", "", Path(path).read_text(encoding="utf-8"), flags=re.S)
    sections = []
    for m in re.finditer(r"^##\s+(.+?)\n(.*?)(?=^##\s|\Z)", raw, re.S | re.M):
        text = re.sub(r"\s+", " ", m.group(2)).strip()
        if text:
            sections.append(Section(m.group(1).strip(), text))
    return tuple(sections)


def full_script(path: str = str(NARRATION_PATH)) -> str:
    """Whole tour as plain speakable text (section titles are spoken as short lead-ins)."""
    return " ".join(f"{s.title}. {s.text}" for s in load_sections(path))


def word_count(path: str = str(NARRATION_PATH)) -> int:
    return len(full_script(path).split())
