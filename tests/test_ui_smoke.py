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


def _login(at, user, pw):
    at.text_input[0].set_value(user)
    at.text_input[1].set_value(pw)
    at.button[0].click().run()
    return at


def test_student_login_and_chat(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/ui.db")
    monkeypatch.setenv("MODEL_PROVIDER", "mock")
    at = _login(AppTest.from_file(APP, default_timeout=60).run(), "aarav", "Aarav@2026")
    assert not at.exception and "aarav" in at.sidebar.success[0].value
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
