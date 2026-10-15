"""Targets: where a connection string comes from and how it is cleaned up."""

from __future__ import annotations

import pytest
from fakes import install_fake_dronekit_sitl

from dyodrone.core.targets import TARGETS, ExternalTarget, SitlTarget, make_target


def test_target_names():
    assert TARGETS == ("sitl", "pixhawk")


def test_external_target_returns_its_connection():
    target = ExternalTarget("/dev/ttyUSB0")
    assert target.acquire() == "/dev/ttyUSB0"
    target.release()  # nothing to stop
    assert target.acquire() == "/dev/ttyUSB0"


@pytest.mark.parametrize("connection", ["", None])
def test_external_target_requires_a_connection(connection):
    with pytest.raises(ValueError, match="connection string is required"):
        ExternalTarget(connection)


def test_sitl_target_starts_once_and_reuses_the_simulator(monkeypatch):
    log = install_fake_dronekit_sitl(monkeypatch, "tcp:127.0.0.1:5999")
    target = SitlTarget()
    assert target.acquire() == "tcp:127.0.0.1:5999"
    assert target.acquire() == "tcp:127.0.0.1:5999"
    assert log == ["start"]


def test_sitl_target_does_not_start_anything_until_acquired(monkeypatch):
    log = install_fake_dronekit_sitl(monkeypatch)
    SitlTarget().release()
    assert log == []


def test_sitl_release_stops_the_simulator_and_is_idempotent(monkeypatch):
    log = install_fake_dronekit_sitl(monkeypatch)
    target = SitlTarget()
    target.acquire()
    target.release()
    target.release()
    assert log == ["start", "stop"]


def test_sitl_target_can_be_reacquired_after_release(monkeypatch):
    log = install_fake_dronekit_sitl(monkeypatch)
    target = SitlTarget()
    target.acquire()
    target.release()
    target.acquire()
    assert log == ["start", "stop", "start"]


def test_make_target_builds_by_name(monkeypatch):
    assert isinstance(make_target("sitl"), SitlTarget)
    pix = make_target("pixhawk", "tcp:1.2.3.4:5760")
    assert isinstance(pix, ExternalTarget) and pix.connection == "tcp:1.2.3.4:5760"


def test_make_target_rejects_unknown_names_and_empty_pixhawk():
    with pytest.raises(ValueError, match="Unknown target"):
        make_target("moon")
    with pytest.raises(ValueError):
        make_target("pixhawk")
