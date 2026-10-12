"""DyopilotSITLController / DyopilotPixhawkController lifecycle with fakes."""

from __future__ import annotations

import pytest
from fakes import FakeMaster, install_fake_dronekit_sitl
from marks import needs_pymavlink

pytestmark = [needs_pymavlink, pytest.mark.dyopilot]

from dyodrone.drivers import dyopilot_driver as driver  # noqa: E402
from dyodrone.drivers.dyopilot_pixhawk import DyopilotPixhawkController  # noqa: E402
from dyodrone.drivers.dyopilot_sitl import DyopilotSITLController  # noqa: E402


@pytest.fixture
def master(monkeypatch):
    fake = FakeMaster()
    monkeypatch.setattr(driver.mavutil, "mavlink_connection", lambda conn: fake)
    return fake


def test_sitl_starts_simulator_and_connects_to_it(monkeypatch, master):
    sitl_log = install_fake_dronekit_sitl(monkeypatch, "tcp:127.0.0.1:5999")
    ctrl = DyopilotSITLController(gcs_port=None, heartbeat_timeout=0.1)
    ctrl.connect()
    try:
        assert sitl_log == ["start"]
        assert ctrl.active_connection == "tcp:127.0.0.1:5999"
        assert ctrl.connection_details() == ["Connection: tcp:127.0.0.1:5999"]
    finally:
        ctrl.close()
    assert sitl_log == ["start", "stop"]


def test_sitl_connect_is_idempotent(monkeypatch, master):
    sitl_log = install_fake_dronekit_sitl(monkeypatch)
    ctrl = DyopilotSITLController(gcs_port=None, heartbeat_timeout=0.1)
    ctrl.connect()
    ctrl.connect()
    ctrl.close()
    assert sitl_log == ["start", "stop"]


def test_sitl_close_stops_proxy_then_connection_then_simulator(monkeypatch, master):
    sitl_log = install_fake_dronekit_sitl(monkeypatch)
    order = []
    ctrl = DyopilotSITLController(gcs_port=None, heartbeat_timeout=0.1)
    ctrl._proxy = type("P", (), {"stop": lambda self: order.append("proxy"), "forward": lambda self, b: None,
                                 "gcs_host": "127.0.0.1", "gcs_port": 14550})()
    master.close = lambda: order.append("connection")  # type: ignore[assignment]
    ctrl.connect()
    assert any("GCS Proxy" in line for line in ctrl.connection_details())
    ctrl.close()
    assert order == ["proxy", "connection"] and sitl_log[-1] == "stop"


def test_sitl_with_proxy_port_builds_a_proxy():
    ctrl = DyopilotSITLController(gcs_port=14550)
    assert ctrl._proxy is not None
    ctrl._proxy.stop()


def test_failed_heartbeat_leaves_nothing_running(monkeypatch):
    sitl_log = install_fake_dronekit_sitl(monkeypatch)
    monkeypatch.setattr(driver.mavutil, "mavlink_connection", lambda conn: FakeMaster(heartbeat=False))
    ctrl = DyopilotSITLController(gcs_port=None, heartbeat_timeout=0.1)
    with pytest.raises(TimeoutError):
        ctrl.connect()
    ctrl.close()  # the caller's cleanup path must still stop the simulator
    assert sitl_log == ["start", "stop"]


def test_pixhawk_requires_a_connection_string():
    with pytest.raises(ValueError, match="connection string is required"):
        DyopilotPixhawkController(connection="")


def test_pixhawk_connects_to_the_given_string_and_starts_no_simulator(monkeypatch, master):
    sitl_log = install_fake_dronekit_sitl(monkeypatch)
    ctrl = DyopilotPixhawkController(connection="/dev/ttyUSB0", heartbeat_timeout=0.1)
    ctrl.connect()
    try:
        assert ctrl.active_connection == "/dev/ttyUSB0"
        assert sitl_log == []
    finally:
        ctrl.close()
    assert master.closed
