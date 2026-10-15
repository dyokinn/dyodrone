"""dyopilot flight logic (pymavlink) against a fake MAVLink connection."""

from __future__ import annotations

import math
import time
from types import SimpleNamespace

import pytest
from fakes import FakeMaster, FakeTarget
from marks import needs_pymavlink

pytestmark = [needs_pymavlink, pytest.mark.dyopilot]

pytest.importorskip("pymavlink")

from pymavlink import mavutil  # noqa: E402

from dyodrone.drivers import dyopilot_driver as driver  # noqa: E402
from dyodrone.drivers.dyopilot_driver import DyopilotController  # noqa: E402

HOME_LAT, HOME_LON = -35.363261, 149.165230



@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Skip the polling delays but keep real timestamps."""
    monkeypatch.setattr(driver, "time", SimpleNamespace(time=time.time, sleep=lambda _s: None))


@pytest.fixture
def master():
    m = FakeMaster()
    m.messages["GPS_RAW_INT"] = SimpleNamespace(fix_type=3)
    m.set_position(HOME_LAT, HOME_LON, relative_alt_m=10.0)
    return m


@pytest.fixture
def ctrl(master):
    c = DyopilotController(FakeTarget(), heartbeat_timeout=0.1)
    c._master = master
    return c


@pytest.fixture
def airborne(ctrl, master):
    master.arm()
    master.flightmode = "GUIDED"
    return ctrl


def position_target(master):
    sent = [c for c in master.calls if c[0] == "set_position_target_global_int_send"]
    assert len(sent) == 1, master.calls
    args = sent[0][1]
    return args[5] / 1e7, args[6] / 1e7, args[7]  # lat, lon, alt


# -- connection ------------------------------------------------------------


def test_master_property_requires_a_connection():
    with pytest.raises(RuntimeError, match="not been established"):
        DyopilotController(FakeTarget()).master


def test_open_master_connects_requests_streams_and_starts_reader(monkeypatch):
    fake = FakeMaster()
    monkeypatch.setattr(driver.mavutil, "mavlink_connection", lambda conn: fake)
    c = DyopilotController(FakeTarget(), heartbeat_timeout=0.1)
    c._open_master("tcp:127.0.0.1:5760")
    try:
        assert c.active_connection == "tcp:127.0.0.1:5760"
        assert "request_data_stream_send" in fake.names()
        assert c._reader is not None
    finally:
        c.close()
    assert fake.closed and c._reader is None and c.active_connection is None


def test_open_master_times_out_without_heartbeat(monkeypatch):
    monkeypatch.setattr(driver.mavutil, "mavlink_connection", lambda conn: FakeMaster(heartbeat=False))
    c = DyopilotController(FakeTarget(), heartbeat_timeout=0.1)
    with pytest.raises(TimeoutError, match="No heartbeat"):
        c._open_master("tcp:127.0.0.1:1")
    assert c._reader is None


def test_open_master_wires_the_proxy_into_the_reader(monkeypatch):
    monkeypatch.setattr(driver.mavutil, "mavlink_connection", lambda conn: FakeMaster())
    proxy = SimpleNamespace(forward=lambda b: None)
    c = DyopilotController(FakeTarget(), heartbeat_timeout=0.1)
    c._open_master("tcp:x:1", proxy=proxy)
    try:
        assert c._reader._on_frame is proxy.forward
    finally:
        c.close()


# -- mode changes ----------------------------------------------------------


def test_set_mode_sends_legacy_set_mode_message(ctrl, master):
    """Regression: ArduCopter 3.3 rejects MAV_CMD_DO_SET_MODE (COMMAND_ACK result 3)."""
    ctrl._set_mode("GUIDED")
    assert master.calls == [("set_mode_send", (1, mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, 4))]
    assert "command_long_send" not in master.names()


def test_set_mode_rejects_unknown_mode(ctrl):
    with pytest.raises(RuntimeError, match="Unknown flight mode"):
        ctrl._set_mode("WARP")


def test_wait_for_mode_returns_once_the_mode_is_active(ctrl, master):
    ctrl._wait_for_mode("land", timeout=1)
    assert master.flightmode == "LAND"


def test_wait_for_mode_times_out(ctrl, master):
    master.mav._on_call = None  # the vehicle never changes mode
    with pytest.raises(TimeoutError, match="Failed to enter GUIDED"):
        ctrl._wait_for_mode("GUIDED", timeout=0)


def test_land_switches_to_land_mode(ctrl, master):
    ctrl.land()
    assert master.flightmode == "LAND"


# -- takeoff ---------------------------------------------------------------


def test_arm_and_takeoff_orders_mode_arm_takeoff(ctrl, master):
    ctrl.arm_and_takeoff(12.5)
    assert master.names() == ["set_mode_send", "arducopter_arm", "command_long_send"]
    command = master.calls[-1][1]
    assert command[2] == mavutil.mavlink.MAV_CMD_NAV_TAKEOFF
    assert command[-1] == 12.5


@pytest.mark.parametrize("altitude", [0, -3])
def test_arm_and_takeoff_rejects_non_positive_altitude(ctrl, altitude):
    with pytest.raises(ValueError):
        ctrl.arm_and_takeoff(altitude)


def test_arm_and_takeoff_waits_for_a_gps_fix(ctrl, master):
    master.messages["GPS_RAW_INT"] = SimpleNamespace(fix_type=1)
    ctrl._wait_for_condition = lambda predicate, timeout, poll_interval=1.0: (_ for _ in ()).throw(
        TimeoutError("Timed out waiting for condition")
    ) if not predicate() else None
    with pytest.raises(TimeoutError):
        ctrl.arm_and_takeoff(5)
    assert master.calls == []  # never tried to change mode or arm


@pytest.mark.parametrize(
    "gps, heartbeat, expected",
    [
        (SimpleNamespace(fix_type=3), SimpleNamespace(base_mode=0), True),
        (SimpleNamespace(fix_type=4), SimpleNamespace(base_mode=0), True),
        (SimpleNamespace(fix_type=2), SimpleNamespace(base_mode=0), False),
        (None, SimpleNamespace(base_mode=0), False),
        (SimpleNamespace(fix_type=3), None, False),
    ],
)
def test_is_armable(ctrl, master, gps, heartbeat, expected):
    master.messages.pop("GPS_RAW_INT", None)
    master.messages.pop("HEARTBEAT", None)
    if gps is not None:
        master.messages["GPS_RAW_INT"] = gps
    if heartbeat is not None:
        master.messages["HEARTBEAT"] = heartbeat
    assert ctrl._is_armable() is expected


# -- movement --------------------------------------------------------------


def test_forward_facing_north_increases_latitude_only(airborne, master):
    airborne.move_forward(111.32)  # 0.001 degrees of latitude
    lat, lon, alt = position_target(master)
    assert lat == pytest.approx(HOME_LAT + 0.001, abs=2e-7)
    assert lon == pytest.approx(HOME_LON, abs=2e-7)
    assert alt == pytest.approx(10.0)


def test_forward_facing_east_increases_longitude_only(airborne, master):
    master.set_position(HOME_LAT, HOME_LON, yaw=math.pi / 2)
    airborne.move_forward(100)
    lat, lon, _ = position_target(master)
    assert lat == pytest.approx(HOME_LAT, abs=2e-7)
    assert lon > HOME_LON


def test_back_is_the_opposite_of_forward(airborne, master):
    airborne.move_back(111.32)
    lat, _lon, _alt = position_target(master)
    assert lat == pytest.approx(HOME_LAT - 0.001, abs=2e-7)


def test_set_altitude_keeps_position(airborne, master):
    airborne.set_altitude(20)
    lat, lon, alt = position_target(master)
    assert (lat, lon, alt) == (pytest.approx(HOME_LAT, abs=1e-7), pytest.approx(HOME_LON, abs=1e-7), 20)


def test_set_altitude_needs_a_position(airborne, master):
    del master.messages["GLOBAL_POSITION_INT"]
    with pytest.raises(RuntimeError, match="No position data"):
        airborne.set_altitude(20)


@pytest.mark.parametrize("action", ["move_forward", "move_back", "rotate_left", "rotate_right", "set_altitude"])
def test_motion_requires_an_armed_vehicle(ctrl, action):
    with pytest.raises(RuntimeError, match="armed"):
        getattr(ctrl, action)(5)


def test_motion_switches_to_guided_first(ctrl, master):
    master.arm()
    master.flightmode = "LOITER"
    ctrl.move_forward(5)
    assert master.flightmode == "GUIDED"
    assert master.names()[0] == "set_mode_send"


@pytest.mark.parametrize("action", ["move_forward", "move_back", "rotate_left", "rotate_right", "set_altitude"])
@pytest.mark.parametrize("value", [0, -1])
def test_motion_rejects_non_positive_values(ctrl, action, value):
    with pytest.raises(ValueError):
        getattr(ctrl, action)(value)


@pytest.mark.parametrize("action, direction", [("rotate_right", 1), ("rotate_left", -1)])
def test_rotate_sends_relative_condition_yaw(airborne, master, action, direction):
    getattr(airborne, action)(90)
    args = master.calls[-1][1]
    assert master.calls[-1][0] == "command_long_send"
    assert args[2] == mavutil.mavlink.MAV_CMD_CONDITION_YAW
    assert args[4:8] == (90, 0, direction, 1)  # angle, speed, direction, relative


# -- telemetry formatting --------------------------------------------------


def test_status_lines_with_full_telemetry(ctrl, master):
    master.arm()
    master.flightmode = "GUIDED"
    master.messages["SYS_STATUS"] = SimpleNamespace(voltage_battery=12200, current_battery=2550, battery_remaining=97)
    lines = ctrl.status_lines()
    text = "\n".join(lines)
    assert lines[0] == "=== Vehicle snapshot ==="
    assert "Mode: GUIDED" in text and "Armed: True" in text and "GPS fix: 3D" in text
    assert "agl=10.0m" in text and "voltage=12.2V, current=25.5A, level=97" in text


def test_status_lines_without_telemetry_say_unknown():
    c = DyopilotController(FakeTarget())
    c._master = FakeMaster()
    c._master.messages.clear()
    text = "\n".join(c.status_lines())
    assert "Armed: False" in text
    assert text.count("unknown") >= 5


def test_battery_sentinels_are_reported_as_unknown():
    out = DyopilotController._format_battery(SimpleNamespace(voltage_battery=11000, current_battery=-1, battery_remaining=-1))
    assert out == "voltage=11.0V, current=unknown, level=unknown"


@pytest.mark.parametrize("fix, label", [(0, "no GPS"), (3, "3D"), (6, "RTK-fixed"), (9, "type=9")])
def test_gps_fix_labels(fix, label):
    assert DyopilotController._format_gps_fix(SimpleNamespace(fix_type=fix)) == label


# -- structured telemetry ---------------------------------------------------


def test_telemetry_reads_position_attitude_and_heartbeat(ctrl, master):
    master.arm()
    master.flightmode = "GUIDED"
    master.set_position(HOME_LAT, HOME_LON, relative_alt_m=9.5, yaw=math.pi / 2)
    t = ctrl.telemetry()
    assert (t.lat, t.lon) == (pytest.approx(HOME_LAT, abs=1e-7), pytest.approx(HOME_LON, abs=1e-7))
    assert t.rel_alt_m == pytest.approx(9.5)
    assert t.yaw_deg == pytest.approx(90.0)
    assert t.armed is True and t.mode == "GUIDED"


def test_telemetry_yaw_is_normalised_to_0_360(ctrl, master):
    master.set_position(HOME_LAT, HOME_LON, yaw=-math.pi / 2)  # -90 deg = West
    assert ctrl.telemetry().yaw_deg == pytest.approx(270.0)


def test_telemetry_fields_are_none_until_received(ctrl, master):
    master.messages.clear()
    t = ctrl.telemetry()
    assert (t.lat, t.lon, t.rel_alt_m, t.yaw_deg, t.armed) == (None,) * 5
