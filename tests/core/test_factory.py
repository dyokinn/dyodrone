"""Backend selection: names, lazy imports, the Python-version gate, proxy wiring."""

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
    BACKENDS,
    DEFAULT_CONNECT,
    DRONEKIT_BACKENDS,
    BackendUnavailable,
    create_controller,
    require_python37,
)


def test_backend_names_are_family_dash_mode():
    assert BACKENDS == ["dronekit-sitl", "dronekit-pixhawk", "dyopilot-sitl", "dyopilot-pixhawk"]
    assert DRONEKIT_BACKENDS == {"dronekit-sitl", "dronekit-pixhawk"}


def test_only_pixhawk_backends_have_a_default_connection():
    assert set(DEFAULT_CONNECT) == {"dronekit-pixhawk", "dyopilot-pixhawk"}
    assert set(DEFAULT_CONNECT.values()) == {"tcp:127.0.0.1:5760"}


def test_unknown_backend_is_rejected():
    with pytest.raises(ValueError, match="Unknown backend"):
        create_controller("nope")


def test_require_python37_blocks_new_interpreters(monkeypatch):
    monkeypatch.setattr(factory, "sys", SimpleNamespace(version_info=(3, 12, 0)))
    with pytest.raises(BackendUnavailable, match="requires Python 3.7"):
        require_python37("dronekit-sitl")


def test_require_python37_allows_old_interpreters(monkeypatch):
    monkeypatch.setattr(factory, "sys", SimpleNamespace(version_info=(3, 7, 17)))
    require_python37("dronekit-sitl")  # no exception


def test_dronekit_backend_fails_cleanly_on_new_python(monkeypatch):
    monkeypatch.setattr(factory, "sys", SimpleNamespace(version_info=(3, 12, 0)))
    with pytest.raises(BackendUnavailable):
        create_controller("dronekit-pixhawk", "tcp:x:1")


def test_dronekit_import_failure_is_translated(monkeypatch):
    """On a 3.8/3.9 interpreter where `import dronekit` still raises AttributeError."""
    monkeypatch.setattr(factory, "sys", SimpleNamespace(version_info=(3, 7, 17)))
    name = "dyodrone.drivers.dronekit_pixhawk"

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
        create_controller("dronekit-pixhawk", "tcp:x:1")


def test_dronekit_backend_is_built_from_its_module_on_py37(monkeypatch):
    monkeypatch.setattr(factory, "sys", SimpleNamespace(version_info=(3, 7, 17)))
    built = {}

    class Fake:
        def __init__(self, **kwargs):
            built.update(kwargs)

    module = types.ModuleType("dyodrone.drivers.dronekit_pixhawk")
    module.DronekitPixhawkController = Fake  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "dyodrone.drivers.dronekit_pixhawk", module)

    assert isinstance(create_controller("dronekit-pixhawk"), Fake)
    assert built == {"connection": "tcp:127.0.0.1:5760"}  # default filled in


@needs_pymavlink
def test_pixhawk_backend_uses_explicit_connection():
    ctrl = create_controller("dyopilot-pixhawk", "/dev/ttyUSB0")
    assert ctrl.connection == "/dev/ttyUSB0"


@needs_pymavlink
def test_pixhawk_backend_defaults_connection():
    assert create_controller("dyopilot-pixhawk").connection == "tcp:127.0.0.1:5760"


@needs_pymavlink
@pytest.mark.parametrize("port, expect_proxy", [(0, False), (None, False), (14550, True)])
def test_gcs_port_controls_the_proxy(port, expect_proxy):
    ctrl = create_controller("dyopilot-sitl", gcs_port=port)
    assert (ctrl._proxy is not None) is expect_proxy
    if ctrl._proxy is not None:
        ctrl._proxy.stop()


@needs_pymavlink
def test_dyopilot_backends_never_import_dronekit():
    code = (
        "import sys\n"
        "from dyodrone.core.factory import create_controller\n"
        "create_controller('dyopilot-pixhawk', 'tcp:127.0.0.1:5760')\n"
        "create_controller('dyopilot-sitl', gcs_port=0)\n"
        "assert 'dronekit' not in sys.modules, 'dronekit was imported'\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
