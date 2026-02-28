"""Business logic for connecting to and commanding a drone."""

from __future__ import annotations

import logging
import math
import time
from typing import Callable, List, Optional

import dronekit_sitl
from dronekit import LocationGlobalRelative, Vehicle, VehicleMode, connect

LOG = logging.getLogger(__name__)


class DroneController:
    """Encapsulates vehicle connection management and high-level commands."""

    def __init__(
        self,
        *,
        connection: Optional[str] = None,
        use_simulator: bool = True,
        wait_ready: bool = True,
    ) -> None:
        self.connection = connection
        self.use_simulator = use_simulator
        self.wait_ready = wait_ready
        self._vehicle: Optional[Vehicle] = None
        self._sitl = None
        self._active_connection: Optional[str] = None

    def __enter__(self) -> DroneController:
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @property
    def vehicle(self) -> Vehicle:
        if not self._vehicle:
            raise RuntimeError("Vehicle connection has not been established.")
        return self._vehicle

    @property
    def active_connection(self) -> Optional[str]:
        return self._active_connection

    def connect(self) -> Vehicle:
        if self._vehicle:
            return self._vehicle

        connection_string = self.connection
        if self.use_simulator:
            LOG.info("Starting simulator (SITL)...")
            self._sitl = dronekit_sitl.start_default()
            connection_string = self._sitl.connection_string()
        elif not connection_string:
            raise ValueError(
                "A connection string is required when not using the simulator."
            )

        print("Connecting to vehicle on: %s", connection_string)
        self._active_connection = connection_string
        self._vehicle = connect(connection_string, wait_ready=self.wait_ready)
        return self._vehicle

    def close(self) -> None:
        if self._vehicle:
            LOG.info("Closing vehicle connection.")
            self._vehicle.close()
            self._vehicle = None
        self._active_connection = None
        if self._sitl:
            LOG.info("Stopping SITL.")
            self._sitl.stop()
            self._sitl = None

    def status_lines(self) -> List[str]:
        vehicle = self.vehicle
        battery = vehicle.battery
        attitude = vehicle.attitude
        mode_name = vehicle.mode.name if vehicle.mode else "unknown"
        system_state = getattr(vehicle.system_status, "state", "unknown")
        lines = [
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
        return lines

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

        def reached_target() -> bool:
            altitude = getattr(vehicle.location.global_relative_frame, "alt", None)
            return altitude is not None and altitude >= target_altitude * 0.95

    def land(self) -> None:
        vehicle = self.vehicle
        vehicle.mode = VehicleMode("LAND")
        self._wait_for_mode("LAND", timeout=30.0)

    def set_altitude(self, target_altitude: float) -> None:
        """Command the drone to a new altitude while airborne."""
        if target_altitude <= 0:
            raise ValueError("Altitude must be greater than 0 meters")

        vehicle = self.vehicle
        if not vehicle.armed:
            raise RuntimeError("Vehicle must be armed and airborne to change altitude")

        if vehicle.mode.name.upper() != "GUIDED":  # pyright: ignore[reportOptionalMemberAccess]
            vehicle.mode = VehicleMode("GUIDED")
            self._wait_for_mode("GUIDED", timeout=30.0)

        current = vehicle.location.global_relative_frame
        target = LocationGlobalRelative(current.lat, current.lon, target_altitude)
        vehicle.simple_goto(target)

    def move_north(self, distance_m: float) -> None:
        """Move the drone north by distance_m meters, keeping current altitude."""
        if distance_m <= 0:
            raise ValueError("Distance must be greater than 0 meters")
        self._move(distance_m / 111_320, 0.0)

    def move_south(self, distance_m: float) -> None:
        """Move the drone south by distance_m meters, keeping current altitude."""
        if distance_m <= 0:
            raise ValueError("Distance must be greater than 0 meters")
        self._move(-distance_m / 111_320, 0.0)

    def move_east(self, distance_m: float) -> None:
        """Move the drone east by distance_m meters, keeping current altitude."""
        if distance_m <= 0:
            raise ValueError("Distance must be greater than 0 meters")
        lat_rad = math.radians(self.vehicle.location.global_relative_frame.lat)  # pyright: ignore[reportArgumentType]
        self._move(0.0, distance_m / (111_320 * math.cos(lat_rad)))

    def move_west(self, distance_m: float) -> None:
        """Move the drone west by distance_m meters, keeping current altitude."""
        if distance_m <= 0:
            raise ValueError("Distance must be greater than 0 meters")
        lat_rad = math.radians(self.vehicle.location.global_relative_frame.lat)  # pyright: ignore[reportArgumentType]
        self._move(0.0, -distance_m / (111_320 * math.cos(lat_rad)))

    def _move(self, d_lat: float, d_lon: float) -> None:
        vehicle = self.vehicle
        if not vehicle.armed:
            raise RuntimeError("Vehicle must be armed and airborne to move")

        if vehicle.mode.name.upper() != "GUIDED":  # pyright: ignore[reportOptionalMemberAccess]
            vehicle.mode = VehicleMode("GUIDED")
            self._wait_for_mode("GUIDED", timeout=30.0)

        current = vehicle.location.global_relative_frame
        target = LocationGlobalRelative(
            current.lat + d_lat,  # pyright: ignore[reportOperatorIssue]
            current.lon + d_lon,  # pyright: ignore[reportOperatorIssue]
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


def main() -> int:
    """Utility entry point to launch the simulator and keep it running."""
    controller = DroneController()
    print("Starting simulator (SITL)... press Ctrl+C to stop.")
    try:
        controller.connect()
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nStopping controller.")
    finally:
        controller.close()
    return 0


if __name__ == "__main__":  # pragma: no cover - utility entry point
    raise SystemExit(main())
