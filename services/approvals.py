"""Human-approval workflow for sensitive actions (currently: course change).

Stage 1  request_course_change(): validate -> create PENDING record -> NOTHING is changed.
Stage 2  decide():  an authorised approver approves/rejects. Approval re-validates the CURRENT record and executes
         inside ONE database transaction guarded by a compare-and-set claim (status PENDING -> PROCESSING), so:
           * a pending / rejected / expired / stale request never executes,
           * a request can be executed at most once (duplicate approvals are blocked),
           * a failure while executing rolls the change back and is recorded as FAILED, never as success.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from agent.state import RequestContext
from config.settings import Settings
from database.connection import Database
from database.models import ApprovalRequest, Course, Student, User
from services.audit import AuditService
from services.authorization import AuthorizationService
from services.privacy import redact

COURSE_CHANGE = "COURSE_CHANGE"


def _naive_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ApprovalError(Exception):
    """Validation problem with a request (safe to show to the user)."""

    def __init__(self, category: str, message: str):
        super().__init__(category)
        self.category, self.message = category, message


class StaleRequest(Exception):
    """The record changed since the request was made; the action must not execute."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class ExecutionFailed(Exception):
    def __init__(self, category: str):
        super().__init__(category)
        self.category = category


@dataclass
class ApprovalOutcome:
    ok: bool                 # True only if the requested decision was applied
    executed: bool           # True only if the sensitive action actually ran and committed
    status: str              # resulting status of the request
    message: str
    request_id: int
    reason: str = ""


def execute_course_change(s: Session, req: ApprovalRequest, payload: dict, approver: RequestContext) -> None:
    """Re-validate against the CURRENT records, then apply the change (inside the caller's transaction)."""
    st = s.get(Student, req.student_id)
    if st is None or st.current_course != payload["from_course"]:
        raise StaleRequest("course_changed_since_request")
    target = s.get(Course, payload["to_course"])
    if target is None:
        raise StaleRequest("course_no_longer_offered")
    if target.seats <= 0:
        raise StaleRequest("seat_unavailable")
    old = s.get(Course, payload["from_course"])
    target.seats -= 1
    if old is not None:
        old.seats += 1
    st.current_course = target.code


class ApprovalService:
    def __init__(self, db: Database, audit: AuditService, authz: AuthorizationService, settings: Settings,
                 clock: Callable[[], datetime] = _naive_utc):
        self.db, self.audit, self.authz, self.settings, self.clock = db, audit, authz, settings, clock
        self.executors: dict[str, Callable] = {COURSE_CHANGE: execute_course_change}   # replaceable in tests

    # ------------------------------------------------------------------ stage 1: request
    def request_course_change(self, ctx: RequestContext, new_course: str, reason: str = "",
                              student_id: str | None = None) -> dict:
        owner = self.authz.require_own_student_record(ctx, "course_change:request_own", student_id,
                                                      action="request_course_change", target_type="student_record")
        reason = redact(reason or "").strip()[:300]
        problem: tuple[str, str] | None = None
        existing: dict | None = None
        created: dict | None = None
        with self.db.session() as s:
            st = s.get(Student, owner)
            course = self._resolve_course(s, new_course)
            pending = s.scalar(select(ApprovalRequest).where(
                ApprovalRequest.student_id == owner, ApprovalRequest.action_type == COURSE_CHANGE,
                ApprovalRequest.status == "PENDING"))
            if st is None:
                problem = ("student_not_found", "No student record was found for your account.")
            elif pending is not None:
                existing = self._brief(pending)
            elif course is None:
                problem = ("unknown_course", "I couldn't find that course. Available courses are listed by the Academic Office.")
            elif course.code == st.current_course:
                problem = ("same_course", "You are already enrolled in that course.")
            elif course.seats <= 0:
                problem = ("course_full", f"{course.name} ({course.code}) currently has no seats available.")
            else:
                now = self.clock()
                req = ApprovalRequest(
                    action_type=COURSE_CHANGE, requester_user_id=ctx.user_id, student_id=owner, status="PENDING",
                    payload_json=json.dumps({"from_course": st.current_course, "to_course": course.code, "reason": reason}),
                    created_at=now, expires_at=now + timedelta(hours=self.settings.approval_ttl_hours))
                s.add(req)
                try:
                    s.flush()
                except IntegrityError:                       # race: the DB-level one-pending rule fired
                    s.rollback()
                    problem = ("duplicate_pending", "You already have a pending course-change request.")
                else:
                    created = {"approval_id": req.id, "display_id": req.display_id, "status": "PENDING",
                               "from_course": st.current_course, "to_course": course.code, "to_course_name": course.name,
                               "expires_at": req.expires_at.isoformat(timespec="minutes"), "duplicate": False,
                               "executed": False}
                    self.audit.record("COURSE_CHANGE_REQUESTED", ctx=ctx, target_type="student_record", target_id=owner,
                                      decision="ALLOWED", approval_request_id=req.id, execution_status="NOT_EXECUTED",
                                      result="pending_approval",
                                      detail={"from_course": st.current_course, "to_course": course.code}, session=s)
        if existing is not None:
            self.audit.record("COURSE_CHANGE_REQUEST_DUPLICATE", ctx=ctx, target_type="student_record", target_id=owner,
                              decision="ALLOWED", approval_request_id=existing["approval_id"],
                              execution_status="NOT_EXECUTED", result="existing_pending_returned")
            return {**existing, "duplicate": True, "executed": False}
        if problem is not None:
            self.audit.record("COURSE_CHANGE_REQUEST_REJECTED", ctx=ctx, target_type="student_record", target_id=owner,
                              decision="ALLOWED", execution_status="NOT_EXECUTED", result="validation_failed",
                              error_category=problem[0])
            raise ApprovalError(*problem)
        return created  # type: ignore[return-value]

    # ------------------------------------------------------------------ stage 2: decision
    def decide(self, ctx: RequestContext, request_id: int, decision: str, note: str = "") -> ApprovalOutcome:
        decision = (decision or "").upper()
        if decision not in ("APPROVE", "REJECT"):
            raise ValueError("decision must be APPROVE or REJECT")
        self.authz.require_permission(ctx, "approvals:review", action="decide_approval", target_type="approval_request",
                                      target_id=str(request_id), audit_action="UNAUTHORIZED_APPROVAL_ATTEMPT")
        note = redact(note or "").strip()[:300]
        with self.db.session() as s:                        # read-only pre-check (no writes, so no lock is held)
            requester = s.scalar(select(ApprovalRequest.requester_user_id).where(ApprovalRequest.id == request_id))
        if requester is None:
            self.audit.record("APPROVAL_NOT_FOUND", ctx=ctx, target_type="approval_request", target_id=str(request_id),
                              decision="ALLOWED", result="not_found", approval_request_id=request_id)
            return ApprovalOutcome(False, False, "NOT_FOUND", "No such approval request.", request_id, "not_found")
        self.authz.forbid_self_approval(ctx, requester, request_id)
        try:
            with self.db.session() as s:
                return self._decide_in_tx(s, ctx, request_id, decision, note)
        except ExecutionFailed as ef:                        # the transaction was rolled back: nothing was changed
            return self._record_failure(ctx, request_id, note, ef.category)

    def _decide_in_tx(self, s: Session, ctx: RequestContext, request_id: int, decision: str, note: str) -> ApprovalOutcome:
        claimed = s.execute(update(ApprovalRequest)
                            .where(ApprovalRequest.id == request_id, ApprovalRequest.status == "PENDING")
                            .values(status="PROCESSING")).rowcount
        if claimed != 1:                                     # already decided (or being decided) -> never execute twice
            current = s.scalar(select(ApprovalRequest.status).where(ApprovalRequest.id == request_id))
            self.audit.record("DUPLICATE_DECISION_BLOCKED", ctx=ctx, target_type="approval_request",
                              target_id=str(request_id), decision="DENIED", approval_request_id=request_id,
                              execution_status="NOT_EXECUTED", result="blocked", error_category=f"already_{(current or '').lower()}",
                              detail={"status": current}, session=s)
            return ApprovalOutcome(False, False, current or "UNKNOWN",
                                   f"This request is already {(current or 'processed').lower()}; no action was taken.",
                                   request_id, "already_decided")
        req = s.get(ApprovalRequest, request_id, populate_existing=True)
        now = self.clock()
        common = dict(ctx=ctx, target_type="approval_request", target_id=str(request_id), approval_request_id=request_id,
                      approver_user_id=ctx.user_id, session=s)
        if now > req.expires_at:
            req.status, req.decided_at = "EXPIRED", now
            self.audit.record("APPROVAL_EXPIRED", decision="ALLOWED", execution_status="NOT_EXECUTED", result="expired",
                              error_category="expired", **common)
            return ApprovalOutcome(False, False, "EXPIRED", "This request has expired and was not executed.", request_id, "expired")
        req.decided_by_user_id, req.decided_at, req.decision_note = ctx.user_id, now, note
        if decision == "REJECT":
            req.status = "REJECTED"
            self.audit.record("APPROVAL_REJECTED", decision="ALLOWED", approval_decision="REJECTED",
                              execution_status="NOT_EXECUTED", result="rejected", detail={"note": note}, **common)
            return ApprovalOutcome(True, False, "REJECTED", "Request rejected. No change was made.", request_id)
        payload = json.loads(req.payload_json)
        executor = self.executors[req.action_type]
        try:
            executor(s, req, payload, ctx)
        except StaleRequest as stale:
            req.status = "STALE"
            self.audit.record("APPROVAL_STALE", decision="ALLOWED", approval_decision="APPROVED",
                              execution_status="NOT_EXECUTED", result="stale_request", error_category=stale.reason, **common)
            return ApprovalOutcome(False, False, "STALE", f"The record changed since the request was made ({stale.reason}); "
                                   "nothing was executed. Ask the student to submit a new request.", request_id, stale.reason)
        except Exception as exc:                             # leaving the `with` rolls back any partial write
            raise ExecutionFailed(type(exc).__name__) from None
        req.status, req.executed_at = "EXECUTED", now
        self.audit.record("APPROVAL_APPROVED", decision="ALLOWED", approval_decision="APPROVED",
                          execution_status="NOT_EXECUTED", result="approved", detail={"note": note}, **common)
        self.audit.record("SENSITIVE_ACTION_EXECUTED", decision="ALLOWED", approval_decision="APPROVED",
                          execution_status="EXECUTED", result="success",
                          detail={"from_course": payload["from_course"], "to_course": payload["to_course"]}, **common)
        return ApprovalOutcome(True, True, "EXECUTED", f"Approved and executed: course changed to {payload['to_course']}.", request_id)

    def _record_failure(self, ctx: RequestContext, request_id: int, note: str, category: str) -> ApprovalOutcome:
        now = self.clock()
        try:
            with self.db.session() as s:
                s.execute(update(ApprovalRequest).where(ApprovalRequest.id == request_id, ApprovalRequest.status == "PENDING")
                          .values(status="FAILED", decided_by_user_id=ctx.user_id, decided_at=now, decision_note=note,
                                  failure_category=category))
                common = dict(ctx=ctx, target_type="approval_request", target_id=str(request_id),
                              approval_request_id=request_id, approver_user_id=ctx.user_id, session=s)
                self.audit.record("APPROVAL_APPROVED", decision="ALLOWED", approval_decision="APPROVED",
                                  execution_status="NOT_EXECUTED", result="approved", **common)
                self.audit.record("SENSITIVE_ACTION_FAILED", decision="ALLOWED", approval_decision="APPROVED",
                                  execution_status="FAILED", result="failure", error_category=category, **common)
        except Exception:
            pass                                             # DB unavailable: still report failure, never success
        return ApprovalOutcome(False, False, "FAILED", "Execution failed and was rolled back. No change was made.",
                               request_id, category)

    # ------------------------------------------------------------------ read side
    def list_pending(self, ctx: RequestContext) -> list[dict]:
        return self._list(ctx, "approvals:review", ApprovalRequest.status == "PENDING")

    def list_all(self, ctx: RequestContext, limit: int = 100) -> list[dict]:
        return self._list(ctx, "approvals:read_all", None, limit)

    def list_for_student(self, ctx: RequestContext) -> list[dict]:
        owner = self.authz.require_own_student_record(ctx, "approvals:read_own", None, action="list_own_approvals",
                                                      target_type="approval_request")
        return self._list_unchecked(ApprovalRequest.student_id == owner, 50, include_requester=False)

    def _list(self, ctx, permission, cond, limit=100) -> list[dict]:
        self.authz.require_permission(ctx, permission, action="list_approvals", target_type="approval_request")
        return self._list_unchecked(cond, limit)

    def _list_unchecked(self, cond, limit, include_requester: bool = True) -> list[dict]:
        with self.db.session() as s:
            q = select(ApprovalRequest).order_by(ApprovalRequest.id.desc()).limit(limit)
            if cond is not None:
                q = q.where(cond)
            return [self._describe(s, r, include_requester) for r in s.scalars(q)]

    def _brief(self, r: ApprovalRequest) -> dict:
        p = json.loads(r.payload_json)
        return {"approval_id": r.id, "display_id": r.display_id, "status": r.status, "from_course": p["from_course"],
                "to_course": p["to_course"], "expires_at": r.expires_at.isoformat(timespec="minutes")}

    def _describe(self, s: Session, r: ApprovalRequest, include_requester: bool = True) -> dict:
        p = json.loads(r.payload_json)
        st = s.get(Student, r.student_id)
        to_c, from_c = s.get(Course, p["to_course"]), s.get(Course, p["from_course"]) if p["from_course"] else None
        requester = s.get(User, r.requester_user_id)
        decider = s.get(User, r.decided_by_user_id) if r.decided_by_user_id else None
        consequences = (f"{st.name} ({st.student_id}) will move from {from_c.name if from_c else 'no course'} to "
                        f"{to_c.name if to_c else p['to_course']}. Seats in {p['to_course']}: {to_c.seats if to_c else '?'} -> "
                        f"{(to_c.seats - 1) if to_c else '?'}; seats in {p['from_course']} increase by 1.")
        return {"id": r.id, "display_id": r.display_id, "action": r.action_type, "status": r.status,
                "student_id": r.student_id, "student_name": st.name if st else "",
                "requested_by": requester.username if (requester and include_requester) else "(you)",
                "from_course": p["from_course"], "to_course": p["to_course"], "reason": p.get("reason", ""),
                "consequences": consequences, "created_at": r.created_at.isoformat(timespec="minutes"),
                "expires_at": r.expires_at.isoformat(timespec="minutes"),
                "decided_by": decider.username if decider else "", "decision_note": r.decision_note,
                "executed_at": r.executed_at.isoformat(timespec="minutes") if r.executed_at else "",
                "failure_category": r.failure_category}

    @staticmethod
    def _resolve_course(s: Session, text: str) -> Course | None:
        t = (text or "").strip()
        if not t:
            return None
        c = s.get(Course, t.upper())
        if c is not None:
            return c
        return s.scalar(select(Course).where(func.lower(Course.name) == t.lower()))
