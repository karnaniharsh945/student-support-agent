from dataclasses import replace

import pytest

from config.settings import Settings
from services import redteam
from services.authorization import AuthorizationService

ST = replace(Settings.from_env(load_env_file=False), model_provider="mock")


def test_all_attacks_blocked_with_compromised_model():
    rep = redteam.run_redteam(ST)
    failed = [a["id"] for a in rep["attacks"] if not a["blocked"]]
    assert failed == [] and rep["metric"]["attacks_total"] == 15


def test_redteam_detects_a_broken_control(monkeypatch):
    """Test-the-tests: if ownership checks were removed, the red-team lab must report the attack as NOT blocked."""
    monkeypatch.setattr(AuthorizationService, "require_own_student_record",
                        lambda self, ctx, perm, target, **kw: target or ctx.student_id)
    res = redteam._run_attack(ST, redteam.ATTACKS[0])
    assert res["blocked"] is False


def test_redteam_detects_lenient_schema(monkeypatch):
    """If unknown tool fields were silently ignored (extra='ignore'), the smuggling attack must no longer count as blocked."""
    from tools.fees import FeeStatusInput
    monkeypatch.setitem(FeeStatusInput.model_config, "extra", "ignore")
    FeeStatusInput.model_rebuild(force=True)
    try:
        res = redteam._run_attack(ST, redteam.ATTACKS[2])
    finally:
        FeeStatusInput.model_config["extra"] = "forbid"
        FeeStatusInput.model_rebuild(force=True)
    assert res["blocked"] is False
