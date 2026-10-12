"""Curses CLI wiring: argument parsing, controller construction, shutdown."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from fakes import FakeController

from dyodrone import cli
from dyodrone.core.factory import BACKENDS, BackendUnavailable


def parse(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["dyodrone-cli", *argv])
    return cli.parse_args()


def test_defaults(monkeypatch):
    args = parse(monkeypatch)
    assert args.backend == "dronekit-sitl"
    assert (args.connect, args.interval, args.duration) == (None, 2.0, None)
    assert (args.gcs_port, args.gcs_host) == (14550, "127.0.0.1")


@pytest.mark.parametrize("backend", BACKENDS)
def test_every_backend_is_selectable(monkeypatch, backend):
    assert parse(monkeypatch, "--backend", backend).backend == backend


def test_unknown_backend_is_an_argparse_error(monkeypatch, capsys):
    with pytest.raises(SystemExit):
        parse(monkeypatch, "--backend", "mavlink")
    assert "invalid choice" in capsys.readouterr().err


def test_options_are_parsed(monkeypatch):
    args = parse(monkeypatch, "--connect", "udp:1.2.3.4:14550", "--interval", "0.5", "--duration", "9",
                 "--gcs-port", "0", "--gcs-host", "10.0.0.5")
    assert (args.connect, args.interval, args.duration, args.gcs_port, args.gcs_host) == (
        "udp:1.2.3.4:14550", 0.5, 9.0, 0, "10.0.0.5")


def test_build_controller_forwards_arguments(monkeypatch):
    seen = {}

    def fake_create(backend, connect, gcs_port, gcs_host):
        seen.update(backend=backend, connect=connect, gcs_port=gcs_port, gcs_host=gcs_host)
        return "controller"

    monkeypatch.setattr(cli, "create_controller", fake_create)
    args = parse(monkeypatch, "--backend", "dyopilot-sitl", "--gcs-port", "5600")
    assert cli.build_controller(args) == "controller"
    assert seen == {"backend": "dyopilot-sitl", "connect": None, "gcs_port": 5600, "gcs_host": "127.0.0.1"}


def test_unusable_backend_exits_with_the_message(monkeypatch):
    def unavailable(*_a, **_k):
        raise BackendUnavailable("Backend 'dronekit-sitl' requires Python 3.7")

    monkeypatch.setattr(cli, "create_controller", unavailable)
    with pytest.raises(SystemExit) as info:
        cli.build_controller(parse(monkeypatch))
    assert "requires Python 3.7" in str(info.value)


def test_main_fills_in_the_pixhawk_default_connection(monkeypatch):
    captured = {}
    monkeypatch.setattr(cli, "build_controller", lambda args: captured.setdefault("args", args) and FakeController())
    monkeypatch.setattr(cli, "run_cli", lambda **kw: 0)
    monkeypatch.setattr(sys, "argv", ["dyodrone-cli", "--backend", "dyopilot-pixhawk"])
    assert cli.main() == 0
    assert captured["args"].connect == "tcp:127.0.0.1:5760"


def test_main_leaves_sitl_backends_without_a_connection(monkeypatch):
    captured = {}
    monkeypatch.setattr(cli, "build_controller", lambda args: captured.setdefault("args", args) and FakeController())
    monkeypatch.setattr(cli, "run_cli", lambda **kw: 0)
    monkeypatch.setattr(sys, "argv", ["dyodrone-cli", "--backend", "dyopilot-sitl"])
    cli.main()
    assert captured["args"].connect is None


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
    assert result.returncode == 0 and "--backend" in result.stdout


@pytest.mark.parametrize("script, marker", [("dyodrone-cli", "--backend"), ("dyodrone-gui", "--no-browser")])
def test_console_scripts_are_installed(script, marker):
    exe = Path(sys.executable).parent / script
    if not exe.exists():
        pytest.skip("%s is not installed in this environment (pip install -e .)" % script)
    result = subprocess.run([str(exe), "--help"], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0 and marker in result.stdout
