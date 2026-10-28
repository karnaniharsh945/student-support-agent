# Privacy and approval rules implemented (Assignment 2 explanation)

**Identity.** Users log in with username + password (bcrypt hashes; lockout after 5 failures for 5 minutes; generic error
messages). The browser holds only an opaque random token; the server stores its SHA-256 and derives `RequestContext`
(user, role, linked student id) from it on every call. A student id typed in chat or supplied by the model is *never*
treated as identity.

**Authorization (two layers, both in backend code).**
1. Role permissions (`services/authorization.py::ROLE_PERMISSIONS`) - checked by the tool guard *before* a tool runs.
2. Record ownership - `require_own_student_record` returns the authenticated student's own id; queries are scoped to that id.
   A different id is denied, audited as `UNAUTHORIZED_ACCESS`, and returned to the model as `permission_denied`.
Approver/admin roles have no access to student fee/scholarship records. Memory is never consulted for authorization.

**Sensitive action: course change.** Stage 1 (student, via chat tool): validate course, seats, ownership -> create a `PENDING`
approval row (at most one pending per student, enforced by a partial unique index) -> **nothing is changed**.
Stage 2 (approver UI): only `approver`/`admin`, never the requester. One transaction: claim (`PENDING->PROCESSING`
compare-and-set) -> check expiry (72 h) -> reject, or re-validate current course/seat -> execute -> mark `EXECUTED`.
Outcomes that never execute: pending, rejected, expired, stale (record changed / seat gone), failed (rolled back, recorded as
`FAILED`), duplicate approval. The LLM has no approve/execute tool.

**Audit.** Append-only table (SQLite triggers block UPDATE/DELETE); fields: event id, timestamp, actor id/role, action, target
type/id, permission decision, approval id/decision, approver, execution status, result, error category. Details are
allow-listed and redacted; no passwords, OTPs, keys or fee amounts. Students cannot read it; approver/admin can.

**Memory privacy.** Only 4 allow-listed non-sensitive keys can be stored; any message containing a credential-like pattern
(password/OTP/PIN/token/API key/card/ID-number shapes) stores *nothing*, is redacted before reaching the LLM, the trace and the
audit trail, and the user is reminded not to share secrets.

**Would need more in a real deployment:** SSO/MFA and an identity provider; a server-side secret store; TLS and secure cookies;
a real database with row-level security and immutable (WORM) audit storage; rate limiting; PII-aware DLP; separation of
duties reviewed by the institution; formal penetration testing.
