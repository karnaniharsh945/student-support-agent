"""Authentication: bcrypt password verification, server-side sessions, lockout, audit.

The browser keeps only an opaque random token. Identity (user id, role, linked student id) is always looked up
server-side from that token, so the frontend is never the source of truth for who is signed in.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

import bcrypt
from sqlalchemy import select

from agent.state import RequestContext
from config.settings import Settings
from database.connection import Database
from database.initialization import hash_password
from database.models import AuthSession, User
from services.audit import AuditService

_DUMMY_HASH = bcrypt.hashpw(b"dummy-password", bcrypt.gensalt(rounds=4)).decode()   # equalises timing for unknown users
MAX_PASSWORD_BYTES = 72                                                             # bcrypt limit


class AuthenticationError(Exception):
    """Authentication failed. The message is intentionally generic (no user enumeration)."""

    def __init__(self, reason: str = "invalid_credentials", message: str = "Invalid username or password."):
        super().__init__(reason)
        self.reason, self.message = reason, message


def _naive_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthService:
    def __init__(self, db: Database, audit: AuditService, settings: Settings,
                 clock: Callable[[], datetime] = _naive_utc):
        self.db, self.audit, self.settings, self.clock = db, audit, settings, clock

    # ---- users -----------------------------------------------------------------------------
    def create_user(self, username: str, password: str, role: str, student_id: str | None = None) -> None:
        if len(password.encode()) > MAX_PASSWORD_BYTES or len(password) < 8:
            raise ValueError("password must be 8-72 bytes")
        with self.db.session() as s:
            s.add(User(username=username, password_hash=hash_password(password, self.settings.bcrypt_rounds),
                       role=role, student_id=student_id))

    # ---- login / logout ----------------------------------------------------------------------
    def login(self, username: str, password: str) -> str:
        """Return a new session token or raise AuthenticationError. Every outcome is audited."""
        now = self.clock()
        pw = (password or "").encode("utf-8")
        failure: AuthenticationError | None = None
        token = ""
        with self.db.session() as s:
            user = s.scalar(select(User).where(User.username == (username or "").strip().lower()))
            if user is not None and user.locked_until and user.locked_until > now:
                self.audit.record("LOGIN_FAILED", actor_username=user.username, decision="DENIED", result="blocked",
                                  error_category="account_locked", detail={"username": user.username}, session=s)
                failure = AuthenticationError("account_locked", "Too many failed attempts. Try again later.")
            else:
                ok = False
                if len(pw) <= MAX_PASSWORD_BYTES:
                    ok = bcrypt.checkpw(pw, (user.password_hash if user else _DUMMY_HASH).encode()) \
                        and user is not None and user.is_active
                if ok:
                    user.failed_attempts, user.locked_until = 0, None
                    token = secrets.token_urlsafe(32)
                    s.add(AuthSession(token_hash=_hash_token(token), user_id=user.id, created_at=now,
                                      expires_at=now + timedelta(hours=self.settings.session_ttl_hours)))
                    self.audit.record("LOGIN_SUCCESS", actor_user_id=user.id, actor_username=user.username,
                                      actor_role=user.role, decision="ALLOWED", result="success", session=s)
                else:
                    if user is not None:
                        user.failed_attempts += 1
                        if user.failed_attempts >= self.settings.max_failed_logins:
                            user.locked_until = now + timedelta(minutes=self.settings.lockout_minutes)
                            user.failed_attempts = 0
                    self.audit.record("LOGIN_FAILED", actor_username=(username or "")[:50], decision="DENIED",
                                      result="failure", error_category="invalid_credentials",
                                      detail={"username": (username or "")[:50]}, session=s)
                    failure = AuthenticationError()
        if failure is not None:          # raised only after the transaction committed, so counters/audit persist
            raise failure
        return token

    def logout(self, token: str) -> None:
        with self.db.session() as s:
            sess = s.get(AuthSession, _hash_token(token or ""))
            if sess is not None and not sess.revoked:
                sess.revoked = True
                user = s.get(User, sess.user_id)
                self.audit.record("LOGOUT", actor_user_id=user.id, actor_username=user.username, actor_role=user.role,
                                  decision="ALLOWED", result="success", session=s)

    # ---- identity resolution (the ONLY way to obtain an authenticated RequestContext) ---------
    def context_from_token(self, token: str | None) -> RequestContext:
        if not token:
            raise AuthenticationError("no_session", "Please sign in.")
        with self.db.session() as s:
            sess = s.get(AuthSession, _hash_token(token))
            if sess is None or sess.revoked or sess.expires_at <= self.clock():
                raise AuthenticationError("invalid_session", "Your session is invalid or has expired. Please sign in again.")
            user = s.get(User, sess.user_id)
            if user is None or not user.is_active:
                raise AuthenticationError("invalid_session", "Your session is invalid or has expired. Please sign in again.")
            return RequestContext(session_id=sess.token_hash[:16], student_id=user.student_id, user_id=user.id,
                                  username=user.username, role=user.role, authenticated=True)
