"""Web console for monitoring and commanding a drone from the browser."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import webbrowser
from pathlib import Path

# This script lives in entry_points/, so sys.path[0] is that folder, not the
# repo root where the packages live.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from drone_gui.server import ConsoleServer  # noqa: E402
from drone_gui.session import FAMILIES, ConsoleSession, default_family  # noqa: E402

# DroneKit's autopilot logger would otherwise print status lines over the log.
logging.getLogger("autopilot").disabled = True


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments (bind address, backend family, browser)."""
    parser = argparse.ArgumentParser(
        description=(
            "Web console for the drone: live vehicle info, a command prompt, and a "
            "Simulator/Pixhawk connection toggle. Serves on localhost only by default."
        )
    )
    parser.add_argument("--host", default="127.0.0.1", help="Address to bind (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8765, help="Port to serve on (default: 8765, 0 = any free port).")
    parser.add_argument(
        "--family",
        choices=FAMILIES,
        default=None,
        help=(
            "Backend family. Default: dronekit on Python < 3.10, dyopilot otherwise. "
            "DroneKit only works on Python 3.7 (see docs/guide/how.rst)."
        ),
    )
    parser.add_argument("--no-browser", action="store_true", help="Print the URL instead of opening a browser.")
    return parser.parse_args()


def main() -> int:
    """Start the server, open the browser, and disconnect the vehicle on exit."""
    args = parse_args()
    session = ConsoleSession(args.family or default_family())
    try:
        server = ConsoleServer((args.host, args.port), session)
    except OSError as exc:
        print(f"Cannot listen on {args.host}:{args.port}: {exc}", file=sys.stderr)
        return 1

    print(f"dyodrone web console ({session.family} backends)")
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
