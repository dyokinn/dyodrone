"""Runs a flight plan closed-loop: send a command, then wait until it has finished.

For every step the runner

1. snapshots telemetry and computes the expected end state
   (:func:`dyodrone.core.expect.expected_after`),
2. sends the command exactly like the console would,
3. every ``poll`` seconds (default 3) reads fresh telemetry and compares it with
   the expectation within the configured margin (default 10 %),
4. moves on when it matches, or fails the plan after ``step_timeout`` seconds.

The plan stops at the first failing step and never lands on its own; use the
``land`` command (or "Land now" in the web console) for that.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from dyodrone.core.commands import handle_command, is_error_message
from dyodrone.core.controller import DroneController
from dyodrone.core.expect import MissingTelemetry, Tolerances, expected_after
from dyodrone.core.plan import Step
from dyodrone.core.telemetry import Telemetry

# Plan states.
IDLE = "idle"
RUNNING = "running"
PAUSED = "paused"
DONE = "done"
FAILED = "failed"
STOPPED = "stopped"

# Per-step states.
PENDING = "pending"
SENDING = "sending"
WAITING = "waiting"
STEP_DONE = "done"
STEP_FAILED = "failed"

_NAP = 0.2  # longest single sleep, so stop/pause react quickly


@dataclass
class PlanEvent:
    """Progress notification passed to the ``on_event`` callback."""

    index: int  # 0-based step index, -1 for plan-level events
    total: int
    command: str
    state: str
    detail: str = ""

    def line(self) -> str:
        where = f"[{self.index + 1}/{self.total}] {self.command}" if self.index >= 0 else "plan"
        return f"{where}: {self.state}" + (f" — {self.detail}" if self.detail else "")


class PlanRunner:
    """Executes plan steps against *controller* and verifies each with telemetry.

    Parameters
    ----------
    poll:
        Seconds between telemetry checks while a command is in progress.
    step_timeout:
        Seconds, counted from when the command was sent, before the step fails.
    execute:
        ``command -> (exit_requested, message)``; defaults to
        :func:`~dyodrone.core.commands.handle_command` on *controller*.
    clock, sleep:
        Injectable for tests.
    """

    def __init__(
        self,
        controller: DroneController,
        steps: List[Step],
        *,
        poll: float = 3.0,
        step_timeout: float = 120.0,
        tolerances: Optional[Tolerances] = None,
        on_event: Optional[Callable[[PlanEvent], None]] = None,
        execute: Optional[Callable[[str], Tuple[bool, str]]] = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._controller = controller
        self._steps = list(steps)
        self._poll = poll
        self._step_timeout = step_timeout
        self._tol = tolerances or Tolerances()
        self._on_event = on_event
        self._execute = execute or (lambda command: handle_command(command, controller))
        self._clock = clock
        self._sleep = sleep

        self._lock = threading.RLock()
        self._state = IDLE
        self._paused = False
        self._stop = threading.Event()
        self._index = -1
        self._step_states: List[Dict[str, Any]] = [
            {"line": s.line, "command": s.command, "state": PENDING, "detail": ""} for s in self._steps
        ]
        self._message = ""

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------

    def pause(self) -> None:
        """Hold before the next step (a command already in progress finishes first)."""
        with self._lock:
            if self._state == RUNNING:
                self._paused = True
                self._state = PAUSED

    def resume(self) -> None:
        with self._lock:
            if self._state == PAUSED:
                self._paused = False
                self._state = RUNNING

    def stop(self) -> None:
        """Stop after the current poll. The vehicle keeps doing whatever it is doing."""
        self._stop.set()

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def snapshot(self) -> Dict[str, Any]:
        """State for the UI: overall state, current step, per-step status and a message."""
        with self._lock:
            return {
                "state": self._state,
                "index": self._index,
                "total": len(self._steps),
                "message": self._message,
                "steps": [dict(s) for s in self._step_states],
            }

    # ------------------------------------------------------------------
    # Running
    # ------------------------------------------------------------------

    def run(self) -> bool:
        """Run every step. Returns ``True`` if the whole plan completed."""
        with self._lock:
            if self._state not in (IDLE,):
                raise RuntimeError("A plan runner can only be run once")
            self._state = RUNNING
        self._emit(-1, "", RUNNING, f"{len(self._steps)} steps")

        for index, step in enumerate(self._steps):
            self._hold_while_paused()
            if self._stop.is_set():
                return self._finish(STOPPED, "stopped")
            with self._lock:
                self._index = index
            if not self._run_step(index, step):
                return self._finish(STOPPED if self._stop.is_set() else FAILED, self._message)

        return self._finish(DONE, "plan complete")

    def _finish(self, state: str, message: str) -> bool:
        with self._lock:
            self._state = state
            self._message = message
        self._emit(-1, "", state, message)
        return state == DONE

    def _hold_while_paused(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                if not self._paused:
                    return
            self._sleep(_NAP)

    def _run_step(self, index: int, step: Step) -> bool:
        if step.verb == "wait":
            return self._run_wait(index, step)

        self._set_step(index, SENDING, "")
        before = self._snapshot_before(index, step)
        if before is None:
            return False
        try:
            expectation = expected_after(step, before, self._tol)
        except MissingTelemetry as exc:  # pragma: no cover - guarded by _snapshot_before
            return self._fail(index, f"no {exc} telemetry")

        exit_requested, message = self._execute(step.command)
        if is_error_message(message):
            return self._fail(index, message)

        self._set_step(index, WAITING, expectation.description)
        started = self._clock()
        while True:
            if not self._nap(self._poll):
                self._set_step(index, PENDING, "stopped")
                return False
            try:
                result = expectation.check(self._controller.telemetry())
            except Exception as exc:  # noqa: BLE001 - a telemetry hiccup should not end the plan
                result = None
                detail = f"telemetry unavailable: {exc}"
            else:
                detail = result.detail
            if result is not None and result.done:
                self._set_step(index, STEP_DONE, detail)
                return True
            self._set_step(index, WAITING, detail)
            if self._clock() - started >= self._step_timeout:
                return self._fail(index, f"timed out after {self._step_timeout:g} s — {detail}")

    def _run_wait(self, index: int, step: Step) -> bool:
        self._set_step(index, WAITING, f"{step.value:g} s")
        if not self._nap(float(step.value)):
            self._set_step(index, PENDING, "stopped")
            return False
        self._set_step(index, STEP_DONE, f"waited {step.value:g} s")
        return True

    def _snapshot_before(self, index: int, step: Step) -> Optional[Telemetry]:
        """Telemetry needed to compute the expectation; waits for it if not yet received."""
        started = self._clock()
        last = ""
        while True:
            try:
                before = self._controller.telemetry()
                expected_after(step, before, self._tol)
                return before
            except MissingTelemetry as exc:
                last = f"waiting for {exc} telemetry"
            except Exception as exc:  # noqa: BLE001
                last = f"telemetry unavailable: {exc}"
            if self._clock() - started >= self._step_timeout:
                self._fail(index, last)
                return None
            self._set_step(index, SENDING, last)
            if not self._nap(self._poll):
                self._set_step(index, PENDING, "stopped")
                return None

    def _nap(self, seconds: float) -> bool:
        """Sleep *seconds* in short slices; returns ``False`` if stopped meanwhile."""
        end = self._clock() + seconds
        while True:
            if self._stop.is_set():
                return False
            remaining = end - self._clock()
            if remaining <= 0:
                return True
            self._sleep(min(_NAP, remaining))

    # ------------------------------------------------------------------
    # Bookkeeping
    # ------------------------------------------------------------------

    def _set_step(self, index: int, state: str, detail: str) -> None:
        with self._lock:
            self._step_states[index].update(state=state, detail=detail)
        self._emit(index, self._steps[index].command, state, detail)

    def _fail(self, index: int, message: str) -> bool:
        with self._lock:
            self._message = f"step {index + 1} ({self._steps[index].command}) failed: {message}"
        self._set_step(index, STEP_FAILED, message)
        return False

    def _emit(self, index: int, command: str, state: str, detail: str) -> None:
        if self._on_event is not None:
            self._on_event(PlanEvent(index, len(self._steps), command, state, detail))
