"""DroneKit backend for a real Pixhawk board over a connection string."""

from __future__ import annotations

import logging

from dronekit import connect

from dronekit_version.dronekit_controller import _DroneKitBase

LOG = logging.getLogger(__name__)


class DronekitPixhawkController(_DroneKitBase):
    """Connects to a physical Pixhawk via a MAVLink connection string.

    Examples of valid connection strings:
        - ``/dev/ttyUSB0``         (USB serial)
        - ``tcp:192.168.1.1:5760`` (TCP)
        - ``udp:127.0.0.1:14550``  (UDP)
    """

    def __init__(self, *, connection: str, wait_ready: bool = True) -> None:
        if not connection:
            raise ValueError("A connection string is required for the Pixhawk backend.")
        super().__init__(connection=connection, wait_ready=wait_ready)

    def connect(self) -> None:
        if self._vehicle:
            return
        LOG.info("Connecting to Pixhawk on %s", self.connection)
        self._active_connection = self.connection
        self._vehicle = connect(self.connection, wait_ready=self.wait_ready)

    # close() is inherited from _DroneKitBase — no extra resources to release
