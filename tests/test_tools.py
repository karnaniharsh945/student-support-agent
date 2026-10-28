import pytest

from agent.state import RequestContext


def test_fee_tool_returns_database_values(env):
    res, rec = env.registry.execute("get_fee_status", {}, env.ctx("S1001"))
    assert res.ok and res.data["outstanding"] == 150000 and res.data["status"] == "PARTIALLY_PAID" and rec.ok


def test_scholarship_tool_none_on_record(env):
    res, _ = env.registry.execute("get_scholarship_status", {}, env.ctx("S1003"))
    assert res.ok and res.data["status"] == "NOT_APPLIED"


def test_support_request_tool_creates_row(env):
    res, _ = env.registry.execute("create_support_request",
                                  {"category": "FEES", "description": "Receipt missing for my payment"}, env.ctx("S1001"))
    assert res.ok and res.data["ticket"].startswith("SR-") and res.data["status"] == "OPEN"
    assert env.svc.support.list_for_student(env.ctx("S1001"))[0]["category"] == "FEES"


@pytest.mark.parametrize("args", [{"category": "NOPE", "description": "long enough text"}, {"category": "FEES"},
                                  {"category": "FEES", "description": "short"}])
def test_invalid_arguments_rejected_before_execution(env, args):
    res, _ = env.registry.execute("create_support_request", args, env.ctx("S1001"))
    assert not res.ok and res.error_code == "invalid_arguments"
    assert env.svc.support.list_for_student(env.ctx("S1001")) == []


def test_unknown_tool_and_malformed_args(env):
    assert env.registry.execute("drop_tables", {}, env.ctx("S1001"))[0].error_code == "unknown_tool"
    assert env.registry.execute("get_fee_status", "not a dict", env.ctx("S1001"))[0].error_code == "invalid_arguments"
    assert env.registry.execute("get_fee_status", {"student_id": "x'; DROP TABLE students;--"}, env.ctx("S1001"))[0].error_code == "invalid_arguments"


def test_non_student_has_no_fee_tool_access(env):
    res, _ = env.registry.execute("get_fee_status", {}, env.ctx("approver"))
    assert res.error_code == "permission_denied"


def test_tool_exception_is_sanitised(env):
    def boom(*a, **k): raise RuntimeError("secret /etc/passwd")
    env.svc.fees.get_fee_status = boom
    res, _ = env.registry.execute("get_fee_status", {}, env.ctx("S1001"))
    assert res.error_code == "tool_error" and "passwd" not in res.user_message


def test_policy_tool_returns_evidence_metadata(env):
    res, _ = env.registry.execute("search_student_policy", {"query": "What is the late fee?"}, env.ctx("S1001"))
    assert res.ok and res.evidence[0]["chunk_id"] == "policy-s3-c1" and "text" not in res.evidence[0]


def test_schemas_exported_for_llm(env):
    names = {s["function"]["name"] for s in env.registry.schemas()}
    assert {"get_fee_status", "get_scholarship_status", "create_support_request", "search_student_policy"} <= names
