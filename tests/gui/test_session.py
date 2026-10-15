"""ConsoleSession: connection state machine, command queue, console verbs, log."""

from __future__ import annotations

import pytest
from fakes import FakeController, wait_for

from dyodrone.core.commands import COMMAND_HELP
from dyodrone.core.factory import BackendUnavailable
from dyodrone.gui import session as session_module
from dyodrone.gui.session import (
    CONNECTED,
    CONNECTING,
    DISCONNECTED,
    ERROR,
    ConsoleSession,
    SessionError,
)


@pytest.fixture
def factory(monkeypatch):
    """Patch create_controller; tests choose what it returns via ``factory.controller``."""

    class Factory:
        controller = FakeController()
        raises = None
        calls = []

        def __call__(self, driver, target, connect=None, gcs_port=None, gcs_host="127.0.0.1"):
            self.calls.append((driver, target, connect, gcs_port))
            if self.raises is not None:
                raise self.raises
            return self.controller

    f = Factory()
    f.calls = []
    monkeypatch.setattr(session_module, "create_controller", f)
    return f


@pytest.fixture
def session(factory):
    s = ConsoleSession("dyopilot")
    yield s
    s.close()


def texts(s, kind=None):
    return [e["text"] for e in s.snapshot()["log"] if kind is None or e["kind"] == kind]


def connected(s):
    s.connect("sitl")
    assert wait_for(lambda: s.snapshot()["status"] == CONNECTED)


# -- construction ----------------------------------------------------------


def test_driver_is_validated():
    with pytest.raises(ValueError):
        ConsoleSession("ardupilot")


def test_driver_defaults_to_the_one_for_this_interpreter(monkeypatch):
    from dyodrone.core import factory

    monkeypatch.setattr(factory.sys, "version_info", (3, 7, 17))
    assert ConsoleSession().driver == "dronekit"
    monkeypatch.setattr(factory.sys, "version_info", (3, 12, 0))
    assert ConsoleSession().driver == "dyopilot"


def test_initial_state_is_disconnected_with_a_banner(session):
    snap = session.snapshot()
    assert snap["status"] == DISCONNECTED and snap["driver"] == "dyopilot" and snap["target"] == "sitl"
    assert snap["telemetry"] == [] and snap["details"] == []
    assert "Type 'help'" in snap["log"][0]["text"]


# -- connecting ------------------------------------------------------------


def test_connect_sitl_reaches_connected(session, factory):
    connected(session)
    assert factory.calls == [("dyopilot", "sitl", "tcp:127.0.0.1:5760", 14550)]
    assert "Connected: fake:0" in texts(session, "sys")
    snap = session.snapshot()
    assert snap["telemetry"][1] == "Mode: GUIDED"


def test_connect_pixhawk_passes_the_connection_string(session, factory):
    session.connect("pixhawk", "/dev/ttyUSB0")
    assert wait_for(lambda: session.snapshot()["status"] == CONNECTED)
    assert factory.calls == [("dyopilot", "pixhawk", "/dev/ttyUSB0", 0)]  # no proxy by default for a real board
    assert session.snapshot()["connection"] == "/dev/ttyUSB0"


def test_blank_pixhawk_connection_falls_back_to_the_default(session, factory):
    session.connect("pixhawk", "   ")
    assert wait_for(lambda: session.snapshot()["status"] == CONNECTED)
    assert factory.calls[0][2] == "tcp:127.0.0.1:5760"


def test_custom_gcs_port_is_forwarded(session, factory):
    session.connect("sitl", gcs_port=0)
    assert wait_for(lambda: session.snapshot()["status"] == CONNECTED)
    assert factory.calls[0][3] == 0


@pytest.mark.parametrize("kwargs", [{"target": "warp"}, {"target": "sitl", "gcs_port": 70000}, {"target": "sitl", "gcs_port": -1}])
def test_invalid_connect_arguments_are_rejected(session, kwargs):
    with pytest.raises(ValueError):
        session.connect(**kwargs)
    assert session.snapshot()["status"] == DISCONNECTED


def test_connect_failure_sets_error_and_cleans_up(session, factory):
    factory.controller = FakeController(connect_error=RuntimeError("boom"))
    session.connect("sitl")
    assert wait_for(lambda: session.snapshot()["status"] == ERROR)
    assert "Connection failed: boom" in texts(session, "err")
    assert factory.controller.closed  # a half-started simulator must not leak


def test_unavailable_backend_is_shown_as_an_error(session, factory):
    factory.raises = BackendUnavailable("Backend 'dronekit-sitl' requires Python 3.7")
    session.connect("sitl")
    assert wait_for(lambda: session.snapshot()["status"] == ERROR)
    assert "requires Python 3.7" in texts(session, "err")[0]


def test_can_reconnect_after_an_error(session, factory):
    factory.raises = RuntimeError("nope")
    session.connect("sitl")
    assert wait_for(lambda: session.snapshot()["status"] == ERROR)
    factory.raises = None
    connected(session)


def test_connect_while_connecting_or_connected_conflicts(session, factory):
    gate = {"release": False}
    original = factory.controller.connect

    def slow():
        wait_for(lambda: gate["release"], timeout=3)
        original()

    factory.controller.connect = slow
    session.connect("sitl")
    assert session.snapshot()["status"] == CONNECTING
    with pytest.raises(SessionError):
        session.connect("sitl")
    with pytest.raises(SessionError, match="in progress"):
        session.disconnect()
    gate["release"] = True
    assert wait_for(lambda: session.snapshot()["status"] == CONNECTED)
    with pytest.raises(SessionError):
        session.connect("sitl")


# -- disconnecting ---------------------------------------------------------


def test_disconnect_closes_the_controller(session, factory):
    connected(session)
    session.disconnect()
    assert wait_for(lambda: session.snapshot()["status"] == DISCONNECTED)
    assert factory.controller.closed
    assert "Disconnected." in texts(session, "sys")


def test_disconnect_when_idle_is_harmless(session):
    session.disconnect()
    assert session.snapshot()["status"] == DISCONNECTED


def test_close_is_synchronous(session, factory):
    connected(session)
    session.close()
    assert factory.controller.closed and session.snapshot()["status"] == DISCONNECTED


def test_disconnect_discards_queued_commands(session, factory):
    factory.controller = FakeController(block_takeoff=True)
    connected(session)
    session.submit("takeoff 5")
    assert wait_for(lambda: session.snapshot()["busy"] == "takeoff 5")
    session.submit("land")
    session.submit("forward 3")
    assert session.snapshot()["queued"] == 2
    session.disconnect()
    assert session.snapshot()["queued"] == 0
    factory.controller.release_takeoff.set()


# -- commands --------------------------------------------------------------


def test_commands_before_connecting_are_refused(session):
    session.submit("takeoff 5")
    assert texts(session, "cmd") == ["takeoff 5"]
    assert "Not connected. Use Connect." in texts(session, "err")


def test_commands_run_in_order_and_report_results(session, factory):
    connected(session)
    session.submit("takeoff 7")
    session.submit("forward 2")
    session.submit("land")
    assert wait_for(lambda: len(factory.controller.calls) >= 4)
    assert factory.controller.calls[1:] == [("arm_and_takeoff", 7.0), ("move_forward", 2.0), ("land",)]
    outs = texts(session, "out")
    assert outs[-3:] == ["Takeoff initiated to 7.0 m", "Moving forward 2.0 m", "Landing command sent"]


def test_a_long_command_is_reported_busy_and_blocks_the_queue(session, factory):
    factory.controller = FakeController(block_takeoff=True)
    connected(session)
    session.submit("takeoff 5")
    session.submit("land")
    assert wait_for(lambda: session.snapshot()["busy"] == "takeoff 5")
    assert session.snapshot()["queued"] == 1
    assert ("land",) not in factory.controller.calls
    factory.controller.release_takeoff.set()
    assert wait_for(lambda: ("land",) in factory.controller.calls)
    assert wait_for(lambda: session.snapshot()["busy"] == "")


@pytest.mark.parametrize("line", ["bogus", "takeoff", "takeoff x", "left"])
def test_bad_commands_are_logged_as_errors(session, factory, line):
    connected(session)
    session.submit(line)
    assert wait_for(lambda: len(texts(session, "err")) >= 1)
    assert factory.controller.calls == [("connect",)]


def test_help_lists_commands_without_a_connection(session):
    session.submit("help")
    out = texts(session, "out")[0]
    for line in COMMAND_HELP:
        assert line in out
    assert "info" in out and "clear" in out


def test_info_prints_the_snapshot_or_says_not_connected(session, factory):
    session.submit("info")
    assert "Not connected. Use Connect." in texts(session, "out")
    connected(session)
    session.submit("info")
    assert "Mode: GUIDED" in texts(session, "out")[-1]


def test_quit_disconnects(session, factory):
    connected(session)
    session.submit("quit")
    assert wait_for(lambda: session.snapshot()["status"] == DISCONNECTED)


def test_blank_lines_are_ignored(session):
    before = session.snapshot()["last_id"]
    session.submit("   ")
    assert session.snapshot()["last_id"] == before


# -- log -------------------------------------------------------------------


def test_snapshot_returns_only_entries_after_since(session):
    session.submit("help")
    first = session.snapshot()
    ids = [e["id"] for e in first["log"]]
    assert ids == sorted(ids) and first["last_id"] == ids[-1]
    assert session.snapshot(since=first["last_id"])["log"] == []
    session.submit("help")
    assert len(session.snapshot(since=first["last_id"])["log"]) == 2  # echo + output


def test_log_is_capped(factory):
    s = ConsoleSession("dyopilot", max_log=5)
    for _ in range(10):
        s.submit("help")
    snap = s.snapshot()
    assert len(snap["log"]) == 5 and snap["last_id"] > 5
    s.close()


def test_telemetry_errors_do_not_break_the_snapshot(session, factory):
    connected(session)

    def broken():
        raise RuntimeError("link lost")

    factory.controller.status_lines = broken
    assert "Telemetry unavailable: link lost" in session.snapshot()["telemetry"][0]
