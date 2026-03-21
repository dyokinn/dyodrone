"""DroneKit backend that runs a built-in SITL simulator."""

from __future__ import annotations

import logging
from typing import Optional

import dronekit_sitl
from dronekit import connect

from dronekit_version.dronekit_controller import _DroneKitBase
from dronekit_version.gcs_proxy import GCSProxy

LOG = logging.getLogger(__name__)


class DronekitSITLController(_DroneKitBase):
    """Spins up a local SITL simulator and connects to it via DroneKit.

    Parameters
    ----------
    wait_ready:
        Block until the vehicle reports ready (default ``True``).
    gcs_port:
        When provided, a :class:`~dronekit_version.gcs_proxy.GCSProxy` is
        started that forwards all MAVLink telemetry from SITL to QGroundControl
        (or any GCS) via UDP broadcast on this port.  The standard QGC port is
        ``14550``.  Pass ``None`` (the default) to disable the proxy.
    """

    def __init__(
        self,
        *,
        wait_ready: bool = True,
        gcs_port: Optional[int] = None,
        gcs_host: str = "127.0.0.1",
    ) -> None:
        super().__init__(connection=None, wait_ready=wait_ready)
        self._sitl = None
        self._proxy: Optional[GCSProxy] = (
            GCSProxy(gcs_port, gcs_host) if gcs_port is not None else None
        )

    def connect(self) -> None:
        if self._vehicle:
            return

        LOG.info("Starting SITL simulator...")
        self._sitl = dronekit_sitl.start_default()
        conn_str = self._sitl.connection_string()
        self._active_connection = conn_str
        self._vehicle = connect(conn_str, wait_ready=self.wait_ready)

        if self._proxy is not None:
            self._proxy.start(self._vehicle)

    def connection_details(self) -> list:
        lines = super().connection_details()
        if self._proxy is not None:
            lines.append(
                f"GCS Proxy: → {self._proxy.gcs_host}:{self._proxy.gcs_port}  (QGC ready)"
            )
        return lines

    def close(self) -> None:
        if self._proxy is not None:
            self._proxy.stop()
        super().close()  # closes vehicle
        if self._sitl:
            LOG.info("Stopping SITL simulator.")
            self._sitl.stop()
            self._sitl = None
