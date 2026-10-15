"""Skip markers for tests that need optional packages."""

from __future__ import annotations

import pytest


def _importable(name: str) -> bool:
    """True if *name* imports cleanly. Catches everything: DroneKit raises
    AttributeError (not ImportError) on Python 3.10+."""
    try:
        __import__(name)
    except Exception:  # noqa: BLE001
        return False
    return True


HAVE_DRONEKIT = _importable("dronekit")
HAVE_PYMAVLINK = _importable("pymavlink.mavutil")

needs_dronekit = pytest.mark.skipif(not HAVE_DRONEKIT, reason="DroneKit is only importable on Python 3.7")
needs_pymavlink = pytest.mark.skipif(not HAVE_PYMAVLINK, reason="pymavlink is not installed")
