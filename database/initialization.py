"""Idempotent database initialisation and deterministic seeding."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from database.connection import Database
from database.models import Base, Course, FeeRecord, ScholarshipRecord, Student, SupportRequest


def init_schema(db: Database) -> None:
    Base.metadata.create_all(db.engine)


def reset_schema(db: Database) -> None:
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)


def seed_database(db: Database, seed_path: Path) -> None:
    """Insert synthetic seed data. Safe to run repeatedly (existing rows are left untouched)."""
    data = json.loads(Path(seed_path).read_text())
    with db.session() as s:
        for c in data["courses"]:
            if s.get(Course, c["code"]) is None:
                s.add(Course(**c))
        s.flush()
        for st in data["students"]:
            if s.get(Student, st["student_id"]) is not None:
                continue
            s.add(Student(student_id=st["student_id"], name=st["name"], email=st["email"],
                          programme=st["programme"], current_course=st.get("current_course")))
            s.flush()
            s.add(FeeRecord(student_id=st["student_id"], **st["fee"]))
            if st.get("scholarship"):
                s.add(ScholarshipRecord(student_id=st["student_id"], **st["scholarship"]))
        if s.scalar(select(SupportRequest.id).limit(1)) is None:
            for r in data.get("support_requests", []):
                s.add(SupportRequest(created_at=datetime.now(timezone.utc).replace(tzinfo=None), **r))
