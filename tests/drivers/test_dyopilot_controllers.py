"""DyopilotController lifecycle: connect, cleanup order, targets, proxy."""

from __future__ import annotations

import pytest
from fakes import FakeMaster, FakeTarget, install_fake_dronekit_sitl
from marks import needs_pymavlink

pytestmark = [needs_pymavlink, pytest.mark.dyopilot]

from dyodrone.core.targets import ExternalTarget, SitlTarget  # noqa: E402
from dyodrone.drivers import dyopilot_driver as driver  # noqa: E402
from dyodrone.drivers.dyopilot_driver import DyopilotController  # noqa: E402


@pytest.fixture
def master(monkeypatch):
    fake = FakeMaster()
    monkeypatch.setattr(driver.mavutil, "mavlink_connection", lambda conn: fake)
    return fake


class FakeProxy:
    gcs_host, gcs_port = "127.0.0.1", 14550

    def __init__(self, log):
        self.log = log

    def forward(self, _frame):
        pass

    def stop(self):
        self.log.append("proxy.stop")


def test_connect_acquires_the_target_and_connects_to_its_string(master):
    target = FakeTarget("tcp:127.0.0.1:5999")
    ctrl = DyopilotController(target, heartbeat_timeout=0.1)
    ctrl.connect()
    try:
        assert ctrl.active_connection == "tcp:127.0.0.1:5999"
        assert target.log == ["acquire"]
        assert ctrl.connection_details() == ["Connection: tcp:127.0.0.1:5999"]
    finally:
        ctrl.close()
    assert target.log == ["acquire", "release"]


def test_connect_is_idempotent(master):
    target = FakeTarget()
    ctrl = DyopilotController(target, heartbeat_timeout=0.1)
    ctrl.connect()
    ctrl.connect()
    ctrl.close()
    assert target.log == ["acquire", "release"]


def test_close_stops_proxy_then_connection_then_target(master):
    order = []
    master.close = lambda: order.append("connection")  # type: ignore[assignment]
    ctrl = DyopilotController(FakeTarget(log=order), FakeProxy(order), heartbeat_timeout=0.1)
    ctrl.connect()
    assert any("GCS Proxy: → 127.0.0.1:14550" in line for line in ctrl.connection_details())
    ctrl.close()
    assert order == ["acquire", "proxy.stop", "connection", "release"]


def test_failed_heartbeat_cleans_up_without_a_close_call(monkeypatch):
    monkeypatch.setattr(driver.mavutil, "mavlink_connection", lambda conn: FakeMaster(heartbeat=False))
    target = FakeTarget()
    ctrl = DyopilotController(target, heartbeat_timeout=0.1)
    with pytest.raises(TimeoutError):
        ctrl.connect()
    assert target.log == ["acquire", "release"]  # simulator stopped, nothing leaked
    assert ctrl._master is None and ctrl.active_connection is None


def test_a_target_that_cannot_start_leaves_nothing_behind(master):
    class Broken(FakeTarget):
        def acquire(self):
            raise RuntimeError("no simulator binary")

    target = Broken()
    ctrl = DyopilotController(target)
    with pytest.raises(RuntimeError, match="no simulator"):
        ctrl.connect()
    assert target.log == ["release"]


def test_sitl_target_starts_and_stops_the_simulator(monkeypatch, master):
    sitl_log = install_fake_dronekit_sitl(monkeypatch, "tcp:127.0.0.1:5999")
    ctrl = DyopilotController(SitlTarget(), heartbeat_timeout=0.1)
    ctrl.connect()
    assert sitl_log == ["start"] and ctrl.active_connection == "tcp:127.0.0.1:5999"
    ctrl.close()
    assert sitl_log == ["start", "stop"]


def test_external_target_starts_no_simulator(monkeypatch, master):
    sitl_log = install_fake_dronekit_sitl(monkeypatch)
    ctrl = DyopilotController(ExternalTarget("/dev/ttyUSB0"), heartbeat_timeout=0.1)
    ctrl.connect()
    try:
        assert ctrl.active_connection == "/dev/ttyUSB0" and sitl_log == []
    finally:
        ctrl.close()
    assert master.closed


def test_close_without_connect_is_safe():
    target = FakeTarget()
    DyopilotController(target).close()
    assert target.log == ["release"]
