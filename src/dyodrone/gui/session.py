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

from dyodrone.core.commands import COMMAND_HELP, handle_command
from dyodrone.core.factory import (
    DEFAULT_CONNECTION,
    DEFAULT_GCS_PORT,
    DRIVERS,
    BackendUnavailable,
    create_controller,
    default_driver,
)
from dyodrone.core.targets import TARGETS


# Connection states reported to the page.
DISCONNECTED = "disconnected"
CONNECTING = "connecting"
CONNECTED = "connected"
DISCONNECTING = "disconnecting"
ERROR = "error"

_ERROR_MARKERS = ("failed", "usage:", "unknown command", "must be", "not connected")


class SessionError(Exception):
    """An action is not valid in the session's current state (HTTP 409)."""


class ConsoleSession:
    """Owns the controller, the connection state and a capped command log.

    Parameters
    ----------
    driver:
        ``"dronekit"`` or ``"dyopilot"``. Fixed for the life of the session: a
        process runs on one interpreter, and DroneKit and dyopilot need
        different ones (see the installation guide).
    max_log:
        Number of log entries kept; older ones are dropped.
    """

    def __init__(self, driver: Optional[str] = None, max_log: int = 1000) -> None:
        driver = driver or default_driver()
        if driver not in DRIVERS:
            raise ValueError(f"driver must be one of {DRIVERS}, got {driver!r}")
        self.driver = driver
        self.target = "sitl"
        self.connection = DEFAULT_CONNECTION
        self.gcs_port = DEFAULT_GCS_PORT

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
        self._add("sys", f"dyodrone console — {driver} driver, Python {sys.version.split()[0]}. Type 'help'.")

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

    def connect(self, target: str, connection: Optional[str] = None, gcs_port: Optional[int] = None) -> None:
        """Start connecting to *target* (``"sitl"`` or ``"pixhawk"``) in the background.

        ``connection`` is the Pixhawk connection string; ``gcs_port`` is the
        QGroundControl proxy port for the simulator (``0`` disables it).
        """
        if target not in TARGETS:
            raise ValueError(f"target must be one of {TARGETS}, got {target!r}")
        if gcs_port is not None and not 0 <= gcs_port <= 65535:
            raise ValueError("gcs_port must be between 0 and 65535")
        connection = (connection or "").strip() or DEFAULT_CONNECTION

        with self._lock:
            if self._status in (CONNECTING, CONNECTED, DISCONNECTING):
                raise SessionError(f"Cannot connect while {self._status}")
            self._status = CONNECTING
            self.target = target
            if target == "pixhawk":
                self.connection = connection
            if gcs_port is not None:
                self.gcs_port = gcs_port
            proxy_port = self.gcs_port if target == "sitl" else 0

        threading.Thread(target=self._connect, args=(target, connection, proxy_port), daemon=True).start()

    def _connect(self, target: str, connection: str, gcs_port: int) -> None:
        label = "built-in simulator" if target == "sitl" else connection
        self._add("sys", f"Connecting ({self.driver}/{target}) to {label} …")
        controller = None
        try:
            controller = create_controller(self.driver, target, connection, gcs_port)
            controller.connect()
        except BackendUnavailable as exc:
            self._fail(str(exc), controller)
            return
        except Exception as exc:  # noqa: BLE001 - surface any driver failure in the console
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
                "driver": self.driver,
                "python": sys.version.split()[0],
                "target": self.target,
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
