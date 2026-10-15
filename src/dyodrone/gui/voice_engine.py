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
import sys
import tempfile
import threading
import urllib.request
import zipfile
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
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
    """Download *url* to *destination*.

    The model host throttles a single connection to a crawl after the first few
    megabytes, so when it supports byte ranges the file is fetched in parallel
    pieces (about ten times faster). Otherwise it is streamed on one connection.
    Either way a stalled connection fails after 30 s instead of hanging.
    """
    size, ranged = 0, False
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=30) as head:
            size = int(head.headers.get("Content-Length") or 0)
            ranged = "bytes" in (head.headers.get("Accept-Ranges") or "").lower()
    except Exception:  # noqa: BLE001 - fall back to a plain stream
        pass
    if ranged and size > 0:
        _download_ranges(url, destination, size, say)
    else:
        _download_stream(url, destination, say)


def _download_stream(url: str, destination: Path, say: Callable[[str], None]) -> None:
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


def _download_ranges(url: str, destination: Path, size: int, say: Callable[[str], None],
                     pieces: int = 16, workers: int = 8) -> None:
    step = (size + pieces - 1) // pieces
    ranges = [(i * step, min(size, (i + 1) * step) - 1) for i in range(pieces) if i * step < size]
    with open(str(destination), "wb") as out:
        out.truncate(size)
    lock = threading.Lock()
    progress = {"done": 0, "next": 10}

    def fetch(piece):
        first, last = piece
        for attempt in range(3):
            try:
                request = urllib.request.Request(url, headers={"Range": f"bytes={first}-{last}"})
                with urllib.request.urlopen(request, timeout=30) as response:
                    data = response.read()
                if len(data) != last - first + 1:
                    raise OSError(f"short read for bytes {first}-{last}")
                break
            except Exception:  # noqa: BLE001
                if attempt == 2:
                    raise
        with lock:
            with open(str(destination), "r+b") as out:
                out.seek(first)
                out.write(data)
            progress["done"] += len(data)
            percent = progress["done"] * 100 // size
            if percent >= progress["next"]:
                say(f"Downloading the speech model … {percent}% of {size // (1024 * 1024)} MB")
                progress["next"] = percent // 10 * 10 + 10

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for future in [pool.submit(fetch, r) for r in ranges]:
            future.result()


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
                "Voice mode needs the optional 'vosk' package, which is not installed in this "
                f"environment ({sys.executable}). Install it with: {sys.executable} -m pip install vosk "
                "(or, from the repo, pip install -e \".[voice]\"), then restart dyodrone-gui."
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
