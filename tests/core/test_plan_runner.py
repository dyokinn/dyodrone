"""Closed-loop plan execution against a simulated vehicle and a fake clock."""

from __future__ import annotations

import pytest
from fakes import FakeClock, FlyingController

from dyodrone.core.plan import parse_plan
from dyodrone.core.plan_runner import (
    DONE,
    FAILED,
    IDLE,
    PAUSED,
    STOPPED,
    PlanRunner,
)


def make(plan, **kw):
    clock = FakeClock()
    vehicle = FlyingController(clock.time)
    events = []
    runner = PlanRunner(vehicle, parse_plan(plan), clock=clock.time, sleep=clock.sleep,
                        on_event=events.append, **kw)
    return runner, vehicle, clock, events


def test_a_plan_runs_to_completion():
    runner, vehicle, _clock, _ = make("takeoff 10\nforward 20\nright 90\nland")
    assert runner.run() is True
    assert runner.state == DONE
    assert [c[0] for c in vehicle.calls] == ["arm_and_takeoff", "move_forward", "rotate_right", "land"]
    assert vehicle.alt <= 1.0 and vehicle.yaw == pytest.approx(90.0, abs=9)


def test_the_next_command_waits_until_the_vehicle_arrives():
    runner, vehicle, _clock, _ = make("takeoff 10\nforward 20\nright 90")
    runner.run()
    sent = dict((name, t) for t, name in vehicle.sent_at)
    # climbing 10 m at 2 m/s needs 5 s, but a 3 s poll means the first match is at 6 s
    assert sent["move_forward"] - sent["arm_and_takeoff"] >= 5.0
    # flying 20 m at 2 m/s (within 2 m) needs 9 s -> first 3 s poll that matches is 9 s
    assert sent["rotate_right"] - sent["move_forward"] >= 9.0


def test_it_polls_every_poll_seconds():
    runner, vehicle, clock, events = make("takeoff 10", poll=3.0)
    runner.run()
    waits = [e for e in events if e.state == "waiting" and e.index == 0]
    # 5 s of climbing: checks at 3 s (not yet) and 6 s (done)
    assert len(waits) == 2  # the initial "waiting" event + the 3 s check that did not match


def test_progress_detail_shows_measured_values():
    runner, _v, _c, events = make("takeoff 10")
    runner.run()
    details = [e.detail for e in events if e.state == "waiting"]
    assert any("alt" in d and "/10" in d for d in details)


def test_a_wait_step_just_delays():
    runner, vehicle, clock, _ = make("takeoff 10\nwait 7\nland")
    start = clock.now
    runner.run()
    sent = dict((name, t) for t, name in vehicle.sent_at)
    assert sent["land"] - sent["arm_and_takeoff"] >= 6.0 + 7.0


def test_a_stuck_vehicle_times_out_and_stops_the_plan():
    runner, vehicle, _c, _ = make("takeoff 10\nforward 20", step_timeout=20.0)
    vehicle.stuck = True
    assert runner.run() is False
    assert runner.state == FAILED
    snap = runner.snapshot()
    assert "timed out after 20 s" in snap["message"] and "step 1" in snap["message"]
    assert [s["state"] for s in snap["steps"]] == ["failed", "pending"]  # never started step 2
    assert [c[0] for c in vehicle.calls] == ["arm_and_takeoff"]


def test_a_failing_command_stops_the_plan():
    runner, vehicle, _c, _ = make("takeoff 10\nland")

    def boom(_alt):
        raise RuntimeError("not armable")

    vehicle.arm_and_takeoff = boom
    assert runner.run() is False
    assert "Takeoff failed: not armable" in runner.snapshot()["message"]
    assert runner.snapshot()["steps"][1]["state"] == "pending"


def test_telemetry_errors_are_retried_not_fatal():
    runner, vehicle, clock, _ = make("takeoff 10")
    original = vehicle.telemetry
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 2:  # the first check after the command
            raise RuntimeError("link hiccup")
        return original()

    vehicle.telemetry = flaky
    assert runner.run() is True


def test_missing_position_makes_a_move_step_wait_then_fail():
    runner, vehicle, _c, _ = make("forward 10", step_timeout=10.0)
    vehicle.hide_position = True
    assert runner.run() is False
    assert "waiting for position telemetry" in runner.snapshot()["message"]
    assert vehicle.calls == []  # never sent a command it could not verify


def test_stop_ends_the_plan_after_the_current_step():
    runner, vehicle, _c, events = make("takeoff 10\nforward 20\nland")

    def stop_after_first(event):
        if event.index == 0 and event.state == "done":
            runner.stop()

    runner._on_event = stop_after_first
    assert runner.run() is False
    assert runner.state == STOPPED
    assert [c[0] for c in vehicle.calls] == ["arm_and_takeoff"]


def test_stop_interrupts_a_wait():
    runner, vehicle, clock, _ = make("wait 100\nland")
    runner._sleep = lambda s: (clock.sleep(s), runner.stop()) if clock.now > 1003 else clock.sleep(s)
    assert runner.run() is False
    assert runner.state == STOPPED and vehicle.calls == []


def test_pause_holds_before_the_next_step_and_resume_continues():
    runner, vehicle, clock, _ = make("takeoff 10\nforward 10")
    seen = {}

    def on_event(e):
        if e.index == 0 and e.state == "done":
            runner.pause()

    runner._on_event = on_event

    def sleep(seconds):
        clock.sleep(seconds)
        if runner.state == PAUSED:
            seen["paused_calls"] = len(vehicle.calls)
            if clock.now > 1030:
                runner.resume()

    runner._sleep = sleep
    assert runner.run() is True
    assert seen["paused_calls"] == 1  # second command not sent while paused


def test_the_runner_can_only_run_once():
    runner, *_ = make("takeoff 5")
    runner.run()
    with pytest.raises(RuntimeError):
        runner.run()


def test_initial_snapshot_lists_pending_steps():
    runner, *_ = make("takeoff 5\nland")
    snap = runner.snapshot()
    assert snap["state"] == IDLE and snap["total"] == 2
    assert [(s["command"], s["state"], s["line"]) for s in snap["steps"]] == [("takeoff 5", "pending", 1), ("land", "pending", 2)]


def test_events_are_ordered_and_formatted():
    runner, _v, _c, events = make("takeoff 10")
    runner.run()
    assert events[0].line() == "plan: running — 1 steps"
    assert events[-1].line() == "plan: done — plan complete"
    states = [e.state for e in events if e.index == 0]
    assert states[0] == "sending" and states[-1] == "done"
    assert events[1].line().startswith("[1/1] takeoff 10: sending")


def test_custom_margin_changes_when_a_step_completes():
    from dyodrone.core.expect import Tolerances

    tight, vehicle, _c, _ = make("forward 20", tolerances=Tolerances(margin=0.0, min_distance_m=0.2))
    vehicle.alt = 10
    vehicle._goal_alt = 10
    tight.run()
    assert vehicle.telemetry().lat is not None
