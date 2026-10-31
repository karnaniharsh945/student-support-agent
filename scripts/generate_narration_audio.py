"""Pre-render the narration script to an audio file with a local TTS engine.

Usage:  python scripts/generate_narration_audio.py [--engine espeak|pyttsx3|gtts] [--out assets/tour.mp3]

  espeak   offline; needs the `espeak-ng` program (apt install espeak-ng / brew install espeak-ng); robotic formant voice
  pyttsx3  offline; uses your operating system's voices (pip install pyttsx3)
  gtts     ONLINE (Google Translate TTS); pip install gTTS; most natural of the three, needs internet
MP3 output needs `ffmpeg`; without it a .wav is written instead.
The in-app tour ALSO speaks the same text with the browser's built-in speech synthesis (usually higher quality).
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.narration import full_script, word_count   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def to_mp3(wav: Path, out: Path) -> Path:
    if shutil.which("ffmpeg") and out.suffix == ".mp3":
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-codec:a", "libmp3lame", "-q:a", "5", str(out)], check=True)
        return out
    out = out.with_suffix(".wav")
    shutil.copy(wav, out)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="espeak", choices=["espeak", "pyttsx3", "gtts"])
    ap.add_argument("--out", default=str(ROOT / "assets" / "tour.mp3"))
    a = ap.parse_args()
    text, out = full_script(), Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "tour.wav"
        if a.engine == "espeak":
            exe = shutil.which("espeak-ng") or shutil.which("espeak")
            if not exe:
                sys.exit("espeak-ng not found. Install it (apt install espeak-ng) or choose another --engine.")
            subprocess.run([exe, "-v", "en-us+f3", "-s", "158", "-p", "52", "-w", str(wav), text], check=True)
        elif a.engine == "pyttsx3":
            import pyttsx3
            eng = pyttsx3.init(); eng.setProperty("rate", 165); eng.save_to_file(text, str(wav)); eng.runAndWait()
        else:
            from gtts import gTTS
            mp3 = Path(td) / "tour.mp3"; gTTS(text, lang="en").save(str(mp3))
            out = Path(shutil.copy(mp3, out.with_suffix(".mp3")))
            print(f"wrote {out} ({out.stat().st_size // 1024} KB, {word_count()} words, engine=gtts)"); return
        out = to_mp3(wav, out)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB, {word_count()} words, engine={a.engine})")


if __name__ == "__main__":
    main()
