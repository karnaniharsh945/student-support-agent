"""Application configuration, read from environment variables (and an optional .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


class ConfigurationError(Exception):
    """Raised when required configuration is missing or inconsistent."""


@dataclass(frozen=True)
class Settings:
    model_provider: str = "mock"          # mock | groq | openai_compatible
    model_name: str = ""
    groq_api_key: str = ""
    openai_compatible_base_url: str = ""
    openai_compatible_api_key: str = ""
    database_url: str = f"sqlite:///{ROOT / 'data' / 'student_support.db'}"
    embedding_model: str = "tfidf-sparse"
    max_agent_steps: int = 4
    llm_timeout_s: float = 30.0
    agent_deadline_s: float = 90.0
    bcrypt_rounds: int = 12               # lower only in tests/evaluation for speed
    session_ttl_hours: float = 8.0
    approval_ttl_hours: float = 72.0
    max_failed_logins: int = 5
    lockout_minutes: float = 5.0
    policy_path: Path = ROOT / "data" / "student_policy.md"
    seed_path: Path = ROOT / "data" / "sample_students.json"

    @classmethod
    def from_env(cls, load_env_file: bool = True) -> "Settings":
        if load_env_file:
            load_dotenv(ROOT / ".env", override=False)
        g = os.environ.get
        return cls(
            model_provider=(g("MODEL_PROVIDER") or "mock").strip().lower(),
            model_name=(g("MODEL_NAME") or "").strip(),
            groq_api_key=(g("GROQ_API_KEY") or "").strip(),
            openai_compatible_base_url=(g("OPENAI_COMPATIBLE_BASE_URL") or "").strip(),
            openai_compatible_api_key=(g("OPENAI_COMPATIBLE_API_KEY") or "").strip(),
            database_url=(g("DATABASE_URL") or cls.database_url),
            embedding_model=(g("EMBEDDING_MODEL") or cls.embedding_model),
            max_agent_steps=int(g("MAX_AGENT_STEPS") or cls.max_agent_steps),
            llm_timeout_s=float(g("LLM_TIMEOUT_SECONDS") or cls.llm_timeout_s),
        )
