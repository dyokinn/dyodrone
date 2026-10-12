"""Pymavlink backend for a real Pixhawk board over a connection string."""

from __future__ import annotations

import logging

from dyopilot_version.dyopilot_controller import _PyMAVLinkBase

LOG = logging.getLogger(__name__)


class DyopilotPixhawkController(_PyMAVLinkBase):
    """Connects to a physical Pixhawk via a MAVLink connection string.

    Examples of valid connection strings:
        - ``/dev/ttyUSB0``         (USB serial)
        - ``tcp:192.168.1.1:5760`` (TCP)
        - ``udp:127.0.0.1:14550``  (UDP)
    """

    def __init__(self, *, connection: str, heartbeat_timeout: float = 30.0) -> None:
        if not connection:
            raise ValueError("A connection string is required for the Pixhawk backend.")
        super().__init__(heartbeat_timeout=heartbeat_timeout)
        self.connection = connection

    def connect(self) -> None:
        if self._master:
            return
        LOG.info("Connecting to Pixhawk on %s", self.connection)
        self._open_master(self.connection)

    # close() is inherited from _PyMAVLinkBase — no extra resources to release
