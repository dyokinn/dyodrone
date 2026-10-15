"""Structured vehicle telemetry, read from the MAVLink data a driver already caches."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Telemetry:
    """A snapshot of the vehicle state. A field is ``None`` until it has been received.

    Attributes
    ----------
    lat, lon:
        Position in degrees (``GLOBAL_POSITION_INT``).
    rel_alt_m:
        Altitude above the take-off point in metres.
    yaw_deg:
        Heading in degrees, ``0 <= yaw < 360``, 0 = North, clockwise positive.
    armed:
        Whether the motors are armed (``HEARTBEAT``).
    mode:
        Flight mode name, e.g. ``"GUIDED"``.
    timestamp:
        When the snapshot was taken (``time.time()``).
    """

    lat: Optional[float] = None
    lon: Optional[float] = None
    rel_alt_m: Optional[float] = None
    yaw_deg: Optional[float] = None
    armed: Optional[bool] = None
    mode: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    @property
    def has_position(self) -> bool:
        return self.lat is not None and self.lon is not None

    def summary(self) -> str:
        """One line for logs, e.g. ``alt 9.8 m, yaw 90°, armed``."""
        parts = []
        if self.rel_alt_m is not None:
            parts.append(f"alt {self.rel_alt_m:.1f} m")
        if self.yaw_deg is not None:
            parts.append(f"yaw {self.yaw_deg:.0f}°")
        if self.armed is not None:
            parts.append("armed" if self.armed else "disarmed")
        return ", ".join(parts) if parts else "no telemetry"
