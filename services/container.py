"""Service container: builds and wires the application services (simple dependency injection)."""
from __future__ import annotations

from dataclasses import dataclass

from config.settings import Settings
from database.connection import Database
from agent.state import RequestContext, ToolResult
from services.approvals import ApprovalService
from services.audit import AuditService
from services.authentication import AuthService
from services.authorization import AuthorizationService
from services.memory import MemoryService
from services.policy_retrieval import PolicyRetriever
from services.records import FeeService, ScholarshipService, SupportRequestService
from services.tracing import TraceService


@dataclass
class Services:
    settings: Settings
    db: Database
    fees: FeeService
    scholarships: ScholarshipService
    support: SupportRequestService
    memory: MemoryService
    policy: PolicyRetriever
    tracer: TraceService
    audit: AuditService
    authz: AuthorizationService
    auth: AuthService
    approvals: ApprovalService

    def tool_guard(self, spec, ctx: RequestContext) -> ToolResult | None:
        """Registry guard: identity + role permission must hold before a tool runs (audited on denial)."""
        if spec.required_permission is None:
            return None
        if not ctx.authenticated:
            self.audit.record("TOOL_PERMISSION_DENIED", ctx=ctx, target_type="tool", target_id=spec.name,
                              decision="DENIED", result="blocked", error_category="not_authenticated")
            return ToolResult(False, error_code="permission_denied", user_message="Please sign in first.")
        if not self.authz.has_permission(ctx, spec.required_permission):
            self.audit.record("TOOL_PERMISSION_DENIED", ctx=ctx, target_type="tool", target_id=spec.name,
                              decision="DENIED", result="blocked", error_category="role_not_permitted",
                              detail={"tool": spec.name, "permission": spec.required_permission})
            return ToolResult(False, error_code="permission_denied",
                              user_message="Your account is not permitted to use this action.")
        return None


def build_services(settings: Settings, db: Database | None = None) -> Services:
    db = db or Database(settings.database_url)
    audit = AuditService(db)
    authz = AuthorizationService(audit)
    audit.authz = authz
    tracer = TraceService(db, authz)
    return Services(
        settings=settings, db=db, fees=FeeService(db, authz, audit), scholarships=ScholarshipService(db, authz, audit),
        support=SupportRequestService(db, authz, audit), memory=MemoryService(db),
        policy=PolicyRetriever(settings.policy_path), tracer=tracer, audit=audit, authz=authz,
        auth=AuthService(db, audit, settings), approvals=ApprovalService(db, audit, authz, settings))
