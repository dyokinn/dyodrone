"""Pymavlink backend that runs a built-in SITL simulator.

Launches the same ArduCopter 3.3 SITL subprocess the DroneKit SITL backend
uses (via ``dronekit_sitl``), but drives it with raw pymavlink/mavutil
instead of DroneKit's ``Vehicle`` wrapper. ``dronekit_sitl``'s own runtime
code never imports ``dronekit`` — only its unused ``forwarder.py`` submodule
does — so this works fine on a current Python interpreter even though
``dronekit`` itself is broken on Python 3.10+. See docs/guide/how.rst.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from dyodrone.core.proxy import GCSProxy
from dyodrone.drivers.dyopilot_driver import _PyMAVLinkBase

LOG = logging.getLogger(__name__)


class DyopilotSITLController(_PyMAVLinkBase):
    """Spins up a local SITL simulator and connects to it via pymavlink.

    Parameters
    ----------
    gcs_port:
        When provided, a :class:`~dyodrone.core.proxy.GCSProxy` is
        started that forwards all MAVLink telemetry from SITL to QGroundControl
        (or any GCS) via UDP broadcast on this port.  The standard QGC port is
        ``14550``.  Pass ``None`` (the default) to disable the proxy.
    """

    def __init__(
        self,
        *,
        gcs_port: Optional[int] = None,
        gcs_host: str = "127.0.0.1",
        heartbeat_timeout: float = 30.0,
    ) -> None:
        super().__init__(heartbeat_timeout=heartbeat_timeout)
        self._sitl = None
        self._proxy: Optional[GCSProxy] = (
            GCSProxy(gcs_port, gcs_host) if gcs_port is not None else None
        )

    def connection_details(self) -> List[str]:
        lines = super().connection_details()
        if self._proxy is not None:
            lines.append(
                f"GCS Proxy: → {self._proxy.gcs_host}:{self._proxy.gcs_port}  (QGC ready)"
            )
        return lines

    def connect(self) -> None:
        if self._master:
            return

        import dronekit_sitl

        LOG.info("Starting SITL simulator...")
        self._sitl = dronekit_sitl.start_default()
        conn_str = self._sitl.connection_string()

        self._open_master(conn_str, proxy=self._proxy)

        if self._proxy is not None:
            LOG.info("GCS proxy active: → %s:%d", self._proxy.gcs_host, self._proxy.gcs_port)

    def close(self) -> None:
        if self._proxy is not None:
            self._proxy.stop()
        super().close()  # stops reader, closes master
        if self._sitl is not None:
            LOG.info("Stopping SITL simulator.")
            self._sitl.stop()
            self._sitl = None
