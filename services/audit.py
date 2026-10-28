"""Append-only audit trail.

The application exposes only `record` and (permission-gated) `list_events`; there is no update or delete
API, and SQLite triggers additionally reject UPDATE/DELETE on the table. Event details are restricted to an
allow-list of keys and redacted, so audit rows never contain credentials or private record contents.
"""
from __future__ import annotations

import hashlib
import json
import threading
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
GENESIS = "0" * 64


def compute_event_hash(e: AuditEvent, prev_hash: str) -> str:
    """SHA-256 over every audited field plus the previous event's hash (a hash chain)."""
    body = json.dumps([e.event_id, e.timestamp.isoformat(), e.actor_user_id, e.actor_username, e.actor_role, e.action,
                       e.target_type, e.target_id, e.permission_decision, e.approval_request_id, e.approval_decision,
                       e.approver_user_id, e.execution_status, e.result, e.error_category, e.detail_json, prev_hash],
                      separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


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
        self._lock = threading.Lock()   # keeps the chain linear within one process (single-process demo)

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
        with self._lock:
            if session is not None:
                self._append(session, ev)
            else:
                with self.db.session() as s:
                    self._append(s, ev)

    @staticmethod
    def _append(s: Session, ev: AuditEvent) -> None:
        s.flush()                                     # make earlier events of this transaction visible
        prev = s.scalar(select(AuditEvent.event_hash).order_by(AuditEvent.id.desc()).limit(1)) or GENESIS
        ev.prev_hash, ev.event_hash = prev, compute_event_hash(ev, prev)
        s.add(ev)
        s.flush()

    # -- tamper evidence ---------------------------------------------------------------------
    def verify_chain(self, ctx: RequestContext) -> dict:
        """Permission-gated integrity check (approver/admin)."""
        self.authz.require_permission(ctx, "audit:read", action="AUDIT_VERIFY", target_type="audit_events")
        return self.verify_chain_system()

    def verify_chain_system(self) -> dict:
        """Re-compute every hash in order. Detects edited rows and deleted/inserted rows in the middle of the chain.

        Limitation: deleting the NEWEST rows leaves a valid shorter chain; publish/anchor `head_hash` externally to detect that.
        """
        prev, n = GENESIS, 0
        with self.db.session() as s:
            for e in s.scalars(select(AuditEvent).order_by(AuditEvent.id)):
                n += 1
                if e.prev_hash != prev or e.event_hash != compute_event_hash(e, prev):
                    return {"ok": False, "checked": n, "first_broken_event_id": e.event_id, "head_hash": prev}
                prev = e.event_hash
        return {"ok": True, "checked": n, "first_broken_event_id": None, "head_hash": prev}

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
