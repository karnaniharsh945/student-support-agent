"""Fee, scholarship and support-request services - authorization-aware (Milestone 2).

Every method takes the server-derived RequestContext. Queries are scoped to `ctx.student_id` (the value returned
by the authorization check), never to a user- or model-supplied identifier.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import select

from agent.state import RequestContext
from database.connection import Database
from database.models import FeeRecord, ScholarshipRecord, Student, SupportRequest
from services.audit import AuditService
from services.authorization import AuthorizationService


class RecordNotFound(Exception):
    """The requested record does not exist."""


def _naive_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class FeeService:
    def __init__(self, db: Database, authz: AuthorizationService, audit: AuditService):
        self.db, self.authz, self.audit = db, authz, audit

    def get_fee_status(self, ctx: RequestContext, requested_student_id: str | None = None) -> dict:
        owner = self.authz.require_own_student_record(ctx, "fee:read_own", requested_student_id,
                                                      action="get_fee_status", target_type="fee_record")
        with self.db.session() as s:
            st, fee = s.get(Student, owner), s.get(FeeRecord, owner)          # scoped to the authenticated student
            if st is None or fee is None:
                result = None
            else:
                result = {"student_id": owner, "student_name": st.name, "currency": "INR",
                          "total_fee": fee.total_fee, "amount_paid": fee.amount_paid,
                          "outstanding": fee.total_fee - fee.amount_paid, "due_date": fee.due_date,
                          "last_payment_date": fee.last_payment_date, "status": fee.status}
        self.audit.record("FEE_STATUS_READ", ctx=ctx, target_type="fee_record", target_id=owner, decision="ALLOWED",
                          result="success" if result else "not_found")
        if result is None:
            raise RecordNotFound(owner)
        return result


class ScholarshipService:
    def __init__(self, db: Database, authz: AuthorizationService, audit: AuditService):
        self.db, self.authz, self.audit = db, authz, audit

    def get_scholarship_status(self, ctx: RequestContext, requested_student_id: str | None = None) -> dict:
        owner = self.authz.require_own_student_record(ctx, "scholarship:read_own", requested_student_id,
                                                      action="get_scholarship_status", target_type="scholarship_record")
        with self.db.session() as s:
            st = s.get(Student, owner)
            if st is None:
                result = None
            else:
                sch = s.get(ScholarshipRecord, owner)
                result = ({"student_id": owner, "student_name": st.name, "status": "NOT_APPLIED", "scheme": None,
                           "amount": 0, "note": "No scholarship application on record."} if sch is None else
                          {"student_id": owner, "student_name": st.name, "status": sch.status, "scheme": sch.scheme,
                           "amount": sch.amount, "note": sch.note})
        self.audit.record("SCHOLARSHIP_STATUS_READ", ctx=ctx, target_type="scholarship_record", target_id=owner,
                          decision="ALLOWED", result="success" if result else "not_found")
        if result is None:
            raise RecordNotFound(owner)
        return result


class SupportRequestService:
    CATEGORIES = ("FEES", "SCHOLARSHIP", "COURSE_CHANGE", "TECHNICAL", "OTHER")
    PRIORITIES = ("LOW", "NORMAL", "HIGH")

    def __init__(self, db: Database, authz: AuthorizationService, audit: AuditService,
                 clock: Callable[[], datetime] = _naive_utc):
        self.db, self.authz, self.audit, self.clock = db, authz, audit, clock

    def create(self, ctx: RequestContext, category: str, description: str, priority: str = "NORMAL") -> dict:
        owner = self.authz.require_own_student_record(ctx, "support:create_own", None, action="create_support_request",
                                                      target_type="support_request")
        if category not in self.CATEGORIES or priority not in self.PRIORITIES:
            raise ValueError("invalid category or priority")
        with self.db.session() as s:
            req = SupportRequest(student_id=owner, category=category, description=description, priority=priority,
                                 status="OPEN", created_at=self.clock())
            s.add(req)
            s.flush()
            out = {"ticket": req.ticket, "id": req.id, "category": category, "priority": priority,
                   "status": req.status, "description": description}
            self.audit.record("SUPPORT_REQUEST_CREATED", ctx=ctx, target_type="support_request", target_id=req.ticket,
                              decision="ALLOWED", result="success", detail={"category": category, "ticket": req.ticket},
                              session=s)
        return out

    def list_for_student(self, ctx: RequestContext) -> list[dict]:
        owner = self.authz.require_own_student_record(ctx, "support:read_own", None, action="list_support_requests",
                                                      target_type="support_request")
        with self.db.session() as s:
            rows = s.scalars(select(SupportRequest).where(SupportRequest.student_id == owner)
                             .order_by(SupportRequest.id.desc())).all()
            return [{"ticket": r.ticket, "category": r.category, "priority": r.priority, "status": r.status,
                     "description": r.description, "created_at": r.created_at.isoformat(timespec="seconds")}
                    for r in rows]
