"""Abstract base class defining the public interface for all drone backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional


class DroneController(ABC):
    """Backend-agnostic contract for connecting to and commanding a drone.

    The CLI depends only on this interface — no backend-specific details
    (DroneKit, SITL, MAVLink, etc.) are exposed here.
    """

    def __enter__(self) -> DroneController:
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @property
    @abstractmethod
    def active_connection(self) -> Optional[str]:
        """The active connection string, or None if not connected."""
        ...

    @abstractmethod
    def connect(self) -> None:
        """Establish the connection to the vehicle."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Close the connection and release all resources."""
        ...

    @abstractmethod
    def status_lines(self) -> List[str]:
        """Return a list of human-readable telemetry lines for display."""
        ...

    @abstractmethod
    def arm_and_takeoff(self, target_altitude: float) -> None:
        """Arm the vehicle and take off to target_altitude meters AGL."""
        ...

    @abstractmethod
    def land(self) -> None:
        """Initiate landing."""
        ...

    @abstractmethod
    def set_altitude(self, target_altitude: float) -> None:
        """Command the drone to a new altitude while airborne (fire-and-forget)."""
        ...

    @abstractmethod
    def move_forward(self, distance_m: float) -> None:
        """Move in the direction the drone is currently facing."""
        ...

    @abstractmethod
    def move_back(self, distance_m: float) -> None:
        """Move opposite to the direction the drone is currently facing."""
        ...

    @abstractmethod
    def rotate_left(self, degrees: float) -> None:
        """Yaw left (counter-clockwise) by the given degrees."""
        ...

    @abstractmethod
    def rotate_right(self, degrees: float) -> None:
        """Yaw right (clockwise) by the given degrees."""
        ...

    def connection_details(self) -> List[str]:
        """Return human-readable lines describing the active connection(s).

        The default implementation shows the vehicle connection string.
        Backends that manage additional channels (e.g. a GCS proxy) should
        override this and append their own lines.
        """
        conn = self.active_connection
        if conn:
            return [f"Connection: {conn}"]
        return ["Connection: not connected"]
