"""dyodrone-plan: dry runs, validation exit codes, and a full run on a fake vehicle."""

from __future__ import annotations

import time

import pytest
from fakes import FlyingController

from dyodrone import plan_cli


def write(tmp_path, text):
    path = tmp_path / "plan.txt"
    path.write_text(text)
    return str(path)


def test_defaults(tmp_path):
    args = plan_cli.parse_args([write(tmp_path, "land")])
    assert (args.target, args.poll, args.margin, args.step_timeout, args.dry_run) == ("sitl", 3.0, 0.10, 120.0, False)
    assert args.gcs_port is None and args.connect is None


def test_dry_run_prints_the_steps_and_expectations_without_connecting(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(plan_cli, "create_controller", lambda *a, **k: pytest.fail("must not connect"))
    code = plan_cli.main([write(tmp_path, "takeoff 10\nforward 20\nland\n"), "--dry-run"])
    out = capsys.readouterr().out
    assert code == 0
    assert "3 steps" in out and "takeoff 10" in out and "armed and at 10 m (±1.0 m)" in out


def test_dry_run_uses_the_margin_option(tmp_path, capsys):
    plan_cli.main([write(tmp_path, "forward 20"), "--dry-run", "--margin", "0.25"])
    assert "±5.0 m" in capsys.readouterr().out


def test_invalid_plan_exits_2_and_lists_every_problem(tmp_path, capsys):
    code = plan_cli.main([write(tmp_path, "takeoff\nflip 3\n"), "--dry-run"])
    err = capsys.readouterr().err
    assert code == 2 and "line 1" in err and "line 2" in err


def test_missing_file_exits_2(tmp_path, capsys):
    assert plan_cli.main([str(tmp_path / "nope.txt")]) == 2
    assert "Cannot read" in capsys.readouterr().err


def test_unusable_driver_exits_1(tmp_path, monkeypatch, capsys):
    from dyodrone.core.factory import BackendUnavailable

    def unavailable(*a, **k):
        raise BackendUnavailable("Driver 'dronekit' requires Python 3.7")

    monkeypatch.setattr(plan_cli, "create_controller", unavailable)
    assert plan_cli.main([write(tmp_path, "land")]) == 1
    assert "requires Python 3.7" in capsys.readouterr().err


def fast_vehicle():
    return FlyingController(time.time, climb=1000, speed=1000, turn=10000)


def test_a_plan_runs_closed_loop_and_closes_the_connection(tmp_path, monkeypatch, capsys):
    vehicle = fast_vehicle()
    seen = {}

    def create(driver, target, connect, gcs_port, gcs_host):
        seen.update(driver=driver, target=target, gcs_port=gcs_port)
        return vehicle

    monkeypatch.setattr(plan_cli, "create_controller", create)
    code = plan_cli.main([write(tmp_path, "takeoff 10\nforward 20\nland\n"), "--driver", "dyopilot", "--poll", "0.01"])
    out = capsys.readouterr().out
    assert code == 0
    assert seen == {"driver": "dyopilot", "target": "sitl", "gcs_port": 14550}
    assert [c[0] for c in vehicle.calls if c[0] != "connect"][:3] == ["arm_and_takeoff", "move_forward", "land"]
    assert vehicle.closed and "plan: done" in out and "Connection closed." in out


def test_pixhawk_target_has_the_proxy_off_by_default(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(plan_cli, "create_controller", lambda d, t, c, g, h: seen.update(gcs=g, connect=c) or fast_vehicle())
    plan_cli.main([write(tmp_path, "takeoff 5"), "--target", "pixhawk", "--poll", "0.01"])
    assert seen["gcs"] == 0


def test_a_failed_step_exits_1_and_still_closes(tmp_path, monkeypatch, capsys):
    vehicle = fast_vehicle()
    vehicle.stuck = True
    monkeypatch.setattr(plan_cli, "create_controller", lambda *a, **k: vehicle)
    code = plan_cli.main([write(tmp_path, "takeoff 10\n"), "--poll", "0.01", "--step-timeout", "0.1"])
    assert code == 1 and vehicle.closed
    assert "timed out" in capsys.readouterr().out


def test_a_connection_error_exits_1_and_closes(tmp_path, monkeypatch, capsys):
    vehicle = fast_vehicle()
    vehicle.connect_error = RuntimeError("no vehicle")
    monkeypatch.setattr(plan_cli, "create_controller", lambda *a, **k: vehicle)
    assert plan_cli.main([write(tmp_path, "land")]) == 1
    assert vehicle.closed and "no vehicle" in capsys.readouterr().err
