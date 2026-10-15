"""Speech engine adapter: model lookup/download and the Vosk wrapper (with fakes)."""

from __future__ import annotations

import io
import json
import sys
import types
import zipfile

import pytest

from dyodrone.core.voice import VOCABULARY
from dyodrone.gui import voice_engine
from dyodrone.gui.voice_engine import (
    MODEL_NAME,
    EngineUnavailable,
    SpeechResult,
    VoskEngine,
    cache_dir,
    ensure_model,
    load_vosk_engine,
)


def test_cache_dir_honours_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("DYODRONE_CACHE", str(tmp_path))
    assert cache_dir() == tmp_path
    monkeypatch.delenv("DYODRONE_CACHE")
    assert cache_dir().parts[-2:] == (".cache", "dyodrone")


def test_an_explicit_model_folder_is_used_as_is(tmp_path):
    assert ensure_model(str(tmp_path)) == tmp_path


def test_a_missing_explicit_model_folder_is_an_error(tmp_path):
    with pytest.raises(EngineUnavailable, match="not found"):
        ensure_model(str(tmp_path / "nope"))


def test_a_cached_model_is_not_downloaded_again(monkeypatch, tmp_path):
    monkeypatch.setenv("DYODRONE_CACHE", str(tmp_path))
    (tmp_path / "vosk" / MODEL_NAME).mkdir(parents=True)
    monkeypatch.setattr(voice_engine.urllib.request, "urlopen", lambda *a, **k: pytest.fail("must not download"))
    assert ensure_model() == tmp_path / "vosk" / MODEL_NAME


class FakeResponse(io.BytesIO):
    def __init__(self, data, headers=None):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}
        self.headers.update(headers or {})

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def model_zip():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(f"{MODEL_NAME}/conf/model.conf", "x")
    return buffer.getvalue()


def fake_server(data, ranges=True, seen=None):
    """A urlopen replacement that answers HEAD, ranged GET and plain GET for *data*."""

    def urlopen(request, timeout=None):
        url = request if isinstance(request, str) else request.full_url
        method = "GET" if isinstance(request, str) else request.get_method()
        range_header = None if isinstance(request, str) else request.headers.get("Range")
        if seen is not None:
            seen.append((method, range_header, timeout))
        if method == "HEAD":
            return FakeResponse(b"", {"Content-Length": str(len(data)), "Accept-Ranges": "bytes" if ranges else "none"})
        if range_header:
            first, last = (int(x) for x in range_header.split("=")[1].split("-"))
            return FakeResponse(data[first:last + 1])
        return FakeResponse(data)

    return urlopen


def test_the_model_is_downloaded_unzipped_and_cached(monkeypatch, tmp_path):
    monkeypatch.setenv("DYODRONE_CACHE", str(tmp_path))
    seen = []
    monkeypatch.setattr(voice_engine.urllib.request, "urlopen", fake_server(model_zip(), ranges=False, seen=seen))
    messages = []
    path = ensure_model(progress=messages.append)
    assert (path / "conf" / "model.conf").exists() and path == tmp_path / "vosk" / MODEL_NAME
    assert all(timeout == 30 for _m, _r, timeout in seen)
    assert list((tmp_path / "vosk").iterdir()) == [path]  # temp files cleaned up


def test_a_server_that_supports_ranges_is_fetched_in_parallel_pieces(monkeypatch, tmp_path):
    monkeypatch.setenv("DYODRONE_CACHE", str(tmp_path))
    seen = []
    monkeypatch.setattr(voice_engine.urllib.request, "urlopen", fake_server(model_zip(), ranges=True, seen=seen))
    messages = []
    path = ensure_model(progress=messages.append)
    assert (path / "conf" / "model.conf").read_text() == "x"
    ranged = [r for m, r, _t in seen if r]
    assert len(ranged) > 1 and all(m == "GET" for m, r, _t in seen if r)  # several pieces, not one stream
    assert any("Downloading the speech model" in m for m in messages)


def test_ranged_download_reassembles_the_file_byte_for_byte(monkeypatch, tmp_path):
    data = bytes(range(256)) * 1000 + b"tail"
    monkeypatch.setattr(voice_engine.urllib.request, "urlopen", fake_server(data, ranges=True))
    target = tmp_path / "out.bin"
    voice_engine._download("http://example/x", target, lambda m: None)
    assert target.read_bytes() == data


def test_a_ranged_piece_is_retried_after_a_transient_error(monkeypatch, tmp_path):
    data = b"abcdefghij" * 5000
    server = fake_server(data, ranges=True)
    failures = {"n": 0}

    def flaky(request, timeout=None):
        if not isinstance(request, str) and request.headers.get("Range") and failures["n"] < 2:
            failures["n"] += 1
            raise OSError("connection reset")
        return server(request, timeout)

    monkeypatch.setattr(voice_engine.urllib.request, "urlopen", flaky)
    target = tmp_path / "out.bin"
    voice_engine._download("http://example/x", target, lambda m: None)
    assert target.read_bytes() == data and failures["n"] == 2


def test_a_server_without_head_support_still_downloads_by_streaming(monkeypatch, tmp_path):
    data = b"z" * 1000
    plain = fake_server(data, ranges=False)

    def no_head(request, timeout=None):
        if not isinstance(request, str) and request.get_method() == "HEAD":
            raise OSError("405")
        return plain(request, timeout)

    monkeypatch.setattr(voice_engine.urllib.request, "urlopen", no_head)
    target = tmp_path / "out.bin"
    voice_engine._download("http://example/x", target, lambda m: None)
    assert target.read_bytes() == data


def test_a_failed_download_explains_how_to_fix_it(monkeypatch, tmp_path):
    monkeypatch.setenv("DYODRONE_CACHE", str(tmp_path))

    def offline(*a, **k):
        raise OSError("network is unreachable")

    monkeypatch.setattr(voice_engine.urllib.request, "urlopen", offline)
    with pytest.raises(EngineUnavailable) as info:
        ensure_model()
    assert "network is unreachable" in str(info.value) and "--vosk-model" in str(info.value)
    assert not (tmp_path / "vosk" / MODEL_NAME).exists()


def test_vosk_missing_is_a_clear_actionable_error(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "vosk", None)  # makes `import vosk` raise ImportError
    with pytest.raises(EngineUnavailable) as info:
        VoskEngine(tmp_path)
    message = str(info.value)
    assert "'vosk' package" in message and sys.executable in message   # names the exact interpreter
    assert "-m pip install vosk" in message and ".[voice]" in message and "restart" in message


def install_fake_vosk(monkeypatch):
    log = {}

    class Recognizer:
        def __init__(self, model, rate, grammar):
            log.update(rate=rate, grammar=json.loads(grammar))
            self.final = False

        def AcceptWaveform(self, pcm):
            return self.final

        def Result(self):
            return json.dumps({"text": "takeoff ten"})

        def PartialResult(self):
            return json.dumps({"partial": "take"})

    module = types.ModuleType("vosk")
    module.SetLogLevel = lambda level: None
    module.Model = lambda path: log.update(model=path) or object()
    module.KaldiRecognizer = Recognizer
    monkeypatch.setitem(sys.modules, "vosk", module)
    return log


def test_the_recognizer_is_limited_to_the_cli_vocabulary_at_16khz(monkeypatch, tmp_path):
    log = install_fake_vosk(monkeypatch)
    VoskEngine(tmp_path)
    assert log["rate"] == 16000 and log["model"] == str(tmp_path)
    assert set(log["grammar"]) == set(VOCABULARY) | {"[unk]"}
    assert {"takeoff", "forward", "land"} <= set(log["grammar"])


def test_partial_and_final_results_are_mapped(monkeypatch, tmp_path):
    install_fake_vosk(monkeypatch)
    engine = VoskEngine(tmp_path)
    assert engine.accept(b"\0\0") == SpeechResult(partial="take", finals=[])
    engine._rec.final = True
    assert engine.accept(b"\0\0") == SpeechResult(partial="", finals=["takeoff ten"])
    engine.close()


def test_load_vosk_engine_combines_lookup_and_construction(monkeypatch, tmp_path):
    install_fake_vosk(monkeypatch)
    assert isinstance(load_vosk_engine(str(tmp_path)), VoskEngine)
