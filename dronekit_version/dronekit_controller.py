"""Internal DroneKit base — shared flight logic for SITL and Pixhawk backends.

Not meant to be instantiated directly. Use DronekitSITLController or
DronekitPixhawkController instead.
"""

from __future__ import annotations

import logging
import math
import time
from typing import Callable, List, Optional

from dronekit import LocationGlobalRelative, Vehicle, VehicleMode, connect  # noqa: F401
from pymavlink import mavutil

from drone_controller import DroneController

LOG = logging.getLogger(__name__)


class _DroneKitBase(DroneController):
    """Implements all DroneKit flight operations.

    Subclasses only need to override ``connect()`` (and ``close()`` for
    backends that own additional resources such as a SITL process).
    """

    def __init__(
        self,
        *,
        connection: Optional[str] = None,
        wait_ready: bool = True,
    ) -> None:
        self.connection = connection
        self.wait_ready = wait_ready
        self._vehicle: Optional[Vehicle] = None
        self._active_connection: Optional[str] = None

    @property
    def vehicle(self) -> Vehicle:
        if not self._vehicle:
            raise RuntimeError("Vehicle connection has not been established.")
        return self._vehicle

    @property
    def active_connection(self) -> Optional[str]:
        return self._active_connection

    def close(self) -> None:
        if self._vehicle:
            LOG.info("Closing vehicle connection.")
            self._vehicle.close()
            self._vehicle = None
        self._active_connection = None

    def status_lines(self) -> List[str]:
        vehicle = self.vehicle
        battery = vehicle.battery
        attitude = vehicle.attitude
        mode_name = vehicle.mode.name if vehicle.mode else "unknown"
        system_state = getattr(vehicle.system_status, "state", "unknown")
        return [
            "=== Vehicle snapshot ===",
            f"Mode: {mode_name}",
            f"System status: {system_state}",
            f"Armable: {vehicle.is_armable}",
            f"Armed: {vehicle.armed}",
            f"Altitude: {vehicle.location.global_relative_frame.alt}",
            f"Location: {self._format_location(vehicle)} ({self._format_relative_altitude(vehicle)})",
            "Attitude: roll={:.2f}, pitch={:.2f}, yaw={:.2f}".format(
                getattr(attitude, "roll", 0.0),
                getattr(attitude, "pitch", 0.0),
                getattr(attitude, "yaw", 0.0),
            ),
            f"Velocity: {self._format_velocity(vehicle)}",
            "Battery: voltage={:.1f}V, current={:.1f}A, level={}".format(
                getattr(battery, "voltage", 0.0) or 0.0,
                getattr(battery, "current", 0.0) or 0.0,
                getattr(battery, "level", "unknown"),
            ),
        ]

    def arm_and_takeoff(self, target_altitude: float) -> None:
        if target_altitude <= 0:
            raise ValueError("Altitude must be greater than 0 meters")

        vehicle = self.vehicle
        self._wait_for_condition(lambda: vehicle.is_armable, timeout=60)
        vehicle.mode = VehicleMode("GUIDED")
        self._wait_for_mode("GUIDED", timeout=45.0)
        self._ensure_armed(timeout=45.0)
        time.sleep(1.0)
        vehicle.simple_takeoff(target_altitude)

    def land(self) -> None:
        vehicle = self.vehicle
        vehicle.mode = VehicleMode("LAND")
        self._wait_for_mode("LAND", timeout=30.0)

    def set_altitude(self, target_altitude: float) -> None:
        if target_altitude <= 0:
            raise ValueError("Altitude must be greater than 0 meters")

        vehicle = self.vehicle
        if not vehicle.armed:
            raise RuntimeError("Vehicle must be armed and airborne to change altitude")

        if vehicle.mode.name.upper() != "GUIDED":
            vehicle.mode = VehicleMode("GUIDED")
            self._wait_for_mode("GUIDED", timeout=30.0)

        current = vehicle.location.global_relative_frame
        target = LocationGlobalRelative(current.lat, current.lon, target_altitude)
        vehicle.simple_goto(target)

    def move_forward(self, distance_m: float) -> None:
        if distance_m <= 0:
            raise ValueError("Distance must be greater than 0 meters")
        yaw = self.vehicle.attitude.yaw  # radians; 0 = North, CW positive
        lat_rad = math.radians(self.vehicle.location.global_relative_frame.lat)
        d_lat = distance_m * math.cos(yaw) / 111_320
        d_lon = distance_m * math.sin(yaw) / (111_320 * math.cos(lat_rad))
        self._move(d_lat, d_lon)

    def move_back(self, distance_m: float) -> None:
        if distance_m <= 0:
            raise ValueError("Distance must be greater than 0 meters")
        yaw = self.vehicle.attitude.yaw
        lat_rad = math.radians(self.vehicle.location.global_relative_frame.lat)
        d_lat = -distance_m * math.cos(yaw) / 111_320
        d_lon = -distance_m * math.sin(yaw) / (111_320 * math.cos(lat_rad))
        self._move(d_lat, d_lon)

    def rotate_left(self, degrees: float) -> None:
        if degrees <= 0:
            raise ValueError("Degrees must be greater than 0")
        self._rotate(degrees, clockwise=False)

    def rotate_right(self, degrees: float) -> None:
        if degrees <= 0:
            raise ValueError("Degrees must be greater than 0")
        self._rotate(degrees, clockwise=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rotate(self, degrees: float, clockwise: bool) -> None:
        vehicle = self.vehicle
        if not vehicle.armed:
            raise RuntimeError("Vehicle must be armed and airborne to rotate")

        if vehicle.mode.name.upper() != "GUIDED":
            vehicle.mode = VehicleMode("GUIDED")
            self._wait_for_mode("GUIDED", timeout=30.0)

        direction = 1 if clockwise else -1
        msg = vehicle.message_factory.command_long_encode(
            0, 0,                                    # target system, component
            mavutil.mavlink.MAV_CMD_CONDITION_YAW,
            0,                                       # confirmation
            degrees,                                 # param1: angle in degrees
            0,                                       # param2: angular speed (0 = default)
            direction,                               # param3: 1 CW, -1 CCW
            1,                                       # param4: 1 = relative offset
            0, 0, 0,
        )
        vehicle.send_mavlink(msg)

    def _move(self, d_lat: float, d_lon: float) -> None:
        vehicle = self.vehicle
        if not vehicle.armed:
            raise RuntimeError("Vehicle must be armed and airborne to move")

        if vehicle.mode.name.upper() != "GUIDED":
            vehicle.mode = VehicleMode("GUIDED")
            self._wait_for_mode("GUIDED", timeout=30.0)

        current = vehicle.location.global_relative_frame
        target = LocationGlobalRelative(
            current.lat + d_lat,
            current.lon + d_lon,
            current.alt,
        )
        vehicle.simple_goto(target)

    def _wait_for_condition(
        self,
        predicate: Callable[[], bool],
        timeout: float,
        poll_interval: float = 1.0,
    ) -> None:
        start = time.time()
        while not predicate():
            if time.time() - start > timeout:
                raise TimeoutError("Timed out waiting for condition")
            time.sleep(poll_interval)

    def _wait_for_mode(self, target_mode: str, timeout: float = 30.0) -> None:
        vehicle = self.vehicle
        normalized = target_mode.upper()
        desired_mode = VehicleMode(normalized)
        start = time.time()
        last_set = 0.0

        while True:
            now = time.time()
            if now - last_set >= 1.0:
                vehicle.mode = desired_mode
                last_set = now

            mode_name = vehicle.mode.name.upper() if vehicle.mode else ""
            if mode_name == normalized:
                return

            if now - start > timeout:
                raise TimeoutError(f"Failed to enter {normalized} mode")

            time.sleep(0.5)

    def _ensure_armed(self, timeout: float = 30.0) -> None:
        vehicle = self.vehicle
        start = time.time()
        while True:
            if not vehicle.armed:
                vehicle.armed = True
            if vehicle.armed:
                return
            if time.time() - start > timeout:
                raise TimeoutError("Failed to arm vehicle")
            time.sleep(0.5)

    @staticmethod
    def _format_location(vehicle: Vehicle) -> str:
        location = vehicle.location.global_frame
        lat = getattr(location, "lat", None)
        lon = getattr(location, "lon", None)
        alt = getattr(location, "alt", None)
        if any(value is None for value in (lat, lon, alt)):
            return "unknown"
        return f"lat={lat:.6f}, lon={lon:.6f}, alt={alt:.1f}m"

    @staticmethod
    def _format_relative_altitude(vehicle: Vehicle) -> str:
        rel_location = vehicle.location.global_relative_frame
        alt = getattr(rel_location, "alt", None)
        return f"agl={alt:.1f}m" if alt is not None else "agl=unknown"

    @staticmethod
    def _format_velocity(vehicle: Vehicle) -> str:
        velocity = vehicle.velocity or (None, None, None)
        vy, vx, vz = velocity
        if any(value is None for value in (vx, vy, vz)):
            return "unknown"
        return f"vx={vx:.2f}m/s, vy={vy:.2f}m/s, vz={vz:.2f}m/s"
