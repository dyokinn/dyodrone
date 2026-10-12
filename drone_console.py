"""Backend selection and command handling shared by the console front ends.

Both ``entry_points/drone_cli.py`` (curses) and ``entry_points/drone_gui.py``
(web) use this module, so a command behaves identically in either. It imports
no UI toolkit and stays compatible with Python 3.7.
"""

from __future__ import annotations

import sys
from typing import Dict, List, Optional, Tuple

from drone_controller import DroneController

#: All selectable backends, ``<family>-<mode>``.
BACKENDS: List[str] = [
    "dronekit-sitl",
    "dronekit-pixhawk",
    "dyopilot-sitl",
    "dyopilot-pixhawk",
]

#: Backends whose controllers import DroneKit, which is incompatible with
#: Python 3.10+. They must run under the Python 3.7 interpreter described in
#: ``dronekit_version/requirements-3.7.17.txt``.
DRONEKIT_BACKENDS = {"dronekit-sitl", "dronekit-pixhawk"}

#: Default connection strings used when no connection is given. The two
#: ``-sitl`` backends self-provision one when they launch their own simulator.
DEFAULT_CONNECT: Dict[str, str] = {
    "dronekit-pixhawk": "tcp:127.0.0.1:5760",
    "dyopilot-pixhawk": "tcp:127.0.0.1:5760",
}

#: Help text for the commands :func:`handle_command` understands.
COMMAND_HELP: List[str] = [
    "takeoff <alt>     arm and climb to <alt> metres",
    "altitude <alt>    change altitude while airborne",
    "forward <m>       move forward <m> metres",
    "back <m>          move back <m> metres",
    "left <deg>        yaw counter-clockwise",
    "right <deg>       yaw clockwise",
    "land              descend and disarm",
    "quit | exit       leave the console",
]


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
                from dronekit_version.dronekit_sitl_controller import DronekitSITLController

                return DronekitSITLController(gcs_port=gcs_port, gcs_host=gcs_host)
            from dronekit_version.dronekit_pixhawk_controller import DronekitPixhawkController

            return DronekitPixhawkController(connection=connect)
        except AttributeError as exc:
            raise BackendUnavailable(_python37_message(backend)) from exc

    if backend == "dyopilot-sitl":
        from dyopilot_version.dyopilot_sitl_controller import DyopilotSITLController

        return DyopilotSITLController(gcs_port=gcs_port, gcs_host=gcs_host)
    if backend == "dyopilot-pixhawk":
        from dyopilot_version.dyopilot_pixhawk_controller import DyopilotPixhawkController

        return DyopilotPixhawkController(connection=connect)
    raise ValueError(f"Unknown backend: {backend!r}")


def handle_command(command: str, controller: DroneController) -> Tuple[bool, str]:
    """Run one console command line against *controller*.

    Shared by the curses CLI and the web console. Returns
    ``(exit_requested, status_message)``.
    """
    if not command:
        return False, "Awaiting command..."

    parts = command.split()
    action = parts[0].lower()

    if action == "takeoff":
        if len(parts) != 2:
            return False, "Usage: takeoff <altitude meters>"
        try:
            altitude = float(parts[1])
        except ValueError:
            return False, "Altitude must be numeric"
        try:
            controller.arm_and_takeoff(altitude)
        except Exception as exc:  # noqa: BLE001
            return False, f"Takeoff failed: {exc}"
        return False, f"Takeoff initiated to {altitude:.1f} m"

    if action == "land":
        try:
            controller.land()
        except Exception as exc:  # noqa: BLE001
            return False, f"Landing failed: {exc}"
        return False, "Landing command sent"

    if action == "altitude":
        if len(parts) != 2:
            return False, "Usage: altitude <meters>"
        try:
            altitude = float(parts[1])
        except ValueError:
            return False, "Altitude must be numeric"
        try:
            controller.set_altitude(altitude)
        except Exception as exc:  # noqa: BLE001
            return False, f"Altitude change failed: {exc}"
        return False, f"Altitude set to {altitude:.1f} m"

    if action in {"forward", "back"}:
        if len(parts) != 2:
            return False, f"Usage: {action} <meters>"
        try:
            distance = float(parts[1])
        except ValueError:
            return False, "Distance must be numeric"
        try:
            getattr(controller, f"move_{action}")(distance)
        except Exception as exc:  # noqa: BLE001
            return False, f"{action.capitalize()} failed: {exc}"
        return False, f"Moving {action} {distance:.1f} m"

    if action in {"left", "right"}:
        if len(parts) != 2:
            return False, f"Usage: {action} <degrees>"
        try:
            degrees = float(parts[1])
        except ValueError:
            return False, "Degrees must be numeric"
        try:
            getattr(controller, f"rotate_{action}")(degrees)
        except Exception as exc:  # noqa: BLE001
            return False, f"Rotate {action} failed: {exc}"
        return False, f"Rotating {action} {degrees:.1f}°"

    if action in {"quit", "exit"}:
        return True, "Exiting CLI"

    return False, f"Unknown command: {action}"
