"""SQLAlchemy ORM models (relational schema)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Course(Base):
    __tablename__ = "courses"
    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    seats: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (CheckConstraint("seats >= 0", name="ck_course_seats_nonneg"),)


class Student(Base):
    """Authoritative student profile. Authentication data lives elsewhere."""
    __tablename__ = "students"
    student_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(120))
    programme: Mapped[str] = mapped_column(String(120))
    current_course: Mapped[str | None] = mapped_column(ForeignKey("courses.code"), nullable=True)

    fee: Mapped["FeeRecord | None"] = relationship(back_populates="student", uselist=False)
    scholarship: Mapped["ScholarshipRecord | None"] = relationship(back_populates="student", uselist=False)


class FeeRecord(Base):
    __tablename__ = "fee_records"
    student_id: Mapped[str] = mapped_column(ForeignKey("students.student_id"), primary_key=True)
    total_fee: Mapped[int] = mapped_column(Integer)
    amount_paid: Mapped[int] = mapped_column(Integer)
    due_date: Mapped[str] = mapped_column(String(10))
    last_payment_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    student: Mapped[Student] = relationship(back_populates="fee")
    __table_args__ = (CheckConstraint("amount_paid >= 0 AND amount_paid <= total_fee", name="ck_fee_amounts"),)


class ScholarshipRecord(Base):
    __tablename__ = "scholarship_records"
    student_id: Mapped[str] = mapped_column(ForeignKey("students.student_id"), primary_key=True)
    scheme: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20))
    amount: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(Text, default="")
    student: Mapped[Student] = relationship(back_populates="scholarship")


class SupportRequest(Base):
    __tablename__ = "support_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.student_id"), index=True)
    category: Mapped[str] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(10), default="NORMAL")
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    created_at: Mapped[datetime] = mapped_column(DateTime)

    @property
    def ticket(self) -> str:
        return f"SR-{self.id:04d}"


class MemoryItem(Base):
    """Long-term, non-sensitive memory. Never authoritative for identity or authorization."""
    __tablename__ = "memory_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.student_id"), index=True)
    key: Mapped[str] = mapped_column(String(40))
    value: Mapped[str] = mapped_column(String(200))
    source_session: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    __table_args__ = (UniqueConstraint("student_id", "key", name="uq_memory_student_key"),)


class Trace(Base):
    """One row per agent run (structured trace). Sensitive fields are redacted before storage."""
    __tablename__ = "traces"
    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    session_id: Mapped[str] = mapped_column(String(64))
    student_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    question: Mapped[str] = mapped_column(Text)               # redacted, truncated
    category: Mapped[str] = mapped_column(String(30), default="")
    decision: Mapped[str] = mapped_column(String(40), default="")
    tool_calls_json: Mapped[str] = mapped_column(Text, default="[]")   # name, redacted args, ok, error
    policy_chunks_json: Mapped[str] = mapped_column(Text, default="[]")
    memory_refs_json: Mapped[str] = mapped_column(Text, default="[]")
    context_sources_json: Mapped[str] = mapped_column(Text, default="[]")
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="")
    authorization_json: Mapped[str] = mapped_column(Text, default="[]")     # per tool call: allowed / denied
    approval_state: Mapped[str] = mapped_column(String(30), default="")      # e.g. PENDING when a sensitive action was queued
    latency_ms: Mapped[float] = mapped_column(default=0.0)
    model_latency_ms: Mapped[float | None] = mapped_column(nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_source: Mapped[str] = mapped_column(String(20), default="unavailable")
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    provider: Mapped[str] = mapped_column(String(30), default="")
    model: Mapped[str] = mapped_column(String(80), default="")
    error_category: Mapped[str] = mapped_column(String(40), default="")
    outcome: Mapped[str] = mapped_column(String(30), default="")


# ----------------------------------------------------------------------------- Milestone 2 tables
class User(Base):
    """Login identity. Kept separate from the student profile (authentication != student data)."""
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(100))            # bcrypt; never plaintext
    role: Mapped[str] = mapped_column(String(20))                      # student | approver | admin
    student_id: Mapped[str | None] = mapped_column(ForeignKey("students.student_id"), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    __table_args__ = (CheckConstraint("role IN ('student','approver','admin')", name="ck_user_role"),)


class AuthSession(Base):
    """Server-side session. Only the SHA-256 of the bearer token is stored."""
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class ApprovalRequest(Base):
    """A sensitive action waiting for (or past) human approval."""
    __tablename__ = "approval_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action_type: Mapped[str] = mapped_column(String(30))                 # COURSE_CHANGE
    requester_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    student_id: Mapped[str] = mapped_column(ForeignKey("students.student_id"), index=True)
    payload_json: Mapped[str] = mapped_column(Text)                      # {from_course,to_course,reason}
    # PENDING | PROCESSING (transient claim) | EXECUTED | REJECTED | EXPIRED | STALE | FAILED
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decided_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decision_note: Mapped[str] = mapped_column(String(300), default="")
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failure_category: Mapped[str] = mapped_column(String(40), default="")
    __table_args__ = (
        # database-level guarantee: at most ONE pending request per student per action type
        Index("uq_one_pending_per_student_action", "student_id", "action_type", unique=True,
              sqlite_where=text("status = 'PENDING'")),
    )

    @property
    def display_id(self) -> str:
        return f"APR-{self.id:04d}"


class AuditEvent(Base):
    """Append-only audit trail (UPDATE/DELETE are blocked by SQLite triggers; see database/initialization.py)."""
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(36), unique=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_username: Mapped[str] = mapped_column(String(50), default="")
    actor_role: Mapped[str] = mapped_column(String(20), default="")
    action: Mapped[str] = mapped_column(String(50), index=True)
    target_type: Mapped[str] = mapped_column(String(30), default="")
    target_id: Mapped[str] = mapped_column(String(40), default="")
    permission_decision: Mapped[str] = mapped_column(String(10), default="N/A")      # ALLOWED | DENIED | N/A
    approval_request_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approval_decision: Mapped[str] = mapped_column(String(12), default="")           # APPROVED | REJECTED | ""
    approver_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    execution_status: Mapped[str] = mapped_column(String(20), default="")            # EXECUTED | NOT_EXECUTED | FAILED | ""
    result: Mapped[str] = mapped_column(String(40), default="")
    error_category: Mapped[str] = mapped_column(String(40), default="")
    detail_json: Mapped[str] = mapped_column(Text, default="{}")                     # allow-listed, redacted keys only
    prev_hash: Mapped[str] = mapped_column(String(64), default="")                   # tamper-evident chain (see AuditService)
    event_hash: Mapped[str] = mapped_column(String(64), default="")
