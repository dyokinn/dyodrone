"""``dyodrone-plan``: run a flight-plan text file with no UI."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
from pathlib import Path
from typing import List, Optional

from dyodrone.core.expect import Tolerances, describe_step
from dyodrone.core.factory import (
    DEFAULT_CONNECTION,
    DEFAULT_GCS_PORT,
    DRIVERS,
    BackendUnavailable,
    create_controller,
    default_driver,
    default_gcs_port,
)
from dyodrone.core.plan import PlanError, Step, parse_plan
from dyodrone.core.plan_runner import PlanEvent, PlanRunner
from dyodrone.core.targets import TARGETS

logging.getLogger("autopilot").disabled = True


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments for ``dyodrone-plan``."""
    parser = argparse.ArgumentParser(
        prog="dyodrone-plan",
        description=(
            "Run a flight plan: one console command per line (takeoff, altitude, forward, back, "
            "left, right, land, wait). After each command the vehicle's telemetry is checked "
            "every --poll seconds and the next step starts once the expected state is reached "
            "within --margin."
        ),
    )
    parser.add_argument("plan", help="Path to the plan text file.")
    parser.add_argument("--driver", choices=DRIVERS, default=default_driver(),
                        help=f"Flight-control library (default for this Python: {default_driver()}).")
    parser.add_argument("--target", choices=TARGETS, default="sitl",
                        help="sitl (built-in simulator, default) or pixhawk.")
    parser.add_argument("--connect", default=None,
                        help=f"Connection string for --target pixhawk (default {DEFAULT_CONNECTION}).")
    parser.add_argument("--gcs-port", type=int, default=None, metavar="PORT",
                        help=f"QGroundControl proxy UDP port (default {DEFAULT_GCS_PORT} for sitl, off for pixhawk; 0 disables).")
    parser.add_argument("--gcs-host", default="127.0.0.1", metavar="HOST")
    parser.add_argument("--poll", type=float, default=3.0, metavar="SECONDS",
                        help="Seconds between telemetry checks while a command runs (default 3).")
    parser.add_argument("--margin", type=float, default=0.10, metavar="FRACTION",
                        help="Allowed error as a fraction of the commanded amount (default 0.10 = 10%%).")
    parser.add_argument("--step-timeout", type=float, default=120.0, metavar="SECONDS",
                        help="Fail a step that has not completed this long after it was sent (default 120).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate the plan and print what each step expects; do not connect.")
    return parser.parse_args(argv)


def _print_steps(steps: List[Step], tol: Tolerances) -> None:
    for i, step in enumerate(steps, start=1):
        print(f"  {i:>2}. {step.command:<16} expects {describe_step(step, tol)}")


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point. Exit code 0 = plan completed, 1 = failed or stopped, 2 = invalid plan."""
    args = parse_args(argv)
    tol = Tolerances(margin=args.margin)

    try:
        text = Path(args.plan).read_text()
    except OSError as exc:
        print(f"Cannot read {args.plan}: {exc}", file=sys.stderr)
        return 2
    try:
        steps = parse_plan(text)
    except PlanError as exc:
        print(f"Invalid plan {args.plan}:", file=sys.stderr)
        for line, message in exc.errors:
            print(f"  line {line}: {message}" if line else f"  {message}", file=sys.stderr)
        return 2

    print(f"{args.plan}: {len(steps)} steps")
    if args.dry_run:
        _print_steps(steps, tol)
        return 0

    try:
        controller = create_controller(
            args.driver, args.target, args.connect, default_gcs_port(args.target, args.gcs_port), args.gcs_host
        )
    except BackendUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 1

    def show(event: PlanEvent) -> None:
        print(event.line(), flush=True)

    runner = PlanRunner(
        controller, steps, poll=args.poll, step_timeout=args.step_timeout, tolerances=tol, on_event=show
    )

    def stop(signum, frame):  # Ctrl-C / SIGTERM: stop issuing commands, then clean up
        runner.stop()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    try:
        print(f"Connecting ({args.driver}/{args.target}) …", flush=True)
        controller.connect()
        print(f"Connected: {controller.active_connection}", flush=True)
        completed = runner.run()
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        controller.close()
        print("Connection closed.")
    return 0 if completed else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
