"""handle_command: parsing and dispatch shared by the CLI and the web console."""

from __future__ import annotations

import pytest
from fakes import FakeController

from dyodrone.core.commands import COMMAND_HELP, handle_command


@pytest.fixture
def ctrl():
    return FakeController()


@pytest.mark.parametrize(
    "line, call, message",
    [
        ("takeoff 10", ("arm_and_takeoff", 10.0), "Takeoff initiated to 10.0 m"),
        ("altitude 15.5", ("set_altitude", 15.5), "Altitude set to 15.5 m"),
        ("forward 5", ("move_forward", 5.0), "Moving forward 5.0 m"),
        ("back 3", ("move_back", 3.0), "Moving back 3.0 m"),
        ("left 45", ("rotate_left", 45.0), "Rotating left 45.0°"),
        ("right 90", ("rotate_right", 90.0), "Rotating right 90.0°"),
        ("land", ("land",), "Landing command sent"),
    ],
)
def test_command_dispatches_to_controller(ctrl, line, call, message):
    exit_requested, text = handle_command(line, ctrl)
    assert (exit_requested, text) == (False, message)
    assert ctrl.calls == [call]


def test_verbs_are_case_insensitive(ctrl):
    handle_command("TAKEOFF 4", ctrl)
    assert ctrl.calls == [("arm_and_takeoff", 4.0)]


def test_empty_line_is_a_noop(ctrl):
    assert handle_command("", ctrl) == (False, "Awaiting command...")
    assert ctrl.calls == []


@pytest.mark.parametrize("line", ["quit", "exit", "QUIT"])
def test_quit_requests_exit(ctrl, line):
    assert handle_command(line, ctrl)[0] is True


@pytest.mark.parametrize(
    "line, message",
    [
        ("takeoff", "Usage: takeoff <altitude meters>"),
        ("takeoff 1 2", "Usage: takeoff <altitude meters>"),
        ("takeoff abc", "Altitude must be numeric"),
        ("altitude", "Usage: altitude <meters>"),
        ("altitude x", "Altitude must be numeric"),
        ("forward", "Usage: forward <meters>"),
        ("back x", "Distance must be numeric"),
        ("left", "Usage: left <degrees>"),
        ("right x", "Degrees must be numeric"),
        ("bogus", "Unknown command: bogus"),
    ],
)
def test_bad_input_is_reported_without_touching_the_vehicle(ctrl, line, message):
    assert handle_command(line, ctrl) == (False, message)
    assert ctrl.calls == []


def test_controller_errors_become_messages_not_exceptions(ctrl):
    def boom(_):
        raise RuntimeError("not armed")

    ctrl.arm_and_takeoff = boom
    assert handle_command("takeoff 5", ctrl) == (False, "Takeoff failed: not armed")


def test_help_text_lists_every_flight_command():
    text = "\n".join(COMMAND_HELP)
    for verb in ("takeoff", "altitude", "forward", "back", "left", "right", "land", "quit"):
        assert verb in text
