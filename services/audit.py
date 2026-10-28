"""Append-only audit trail.

The application exposes only `record` and (permission-gated) `list_events`; there is no update or delete
API, and SQLite triggers additionally reject UPDATE/DELETE on the table. Event details are restricted to an
allow-list of keys and redacted, so audit rows never contain credentials or private record contents.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.state import RequestContext
from database.connection import Database
from database.models import AuditEvent
from services.privacy import redact

ALLOWED_DETAIL_KEYS = {"tool", "reason", "from_course", "to_course", "username", "permission", "status", "category",
                       "ticket", "session", "note", "requested_student", "outcome"}
MAX_DETAIL_VALUE = 200


def _naive_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def clean_detail(detail: dict[str, Any] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in (detail or {}).items():
        if k in ALLOWED_DETAIL_KEYS and v is not None:
            out[k] = redact(str(v))[:MAX_DETAIL_VALUE]
    return out


class AuditService:
    def __init__(self, db: Database, clock: Callable[[], datetime] = _naive_utc):
        self.db = db
        self.clock = clock
        self.authz = None            # set by the container (permission check for list_events)

    def record(self, action: str, *, ctx: RequestContext | None = None, actor_user_id: int | None = None,
               actor_username: str = "", actor_role: str = "", target_type: str = "", target_id: str = "",
               decision: str = "N/A", approval_request_id: int | None = None, approval_decision: str = "",
               approver_user_id: int | None = None, execution_status: str = "", result: str = "",
               error_category: str = "", detail: dict[str, Any] | None = None, session: Session | None = None) -> None:
        """Write one event. Pass `session` to make it part of the caller's transaction."""
        if ctx is not None and ctx.authenticated:
            actor_user_id, actor_username, actor_role = ctx.user_id, ctx.username, ctx.role
        ev = AuditEvent(event_id=str(uuid.uuid4()), timestamp=self.clock(), actor_user_id=actor_user_id,
                        actor_username=actor_username[:50], actor_role=actor_role, action=action,
                        target_type=target_type, target_id=str(target_id), permission_decision=decision,
                        approval_request_id=approval_request_id, approval_decision=approval_decision,
                        approver_user_id=approver_user_id, execution_status=execution_status, result=result,
                        error_category=error_category, detail_json=json.dumps(clean_detail(detail)))
        if session is not None:
            session.add(ev)
        else:
            with self.db.session() as s:
                s.add(ev)

    # -- read side (permission gated; students have no access) -----------------------------
    def list_events(self, ctx: RequestContext, *, action: str | None = None, approval_request_id: int | None = None,
                    limit: int = 200) -> list[dict]:
        self.authz.require_permission(ctx, "audit:read", action="AUDIT_READ", target_type="audit_events")
        with self.db.session() as s:
            q = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit)
            if action:
                q = q.where(AuditEvent.action == action)
            if approval_request_id is not None:
                q = q.where(AuditEvent.approval_request_id == approval_request_id)
            return [self._to_dict(e) for e in s.scalars(q)]

    def events_for_system(self, *, action: str | None = None, approval_request_id: int | None = None,
                          actor_user_id: int | None = None) -> list[dict]:
        """Internal (non-UI) read used by the evaluation harness and tests."""
        with self.db.session() as s:
            q = select(AuditEvent).order_by(AuditEvent.id)
            if action:
                q = q.where(AuditEvent.action == action)
            if approval_request_id is not None:
                q = q.where(AuditEvent.approval_request_id == approval_request_id)
            if actor_user_id is not None:
                q = q.where(AuditEvent.actor_user_id == actor_user_id)
            return [self._to_dict(e) for e in s.scalars(q)]

    @staticmethod
    def _to_dict(e: AuditEvent) -> dict:
        return {"event_id": e.event_id, "timestamp": e.timestamp.isoformat(timespec="seconds"),
                "actor_user_id": e.actor_user_id, "actor": e.actor_username, "actor_role": e.actor_role,
                "action": e.action, "target_type": e.target_type, "target_id": e.target_id,
                "permission_decision": e.permission_decision, "approval_request_id": e.approval_request_id,
                "approval_decision": e.approval_decision, "approver_user_id": e.approver_user_id,
                "execution_status": e.execution_status, "result": e.result, "error_category": e.error_category,
                "detail": json.loads(e.detail_json)}
