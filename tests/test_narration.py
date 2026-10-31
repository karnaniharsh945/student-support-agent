import re
from pathlib import Path

from services import redteam
from services.narration import full_script, load_sections, word_count

ROOT = Path(__file__).resolve().parent.parent


def test_sections_parsed_and_comments_not_spoken():
    sections = load_sections()
    assert len(sections) >= 10 and sections[0].title == "Welcome"
    assert "<!--" not in full_script() and "single source" not in full_script()


def test_script_covers_every_headline_feature():
    text = full_script().lower()
    for kw in ("agent loop", "tools", "policy", "citation", "memory", "bcrypt", "approv", "risk advisor", "audit",
               "hash", "red team", "hostile", "baseline", "mock", "synthetic", "unavailable"):
        assert kw in text, kw


def test_script_is_speakable_plain_text():
    text = full_script()
    assert not re.search(r"[#*`_\[\]{}<>|]", text) and not re.search(r"\d", text)     # numbers written as words, no markup
    assert 300 <= word_count() <= 1000


def test_narration_claims_match_the_real_red_team_catalogue():
    total = len(redteam.ATTACKS) + 3                  # + flood, endless loop, memory poisoning
    assert total == 15 and "fifteen" in full_script().lower()


def test_ui_assets_and_audio_present():
    for f in ("cat_bg.jpg", "cat_mascot.png", "tour.mp3"):
        assert (ROOT / "assets" / f).stat().st_size > 10_000, f


def test_narration_audio_script_runs_help():
    import subprocess, sys
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_narration_audio.py"), "--help"], capture_output=True, text=True)
    assert out.returncode == 0 and "espeak" in out.stdout
