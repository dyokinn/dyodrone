"""Interactive CLI for monitoring and commanding a drone."""

from __future__ import annotations

import argparse
import curses
import logging
import sys
import time
from typing import Any, Optional, Tuple

from drone_controller import DroneController
from dronekit_version.dronekit_sitl_controller import DronekitSITLController
from dronekit_version.dronekit_pixhawk_controller import DronekitPixhawkController
from dyopilot_version.dyopilot import PyMAVLinkController

# Silence autopilot logger that spams the curses console with status lines.
logging.getLogger("autopilot").disabled = True

# Default connection strings used when --connect is omitted.
_DEFAULT_CONNECT: dict[str, str] = {
    "pixhawk": "tcp:127.0.0.1:5760",
    "mavlink": "tcp:127.0.0.1:5760",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Interactive drone control CLI. Supports multiple backends: "
            "SITL simulation, Pixhawk hardware, and PyMAVLink."
        )
    )
    parser.add_argument(
        "--backend",
        choices=["sitl", "pixhawk", "mavlink"],
        default="sitl",
        help="Backend to use: sitl (default), pixhawk, or mavlink.",
    )
    parser.add_argument(
        "--connect",
        type=str,
        default=None,
        help=(
            "Vehicle connection string (e.g. /dev/ttyUSB0, tcp:192.168.1.1:5760). "
            "Defaults to tcp:127.0.0.1:5760 for pixhawk and mavlink when omitted."
        ),
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Seconds between telemetry refreshes (default: 2.0)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Optional time limit in seconds. Runs until quit when omitted.",
    )
    parser.add_argument(
        "--gcs-port",
        type=int,
        default=14550,
        metavar="PORT",
        help=(
            "UDP port for the QGroundControl proxy (default: 14550). "
            "Set to 0 to disable. Only applies to --backend sitl."
        ),
    )
    parser.add_argument(
        "--gcs-host",
        type=str,
        default="127.0.0.1",
        metavar="HOST",
        help=(
            "IP address of the machine running QGroundControl (default: 127.0.0.1). "
            "Use 255.255.255.255 to broadcast to the whole LAN. "
            "Only applies to --backend sitl."
        ),
    )
    return parser.parse_args()


def build_controller(args: argparse.Namespace) -> DroneController:
    if args.backend == "sitl":
        gcs_port = args.gcs_port if args.gcs_port else None
        return DronekitSITLController(gcs_port=gcs_port, gcs_host=args.gcs_host)
    if args.backend == "pixhawk":
        return DronekitPixhawkController(connection=args.connect)
    if args.backend == "mavlink":
        return PyMAVLinkController()
    raise ValueError(f"Unknown backend: {args.backend!r}")


def safe_addstr(stdscr: Any, y: int, x: int, text: str) -> None:
    try:
        stdscr.addstr(y, x, text)
    except curses.error:
        pass


def render_screen(
    stdscr: Any,
    controller: DroneController,
    status_message: str,
    command_buffer: str,
) -> None:
    stdscr.erase()
    _, width = stdscr.getmaxyx()
    max_width = max(1, width - 1)
    lines = controller.status_lines()
    for idx, line in enumerate(lines):
        safe_addstr(stdscr, idx, 0, line[:max_width])

    conn_lines = controller.connection_details()
    conn_start = len(lines) + 1
    for i, line in enumerate(conn_lines):
        safe_addstr(stdscr, conn_start + i, 0, line[:max_width])

    base_row = conn_start + len(conn_lines) + 1
    safe_addstr(
        stdscr,
        base_row,
        0,
        f"Last command: {status_message}"[:max_width],
    )
    safe_addstr(
        stdscr,
        base_row + 2,
        0,
        "Commands: takeoff <alt>, altitude <alt>, forward/back <m>, left/right <deg>, land, quit"[
            :max_width
        ],
    )
    prompt = f"> {command_buffer}"
    safe_addstr(stdscr, base_row + 3, 0, prompt[:max_width])
    try:
        stdscr.move(base_row + 3, min(len(prompt), max_width))
    except curses.error:
        pass
    stdscr.refresh()


def handle_command(command: str, controller: DroneController) -> Tuple[bool, str]:
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


def cli_loop(
    stdscr: Any,
    controller: DroneController,
    interval: float,
    duration: Optional[float],
) -> None:
    curses.noecho()
    stdscr.nodelay(True)
    stdscr.keypad(True)
    stdscr.timeout(100)
    try:
        curses.curs_set(1)
    except curses.error:
        pass

    buffer = ""
    status_message = "Ready."
    last_refresh = 0.0
    start_time = time.time()

    render_screen(stdscr, controller, status_message, buffer)

    while True:
        now = time.time()
        if now - last_refresh >= interval:
            render_screen(stdscr, controller, status_message, buffer)
            last_refresh = now

        if duration and now - start_time >= duration:
            status_message = "Duration elapsed. Shutting down."
            render_screen(stdscr, controller, status_message, buffer)
            time.sleep(1)
            break

        key = stdscr.getch()
        if key == -1:
            continue

        if key in (curses.KEY_BACKSPACE, 127, 8):
            if buffer:
                buffer = buffer[:-1]
                render_screen(stdscr, controller, status_message, buffer)
            continue

        if key in (10, 13):
            command = buffer.strip()
            buffer = ""
            exit_requested, status_message = handle_command(command, controller)
            render_screen(stdscr, controller, status_message, buffer)
            if exit_requested:
                time.sleep(0.5)
                break
            continue

        if key == curses.KEY_RESIZE:
            render_screen(stdscr, controller, status_message, buffer)
            continue

        if 32 <= key <= 126:
            buffer += chr(key)
            render_screen(stdscr, controller, status_message, buffer)


def run_cli(
    interval: float,
    duration: Optional[float],
    controller: DroneController,
) -> int:
    try:
        controller.connect()
        connection_desc = controller.active_connection
        if connection_desc:
            print(f"Connected to vehicle on: {connection_desc}")
        print("Launching interactive console. Press Ctrl+C to exit.")
        curses.wrapper(cli_loop, controller, interval, duration)
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    finally:
        controller.close()
        print("Connection closed. Goodbye!")

    return 0


def main() -> int:
    args = parse_args()

    if not args.connect and args.backend in _DEFAULT_CONNECT:
        args.connect = _DEFAULT_CONNECT[args.backend]

    print(f"Starting {args.backend} backend...")
    controller = build_controller(args)
    return run_cli(interval=args.interval, duration=args.duration, controller=controller)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
