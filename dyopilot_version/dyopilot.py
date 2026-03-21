"""PyMAVLink / MAVProxy backend — stub, not yet implemented."""

from __future__ import annotations

from typing import List, Optional

from drone_controller import DroneController


class PyMAVLinkController(DroneController):
    """Future backend built on pymavlink and MAVProxy.

    All methods raise ``NotImplementedError`` until the implementation is
    written. The class is intentionally concrete so it can be instantiated
    and passed to the CLI — errors fire only when a method is called.
    """

    _MSG = "PyMAVLink backend is not yet implemented."

    @property
    def active_connection(self) -> Optional[str]:
        raise NotImplementedError(self._MSG)

    def connect(self) -> None:
        raise NotImplementedError(self._MSG)

    def close(self) -> None:
        raise NotImplementedError(self._MSG)

    def status_lines(self) -> List[str]:
        raise NotImplementedError(self._MSG)

    def arm_and_takeoff(self, target_altitude: float) -> None:
        raise NotImplementedError(self._MSG)

    def land(self) -> None:
        raise NotImplementedError(self._MSG)

    def set_altitude(self, target_altitude: float) -> None:
        raise NotImplementedError(self._MSG)

    def move_forward(self, distance_m: float) -> None:
        raise NotImplementedError(self._MSG)

    def move_back(self, distance_m: float) -> None:
        raise NotImplementedError(self._MSG)

    def rotate_left(self, degrees: float) -> None:
        raise NotImplementedError(self._MSG)

    def rotate_right(self, degrees: float) -> None:
        raise NotImplementedError(self._MSG)
