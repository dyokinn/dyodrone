"""Console session: one vehicle connection plus its command log.

The web server is a thin layer over :class:`ConsoleSession`. Everything that can
block — booting a simulator, ``takeoff``, closing the connection — runs on a
worker thread so HTTP requests return immediately and the page stays live.
"""

from __future__ import annotations

import queue
import sys
import threading
import time
from typing import Any, Dict, List, Optional

from drone_console import (
    COMMAND_HELP,
    DEFAULT_CONNECT,
    BackendUnavailable,
    create_controller,
    handle_command,
)

FAMILIES = ("dronekit", "dyopilot")
MODES = ("sitl", "pixhawk")

# Connection states reported to the page.
DISCONNECTED = "disconnected"
CONNECTING = "connecting"
CONNECTED = "connected"
DISCONNECTING = "disconnecting"
ERROR = "error"

_ERROR_MARKERS = ("failed", "usage:", "unknown command", "must be", "not connected")


class SessionError(Exception):
    """An action is not valid in the session's current state (HTTP 409)."""


def default_family() -> str:
    """Backend family that can run on this interpreter."""
    return "dronekit" if sys.version_info < (3, 10) else "dyopilot"


class ConsoleSession:
    """Owns the controller, the connection state and a capped command log.

    Parameters
    ----------
    family:
        ``"dronekit"`` or ``"dyopilot"``. Fixed for the life of the session: a
        process runs on one interpreter, and DroneKit and dyopilot need
        different ones (see the installation guide).
    max_log:
        Number of log entries kept; older ones are dropped.
    """

    def __init__(self, family: Optional[str] = None, max_log: int = 1000) -> None:
        family = family or default_family()
        if family not in FAMILIES:
            raise ValueError(f"family must be one of {FAMILIES}, got {family!r}")
        self.family = family
        self.mode = "sitl"
        self.connection = DEFAULT_CONNECT.get(f"{family}-pixhawk", "")
        self.gcs_port = 14550

        self._lock = threading.RLock()
        self._controller: Any = None
        self._status = DISCONNECTED
        self._busy = ""
        self._log: List[Dict[str, Any]] = []
        self._next_id = 1
        self._max_log = max_log
        self._commands: "queue.Queue[str]" = queue.Queue()

        self._worker = threading.Thread(target=self._run_commands, name="console-commands", daemon=True)
        self._worker.start()
        self._add("sys", f"dyodrone console — {family} backends, Python {sys.version.split()[0]}. Type 'help'.")

    # ------------------------------------------------------------------
    # Log
    # ------------------------------------------------------------------

    def _add(self, kind: str, text: str) -> None:
        with self._lock:
            self._log.append({"id": self._next_id, "ts": time.time(), "kind": kind, "text": text})
            self._next_id += 1
            if len(self._log) > self._max_log:
                del self._log[: len(self._log) - self._max_log]

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self, mode: str, connection: Optional[str] = None, gcs_port: Optional[int] = None) -> None:
        """Start connecting in the background using the ``<family>-<mode>`` backend."""
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
        if gcs_port is not None and not 0 <= gcs_port <= 65535:
            raise ValueError("gcs_port must be between 0 and 65535")
        connection = (connection or "").strip() or DEFAULT_CONNECT.get(f"{self.family}-{mode}", "")
        if mode == "pixhawk" and not connection:
            raise ValueError("A connection string is required for Pixhawk mode")

        with self._lock:
            if self._status in (CONNECTING, CONNECTED, DISCONNECTING):
                raise SessionError(f"Cannot connect while {self._status}")
            self._status = CONNECTING
            self.mode = mode
            if mode == "pixhawk":
                self.connection = connection
            if gcs_port is not None:
                self.gcs_port = gcs_port

        threading.Thread(target=self._connect, args=(mode, connection, self.gcs_port), daemon=True).start()

    def _connect(self, mode: str, connection: str, gcs_port: int) -> None:
        backend = f"{self.family}-{mode}"
        target = "built-in simulator" if mode == "sitl" else connection
        self._add("sys", f"Connecting ({backend}) to {target} …")
        controller = None
        try:
            controller = create_controller(backend, connection if mode == "pixhawk" else None, gcs_port)
            controller.connect()
        except BackendUnavailable as exc:
            self._fail(str(exc), controller)
            return
        except Exception as exc:  # noqa: BLE001 - surface any backend failure in the console
            self._fail(f"Connection failed: {exc}", controller)
            return
        with self._lock:
            self._controller = controller
            self._status = CONNECTED
        self._add("sys", f"Connected: {controller.active_connection}")

    def _fail(self, message: str, controller: Any) -> None:
        if controller is not None:
            try:
                controller.close()
            except Exception:  # noqa: BLE001
                pass
        with self._lock:
            self._controller = None
            self._status = ERROR
        self._add("err", message)

    def disconnect(self) -> None:
        """Close the connection in the background (stops the proxy and any simulator)."""
        with self._lock:
            if self._status == CONNECTING:
                raise SessionError("Connection in progress; wait for it to finish")
            if self._status == DISCONNECTING:
                return
            controller = self._controller
            if controller is None:
                self._status = DISCONNECTED
                return
            self._status = DISCONNECTING
        self._drain_commands()
        threading.Thread(target=self._close_controller, args=(controller,), daemon=True).start()

    def _close_controller(self, controller: Any) -> None:
        self._add("sys", "Disconnecting …")
        try:
            controller.close()
        except Exception as exc:  # noqa: BLE001
            self._add("err", f"Error while closing: {exc}")
        with self._lock:
            self._controller = None
            self._status = DISCONNECTED
        self._add("sys", "Disconnected.")

    def close(self) -> None:
        """Synchronous disconnect for process shutdown."""
        with self._lock:
            controller = self._controller
            self._controller = None
            self._status = DISCONNECTED
        if controller is not None:
            try:
                controller.close()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def submit(self, line: str) -> None:
        """Accept one console line; flight commands run in order on the worker thread."""
        line = (line or "").strip()
        if not line:
            return
        self._add("cmd", line)
        verb = line.split()[0].lower()

        if verb == "help":
            self._add("out", "\n".join(COMMAND_HELP + ["info              print the vehicle snapshot", "clear             clear the screen (Ctrl-L)"]))
            return
        if verb == "info":
            lines, details = self._telemetry()
            self._add("out", "\n".join(lines + details) if lines else "Not connected. Use Connect.")
            return
        if verb in ("quit", "exit"):
            try:
                self.disconnect()
            except SessionError as exc:
                self._add("err", str(exc))
            return

        if self._status != CONNECTED:
            self._add("err", "Not connected. Use Connect.")
            return
        self._commands.put(line)

    def _run_commands(self) -> None:
        while True:
            line = self._commands.get()
            with self._lock:
                controller = self._controller
                self._busy = line
            try:
                if controller is None:
                    self._add("err", "Not connected. Use Connect.")
                    continue
                _, message = handle_command(line, controller)
                lowered = message.lower()
                self._add("err" if any(m in lowered for m in _ERROR_MARKERS) else "out", message)
            except Exception as exc:  # noqa: BLE001
                self._add("err", f"{line.split()[0]} failed: {exc}")
            finally:
                with self._lock:
                    self._busy = ""

    def _drain_commands(self) -> None:
        try:
            while True:
                self._commands.get_nowait()
        except queue.Empty:
            pass

    # ------------------------------------------------------------------
    # State for the page
    # ------------------------------------------------------------------

    def _telemetry(self):
        with self._lock:
            controller = self._controller if self._status == CONNECTED else None
        if controller is None:
            return [], []
        try:
            return list(controller.status_lines()), list(controller.connection_details())
        except Exception as exc:  # noqa: BLE001
            return [f"Telemetry unavailable: {exc}"], []

    def snapshot(self, since: int = 0) -> Dict[str, Any]:
        """Everything the page needs: state, telemetry and log entries after *since*."""
        lines, details = self._telemetry()
        with self._lock:
            return {
                "family": self.family,
                "python": sys.version.split()[0],
                "mode": self.mode,
                "connection": self.connection,
                "gcs_port": self.gcs_port,
                "status": self._status,
                "busy": self._busy,
                "queued": self._commands.qsize(),
                "telemetry": lines,
                "details": details,
                "log": [e for e in self._log if e["id"] > since],
                "last_id": self._next_id - 1,
            }
