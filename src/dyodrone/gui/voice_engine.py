"""Offline speech-to-text for voice mode (Vosk), behind a small interface.

The engine only turns 16 kHz mono PCM into words; slicing those words into
commands is :mod:`dyodrone.core.voice`. Vosk is an optional dependency
(``pip install "dyodrone[voice]"``) and its ~40 MB model is downloaded once to
``~/.cache/dyodrone/vosk`` (override with ``DYODRONE_CACHE`` or ``--vosk-model``).
Everything runs on this machine; no audio leaves it.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import urllib.request
import zipfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Optional

from dyodrone.core.voice import VOCABULARY

#: Audio format the page sends and the engines expect.
SAMPLE_RATE = 16000

MODEL_NAME = "vosk-model-small-en-us-0.15"
MODEL_URL = f"https://alphacephei.com/vosk/models/{MODEL_NAME}.zip"


class EngineUnavailable(RuntimeError):
    """Voice mode cannot start (Vosk missing, model not downloadable, …)."""


@dataclass
class SpeechResult:
    """What the engine heard in the latest chunk."""

    partial: str = ""  # words so far in the current utterance
    finals: List[str] = field(default_factory=list)  # utterances that just ended


class SpeechEngine(ABC):
    """Consumes PCM16 mono audio at :data:`SAMPLE_RATE` and reports words."""

    @abstractmethod
    def accept(self, pcm: bytes) -> SpeechResult:
        """Feed a chunk of little-endian 16-bit mono PCM."""

    def close(self) -> None:
        """Release the recognizer."""


def cache_dir() -> Path:
    """Where downloaded models live."""
    root = os.environ.get("DYODRONE_CACHE")
    return Path(root) if root else Path.home() / ".cache" / "dyodrone"


def _download(url: str, destination: Path, say: Callable[[str], None]) -> None:
    """Stream *url* to *destination*; a stalled connection fails after 30 s instead of hanging."""
    with urllib.request.urlopen(url, timeout=30) as response, open(str(destination), "wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        next_report = 10 * 1024 * 1024
        while True:
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if done >= next_report:
                say(f"Downloading the speech model … {done // (1024 * 1024)} of {total // (1024 * 1024)} MB")
                next_report += 10 * 1024 * 1024


def ensure_model(
    path: Optional[str] = None,
    progress: Optional[Callable[[str], None]] = None,
) -> Path:
    """Return the model directory, downloading :data:`MODEL_NAME` on first use.

    A *path* given by the user is used as-is (it must exist).
    """
    say = progress or (lambda _msg: None)
    if path:
        model = Path(path).expanduser()
        if not model.is_dir():
            raise EngineUnavailable(f"Speech model folder not found: {model}")
        return model

    target = cache_dir() / "vosk" / MODEL_NAME
    if target.is_dir():
        return target

    say(f"Downloading the speech model (~40 MB, one time) to {target} …")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(dir=str(target.parent)) as tmp:
            archive = Path(tmp) / "model.zip"
            _download(MODEL_URL, archive, say)
            with zipfile.ZipFile(str(archive)) as zf:
                zf.extractall(tmp)
            shutil.move(str(Path(tmp) / MODEL_NAME), str(target))
    except Exception as exc:  # noqa: BLE001
        raise EngineUnavailable(
            f"Could not download the speech model: {exc}. "
            f"Download {MODEL_URL}, unzip it, and start with --vosk-model <folder>."
        ) from exc
    return target


class VoskEngine(SpeechEngine):
    """Vosk recognizer restricted to the console keywords and number words."""

    def __init__(self, model_path: Path) -> None:
        try:
            import vosk
        except ImportError as exc:
            raise EngineUnavailable(
                "Voice mode needs the optional 'vosk' package: pip install \"dyodrone[voice]\""
            ) from exc
        vosk.SetLogLevel(-1)
        self._model = vosk.Model(str(model_path))
        grammar = json.dumps(list(VOCABULARY) + ["[unk]"])
        self._rec = vosk.KaldiRecognizer(self._model, SAMPLE_RATE, grammar)

    def accept(self, pcm: bytes) -> SpeechResult:
        if self._rec.AcceptWaveform(pcm):
            text = json.loads(self._rec.Result()).get("text", "").strip()
            return SpeechResult(partial="", finals=[text] if text else [])
        return SpeechResult(partial=json.loads(self._rec.PartialResult()).get("partial", ""))

    def close(self) -> None:
        self._rec = None
        self._model = None


def load_vosk_engine(
    model_path: Optional[str] = None,
    progress: Optional[Callable[[str], None]] = None,
) -> SpeechEngine:
    """Locate (or download) the model and build a :class:`VoskEngine`."""
    return VoskEngine(ensure_model(model_path, progress))
