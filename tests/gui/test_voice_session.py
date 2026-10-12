"""Voice mode in the session: engine lifecycle, slicing, the cancel window, safety."""

from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest
from fakes import FakeController, FakeEngine, FakeTimer, FlyingController, wait_for

from dyodrone.gui import session as session_module
from dyodrone.gui.session import CONNECTED, ConsoleSession, SessionError
from dyodrone.gui.voice_engine import EngineUnavailable, SpeechResult


def heard(*texts, partial=""):
    return [SpeechResult(partial=partial, finals=[t]) for t in texts]


@pytest.fixture
def vrig(monkeypatch):
    """A connected session with a fake speech engine and manually fired timers."""
    FakeTimer.created = []
    vehicle = FakeController()
    engine = FakeEngine()
    monkeypatch.setattr(session_module, "create_controller", lambda *a, **k: vehicle)
    s = ConsoleSession("dyopilot", engine_factory=lambda progress: engine, timer_factory=FakeTimer, voice_delay=2.0)
    s.connect("sitl")
    assert wait_for(lambda: s.snapshot()["status"] == CONNECTED)
    s.set_inputs(voice=True)
    assert wait_for(lambda: s.snapshot()["voice"]["status"] == "listening")
    yield SimpleNamespace(session=s, vehicle=vehicle, engine=engine, timers=FakeTimer.created)
    s.close()


def say(rig, *texts):
    rig.engine.script.extend(heard(*texts))
    for _ in texts:
        rig.session.voice_audio(b"\0\0")


def pending(s):
    return [(p["id"], p["command"]) for p in s.snapshot()["voice"]["pending"]]


def log(s, kind):
    return [e["text"] for e in s.snapshot()["log"] if e["kind"] == kind]


def calls(vehicle):
    return [c for c in vehicle.calls if c[0] != "connect"]


# -- engine lifecycle ------------------------------------------------------


def test_turning_voice_on_loads_the_engine_then_listens(vrig):
    snap = vrig.session.snapshot()
    assert snap["inputs"]["voice"] is True and snap["voice"]["status"] == "listening"
    assert any("listening" in t for t in log(vrig.session, "sys"))


def test_an_unavailable_engine_turns_the_switch_back_off_with_a_reason(monkeypatch):
    def broken(progress):
        raise EngineUnavailable("Voice mode needs the optional 'vosk' package")

    s = ConsoleSession("dyopilot", engine_factory=broken)
    s.set_inputs(voice=True)
    assert wait_for(lambda: s.snapshot()["voice"]["status"] == "error")
    snap = s.snapshot()
    assert snap["inputs"]["voice"] is False and "vosk" in snap["voice"]["message"]
    assert any("Voice input unavailable" in t for t in log(s, "err"))
    s.close()


def test_progress_messages_from_the_engine_reach_the_log():
    def factory(progress):
        progress("Downloading the speech model …")
        return FakeEngine()

    s = ConsoleSession("dyopilot", engine_factory=factory)
    s.set_inputs(voice=True)
    assert wait_for(lambda: s.snapshot()["voice"]["status"] == "listening")
    assert "Downloading the speech model …" in log(s, "sys")
    s.close()


def test_switching_off_while_loading_discards_the_engine():
    gate, engine = threading.Event(), FakeEngine()

    def slow(progress):
        gate.wait(3)
        return engine

    s = ConsoleSession("dyopilot", engine_factory=slow)
    s.set_inputs(voice=True)
    assert s.snapshot()["voice"]["status"] == "loading"
    s.set_inputs(voice=False)
    gate.set()
    assert wait_for(lambda: engine.closed)
    assert s.snapshot()["voice"]["status"] == "off"
    s.close()


def test_switching_off_closes_the_engine_and_drops_pending(vrig):
    say(vrig, "forward five")
    assert pending(vrig.session)
    vrig.session.set_inputs(voice=False)
    assert vrig.engine.closed and pending(vrig.session) == []
    assert vrig.timers[0].cancelled
    assert vrig.session.snapshot()["voice"]["status"] == "off"


def test_audio_is_refused_while_voice_is_off_or_loading():
    s = ConsoleSession("dyopilot", engine_factory=lambda p: FakeEngine())
    with pytest.raises(SessionError, match="Voice input is off"):
        s.voice_audio(b"\0")
    gate = threading.Event()
    s2 = ConsoleSession("dyopilot", engine_factory=lambda p: (gate.wait(3), FakeEngine())[1])
    s2.set_inputs(voice=True)
    with pytest.raises(SessionError, match="still loading"):
        s2.voice_audio(b"\0")
    gate.set()
    s.close()
    s2.close()


# -- recognition -> pending -> run -----------------------------------------


def test_the_partial_transcript_is_exposed_while_speaking(vrig):
    vrig.engine.script.append(SpeechResult(partial="takeoff ten"))
    assert vrig.session.voice_audio(b"x")["partial"] == "takeoff ten"
    assert vrig.session.snapshot()["voice"]["partial"] == "takeoff ten"
    assert vrig.engine.chunks == [b"x"]


def test_a_spoken_sequence_becomes_pending_commands_with_a_countdown(vrig):
    say(vrig, "takeoff ten forward five right ninety")
    assert pending(vrig.session) == [(1, "takeoff 10"), (2, "forward 5"), (3, "right 90")]
    assert all(0 < p["remaining"] <= 2.0 for p in vrig.session.snapshot()["voice"]["pending"])
    assert [t.interval for t in vrig.timers] == [2.0] * 3 and all(t.started for t in vrig.timers)
    assert calls(vrig.vehicle) == []  # nothing has run yet
    assert 'heard: "takeoff ten forward five right ninety"' in log(vrig.session, "voice")


def test_pending_commands_run_in_order_when_their_timers_fire(vrig):
    say(vrig, "takeoff ten forward five")
    for timer in vrig.timers:
        timer.fire()
    assert wait_for(lambda: len(calls(vrig.vehicle)) == 2)
    assert calls(vrig.vehicle) == [("arm_and_takeoff", 10.0), ("move_forward", 5.0)]
    assert pending(vrig.session) == []
    assert ("cmd", "takeoff 10", "voice") in [(e["kind"], e["text"], e["source"]) for e in vrig.session.snapshot()["log"]]


def test_land_is_never_delayed(vrig):
    say(vrig, "land")
    assert vrig.timers == [] and pending(vrig.session) == []
    assert wait_for(lambda: ("land",) in vrig.vehicle.calls)


def test_a_cancelled_command_does_not_run(vrig):
    say(vrig, "forward five back two")
    vrig.session.voice_cancel(1)
    assert pending(vrig.session) == [(2, "back 2")] and vrig.timers[0].cancelled
    for timer in vrig.timers:
        timer.fire()
    assert wait_for(lambda: len(calls(vrig.vehicle)) == 1)
    assert calls(vrig.vehicle) == [("move_back", 2.0)]
    assert "cancelled: forward 5" in log(vrig.session, "voice")


def test_cancel_all_and_unknown_ids(vrig):
    say(vrig, "forward five back two")
    with pytest.raises(SessionError, match="No such pending"):
        vrig.session.voice_cancel(99)
    vrig.session.voice_cancel()
    assert pending(vrig.session) == [] and all(t.cancelled for t in vrig.timers)


def test_incomplete_speech_is_dropped_with_a_note(vrig):
    say(vrig, "forward")
    assert pending(vrig.session) == []
    assert any("heard 'forward' without a distance" in t for t in log(vrig.session, "sys"))


def test_unrelated_speech_is_logged_but_makes_no_commands(vrig):
    say(vrig, "hello there")
    assert pending(vrig.session) == []
    assert 'heard: "hello there"' in log(vrig.session, "voice")


def test_empty_results_are_ignored(vrig):
    vrig.engine.script.append(SpeechResult())
    vrig.session.voice_audio(b"x")
    assert log(vrig.session, "voice") == []


# -- safety ----------------------------------------------------------------


def test_emergency_land_drops_pending_voice_commands(vrig):
    say(vrig, "forward five")
    vrig.session.emergency_land()
    assert pending(vrig.session) == [] and vrig.timers[0].cancelled
    assert any("dropped 1 pending" in t for t in log(vrig.session, "voice"))


def test_disconnecting_drops_pending_voice_commands(vrig):
    say(vrig, "forward five")
    vrig.session.disconnect()
    assert pending(vrig.session) == []


def test_a_pending_command_that_fires_during_a_plan_is_refused_not_run(monkeypatch):
    FakeTimer.created = []
    vehicle = FlyingController(__import__("time").time)
    vehicle.stuck = True
    monkeypatch.setattr(session_module, "create_controller", lambda *a, **k: vehicle)
    s = ConsoleSession("dyopilot", plan_poll=0.05, plan_step_timeout=1000,
                       engine_factory=lambda p: FakeEngine(), timer_factory=FakeTimer)
    s.connect("sitl")
    assert wait_for(lambda: s.snapshot()["status"] == CONNECTED)
    s.set_inputs(voice=True, plan=True)
    assert wait_for(lambda: s.snapshot()["voice"]["status"] == "listening")
    s._engine.script.extend(heard("forward five"))
    s.voice_audio(b"x")
    s.plan_validate("takeoff 10")
    s.plan_run()
    assert wait_for(lambda: s.snapshot()["plan"]["state"] == "running")
    FakeTimer.created[0].fire()
    assert wait_for(lambda: any("not run" in t and "flight plan is running" in t for t in log(s, "err")))
    assert [c[0] for c in vehicle.calls if c[0] not in ("connect",)] == ["arm_and_takeoff"]
    s.close()


def test_a_command_that_fires_after_voice_was_switched_off_is_refused(vrig):
    say(vrig, "forward five")
    timer = vrig.timers[0]
    vrig.session.inputs["voice"] = False  # simulate the race: switch flips without clearing
    timer.cancelled = False
    timer.fire()
    assert wait_for(lambda: any("Voice input is off" in t for t in log(vrig.session, "err")))
    assert calls(vrig.vehicle) == []


def test_voice_quit_disconnects_after_the_delay(vrig):
    say(vrig, "quit")
    assert pending(vrig.session) == [(1, "quit")]
    vrig.timers[0].fire()
    assert wait_for(lambda: vrig.session.snapshot()["status"] == "disconnected")


def test_voice_commands_are_recorded_in_history(vrig):
    say(vrig, "takeoff ten")
    vrig.timers[0].fire()
    assert wait_for(lambda: vrig.session.snapshot()["history"] == 1)
