from services.memory import MemoryService


def test_extracts_allowed_facts_only(env):
    mem = env.svc.memory
    cands = {c.key: c.value for c in mem.extract_candidates("My programme is PGDM (Big Data Analytics) and I prefer Hindi.")}
    assert cands == {"programme": "PGDM (Big Data Analytics)", "preferred_language": "hindi"}


def test_persists_across_service_instances(env):
    env.svc.memory.remember_from_message("S1001", "Please contact me via email", "sess-1")
    fresh = MemoryService(env.db)                       # new object == new session/process
    assert [(i.key, i.value) for i in fresh.list_items("S1001")] == [("contact_preference", "email")]


def test_update_and_delete(env):
    m = env.svc.memory
    m.upsert("S1001", "preferred_language", "english")
    first = m.list_items("S1001")[0]
    m.upsert("S1001", "preferred_language", "hindi")
    items = m.list_items("S1001")
    assert len(items) == 1 and items[0].value == "hindi" and items[0].updated_at >= first.created_at
    assert m.delete("S1001", "preferred_language") is True and m.list_items("S1001") == []


def test_memory_is_per_student(env):
    env.svc.memory.upsert("S1001", "programme", "A")
    assert env.svc.memory.list_items("S1002") == []


def test_sensitive_message_stores_nothing(env):
    r = env.svc.memory.remember_from_message("S1001", "My password is abc123 and I prefer Hindi", "s")
    assert r.stored == [] and r.blocked_reason == "sensitive_content" and env.svc.memory.list_items("S1001") == []


def test_disallowed_key_and_sensitive_value_refused(env):
    import pytest
    with pytest.raises(ValueError):
        env.svc.memory.upsert("S1001", "password", "x")
    with pytest.raises(ValueError):
        env.svc.memory.upsert("S1001", "programme", "my otp is 123456")


def test_relevance_selection(env):
    m = env.svc.memory
    m.upsert("S1001", "programme", "PGDM"); m.upsert("S1001", "contact_preference", "sms"); m.upsert("S1001", "preferred_language", "hindi")
    keys = lambda q: {i.key for i in m.get_relevant("S1001", q)}
    assert keys("What is the late fee?") == {"preferred_language"}
    assert keys("Which programme am I in?") == {"preferred_language", "programme"}
