"""Shared pytest configuration.

``tests/`` is on ``sys.path`` (rootdir conftest), so test modules import the
doubles with ``from fakes import ...`` and the skip markers with
``from marks import ...``.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def fake_sitl(monkeypatch):
    from fakes import install_fake_dronekit_sitl

    return install_fake_dronekit_sitl(monkeypatch)
