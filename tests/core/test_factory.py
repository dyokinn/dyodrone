"""Driver/target selection: lazy imports, the Python-version gate, proxy wiring."""

from __future__ import annotations

import importlib.abc
import importlib.util
import subprocess
import sys
import types
from types import SimpleNamespace

import pytest
from marks import needs_pymavlink

from dyodrone.core import factory
from dyodrone.core.factory import (
    DEFAULT_CONNECTION,
    DRIVERS,
    BackendUnavailable,
    create_controller,
    default_driver,
    require_python37,
)
from dyodrone.core.targets import ExternalTarget, SitlTarget


def fake_version(monkeypatch, version):
    monkeypatch.setattr(factory, "sys", SimpleNamespace(version_info=version))


def test_drivers_and_default():
    assert DRIVERS == ("dronekit", "dyopilot")
    assert DEFAULT_CONNECTION == "tcp:127.0.0.1:5760"


def test_default_driver_follows_the_interpreter(monkeypatch):
    fake_version(monkeypatch, (3, 7, 17))
    assert default_driver() == "dronekit"
    fake_version(monkeypatch, (3, 9, 0))
    assert default_driver() == "dronekit"
    fake_version(monkeypatch, (3, 10, 0))
    assert default_driver() == "dyopilot"


@pytest.mark.parametrize("driver, target", [("nope", "sitl"), ("dyopilot", "nope"), ("dronekit-sitl", "sitl")])
def test_unknown_driver_or_target_is_rejected(driver, target):
    with pytest.raises(ValueError, match="Unknown"):
        create_controller(driver, target)


def test_require_python37_blocks_new_interpreters(monkeypatch):
    fake_version(monkeypatch, (3, 12, 0))
    with pytest.raises(BackendUnavailable, match="requires Python 3.7"):
        require_python37("dronekit")


def test_require_python37_allows_old_interpreters(monkeypatch):
    fake_version(monkeypatch, (3, 7, 17))
    require_python37("dronekit")  # no exception


@pytest.mark.parametrize("target", ["sitl", "pixhawk"])
def test_dronekit_driver_fails_cleanly_on_new_python(monkeypatch, target):
    fake_version(monkeypatch, (3, 12, 0))
    with pytest.raises(BackendUnavailable):
        create_controller("dronekit", target)


def test_dronekit_import_failure_is_translated(monkeypatch):
    """On a 3.8/3.9 interpreter where `import dronekit` still raises AttributeError."""
    fake_version(monkeypatch, (3, 7, 17))
    name = "dyodrone.drivers.dronekit_driver"

    class Boom(importlib.abc.MetaPathFinder, importlib.abc.Loader):
        def find_spec(self, fullname, path, target=None):
            return importlib.util.spec_from_loader(fullname, self) if fullname == name else None

        def create_module(self, spec):
            return None

        def exec_module(self, module):
            raise AttributeError("module 'collections' has no attribute 'MutableMapping'")

    monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setattr(sys, "meta_path", [Boom()] + sys.meta_path)
    with pytest.raises(BackendUnavailable):
        create_controller("dronekit", "pixhawk", "tcp:x:1")


def test_dronekit_controller_is_built_with_target_and_proxy_on_py37(monkeypatch):
    fake_version(monkeypatch, (3, 7, 17))
    built = {}

    class Fake:
        def __init__(self, target, proxy=None):
            built.update(target=target, proxy=proxy)

    module = types.ModuleType("dyodrone.drivers.dronekit_driver")
    module.DroneKitController = Fake  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "dyodrone.drivers.dronekit_driver", module)

    assert isinstance(create_controller("dronekit", "pixhawk"), Fake)
    assert isinstance(built["target"], ExternalTarget) and built["target"].connection == DEFAULT_CONNECTION
    assert built["proxy"] is None


@needs_pymavlink
def test_dyopilot_pixhawk_uses_the_explicit_connection():
    ctrl = create_controller("dyopilot", "pixhawk", "/dev/ttyUSB0")
    assert isinstance(ctrl._target, ExternalTarget) and ctrl._target.connection == "/dev/ttyUSB0"


@needs_pymavlink
def test_dyopilot_pixhawk_defaults_the_connection():
    assert create_controller("dyopilot", "pixhawk")._target.connection == DEFAULT_CONNECTION


@needs_pymavlink
def test_sitl_target_ignores_the_connection_string():
    ctrl = create_controller("dyopilot", "sitl", "/dev/ttyUSB0")
    assert isinstance(ctrl._target, SitlTarget)


@needs_pymavlink
@pytest.mark.parametrize("target", ["sitl", "pixhawk"])
@pytest.mark.parametrize("port, expect_proxy", [(0, False), (None, False), (14550, True)])
def test_gcs_port_controls_the_proxy_for_any_target(target, port, expect_proxy):
    ctrl = create_controller("dyopilot", target, gcs_port=port)
    assert (ctrl._proxy is not None) is expect_proxy
    if ctrl._proxy is not None:
        assert ctrl._proxy.gcs_port == 14550
        ctrl._proxy.stop()


@needs_pymavlink
def test_dyopilot_never_imports_dronekit():
    code = (
        "import sys\n"
        "from dyodrone.core.factory import create_controller\n"
        "create_controller('dyopilot', 'pixhawk', 'tcp:127.0.0.1:5760')\n"
        "create_controller('dyopilot', 'sitl')\n"
        "assert 'dronekit' not in sys.modules, 'dronekit was imported'\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
