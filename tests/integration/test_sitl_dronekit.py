"""DroneKit against a live SITL (Python 3.7 environment). Opt in with ``pytest -m sitl``."""

from __future__ import annotations

import subprocess

import pytest
from fakes import wait_for
from marks import needs_dronekit

pytestmark = [pytest.mark.sitl, pytest.mark.dronekit, needs_dronekit]


def test_takeoff_land_and_clean_shutdown():
    from dyodrone.drivers.dronekit_sitl import DronekitSITLController

    ctrl = DronekitSITLController(gcs_port=None)
    ctrl.connect()
    try:
        ctrl.arm_and_takeoff(8)
        assert wait_for(lambda: ctrl.vehicle.location.global_relative_frame.alt >= 7.0, timeout=40)
        ctrl.land()
        assert wait_for(lambda: ctrl.vehicle.mode.name == "LAND", timeout=10)
    finally:
        ctrl.close()
    assert wait_for(lambda: subprocess.run(["pgrep", "-f", r"\.dronekit/sitl"], capture_output=True).returncode != 0, timeout=10)
