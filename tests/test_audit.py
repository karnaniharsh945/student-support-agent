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


def test_hash_chain_valid_then_detects_tampering(env):
    env.chat("S1001", "What is my current fee status?")
    env.chat("S1001", "What is the fee status for S1002?")
    ok = env.svc.audit.verify_chain_system()
    assert ok["ok"] and ok["checked"] >= 3 and len(ok["head_hash"]) == 64
    # a privileged attacker drops the append-only trigger and edits a row -> the chain still exposes it
    with env.db.session() as s:
        s.execute(text("DROP TRIGGER audit_events_no_update"))
        s.execute(text("UPDATE audit_events SET result='nothing happened' WHERE action='UNAUTHORIZED_ACCESS'"))
    bad = env.svc.audit.verify_chain_system()
    assert bad["ok"] is False and bad["first_broken_event_id"]


def test_hash_chain_detects_deleted_middle_row(env):
    for _ in range(4):
        env.svc.audit.record("TEST_EVENT")
    with env.db.session() as s:
        s.execute(text("DROP TRIGGER audit_events_no_delete"))
        s.execute(text("DELETE FROM audit_events WHERE id = 2"))
    assert env.svc.audit.verify_chain_system()["ok"] is False


def test_verify_requires_permission(env):
    import pytest
    from services.authorization import AuthorizationError
    with pytest.raises(AuthorizationError):
        env.svc.audit.verify_chain(env.ctx("S1001"))
    assert env.svc.audit.verify_chain(env.ctx("approver"))["ok"]
