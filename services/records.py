"""Fee, scholarship and support-request services (Milestone 1: demonstration user context)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import select

from database.connection import Database
from database.models import FeeRecord, Student, ScholarshipRecord, SupportRequest


class RecordNotFound(Exception):
    """The requested record does not exist."""


def _naive_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class FeeService:
    def __init__(self, db: Database):
        self.db = db

    def get_fee_status(self, student_id: str) -> dict:
        with self.db.session() as s:
            st = s.get(Student, student_id)
            fee = s.get(FeeRecord, student_id)
            if st is None or fee is None:
                raise RecordNotFound(f"no fee record for {student_id}")
            return {"student_id": student_id, "student_name": st.name, "currency": "INR",
                    "total_fee": fee.total_fee, "amount_paid": fee.amount_paid,
                    "outstanding": fee.total_fee - fee.amount_paid, "due_date": fee.due_date,
                    "last_payment_date": fee.last_payment_date, "status": fee.status}


class ScholarshipService:
    def __init__(self, db: Database):
        self.db = db

    def get_scholarship_status(self, student_id: str) -> dict:
        with self.db.session() as s:
            st = s.get(Student, student_id)
            if st is None:
                raise RecordNotFound(f"no student {student_id}")
            sch = s.get(ScholarshipRecord, student_id)
            if sch is None:
                return {"student_id": student_id, "student_name": st.name, "status": "NOT_APPLIED",
                        "scheme": None, "amount": 0, "note": "No scholarship application on record."}
            return {"student_id": student_id, "student_name": st.name, "status": sch.status,
                    "scheme": sch.scheme, "amount": sch.amount, "note": sch.note}


class SupportRequestService:
    CATEGORIES = ("FEES", "SCHOLARSHIP", "COURSE_CHANGE", "TECHNICAL", "OTHER")
    PRIORITIES = ("LOW", "NORMAL", "HIGH")

    def __init__(self, db: Database, clock: Callable[[], datetime] = _naive_utc):
        self.db = db
        self.clock = clock

    def create(self, student_id: str, category: str, description: str, priority: str = "NORMAL") -> dict:
        if category not in self.CATEGORIES or priority not in self.PRIORITIES:
            raise ValueError("invalid category or priority")
        with self.db.session() as s:
            if s.get(Student, student_id) is None:
                raise RecordNotFound(f"no student {student_id}")
            req = SupportRequest(student_id=student_id, category=category, description=description,
                                 priority=priority, status="OPEN", created_at=self.clock())
            s.add(req)
            s.flush()
            return {"ticket": req.ticket, "id": req.id, "category": category, "priority": priority,
                    "status": req.status, "description": description}

    def list_for_student(self, student_id: str) -> list[dict]:
        with self.db.session() as s:
            rows = s.scalars(select(SupportRequest).where(SupportRequest.student_id == student_id)
                             .order_by(SupportRequest.id.desc())).all()
            return [{"ticket": r.ticket, "category": r.category, "priority": r.priority, "status": r.status,
                     "description": r.description, "created_at": r.created_at.isoformat(timespec="seconds")}
                    for r in rows]
