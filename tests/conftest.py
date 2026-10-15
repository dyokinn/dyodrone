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


@pytest.fixture(autouse=True)
def no_real_speech_engine(request, monkeypatch):
    """Tests must never load Vosk or download a model, whatever is installed.

    Sessions built without an explicit ``engine_factory`` get a fake engine; the
    opt-in ``voice`` tests (real speech) are exempt.
    """
    if request.node.get_closest_marker("voice"):
        return
    from fakes import FakeEngine

    from dyodrone.gui import session as session_module

    monkeypatch.setattr(session_module, "_vosk_factory", lambda model_path: (lambda progress: FakeEngine()))
