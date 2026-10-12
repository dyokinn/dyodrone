"""Interactive CLI for monitoring and commanding a drone."""

from __future__ import annotations

import argparse
import curses
import logging
import sys
import time
from typing import Any, Optional

from dyodrone.core.commands import handle_command
from dyodrone.core.controller import DroneController
from dyodrone.core.factory import (
    DEFAULT_CONNECTION,
    DEFAULT_GCS_PORT,
    DRIVERS,
    BackendUnavailable,
    create_controller,
    default_driver,
)
from dyodrone.core.targets import TARGETS

# Silence autopilot logger that spams the curses console with status lines.
logging.getLogger("autopilot").disabled = True

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments (backend, connection, refresh and GCS options)."""
    parser = argparse.ArgumentParser(
        description=(
            "Interactive drone control CLI. Supports multiple backends: "
            "SITL simulation, Pixhawk hardware, and PyMAVLink."
        )
    )
    parser.add_argument(
        "--driver",
        choices=DRIVERS,
        default=default_driver(),
        help=(
            "Flight-control library: dronekit (Python 3.7 only) or dyopilot "
            "(pymavlink, current Python). Default for this interpreter: "
            f"{default_driver()} (see docs/guide/how.rst)."
        ),
    )
    parser.add_argument(
        "--target",
        choices=TARGETS,
        default="sitl",
        help="Vehicle to connect to: sitl (built-in simulator, default) or pixhawk.",
    )
    parser.add_argument(
        "--connect",
        type=str,
        default=None,
        help=(
            "Connection string for --target pixhawk (e.g. /dev/ttyUSB0, "
            f"tcp:192.168.1.1:5760). Default: {DEFAULT_CONNECTION}. Ignored for sitl."
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
        default=None,
        metavar="PORT",
        help=(
            "UDP port for the QGroundControl proxy. Default: "
            f"{DEFAULT_GCS_PORT} for --target sitl, off for pixhawk. 0 disables it."
        ),
    )
    parser.add_argument(
        "--gcs-host",
        type=str,
        default="127.0.0.1",
        metavar="HOST",
        help=(
            "IP address of the machine running QGroundControl (default: 127.0.0.1). "
            "Use 255.255.255.255 to broadcast to the whole LAN."
        ),
    )
    return parser.parse_args()


def build_controller(args: argparse.Namespace) -> DroneController:
    """Instantiate the controller selected by ``--driver`` and ``--target``.

    Thin wrapper over :func:`dyodrone.core.factory.create_controller` that
    applies the proxy default and turns an unusable driver into a clean exit.
    """
    gcs_port = args.gcs_port
    if gcs_port is None:
        gcs_port = DEFAULT_GCS_PORT if args.target == "sitl" else 0
    try:
        return create_controller(args.driver, args.target, args.connect, gcs_port, args.gcs_host)
    except BackendUnavailable as exc:
        raise SystemExit(str(exc))


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
    """Connect *controller*, run the curses console, and always close it on exit."""
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
    """CLI entry point: parse arguments, build the backend, run the console."""
    args = parse_args()

    print(f"Starting {args.driver} driver, {args.target} target...")
    controller = build_controller(args)
    return run_cli(interval=args.interval, duration=args.duration, controller=controller)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
