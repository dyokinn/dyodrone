"""Backend selection shared by the console front ends.

Both the curses CLI (:mod:`dyodrone.cli`) and the web console
(:mod:`dyodrone.gui`) build their controller here. It imports no UI toolkit and
stays compatible with Python 3.7.
"""

from __future__ import annotations

import sys
from typing import Dict, List, Optional

from dyodrone.core.controller import DroneController

#: All selectable backends, ``<family>-<mode>``.
BACKENDS: List[str] = [
    "dronekit-sitl",
    "dronekit-pixhawk",
    "dyopilot-sitl",
    "dyopilot-pixhawk",
]

#: Backends whose controllers import DroneKit, which is incompatible with
#: Python 3.10+. They must run under the Python 3.7 interpreter described in
#: the ``dronekit`` extra (see docs/guide/installation.rst).
DRONEKIT_BACKENDS = {"dronekit-sitl", "dronekit-pixhawk"}

#: Default connection strings used when no connection is given. The two
#: ``-sitl`` backends self-provision one when they launch their own simulator.
DEFAULT_CONNECT: Dict[str, str] = {
    "dronekit-pixhawk": "tcp:127.0.0.1:5760",
    "dyopilot-pixhawk": "tcp:127.0.0.1:5760",
}

class BackendUnavailable(RuntimeError):
    """The selected backend cannot run in this Python interpreter."""


def require_python37(backend: str) -> None:
    """Fail fast with an actionable message instead of a raw AttributeError.

    DroneKit (``dronekit==2.9.2``) has
    ``class Parameters(collections.MutableMapping, ...)``, and
    ``collections.MutableMapping`` was removed in Python 3.10. Importing
    ``dronekit`` on 3.10+ crashes immediately, so ``dronekit-*`` backends must
    run under the Python 3.7 interpreter.
    """
    if sys.version_info >= (3, 10):
        raise BackendUnavailable(_python37_message(backend))


def _python37_message(backend: str) -> str:
    return (
        f"Backend '{backend}' requires Python 3.7 — DroneKit is incompatible "
        "with Python 3.10+. Run it with a 3.7 interpreter "
        "(see docs/guide/how.rst)."
    )


def create_controller(
    backend: str,
    connect: Optional[str] = None,
    gcs_port: Optional[int] = 14550,
    gcs_host: str = "127.0.0.1",
) -> DroneController:
    """Instantiate the controller for *backend* (one of :data:`BACKENDS`).

    Backend modules are imported lazily inside each branch so that choosing a
    ``dyopilot-*`` backend never imports DroneKit (see :doc:`/guide/how`).
    ``gcs_port`` of ``0`` or ``None`` disables the QGroundControl proxy; it and
    ``gcs_host`` only apply to the ``*-sitl`` backends.

    Raises :class:`BackendUnavailable` if the backend cannot run on this
    interpreter and :class:`ValueError` for an unknown backend name.
    """
    connect = connect or DEFAULT_CONNECT.get(backend)
    gcs_port = gcs_port or None

    if backend in DRONEKIT_BACKENDS:
        require_python37(backend)
        try:
            if backend == "dronekit-sitl":
                from dyodrone.drivers.dronekit_sitl import DronekitSITLController

                return DronekitSITLController(gcs_port=gcs_port, gcs_host=gcs_host)
            from dyodrone.drivers.dronekit_pixhawk import DronekitPixhawkController

            return DronekitPixhawkController(connection=connect)
        except AttributeError as exc:
            raise BackendUnavailable(_python37_message(backend)) from exc

    if backend == "dyopilot-sitl":
        from dyodrone.drivers.dyopilot_sitl import DyopilotSITLController

        return DyopilotSITLController(gcs_port=gcs_port, gcs_host=gcs_host)
    if backend == "dyopilot-pixhawk":
        from dyodrone.drivers.dyopilot_pixhawk import DyopilotPixhawkController

        return DyopilotPixhawkController(connection=connect)
    raise ValueError(f"Unknown backend: {backend!r}")
