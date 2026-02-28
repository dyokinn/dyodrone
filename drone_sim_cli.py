"""Interactive CLI for monitoring and commanding a drone."""

from __future__ import annotations

import argparse
import curses
import logging
import sys
import time
from typing import Any, Optional, Tuple

from dronekit_version.dronekit_controller import DroneController

# Silence autopilot logger that spams the curses console with status lines.
logging.getLogger("autopilot").disabled = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Start the DroneKit SITL simulator, show vehicle telemetry, and accept "
            "basic flight commands from the terminal."
        )
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
        "--connect",
        type=str,
        default=None,
        help=(
            "Vehicle connection string. When omitted the CLI starts a simulator and "
            "connects to it."
        ),
    )
    parser.add_argument(
        "--no-sim",
        action="store_true",
        help="Disable the built-in simulator and use the provided --connect string.",
    )
    return parser.parse_args()


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

    base_row = len(lines) + 1
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
        "Commands: takeoff <alt>, altitude <alt>, north/south/east/west <m>, land, quit"[
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

    if action in {"north", "south", "east", "west"}:
        if len(parts) != 2:
            return False, f"Usage: {action} <meters>"
        try:
            distance = float(parts[1])
        except ValueError:
            return False, "Distance must be numeric"
        try:
            getattr(controller, f"move_{action}")(distance)
        except Exception as exc:  # noqa: BLE001
            return False, f"Move {action} failed: {exc}"
        return False, f"Moving {action} {distance:.1f} m"

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
    if controller.use_simulator:
        print("Starting simulator (SITL)...")

    connection_desc: Optional[str] = None
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
        if controller.use_simulator:
            print("SITL stopped. Goodbye!")
        else:
            print("Connection closed. Goodbye!")

    return 0


def main() -> int:
    args = parse_args()
    use_simulator = not args.no_sim
    if not use_simulator and not args.connect:
        print("--connect is required when --no-sim is provided.", file=sys.stderr)
        return 1

    controller = DroneController(
        connection=args.connect,
        use_simulator=use_simulator,
    )
    return run_cli(
        interval=args.interval, duration=args.duration, controller=controller
    )


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
