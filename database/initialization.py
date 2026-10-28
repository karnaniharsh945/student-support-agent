"""Idempotent database initialisation and deterministic seeding."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import bcrypt
from sqlalchemy import inspect, select, text

from database.connection import Database
from database.models import (Base, Course, FeeRecord, ScholarshipRecord, Student, SupportRequest, User)

SCHEMA_HINT = "Database schema is outdated. Run:  python scripts/initialize_database.py --reset   (demo data only)"

_AUDIT_TRIGGERS = [
    """CREATE TRIGGER IF NOT EXISTS audit_events_no_update BEFORE UPDATE ON audit_events
       BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;""",
    """CREATE TRIGGER IF NOT EXISTS audit_events_no_delete BEFORE DELETE ON audit_events
       BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;""",
]


class SchemaOutdated(RuntimeError):
    pass


def init_schema(db: Database) -> None:
    Base.metadata.create_all(db.engine)
    if db.engine.dialect.name == "sqlite":       # enforce append-only audit trail at the database level
        with db.engine.begin() as conn:
            for stmt in _AUDIT_TRIGGERS:
                conn.execute(text(stmt))
    check_schema(db)


def check_schema(db: Database) -> None:
    """Fail loudly if an old (Milestone-1) database file is being reused."""
    insp = inspect(db.engine)
    cols = {c["name"] for c in insp.get_columns("traces")}
    audit_cols = {c["name"] for c in insp.get_columns("audit_events")} if "audit_events" in insp.get_table_names() else set()
    if "authorization_json" not in cols or "users" not in insp.get_table_names() or "event_hash" not in audit_cols:
        raise SchemaOutdated(SCHEMA_HINT)


def reset_schema(db: Database) -> None:
    Base.metadata.drop_all(db.engine)
    init_schema(db)


def hash_password(password: str, rounds: int = 12) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=rounds)).decode("ascii")


def seed_database(db: Database, seed_path: Path, bcrypt_rounds: int = 12) -> None:
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
        # demo accounts: passwords come from the (clearly demo-only) seed file and are stored ONLY as bcrypt hashes
        for u in data.get("users", []):
            if s.scalar(select(User).where(User.username == u["username"])) is None:
                s.add(User(username=u["username"], password_hash=hash_password(u["password"], bcrypt_rounds),
                           role=u["role"], student_id=u.get("student_id")))
