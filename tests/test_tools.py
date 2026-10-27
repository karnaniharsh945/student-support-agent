import pytest

from agent.state import RequestContext

CTX = RequestContext("s", "S1001")


def test_fee_tool_returns_database_values(env):
    res, rec = env.registry.execute("get_fee_status", {}, CTX)
    assert res.ok and res.data["outstanding"] == 150000 and res.data["status"] == "PARTIALLY_PAID" and rec.ok


def test_scholarship_tool_none_on_record(env):
    res, _ = env.registry.execute("get_scholarship_status", {}, RequestContext("s", "S1003"))
    assert res.ok and res.data["status"] == "NOT_APPLIED"


def test_support_request_tool_creates_row(env):
    res, _ = env.registry.execute("create_support_request",
                                  {"category": "FEES", "description": "Receipt missing for my payment"}, CTX)
    assert res.ok and res.data["ticket"].startswith("SR-") and res.data["status"] == "OPEN"
    assert env.svc.support.list_for_student("S1001")[0]["category"] == "FEES"


@pytest.mark.parametrize("args", [{"category": "NOPE", "description": "long enough text"}, {"category": "FEES"},
                                  {"category": "FEES", "description": "short"}])
def test_invalid_arguments_rejected_before_execution(env, args):
    res, _ = env.registry.execute("create_support_request", args, CTX)
    assert not res.ok and res.error_code == "invalid_arguments"
    assert env.svc.support.list_for_student("S1001") == []


def test_unknown_tool_and_malformed_args(env):
    assert env.registry.execute("drop_tables", {}, CTX)[0].error_code == "unknown_tool"
    assert env.registry.execute("get_fee_status", "not a dict", CTX)[0].error_code == "invalid_arguments"
    assert env.registry.execute("get_fee_status", {"student_id": "x'; DROP TABLE students;--"}, CTX)[0].error_code == "invalid_arguments"


def test_missing_student_context(env):
    res, _ = env.registry.execute("get_fee_status", {}, RequestContext("s", None))
    assert res.error_code == "missing_student"


def test_tool_exception_is_sanitised(env):
    def boom(_): raise RuntimeError("secret /etc/passwd")
    env.svc.fees.get_fee_status = boom
    res, _ = env.registry.execute("get_fee_status", {}, CTX)
    assert res.error_code == "tool_error" and "passwd" not in res.user_message


def test_policy_tool_returns_evidence_metadata(env):
    res, _ = env.registry.execute("search_student_policy", {"query": "What is the late fee?"}, CTX)
    assert res.ok and res.evidence[0]["chunk_id"] == "policy-s3-c1" and "text" not in res.evidence[0]


def test_schemas_exported_for_llm(env):
    names = {s["function"]["name"] for s in env.registry.schemas()}
    assert {"get_fee_status", "get_scholarship_status", "create_support_request", "search_student_policy"} <= names
