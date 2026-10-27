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
