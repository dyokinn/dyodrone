"""Telemetry snapshot dataclass and the controller default."""

from __future__ import annotations

import pytest
from fakes import FakeController

from dyodrone.core.telemetry import Telemetry


def test_fields_default_to_none_until_received():
    t = Telemetry()
    assert (t.lat, t.lon, t.rel_alt_m, t.yaw_deg, t.armed, t.mode) == (None,) * 6
    assert not t.has_position and t.timestamp > 0


def test_has_position_needs_both_coordinates():
    assert Telemetry(lat=1.0, lon=2.0).has_position
    assert not Telemetry(lat=1.0).has_position


def test_summary():
    assert Telemetry(rel_alt_m=9.84, yaw_deg=90.0, armed=True).summary() == "alt 9.8 m, yaw 90°, armed"
    assert Telemetry(armed=False).summary() == "disarmed"
    assert Telemetry().summary() == "no telemetry"


def test_controllers_without_telemetry_say_so():
    from dyodrone.core.controller import DroneController

    class Bare(FakeController):
        telemetry = DroneController.telemetry

    with pytest.raises(NotImplementedError, match="telemetry"):
        Bare().telemetry()
