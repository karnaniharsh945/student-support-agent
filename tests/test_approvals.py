import threading

import pytest
from sqlalchemy import update

from database.models import ApprovalRequest
from services.approvals import ApprovalError
from services.authorization import AuthorizationError


def request(env, key="S1001", course="AIML501"):
    return env.svc.approvals.request_course_change(env.ctx(key), course, "because")["approval_id"]


def test_request_creates_pending_and_changes_nothing(env):
    rid = request(env)
    assert env.approval_status(rid) == "PENDING" and env.course_of("S1001") == "BDA502" and env.seats("AIML501") == 30


def test_request_by_course_name_and_validation(env):
    assert env.svc.approvals.request_course_change(env.ctx("S1001"), "machine learning")["to_course"] == "AIML501"
    for key, bad, cat in (("S1002", "AIML501", "same_course"), ("S1002", "DS503", "course_full"), ("S1002", "NOPE", "unknown_course")):
        with pytest.raises(ApprovalError) as e:
            env.svc.approvals.request_course_change(env.ctx(key), bad)
        assert e.value.category == cat


def test_one_pending_per_student_db_rule(env):
    request(env)
    again = env.svc.approvals.request_course_change(env.ctx("S1001"), "FIN504")
    assert again["duplicate"] is True
    with env.db.session() as s:
        assert s.query(ApprovalRequest).count() == 1


def test_approve_executes_once_and_adjusts_seats(env):
    rid = request(env)
    out = env.svc.approvals.decide(env.ctx("approver"), rid, "APPROVE", "ok")
    assert out.executed and env.course_of("S1001") == "AIML501" and env.seats("AIML501") == 29 and env.seats("BDA502") == 3
    again = env.svc.approvals.decide(env.ctx("approver"), rid, "APPROVE")
    assert not again.executed and env.seats("AIML501") == 29


def test_reject_never_executes(env):
    rid = request(env)
    assert env.svc.approvals.decide(env.ctx("approver"), rid, "REJECT", "no").status == "REJECTED"
    assert not env.svc.approvals.decide(env.ctx("approver"), rid, "APPROVE").executed
    assert env.course_of("S1001") == "BDA502"


def test_only_authorised_approver_can_decide(env):
    rid = request(env)
    for who in ("S1001", "S1002"):
        with pytest.raises(AuthorizationError):
            env.svc.approvals.decide(env.ctx(who), rid, "APPROVE")
    assert env.approval_status(rid) == "PENDING"


def test_requester_cannot_approve_own_request_even_with_approver_role(env):
    rid = request(env)
    appr = env.ctx("approver")
    with env.db.session() as s:                         # simulate a user who is both requester and approver
        s.execute(update(ApprovalRequest).where(ApprovalRequest.id == rid).values(requester_user_id=appr.user_id))
    with pytest.raises(AuthorizationError) as e:
        env.svc.approvals.decide(appr, rid, "APPROVE")
    assert e.value.reason == "self_approval_not_allowed" and env.approval_status(rid) == "PENDING"


def test_unknown_request_and_bad_decision(env):
    assert env.svc.approvals.decide(env.ctx("approver"), 999, "APPROVE").status == "NOT_FOUND"
    with pytest.raises(ValueError):
        env.svc.approvals.decide(env.ctx("approver"), 1, "MAYBE")


def test_expired_request_does_not_execute(env):
    rid = request(env)
    env.advance(env.settings.approval_ttl_hours + 1)
    out = env.svc.approvals.decide(env.ctx("approver"), rid, "APPROVE")
    assert out.status == "EXPIRED" and env.course_of("S1001") == "BDA502"
    assert env.audit("APPROVAL_EXPIRED")


def test_stale_request_does_not_execute(env):
    rid = request(env)
    from database.models import Student
    with env.db.session() as s:
        s.get(Student, "S1001").current_course = "FIN504"
    out = env.svc.approvals.decide(env.ctx("approver"), rid, "APPROVE")
    assert out.status == "STALE" and env.course_of("S1001") == "FIN504"


def test_failure_rolls_back_and_is_not_success(env):
    def fail(session, req, payload, approver):
        from database.models import Student
        session.get(Student, req.student_id).current_course = "FIN504"
        raise RuntimeError("boom")
    env.svc.approvals.executors["COURSE_CHANGE"] = fail
    rid = request(env)
    out = env.svc.approvals.decide(env.ctx("approver"), rid, "APPROVE")
    assert out.status == "FAILED" and not out.executed and env.course_of("S1001") == "BDA502"
    assert env.audit("SENSITIVE_ACTION_FAILED") and not env.audit("SENSITIVE_ACTION_EXECUTED")


def test_concurrent_double_approval_executes_at_most_once(env):
    rid = request(env)
    results = []
    def go(who):
        try:
            results.append(env.svc.approvals.decide(env.ctx(who), rid, "APPROVE"))
        except Exception as exc:                         # SQLite may raise 'database is locked' for the loser - still safe
            results.append(exc)
    ts = [threading.Thread(target=go, args=(w,)) for w in ("approver", "admin")]
    [t.start() for t in ts]; [t.join() for t in ts]
    executed = [r for r in results if getattr(r, "executed", False)]
    assert len(executed) <= 1 and env.seats("AIML501") == 30 - len(executed)
    assert len(env.audit("SENSITIVE_ACTION_EXECUTED")) == len(executed)


def test_llm_has_no_approval_tool(env):
    assert not [n for n in env.registry.names() if "approv" in n or "reject" in n or "execute" in n]
