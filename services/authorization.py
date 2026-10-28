"""Server-side authorization (role permissions + record-level ownership).

Authentication answers "who are you?"; authorization answers "what may you do?". Every sensitive service and
tool calls into this module with the server-derived RequestContext. Nothing here trusts model output, chat
text, hidden UI elements or user-supplied student IDs.
"""
from __future__ import annotations

from agent.state import RequestContext
from services.audit import AuditService

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "student": frozenset({
        "policy:read", "fee:read_own", "scholarship:read_own", "support:create_own", "support:read_own",
        "memory:manage_own", "course_change:request_own", "approvals:read_own"}),
    "approver": frozenset({
        "policy:read", "approvals:review", "approvals:read_all", "audit:read", "traces:read", "evaluation:read"}),
    "admin": frozenset({
        "policy:read", "approvals:review", "approvals:read_all", "audit:read", "traces:read", "evaluation:read",
        "evaluation:run"}),
}


class AuthorizationError(Exception):
    """Structured denial. `reason` is a stable machine code; `message` is safe to show to the user."""

    def __init__(self, reason: str, permission: str = "", message: str = ""):
        super().__init__(reason)
        self.reason, self.permission = reason, permission
        self.message = message or "You are not authorized to perform this action."


class AuthorizationService:
    def __init__(self, audit: AuditService):
        self.audit = audit

    @staticmethod
    def has_permission(ctx: RequestContext, permission: str) -> bool:
        return ctx.authenticated and permission in ROLE_PERMISSIONS.get(ctx.role, frozenset())

    def _deny(self, ctx: RequestContext, reason: str, permission: str, action: str, target_type: str, target_id: str,
              message: str = "", audit_action: str = "ACCESS_DENIED") -> AuthorizationError:
        self.audit.record(audit_action, ctx=ctx, target_type=target_type, target_id=target_id, decision="DENIED",
                          result="blocked", error_category=reason, detail={"permission": permission, "reason": action})
        return AuthorizationError(reason, permission, message)

    def require_permission(self, ctx: RequestContext, permission: str, *, action: str, target_type: str = "",
                           target_id: str = "", audit_action: str = "ACCESS_DENIED") -> None:
        """Raise (and audit) unless the authenticated role holds `permission`."""
        if not ctx.authenticated:
            raise self._deny(ctx, "not_authenticated", permission, action, target_type, target_id,
                             "Please sign in first.", audit_action)
        if not self.has_permission(ctx, permission):
            raise self._deny(ctx, "role_not_permitted", permission, action, target_type, target_id,
                             audit_action=audit_action)

    def require_own_student_record(self, ctx: RequestContext, permission: str, target_student_id: str | None, *,
                                   action: str, target_type: str) -> str:
        """Record-level check: the permission AND ownership. Returns the student id the query must be scoped to.

        The returned id is always the authenticated user's own `ctx.student_id`; a user-supplied id that differs is
        refused and audited as an unauthorized access attempt.
        """
        self.require_permission(ctx, permission, action=action, target_type=target_type,
                                target_id=target_student_id or "", audit_action="UNAUTHORIZED_ACCESS")
        if ctx.student_id is None:
            raise self._deny(ctx, "no_student_record", permission, action, target_type, target_student_id or "",
                             "Your account is not linked to a student record.", "UNAUTHORIZED_ACCESS")
        if target_student_id is not None and target_student_id != ctx.student_id:
            raise self._deny(ctx, "not_record_owner", permission, action, target_type, target_student_id,
                             "You can only access your own records.", "UNAUTHORIZED_ACCESS")
        return ctx.student_id

    def forbid_self_approval(self, ctx: RequestContext, requester_user_id: int, request_id: int) -> None:
        """A requester can never decide their own request, whatever roles they hold."""
        if ctx.user_id == requester_user_id:
            raise self._deny(ctx, "self_approval_not_allowed", "approvals:review", "decide_approval", "approval_request",
                             str(request_id), "You cannot approve or reject your own request.",
                             "UNAUTHORIZED_APPROVAL_ATTEMPT")
