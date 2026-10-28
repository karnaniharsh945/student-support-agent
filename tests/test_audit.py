import pytest
from sqlalchemy import text

from services.audit import clean_detail


def test_required_fields_and_actor_for_approval_flow(env):
    rid = env.svc.approvals.request_course_change(env.ctx("S1001"), "AIML501")["approval_id"]
    env.svc.approvals.decide(env.ctx("approver"), rid, "REJECT", "full")
    ev = {e["action"]: e for e in env.svc.audit.list_events(env.ctx("approver"), approval_request_id=rid)}
    assert ev["COURSE_CHANGE_REQUESTED"]["actor"] == "aarav" and ev["COURSE_CHANGE_REQUESTED"]["execution_status"] == "NOT_EXECUTED"
    rej = ev["APPROVAL_REJECTED"]
    assert rej["actor"] == "approver" and rej["approval_decision"] == "REJECTED" and rej["approver_user_id"] == env.ctx("approver").user_id
    assert rej["execution_status"] == "NOT_EXECUTED" and rej["event_id"] and rej["timestamp"]


@pytest.mark.parametrize("stmt", ["UPDATE audit_events SET result='x'", "DELETE FROM audit_events"])
def test_audit_is_append_only_at_database_level(env, stmt):
    env.svc.audit.record("TEST_EVENT")
    with pytest.raises(Exception, match="append-only"):
        with env.db.session() as s:
            s.execute(text(stmt))


def test_students_cannot_read_audit(env):
    from services.authorization import AuthorizationError
    with pytest.raises(AuthorizationError):
        env.svc.audit.list_events(env.ctx("S1001"))


def test_detail_is_allow_listed_and_redacted():
    d = clean_detail({"tool": "x", "password": "p", "total_fee": 450000, "note": "my otp is 123456"})
    assert set(d) == {"tool", "note"} and "123456" not in d["note"]


def test_own_access_failures_and_support_events_are_recorded(env):
    env.chat("S1001", "What is my current fee status?")
    env.chat("S1001", "Please raise a support request about my fee payment receipt not being received")
    actions = {e["action"] for e in env.audit()}
    assert {"LOGIN_SUCCESS", "FEE_STATUS_READ", "SUPPORT_REQUEST_CREATED"} <= actions
    env.set_llm(__import__("services.evaluation", fromlist=["x"]).FailingProvider())
    env.chat("S1001", "hello")
    env.svc.fees.get_fee_status = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))
    assert "LLM_FAILURE" in {e["action"] for e in env.audit()}


def test_no_secrets_in_audit_after_sensitive_chat(env):
    env.chat("S1001", "my password is Hunter2Pass! and OTP 482913")
    blob = str(env.audit())
    assert "Hunter2" not in blob and "482913" not in blob and "SENSITIVE_INPUT_NOT_STORED" in blob
