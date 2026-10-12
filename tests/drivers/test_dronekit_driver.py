"""DroneKit flight logic against a fake Vehicle (Python 3.7 environment only)."""

from __future__ import annotations

import math
import time
from types import SimpleNamespace

import pytest
from fakes import FakeTarget
from marks import needs_dronekit

pytestmark = [needs_dronekit, pytest.mark.dronekit]

pytest.importorskip("pymavlink")


class FakeVehicle:
    def __init__(self):
        self.is_armable = True
        self._armed = False
        self._mode = SimpleNamespace(name="STABILIZE")
        self.location = SimpleNamespace(
            global_relative_frame=SimpleNamespace(lat=-35.363261, lon=149.165230, alt=10.0),
            global_frame=SimpleNamespace(lat=-35.363261, lon=149.165230, alt=594.0),
        )
        self.attitude = SimpleNamespace(roll=0.0, pitch=0.0, yaw=0.0)
        self.battery = SimpleNamespace(voltage=12.2, current=1.0, level=97)
        self.velocity = (0.0, 0.0, 0.0)
        self.system_status = SimpleNamespace(state="ACTIVE")
        self.calls = []
        self.message_factory = SimpleNamespace(command_long_encode=lambda *a: ("encoded",) + a)
        self.closed = False

    armed = property(lambda self: self._armed, lambda self, v: setattr(self, "_armed", v))
    mode = property(lambda self: self._mode, lambda self, v: setattr(self, "_mode", v))

    def simple_takeoff(self, alt):
        self.calls.append(("simple_takeoff", alt))

    def simple_goto(self, target):
        self.calls.append(("simple_goto", target))

    def send_mavlink(self, msg):
        self.calls.append(("send_mavlink", msg))

    def close(self):
        self.closed = True


@pytest.fixture
def ctrl(monkeypatch):
    from dyodrone.drivers import dronekit_driver as driver

    monkeypatch.setattr(driver, "time", SimpleNamespace(time=time.time, sleep=lambda _s: None))
    c = driver.DroneKitController(FakeTarget())
    c._vehicle = FakeVehicle()
    return c


def test_vehicle_property_requires_a_connection():
    from dyodrone.drivers.dronekit_driver import DroneKitController

    with pytest.raises(RuntimeError, match="not been established"):
        DroneKitController(FakeTarget()).vehicle


def test_arm_and_takeoff_sets_guided_arms_then_takes_off(ctrl):
    ctrl.arm_and_takeoff(8)
    v = ctrl.vehicle
    assert v.mode.name == "GUIDED" and v.armed is True
    assert v.calls == [("simple_takeoff", 8)]


def test_arm_and_takeoff_rejects_non_positive_altitude(ctrl):
    with pytest.raises(ValueError):
        ctrl.arm_and_takeoff(0)


def test_land_enters_land_mode(ctrl):
    ctrl.land()
    assert ctrl.vehicle.mode.name == "LAND"


def test_motion_requires_an_armed_vehicle(ctrl):
    with pytest.raises(RuntimeError, match="armed"):
        ctrl.move_forward(5)


def test_forward_facing_north_goes_to_higher_latitude(ctrl):
    ctrl.vehicle.armed = True
    ctrl.move_forward(111.32)
    name, target = ctrl.vehicle.calls[-1]
    assert name == "simple_goto"
    assert target.lat == pytest.approx(-35.363261 + 0.001, abs=1e-6)
    assert target.lon == pytest.approx(149.165230, abs=1e-6)
    assert ctrl.vehicle.mode.name == "GUIDED"


def test_back_facing_east_goes_west(ctrl):
    ctrl.vehicle.armed = True
    ctrl.vehicle.attitude.yaw = math.pi / 2
    ctrl.move_back(100)
    target = ctrl.vehicle.calls[-1][1]
    assert target.lon < 149.165230


def test_set_altitude_keeps_position(ctrl):
    ctrl.vehicle.armed = True
    ctrl.set_altitude(20)
    target = ctrl.vehicle.calls[-1][1]
    assert (target.lat, target.lon, target.alt) == (-35.363261, 149.165230, 20)


@pytest.mark.parametrize("action, direction", [("rotate_right", 1), ("rotate_left", -1)])
def test_rotate_sends_condition_yaw(ctrl, action, direction):
    from pymavlink import mavutil

    ctrl.vehicle.armed = True
    getattr(ctrl, action)(45)
    _name, encoded = ctrl.vehicle.calls[-1]
    assert encoded[3] == mavutil.mavlink.MAV_CMD_CONDITION_YAW
    assert encoded[5:9] == (45, 0, direction, 1)


def test_status_lines_include_mode_and_armed(ctrl):
    ctrl.vehicle.armed = True
    text = "\n".join(ctrl.status_lines())
    assert "Armed: True" in text and "Mode: STABILIZE" in text and "voltage=12.2V" in text


def test_close_closes_the_vehicle(ctrl):
    vehicle = ctrl.vehicle
    ctrl.close()
    assert vehicle.closed and ctrl.active_connection is None


def test_connect_acquires_target_connects_and_starts_the_proxy(monkeypatch):
    from dyodrone.drivers import dronekit_driver as driver

    seen = {}
    vehicle = FakeVehicle()
    monkeypatch.setattr(driver, "connect", lambda conn, wait_ready: seen.update(conn=conn, wait=wait_ready) or vehicle)
    proxy = SimpleNamespace(started=None, gcs_host="127.0.0.1", gcs_port=14550,
                            start=lambda v: seen.update(started=v), stop=lambda: seen.update(stopped=True))
    target = FakeTarget("tcp:127.0.0.1:5999")
    ctrl = driver.DroneKitController(target, proxy)
    ctrl.connect()
    assert seen["conn"] == "tcp:127.0.0.1:5999" and seen["wait"] is True and seen["started"] is vehicle
    assert any("GCS Proxy" in line for line in ctrl.connection_details())
    ctrl.close()
    assert vehicle.closed and seen["stopped"] and target.log == ["acquire", "release"]


def test_failed_connect_releases_the_target(monkeypatch):
    from dyodrone.drivers import dronekit_driver as driver

    def refuse(conn, wait_ready):
        raise ConnectionRefusedError("no vehicle")

    monkeypatch.setattr(driver, "connect", refuse)
    target = FakeTarget()
    ctrl = driver.DroneKitController(target)
    with pytest.raises(ConnectionRefusedError):
        ctrl.connect()
    assert target.log == ["acquire", "release"]
