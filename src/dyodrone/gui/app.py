"""Web console for monitoring and commanding a drone from the browser."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import webbrowser

from dyodrone.gui.server import ConsoleServer
from dyodrone.core.factory import DRIVERS, default_driver
from dyodrone.gui.session import ConsoleSession

# DroneKit's autopilot logger would otherwise print status lines over the log.
logging.getLogger("autopilot").disabled = True


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments (bind address, driver, browser)."""
    parser = argparse.ArgumentParser(
        description=(
            "Web console for the drone: live vehicle info, a command prompt, and a "
            "Simulator/Pixhawk connection toggle. Serves on localhost only by default."
        )
    )
    parser.add_argument("--host", default="127.0.0.1", help="Address to bind (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8765, help="Port to serve on (default: 8765, 0 = any free port).")
    parser.add_argument(
        "--driver",
        choices=DRIVERS,
        default=None,
        help=(
            "Flight-control library. Default: dronekit on Python < 3.10, dyopilot "
            "otherwise. DroneKit only works on Python 3.7 (see docs/guide/how.rst)."
        ),
    )
    parser.add_argument("--plan-poll", type=float, default=3.0, metavar="SECONDS",
                        help="Flight plans: seconds between telemetry checks (default 3).")
    parser.add_argument("--plan-margin", type=float, default=0.10, metavar="FRACTION",
                        help="Flight plans: allowed error as a fraction of the commanded amount (default 0.10).")
    parser.add_argument("--plan-timeout", type=float, default=120.0, metavar="SECONDS",
                        help="Flight plans: fail a step not completed this long after it was sent (default 120).")
    parser.add_argument("--voice-delay", type=float, default=2.0, metavar="SECONDS",
                        help="Voice: seconds a recognised command waits, cancellable, before it runs (default 2; land is immediate).")
    parser.add_argument("--vosk-model", default=None, metavar="FOLDER",
                        help="Voice: unpacked Vosk model folder (default: download vosk-model-small-en-us once to ~/.cache/dyodrone).")
    parser.add_argument("--no-browser", action="store_true", help="Print the URL instead of opening a browser.")
    return parser.parse_args()


def main() -> int:
    """Start the server, open the browser, and disconnect the vehicle on exit."""
    args = parse_args()
    session = ConsoleSession(
        args.driver or default_driver(),
        plan_poll=args.plan_poll,
        plan_margin=args.plan_margin,
        plan_step_timeout=args.plan_timeout,
        voice_delay=args.voice_delay,
        vosk_model=args.vosk_model,
    )
    try:
        server = ConsoleServer((args.host, args.port), session)
    except OSError as exc:
        print(f"Cannot listen on {args.host}:{args.port}: {exc}", file=sys.stderr)
        return 1

    print(f"dyodrone web console ({session.driver} driver)")
    print(f"Open: {server.url}")
    print("Press Ctrl+C to stop; the vehicle connection is closed on exit.")
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print("Warning: bound to a non-loopback address; anyone with the URL token can command the vehicle.")
    if not args.no_browser:
        webbrowser.open(server.url)

    def _stop(signum, frame):  # SIGTERM: leave through the same cleanup path as Ctrl+C
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _stop)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        session.close()
        server.server_close()
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    sys.exit(main())
