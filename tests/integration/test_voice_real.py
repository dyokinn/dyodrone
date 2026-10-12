"""Real speech through the real Vosk model. Opt in with ``pytest -m voice``.

Needs ``pip install "dyodrone[voice]"``, the model (downloaded on first use, or
``DYODRONE_CACHE`` / a folder in ``DYODRONE_VOSK_MODEL``) and macOS ``say`` to
synthesise the test audio.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import wave

import pytest
from fakes import FakeController, FakeTimer, wait_for

pytestmark = pytest.mark.voice

pytest.importorskip("vosk")
pytestmark = [pytest.mark.voice, pytest.mark.skipif(shutil.which("say") is None, reason="needs macOS `say`")]

from dyodrone.core.voice import slice_commands  # noqa: E402
from dyodrone.gui.voice_engine import load_vosk_engine  # noqa: E402


def synthesize(tmp_path, text):
    """16 kHz mono PCM16 bytes of *text* spoken by the system voice, plus a second of silence."""
    out = tmp_path / "speech.wav"
    subprocess.run(["say", "-o", str(out), "--data-format=LEI16@16000", text], check=True)
    with wave.open(str(out)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (16000, 1, 2)
        return w.readframes(w.getnframes()) + b"\0\0" * 16000


@pytest.fixture(scope="module")
def engine():
    return load_vosk_engine(os.environ.get("DYODRONE_VOSK_MODEL"), progress=print)


def transcribe(engine, pcm):
    finals = []
    for i in range(0, len(pcm), 8000):
        finals.extend(engine.accept(pcm[i:i + 8000]).finals)
    return " ".join(finals)


@pytest.mark.parametrize(
    "spoken, expected",
    [
        ("takeoff ten", ["takeoff 10"]),
        ("takeoff ten forward five right ninety land", ["takeoff 10", "forward 5", "right 90", "land"]),
        ("altitude twenty five back two left forty five", ["altitude 25", "back 2", "left 45"]),
    ],
)
def test_spoken_sequences_become_the_expected_commands(tmp_path, engine, spoken, expected):
    text = transcribe(engine, synthesize(tmp_path, spoken))
    commands, _notes = slice_commands(text)
    assert commands == expected, f"heard {text!r}"


def test_through_the_session_audio_path(tmp_path, monkeypatch):
    from dyodrone.gui import session as session_module
    from dyodrone.gui.session import ConsoleSession

    FakeTimer.created = []
    monkeypatch.setattr(session_module, "create_controller", lambda *a, **k: FakeController())
    s = ConsoleSession("dyopilot", vosk_model=os.environ.get("DYODRONE_VOSK_MODEL"), timer_factory=FakeTimer)
    s.set_inputs(voice=True)
    assert wait_for(lambda: s.snapshot()["voice"]["status"] == "listening", timeout=120)
    pcm = synthesize(tmp_path, "takeoff ten forward five")
    for i in range(0, len(pcm), 8000):
        s.voice_audio(pcm[i:i + 8000])
    assert [p["command"] for p in s.snapshot()["voice"]["pending"]] == ["takeoff 10", "forward 5"]
    s.close()
