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
from typing import Any, Callable, Dict, List, Optional, Tuple

from dyodrone.core.commands import COMMAND_HELP, handle_command, is_error_message
from dyodrone.core.factory import (
    DEFAULT_CONNECTION,
    DEFAULT_GCS_PORT,
    DRIVERS,
    BackendUnavailable,
    create_controller,
    default_driver,
)
from dyodrone.core.expect import Tolerances
from dyodrone.core.plan import RECORDABLE_VERBS, PlanError, format_plan, parse_plan
from dyodrone.core.plan_runner import PAUSED, RUNNING, PlanEvent, PlanRunner
from dyodrone.core.targets import TARGETS

#: Input types that can be switched on and off at runtime.
INPUTS = ("console", "plan", "voice")

#: Where a command came from. ``emergency`` bypasses every switch and lock.
SOURCES = ("console", "voice", "emergency")


# Connection states reported to the page.
DISCONNECTED = "disconnected"
CONNECTING = "connecting"
CONNECTED = "connected"
DISCONNECTING = "disconnecting"
ERROR = "error"


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
    plan_poll, plan_margin, plan_step_timeout:
        Flight-plan settings: seconds between telemetry checks, allowed error as
        a fraction of the commanded amount, and per-step timeout.
    clock, sleep:
        Injectable for tests (used by the plan runner).
    """

    def __init__(
        self,
        driver: Optional[str] = None,
        max_log: int = 1000,
        plan_poll: float = 3.0,
        plan_margin: float = 0.10,
        plan_step_timeout: float = 120.0,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
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
        self._commands: "queue.Queue[Tuple[str, str]]" = queue.Queue()

        self.inputs: Dict[str, bool] = {"console": True, "plan": False, "voice": False}
        self._plan_poll, self._plan_margin, self._plan_step_timeout = plan_poll, plan_margin, plan_step_timeout
        self._clock, self._sleep = clock, sleep
        self._runner: Optional[PlanRunner] = None
        self._plan_text = ""
        self._plan_view: List[Dict[str, Any]] = []
        self._history: List[str] = []

        self._worker = threading.Thread(target=self._run_commands, name="console-commands", daemon=True)
        self._worker.start()
        self._add("sys", f"dyodrone console — {driver} driver, Python {sys.version.split()[0]}. Type 'help'.")

    # ------------------------------------------------------------------
    # Log
    # ------------------------------------------------------------------

    def _add(self, kind: str, text: str, source: Optional[str] = None) -> None:
        with self._lock:
            self._log.append(
                {"id": self._next_id, "ts": time.time(), "kind": kind, "text": text, "source": source}
            )
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
        self._stop_plan()
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
        self._stop_plan()
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

    def submit(self, line: str, source: str = "console") -> None:
        """Accept one command line; flight commands run in order on the worker thread.

        *source* is ``"console"``, ``"voice"`` or ``"emergency"``. A source whose
        input switch is off is refused, and while a flight plan runs console and
        voice commands are locked out (``emergency`` is never blocked).
        """
        line = (line or "").strip()
        if not line:
            return
        if source not in SOURCES:
            raise ValueError(f"source must be one of {SOURCES}, got {source!r}")
        self._gate(source)
        self._add("cmd", line, source)
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
        self._commands.put((line, source))

    def _gate(self, source: str) -> None:
        """Raise :class:`SessionError` if *source* may not send commands right now."""
        if source == "emergency":
            return
        if not self.inputs.get(source, False):
            raise SessionError(f"{source.capitalize()} input is off. Turn it on with the {source.capitalize()} switch.")
        if self._plan_active():
            raise SessionError("A flight plan is running — stop it first, or use Land now.")

    def _run_commands(self) -> None:
        while True:
            line, source = self._commands.get()
            with self._lock:
                controller = self._controller
                self._busy = line
            try:
                if controller is None:
                    self._add("err", "Not connected. Use Connect.")
                    continue
                self._execute(line, controller, source)
            except Exception as exc:  # noqa: BLE001
                self._add("err", f"{line.split()[0]} failed: {exc}")
            finally:
                with self._lock:
                    self._busy = ""

    def _execute(self, line: str, controller: Any, source: str) -> None:
        _, message = handle_command(line, controller)
        failed = is_error_message(message)
        self._add("err" if failed else "out", message)
        if not failed and source in ("console", "voice"):
            self._record(line)

    # ------------------------------------------------------------------
    # Input switches and emergency
    # ------------------------------------------------------------------

    def set_inputs(self, **flags: bool) -> Dict[str, bool]:
        """Turn input types on or off at runtime; returns the new switch state."""
        for name, value in flags.items():
            if name not in INPUTS:
                raise ValueError(f"unknown input {name!r} (expected one of {', '.join(INPUTS)})")
            if not isinstance(value, bool):
                raise ValueError(f"input {name!r} must be true or false")
        for name, value in flags.items():
            if self.inputs[name] == value:
                continue
            self.inputs[name] = value
            self._add("sys", f"{name.capitalize()} input turned {'on' if value else 'off'}.")
            if not value and name == "plan":
                self._stop_plan()
        return dict(self.inputs)

    def emergency_land(self) -> None:
        """Land immediately: stop any plan, drop queued commands, bypass every switch."""
        with self._lock:
            controller = self._controller if self._status == CONNECTED else None
        if controller is None:
            raise SessionError("Not connected.")
        self._add("err", "EMERGENCY LAND", "emergency")
        self._stop_plan()
        self._drain_commands()
        threading.Thread(target=self._emergency, args=(controller,), daemon=True).start()

    def _emergency(self, controller: Any) -> None:
        try:
            self._execute("land", controller, "emergency")
        except Exception as exc:  # noqa: BLE001
            self._add("err", f"Emergency land failed: {exc}")

    # ------------------------------------------------------------------
    # Flight plans
    # ------------------------------------------------------------------

    def _plan_active(self) -> bool:
        runner = self._runner
        return runner is not None and runner.state in (RUNNING, PAUSED)

    def _stop_plan(self) -> None:
        runner = self._runner
        if runner is not None and runner.state in (RUNNING, PAUSED):
            runner.stop()

    def plan_validate(self, text: str) -> List[Dict[str, Any]]:
        """Parse *text* and make it the loaded plan. Raises :class:`PlanError` listing every problem."""
        if self._plan_active():
            raise SessionError("A flight plan is running; stop it before loading another.")
        steps = parse_plan(text)
        with self._lock:
            self._plan_text = text
            self._plan_view = [{"line": st.line, "command": st.command, "state": "pending", "detail": ""} for st in steps]
            self._runner = None
            return [dict(v) for v in self._plan_view]

    def plan_run(self) -> None:
        """Start the loaded plan on its own thread (closed-loop, see :class:`PlanRunner`)."""
        with self._lock:
            if not self.inputs["plan"]:
                raise SessionError("Plan input is off. Turn it on with the Plan switch.")
            if self._status != CONNECTED or self._controller is None:
                raise SessionError("Not connected. Use Connect.")
            if self._plan_active():
                raise SessionError("A flight plan is already running.")
            if not self._plan_text:
                raise SessionError("No plan loaded. Validate or upload a plan first.")
            if self._busy or not self._commands.empty():
                raise SessionError("Wait for the current command to finish before starting a plan.")
            runner = PlanRunner(
                self._controller,
                parse_plan(self._plan_text),
                poll=self._plan_poll,
                step_timeout=self._plan_step_timeout,
                tolerances=Tolerances(margin=self._plan_margin),
                on_event=self._on_plan_event,
                clock=self._clock,
                sleep=self._sleep,
            )
            self._runner = runner
        threading.Thread(target=self._run_plan, args=(runner,), name="flight-plan", daemon=True).start()

    def _run_plan(self, runner: PlanRunner) -> None:
        try:
            runner.run()
        except Exception as exc:  # noqa: BLE001
            self._add("err", f"Flight plan crashed: {exc}")

    def _on_plan_event(self, event: PlanEvent) -> None:
        # Only transitions go to the log; the per-poll detail lives in the plan panel.
        if event.index < 0:
            self._add("plan", event.line())
        elif event.state in ("sending", "done", "failed"):
            self._add("err" if event.state == "failed" else "plan", event.line())

    def plan_pause(self) -> None:
        self._require_running_plan().pause()

    def plan_resume(self) -> None:
        self._require_running_plan().resume()

    def plan_stop(self) -> None:
        self._require_running_plan().stop()

    def _require_running_plan(self) -> PlanRunner:
        runner = self._runner
        if runner is None or runner.state not in (RUNNING, PAUSED):
            raise SessionError("No flight plan is running.")
        return runner

    def _record(self, line: str) -> None:
        """Remember a flight command that worked, so the session can be saved as a plan."""
        try:
            step = parse_plan(line)[0]
        except PlanError:
            return
        if step.verb in RECORDABLE_VERBS:
            with self._lock:
                self._history.append(step.command)

    def history_text(self) -> str:
        """Commands that completed without error this session, as plan text."""
        with self._lock:
            commands = list(self._history)
        return format_plan(commands, header="recorded from the console session") if commands else ""

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()

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
        runner = self._runner
        with self._lock:
            plan = runner.snapshot() if runner is not None else {
                "state": "idle", "index": -1, "total": len(self._plan_view), "message": "",
                "steps": [dict(v) for v in self._plan_view],
            }
            plan["loaded"] = bool(self._plan_text)
            return {
                "driver": self.driver,
                "python": sys.version.split()[0],
                "target": self.target,
                "connection": self.connection,
                "gcs_port": self.gcs_port,
                "status": self._status,
                "busy": self._busy,
                "queued": self._commands.qsize(),
                "inputs": dict(self.inputs),
                "plan": plan,
                "history": len(self._history),
                "telemetry": lines,
                "details": details,
                "log": [e for e in self._log if e["id"] > since],
                "last_id": self._next_id - 1,
            }
