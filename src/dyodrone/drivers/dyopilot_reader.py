"""Background thread that keeps a mavutil connection's message cache fresh.

pymavlink has no built-in listener dispatch the way DroneKit does — nothing
populates ``master.messages``/``master.flightmode`` unless something calls
``recv_msg()`` repeatedly. This thread does that, and optionally forwards
every raw frame to a sink (e.g. a GCS proxy).
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

from pymavlink import mavutil


class MAVLinkReader:
    """Drains a mavutil connection on a daemon thread.

    Parameters
    ----------
    master:
        A live ``mavutil.mavlink_connection`` to read from.
    on_frame:
        Called with the raw bytes of every parsed, non-corrupt message.
        Used to forward telemetry to a GCS proxy; pass ``None`` to disable.
    """

    def __init__(
        self,
        master: "mavutil.mavfile",
        on_frame: Optional[Callable[[bytes], None]] = None,
    ) -> None:
        self._master = master
        self._on_frame = on_frame
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="mavlink-reader", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                msg = self._master.recv_msg()
            except Exception:
                break
            if msg is None:
                self._stop_event.wait(0.01)
                continue
            if self._on_frame is not None and msg.get_type() != "BAD_DATA":
                self._on_frame(msg.get_msgbuf())
