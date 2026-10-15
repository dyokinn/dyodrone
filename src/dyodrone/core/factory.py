"""Driver and target selection shared by the console front ends.

Both the curses CLI (:mod:`dyodrone.cli`) and the web console
(:mod:`dyodrone.gui`) build their controller here. It imports no UI toolkit and
stays compatible with Python 3.7.
"""

from __future__ import annotations

import sys
from typing import Optional

from dyodrone.core.controller import DroneController
from dyodrone.core.proxy import GCSProxy
from dyodrone.core.targets import TARGETS, make_target

#: Flight-control libraries. ``dronekit`` needs Python 3.7; ``dyopilot`` (raw
#: pymavlink) runs on current Python.
DRIVERS = ("dronekit", "dyopilot")

#: Connection string used for the ``pixhawk`` target when none is given.
DEFAULT_CONNECTION = "tcp:127.0.0.1:5760"

#: Default QGroundControl proxy port for the ``sitl`` target.
DEFAULT_GCS_PORT = 14550


class BackendUnavailable(RuntimeError):
    """The selected driver cannot run in this Python interpreter."""


def default_gcs_port(target: str, given: Optional[int] = None) -> int:
    """QGroundControl proxy port to use: *given* if set, else on for ``sitl`` and off otherwise."""
    if given is not None:
        return given
    return DEFAULT_GCS_PORT if target == "sitl" else 0


def default_driver() -> str:
    """The driver that can run on this interpreter (``dronekit`` only on < 3.10)."""
    return "dronekit" if sys.version_info < (3, 10) else "dyopilot"


def require_python37(driver: str) -> None:
    """Fail fast with an actionable message instead of a raw AttributeError.

    DroneKit (``dronekit==2.9.2``) has
    ``class Parameters(collections.MutableMapping, ...)``, and
    ``collections.MutableMapping`` was removed in Python 3.10. Importing
    ``dronekit`` on 3.10+ crashes immediately, so the ``dronekit`` driver must
    run under the Python 3.7 interpreter.
    """
    if sys.version_info >= (3, 10):
        raise BackendUnavailable(_python37_message(driver))


def _python37_message(driver: str) -> str:
    return (
        f"Driver '{driver}' requires Python 3.7 — DroneKit is incompatible "
        "with Python 3.10+. Run it with a 3.7 interpreter "
        "(see docs/guide/how.rst)."
    )


def create_controller(
    driver: str,
    target: str,
    connect: Optional[str] = None,
    gcs_port: Optional[int] = None,
    gcs_host: str = "127.0.0.1",
) -> DroneController:
    """Build the controller for *driver* talking to *target*.

    ``connect`` is the connection string for the ``pixhawk`` target (default
    :data:`DEFAULT_CONNECTION`); the ``sitl`` target ignores it. A ``gcs_port``
    of ``None`` or ``0`` disables the QGroundControl proxy, for either target.

    Driver modules are imported lazily so that choosing ``dyopilot`` never
    imports DroneKit (see :doc:`/guide/how`).

    Raises :class:`BackendUnavailable` if the driver cannot run on this
    interpreter and :class:`ValueError` for an unknown driver or target.
    """
    if driver not in DRIVERS:
        raise ValueError(f"Unknown driver: {driver!r} (expected one of {', '.join(DRIVERS)})")
    if target not in TARGETS:
        raise ValueError(f"Unknown target: {target!r} (expected one of {', '.join(TARGETS)})")

    vehicle_target = make_target(target, connect or DEFAULT_CONNECTION)
    proxy = GCSProxy(gcs_port, gcs_host) if gcs_port else None

    if driver == "dronekit":
        require_python37(driver)
        try:
            from dyodrone.drivers.dronekit_driver import DroneKitController

            return DroneKitController(vehicle_target, proxy)
        except AttributeError as exc:
            raise BackendUnavailable(_python37_message(driver)) from exc

    from dyodrone.drivers.dyopilot_driver import DyopilotController

    return DyopilotController(vehicle_target, proxy)
