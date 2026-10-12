"""Console command handling shared by the curses CLI and the web console."""

from __future__ import annotations

from typing import List, Tuple

from dyodrone.core.controller import DroneController

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
