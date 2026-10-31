"""Headless Streamlit smoke test (no browser)."""
import os
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_app_starts_without_exceptions(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/ui.db")
    monkeypatch.setenv("MODEL_PROVIDER", "mock")
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert at.text_input[0].label == "Username"        # login gate shown, nothing else
    html = " ".join(m.value for m in at.markdown)
    assert "ssa-bg" in html and "ssa-cat" in html and "ssa-mascot" in html      # animated cat background + mascot injected


def _login(at, user, pw):
    at.text_input[0].set_value(user)
    at.text_input[1].set_value(pw)
    next(b for b in at.button if b.label == "Sign in").click().run()
    return at


def test_student_login_and_chat(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/ui.db")
    monkeypatch.setenv("MODEL_PROVIDER", "mock")
    at = _login(AppTest.from_file(APP, default_timeout=60).run(), "aarav", "Aarav@2026")
    assert not at.exception and any("aarav" in m.value and "student" in m.value for m in at.sidebar.markdown)
    at.chat_input[0].set_value("What is my current fee status?").run()
    assert not at.exception and any("150,000" in m.markdown[0].value for m in at.chat_message)
    radio = at.sidebar.radio[0]
    assert "Approval queue" not in radio.options and "Audit log" not in radio.options      # student sees no staff pages


def test_wrong_password_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/ui.db")
    monkeypatch.setenv("MODEL_PROVIDER", "mock")
    at = _login(AppTest.from_file(APP, default_timeout=60).run(), "aarav", "nope")
    assert at.error and "Invalid username or password" in at.error[0].value


def test_approver_sees_queue(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/ui.db")
    monkeypatch.setenv("MODEL_PROVIDER", "mock")
    at = _login(AppTest.from_file(APP, default_timeout=60).run(), "approver", "Approver@2026")
    assert not at.exception and "Approval queue" in at.sidebar.radio[0].options


def test_admin_sees_redteam_and_audit_pages(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/ui.db")
    monkeypatch.setenv("MODEL_PROVIDER", "mock")
    at = _login(AppTest.from_file(APP, default_timeout=60).run(), "admin", "Admin@2026")
    assert "Red-team lab" in at.sidebar.radio[0].options
    for page in ("Red-team lab", "Audit log", "Approval queue"):
        at.sidebar.radio[0].set_value(page).run()
        assert not at.exception, page


def test_tour_page_renders_for_student_and_before_login(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/ui.db")
    monkeypatch.setenv("MODEL_PROVIDER", "mock")
    at = AppTest.from_file(APP, default_timeout=60).run()
    next(b for b in at.button if "project tour" in b.label.lower()).click().run()      # reachable before sign-in
    assert not at.exception and any("project tour" in m.value.lower() for m in at.markdown)
    at = _login(AppTest.from_file(APP, default_timeout=60).run(), "aarav", "Aarav@2026")
    at.sidebar.radio[0].set_value("Project tour").run()
    assert not at.exception and any("Listen to the project tour" in m.value for m in at.markdown)
