"""Curses CLI wiring: argument parsing, controller construction, shutdown."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from fakes import FakeController

from dyodrone import cli
from dyodrone.core import factory
from dyodrone.core.factory import BackendUnavailable


def parse(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["dyodrone-cli", *argv])
    return cli.parse_args()


def test_defaults(monkeypatch):
    args = parse(monkeypatch)
    assert args.driver == factory.default_driver() and args.target == "sitl"
    assert (args.connect, args.interval, args.duration) == (None, 2.0, None)
    assert (args.gcs_port, args.gcs_host) == (None, "127.0.0.1")


def test_default_driver_depends_on_the_interpreter(monkeypatch):
    monkeypatch.setattr(factory.sys, "version_info", (3, 7, 17))
    assert parse(monkeypatch).driver == "dronekit"
    monkeypatch.setattr(factory.sys, "version_info", (3, 12, 0))
    assert parse(monkeypatch).driver == "dyopilot"


@pytest.mark.parametrize("driver", ["dronekit", "dyopilot"])
@pytest.mark.parametrize("target", ["sitl", "pixhawk"])
def test_every_driver_target_pair_is_selectable(monkeypatch, driver, target):
    args = parse(monkeypatch, "--driver", driver, "--target", target)
    assert (args.driver, args.target) == (driver, target)


@pytest.mark.parametrize("flag, value", [("--driver", "mavlink"), ("--target", "moon"), ("--backend", "dyopilot-sitl")])
def test_unknown_choices_and_the_old_flag_are_rejected(monkeypatch, capsys, flag, value):
    with pytest.raises(SystemExit):
        parse(monkeypatch, flag, value)
    assert capsys.readouterr().err


def test_options_are_parsed(monkeypatch):
    args = parse(monkeypatch, "--target", "pixhawk", "--connect", "udp:1.2.3.4:14550", "--interval", "0.5",
                 "--duration", "9", "--gcs-port", "5600", "--gcs-host", "10.0.0.5")
    assert (args.connect, args.interval, args.duration, args.gcs_port, args.gcs_host) == (
        "udp:1.2.3.4:14550", 0.5, 9.0, 5600, "10.0.0.5")


@pytest.mark.parametrize(
    "target, given, expected",
    [("sitl", None, 14550), ("pixhawk", None, 0), ("sitl", 0, 0), ("pixhawk", 5600, 5600)],
)
def test_build_controller_applies_the_proxy_default(monkeypatch, target, given, expected):
    seen = {}

    def fake_create(driver, tgt, connect, gcs_port, gcs_host):
        seen.update(driver=driver, target=tgt, connect=connect, gcs_port=gcs_port, gcs_host=gcs_host)
        return "controller"

    monkeypatch.setattr(cli, "create_controller", fake_create)
    argv = ["--driver", "dyopilot", "--target", target]
    if given is not None:
        argv += ["--gcs-port", str(given)]
    assert cli.build_controller(parse(monkeypatch, *argv)) == "controller"
    assert seen == {"driver": "dyopilot", "target": target, "connect": None, "gcs_port": expected, "gcs_host": "127.0.0.1"}


def test_unusable_driver_exits_with_the_message(monkeypatch):
    def unavailable(*_a, **_k):
        raise BackendUnavailable("Driver 'dronekit' requires Python 3.7")

    monkeypatch.setattr(cli, "create_controller", unavailable)
    with pytest.raises(SystemExit) as info:
        cli.build_controller(parse(monkeypatch, "--driver", "dronekit"))
    assert "requires Python 3.7" in str(info.value)


def test_main_builds_runs_and_returns_the_exit_code(monkeypatch):
    ran = {}
    monkeypatch.setattr(cli, "build_controller", lambda args: FakeController())
    monkeypatch.setattr(cli, "run_cli", lambda **kw: ran.update(kw) or 0)
    monkeypatch.setattr(sys, "argv", ["dyodrone-cli", "--interval", "1.5", "--duration", "3"])
    assert cli.main() == 0
    assert (ran["interval"], ran["duration"]) == (1.5, 3.0)


def test_run_cli_connects_runs_the_ui_and_always_closes(monkeypatch):
    ctrl = FakeController()
    monkeypatch.setattr(cli.curses, "wrapper", lambda fn, *a: None)
    assert cli.run_cli(2.0, None, ctrl) == 0
    assert ctrl.calls == [("connect",), ("close",)]


def test_run_cli_closes_on_ctrl_c(monkeypatch):
    ctrl = FakeController()

    def interrupt(fn, *a):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.curses, "wrapper", interrupt)
    assert cli.run_cli(2.0, None, ctrl) == 0
    assert ("close",) in ctrl.calls


def test_run_cli_closes_when_connect_fails(monkeypatch):
    ctrl = FakeController(connect_error=RuntimeError("no link"))
    monkeypatch.setattr(cli.curses, "wrapper", lambda fn, *a: None)
    with pytest.raises(RuntimeError):
        cli.run_cli(2.0, None, ctrl)
    assert ("close",) in ctrl.calls


# -- installed entry points -------------------------------------------------


def run(*args):
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, timeout=60)


def test_python_dash_m_runs_the_cli():
    result = run("-m", "dyodrone", "--help")
    assert result.returncode == 0 and "--driver" in result.stdout and "--target" in result.stdout


@pytest.mark.parametrize("script, marker", [("dyodrone-cli", "--target"), ("dyodrone-gui", "--no-browser")])
def test_console_scripts_are_installed(script, marker):
    exe = Path(sys.executable).parent / script
    if not exe.exists():
        pytest.skip("%s is not installed in this environment (pip install -e .)" % script)
    result = subprocess.run([str(exe), "--help"], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0 and marker in result.stdout
