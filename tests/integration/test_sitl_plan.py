"""Closed-loop flight plans against a live ArduCopter SITL. Opt in with ``pytest -m sitl``."""

from __future__ import annotations

import subprocess
import sys

import pytest
from fakes import wait_for
from marks import HAVE_DRONEKIT, HAVE_PYMAVLINK

pytestmark = pytest.mark.sitl

pytest.importorskip("dronekit_sitl")

PLAN = "# short square leg\ntakeoff 10\nforward 15\nright 90\nland\n"


def simulator_running() -> bool:
    return subprocess.run(["pgrep", "-f", r"\.dronekit/sitl"], capture_output=True).returncode == 0


@pytest.mark.skipif(not HAVE_PYMAVLINK, reason="pymavlink is not installed")
def test_dyodrone_plan_command_flies_a_plan_and_cleans_up(tmp_path):
    plan = tmp_path / "plan.txt"
    plan.write_text(PLAN)
    result = subprocess.run(
        [sys.executable, "-m", "dyodrone.plan_cli", str(plan), "--driver", "dyopilot", "--target", "sitl",
         "--gcs-port", "0", "--step-timeout", "120"],
        capture_output=True, text=True, timeout=400,
    )
    out = result.stdout
    assert result.returncode == 0, out + result.stderr
    # every step completed by telemetry, in order
    for command in ("takeoff 10", "forward 15", "right 90", "land"):
        assert f"{command}: done" in out, out
    assert "plan: done" in out
    assert wait_for(lambda: not simulator_running(), timeout=10)


@pytest.mark.skipif(not HAVE_DRONEKIT, reason="DroneKit is only importable on Python 3.7")
def test_plan_runner_with_the_dronekit_driver():
    from dyodrone.core.factory import create_controller
    from dyodrone.core.plan import parse_plan
    from dyodrone.core.plan_runner import PlanRunner

    ctrl = create_controller("dronekit", "sitl", gcs_port=0)
    ctrl.connect()
    try:
        runner = PlanRunner(ctrl, parse_plan(PLAN), step_timeout=120)
        assert runner.run() is True, runner.snapshot()["message"]
    finally:
        ctrl.close()
    assert wait_for(lambda: not simulator_running(), timeout=10)
