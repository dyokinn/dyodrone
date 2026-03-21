"""UDP proxy that forwards SITL MAVLink telemetry to QGroundControl.

No MAVProxy dependency — uses DroneKit's message listener and stdlib sockets.

How it works
------------
Rather than opening a second TCP connection to SITL (ArduCopter 3.3 only
streams to the primary client), the proxy registers a ``'*'`` wildcard
listener on the DroneKit vehicle object.  Every raw MAVLink frame that DroneKit
receives from SITL is intercepted and forwarded as a UDP datagram to QGC.

Data flow::

    SITL ──TCP──► DroneKit ──on_message('*')──► GCSProxy ──UDP──► QGC

``start(vehicle)`` must be called after ``connect()`` returns a live vehicle.
``stop()`` removes the listener and closes the UDP socket.
"""

from __future__ import annotations

import logging
import socket
from typing import Any, Callable, Optional

LOG = logging.getLogger(__name__)


class GCSProxy:
    """Forwards every MAVLink message to QGroundControl over UDP.

    Parameters
    ----------
    gcs_port:
        UDP port QGroundControl listens on (default 14550).
    gcs_host:
        IP of the machine running QGroundControl.
        ``"127.0.0.1"`` (default) — same machine as the CLI.
        A LAN IP or ``"255.255.255.255"`` — remote machine / broadcast.
    """

    def __init__(self, gcs_port: int = 14550, gcs_host: str = "127.0.0.1") -> None:
        self._gcs_port = gcs_port
        self._gcs_host = gcs_host
        self._vehicle: Optional[Any] = None
        self._listener: Optional[Callable] = None

        self._gcs_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if gcs_host in ("255.255.255.255", "<broadcast>"):
            self._gcs_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def gcs_port(self) -> int:
        return self._gcs_port

    @property
    def gcs_host(self) -> str:
        return self._gcs_host

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, vehicle: Any) -> None:
        """Register a message listener on *vehicle* and start forwarding.

        Parameters
        ----------
        vehicle:
            A live DroneKit ``Vehicle`` object returned by ``dronekit.connect()``.
        """
        self._vehicle = vehicle

        def _forward(_vehicle: Any, _name: str, message: Any) -> None:
            buf = message.get_msgbuf()
            if not buf:
                return
            try:
                self._gcs_sock.sendto(bytes(buf), (self._gcs_host, self._gcs_port))
            except OSError:
                pass

        self._listener = _forward
        vehicle.add_message_listener("*", _forward)
        LOG.info("GCS proxy active: → %s:%d", self._gcs_host, self._gcs_port)

    def stop(self) -> None:
        """Remove the listener and close the UDP socket."""
        if self._vehicle is not None and self._listener is not None:
            try:
                self._vehicle.remove_message_listener("*", self._listener)
            except Exception:
                pass
        try:
            self._gcs_sock.close()
        except OSError:
            pass
