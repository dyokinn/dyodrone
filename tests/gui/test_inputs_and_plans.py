"""Runtime input switches, the flight-plan lock, emergency land and plan recording."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from fakes import FakeClock, FakeController, FlyingController, wait_for

from dyodrone.core.plan import PlanError, parse_plan
from dyodrone.gui import session as session_module
from dyodrone.gui.session import CONNECTED, ConsoleSession, SessionError


@pytest.fixture
def rig(monkeypatch):
    """A connected session over a simulated vehicle and a fake clock."""
    clock = FakeClock()
    vehicle = FlyingController(clock.time)
    monkeypatch.setattr(session_module, "create_controller", lambda *a, **k: vehicle)
    s = ConsoleSession("dyopilot", clock=clock.time, sleep=clock.sleep)
    s.connect("sitl")
    assert wait_for(lambda: s.snapshot()["status"] == CONNECTED)

    yield SimpleNamespace(session=s, vehicle=vehicle, clock=clock)
    s.close()


@pytest.fixture
def live(monkeypatch):
    """A connected session with a *stuck* vehicle on the real clock, so a plan stays running."""
    vehicle = FlyingController(time.time)
    vehicle.stuck = True
    monkeypatch.setattr(session_module, "create_controller", lambda *a, **k: vehicle)
    s = ConsoleSession("dyopilot", plan_poll=0.05, plan_step_timeout=1000)
    s.connect("sitl")
    assert wait_for(lambda: s.snapshot()["status"] == CONNECTED)
    yield SimpleNamespace(session=s, vehicle=vehicle)
    s.close()


def log(s, kind=None):
    return [(e["kind"], e["text"], e["source"]) for e in s.snapshot()["log"] if kind is None or e["kind"] == kind]


def calls(vehicle):
    return [c[0] for c in vehicle.calls if c[0] != "connect"]


# -- switches --------------------------------------------------------------


def test_default_switches_have_only_the_console_on(rig):
    assert rig.session.snapshot()["inputs"] == {"console": True, "plan": False, "voice": False}


def test_switches_can_be_flipped_at_runtime_and_are_logged(rig):
    out = rig.session.set_inputs(plan=True, voice=True)
    assert out == {"console": True, "plan": True, "voice": True}
    assert rig.session.snapshot()["inputs"] == out
    assert "Plan input turned on." in [t for _k, t, _s in log(rig.session, "sys")]
    rig.session.set_inputs(voice=False)
    assert rig.session.snapshot()["inputs"]["voice"] is False


def test_setting_a_switch_to_its_current_value_is_silent(rig):
    before = rig.session.snapshot()["last_id"]
    rig.session.set_inputs(console=True)
    assert rig.session.snapshot()["last_id"] == before


@pytest.mark.parametrize("flags", [{"gamepad": True}, {"voice": "yes"}, {"plan": 1}])
def test_invalid_switches_are_rejected_and_change_nothing(rig, flags):
    with pytest.raises(ValueError):
        rig.session.set_inputs(**flags)
    assert rig.session.snapshot()["inputs"]["plan"] is False


def test_console_commands_are_refused_while_the_console_is_off(rig):
    rig.session.set_inputs(console=False)
    with pytest.raises(SessionError, match="Console input is off"):
        rig.session.submit("takeoff 5")
    assert calls(rig.vehicle) == []
    rig.session.set_inputs(console=True)
    rig.session.submit("takeoff 5")
    assert wait_for(lambda: "arm_and_takeoff" in calls(rig.vehicle))


def test_voice_commands_need_the_voice_switch(rig):
    with pytest.raises(SessionError, match="Voice input is off"):
        rig.session.submit("land", source="voice")
    rig.session.set_inputs(voice=True)
    rig.session.submit("takeoff 6", source="voice")
    assert wait_for(lambda: "arm_and_takeoff" in calls(rig.vehicle))
    assert ("cmd", "takeoff 6", "voice") in log(rig.session)


def test_unknown_sources_are_rejected(rig):
    with pytest.raises(ValueError):
        rig.session.submit("land", source="telepathy")


def test_each_switch_is_independent(rig):
    rig.session.set_inputs(console=False, voice=True)
    rig.session.submit("land", source="voice")
    with pytest.raises(SessionError):
        rig.session.submit("land", source="console")


# -- plans -----------------------------------------------------------------


def test_validate_loads_a_plan_and_reports_its_steps(rig):
    view = rig.session.plan_validate("takeoff 10\nforward 5\n")
    assert [(v["command"], v["state"]) for v in view] == [("takeoff 10", "pending"), ("forward 5", "pending")]
    plan = rig.session.snapshot()["plan"]
    assert plan["state"] == "idle" and plan["loaded"] and plan["total"] == 2


def test_validate_rejects_bad_plans_with_line_numbers_and_keeps_the_old_one(rig):
    rig.session.plan_validate("land")
    with pytest.raises(PlanError) as info:
        rig.session.plan_validate("takeoff\nflip")
    assert [n for n, _ in info.value.errors] == [1, 2]
    assert rig.session.snapshot()["plan"]["total"] == 1


@pytest.mark.parametrize(
    "setup, message",
    [
        (lambda s: None, "Plan input is off"),
        (lambda s: s.set_inputs(plan=True), "No plan loaded"),
    ],
)
def test_a_plan_cannot_start_until_enabled_and_loaded(rig, setup, message):
    setup(rig.session)
    with pytest.raises(SessionError, match=message):
        rig.session.plan_run()


def test_a_plan_runs_closed_loop_to_completion(rig):
    rig.session.set_inputs(plan=True)
    rig.session.plan_validate("takeoff 10\nforward 20\nright 90\nland\n")
    rig.session.plan_run()
    assert wait_for(lambda: rig.session.snapshot()["plan"]["state"] == "done", timeout=5)
    plan = rig.session.snapshot()["plan"]
    assert [s["state"] for s in plan["steps"]] == ["done"] * 4
    assert calls(rig.vehicle) == ["arm_and_takeoff", "move_forward", "rotate_right", "land"]
    texts = [t for _k, t, _s in log(rig.session, "plan")]
    assert "[1/4] takeoff 10: sending" in texts and "plan: done — plan complete" in texts


def test_a_failing_plan_is_reported_and_logged_as_an_error(rig):
    rig.vehicle.stuck = True
    rig.session.set_inputs(plan=True)
    rig.session._plan_step_timeout = 10
    rig.session.plan_validate("takeoff 10")
    rig.session.plan_run()
    assert wait_for(lambda: rig.session.snapshot()["plan"]["state"] == "failed", timeout=5)
    assert any("timed out" in t for _k, t, _s in log(rig.session, "err"))


def test_console_and_voice_are_locked_while_a_plan_runs(live):
    live.session.set_inputs(plan=True, voice=True)
    live.session.plan_validate("takeoff 10")
    live.session.plan_run()
    assert wait_for(lambda: live.session.snapshot()["plan"]["state"] == "running")
    for source in ("console", "voice"):
        with pytest.raises(SessionError, match="flight plan is running"):
            live.session.submit("land", source=source)
    live.session.plan_stop()
    assert wait_for(lambda: live.session.snapshot()["plan"]["state"] == "stopped", timeout=5)
    live.session.submit("help")  # unlocked again


def test_turning_the_plan_switch_off_stops_a_running_plan(live):
    live.session.set_inputs(plan=True)
    live.session.plan_validate("takeoff 10")
    live.session.plan_run()
    assert wait_for(lambda: live.session.snapshot()["plan"]["state"] == "running")
    live.session.set_inputs(plan=False)
    assert wait_for(lambda: live.session.snapshot()["plan"]["state"] == "stopped", timeout=5)


def test_pause_resume_and_stop_need_a_running_plan(rig):
    for action in (rig.session.plan_pause, rig.session.plan_resume, rig.session.plan_stop):
        with pytest.raises(SessionError, match="No flight plan is running"):
            action()


def test_a_plan_cannot_be_replaced_or_started_twice_while_running(live):
    live.session.set_inputs(plan=True)
    live.session.plan_validate("takeoff 10")
    live.session.plan_run()
    assert wait_for(lambda: live.session.snapshot()["plan"]["state"] == "running")
    with pytest.raises(SessionError, match="already running"):
        live.session.plan_run()
    with pytest.raises(SessionError, match="stop it before loading"):
        live.session.plan_validate("land")
    live.session.plan_stop()


def test_a_plan_does_not_start_while_a_command_is_busy(monkeypatch):
    vehicle = FakeController(block_takeoff=True)
    monkeypatch.setattr(session_module, "create_controller", lambda *a, **k: vehicle)
    s = ConsoleSession("dyopilot")
    s.connect("sitl")
    assert wait_for(lambda: s.snapshot()["status"] == CONNECTED)
    s.set_inputs(plan=True)
    s.plan_validate("land")
    s.submit("takeoff 5")
    assert wait_for(lambda: s.snapshot()["busy"] == "takeoff 5")
    with pytest.raises(SessionError, match="current command"):
        s.plan_run()
    vehicle.release_takeoff.set()
    s.close()


def test_disconnecting_stops_the_plan(live):
    live.session.set_inputs(plan=True)
    live.session.plan_validate("takeoff 10")
    live.session.plan_run()
    assert wait_for(lambda: live.session.snapshot()["plan"]["state"] == "running")
    live.session.disconnect()
    assert wait_for(lambda: live.session.snapshot()["plan"]["state"] == "stopped", timeout=5)


# -- emergency -------------------------------------------------------------


def test_emergency_land_works_with_every_switch_off(rig):
    rig.session.set_inputs(console=False)
    rig.session.emergency_land()
    assert wait_for(lambda: "land" in calls(rig.vehicle))
    assert ("err", "EMERGENCY LAND", "emergency") in log(rig.session)


def test_emergency_land_requires_a_connection():
    with pytest.raises(SessionError, match="Not connected"):
        ConsoleSession("dyopilot").emergency_land()


def test_emergency_land_does_not_wait_behind_a_blocking_command(monkeypatch):
    vehicle = FakeController(block_takeoff=True)
    monkeypatch.setattr(session_module, "create_controller", lambda *a, **k: vehicle)
    s = ConsoleSession("dyopilot")
    s.connect("sitl")
    assert wait_for(lambda: s.snapshot()["status"] == CONNECTED)
    s.submit("takeoff 5")
    assert wait_for(lambda: s.snapshot()["busy"] == "takeoff 5")
    s.submit("forward 3")
    s.emergency_land()
    assert wait_for(lambda: ("land",) in vehicle.calls)
    assert s.snapshot()["queued"] == 0  # queued commands were dropped
    vehicle.release_takeoff.set()
    s.close()


def test_emergency_land_stops_a_running_plan(live):
    live.session.set_inputs(plan=True)
    live.session.plan_validate("takeoff 10")
    live.session.plan_run()
    assert wait_for(lambda: live.session.snapshot()["plan"]["state"] == "running")
    live.session.emergency_land()
    assert wait_for(lambda: live.session.snapshot()["plan"]["state"] == "stopped", timeout=5)
    assert wait_for(lambda: "land" in calls(live.vehicle))


# -- recording -------------------------------------------------------------


def test_history_records_successful_flight_commands_only(rig):
    s = rig.session
    for line in ("takeoff 10", "forward 5", "bogus", "right x", "info", "help"):
        s.submit(line)
    assert wait_for(lambda: len(log(s, "out")) >= 4 and s.snapshot()["busy"] == "")
    assert s.history_text().splitlines()[1:] == ["takeoff 10", "forward 5"]


def test_history_includes_voice_commands_but_not_plan_steps_or_emergency(rig):
    s = rig.session
    s.set_inputs(voice=True, plan=True)
    s.submit("takeoff 8", source="voice")
    assert wait_for(lambda: s.snapshot()["history"] == 1)
    s.plan_validate("forward 3")
    s.plan_run()
    assert wait_for(lambda: s.snapshot()["plan"]["state"] == "done", timeout=5)
    s.emergency_land()
    assert wait_for(lambda: "land" in calls(rig.vehicle))
    assert s.snapshot()["history"] == 1


def test_recorded_history_is_a_valid_plan(rig):
    s = rig.session
    s.submit("takeoff 10")
    s.submit("right 90")
    assert wait_for(lambda: s.snapshot()["history"] == 2)
    assert [st.command for st in parse_plan(s.history_text())] == ["takeoff 10", "right 90"]


def test_empty_history_is_an_empty_string_and_can_be_cleared(rig):
    assert rig.session.history_text() == ""
    rig.session.submit("land")
    assert wait_for(lambda: rig.session.snapshot()["history"] == 1)
    rig.session.clear_history()
    assert rig.session.history_text() == ""
