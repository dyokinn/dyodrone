"""Internal pymavlink base — shared flight logic for SITL and Pixhawk backends.

Not meant to be instantiated directly. Use DyopilotSITLController or
DyopilotPixhawkController instead. Mirrors dronekit_version/dronekit_controller.py's
_DroneKitBase, but built on raw pymavlink/mavutil instead of DroneKit's Vehicle
wrapper — no DroneKit dependency anywhere in this file, which is what lets it
run on a current Python interpreter instead of the 3.7 DroneKit is pinned to.
"""

from __future__ import annotations

import logging
import math
import time
from typing import List, Optional

from pymavlink import mavutil

from drone_controller import DroneController
from dronekit_version.gcs_proxy import GCSProxy
from dyopilot_version.pymavlink_reader import MAVLinkReader

LOG = logging.getLogger(__name__)

_POSITION_ONLY_TYPEMASK = (
    mavutil.mavlink.POSITION_TARGET_TYPEMASK_VX_IGNORE
    | mavutil.mavlink.POSITION_TARGET_TYPEMASK_VY_IGNORE
    | mavutil.mavlink.POSITION_TARGET_TYPEMASK_VZ_IGNORE
    | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AX_IGNORE
    | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AY_IGNORE
    | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AZ_IGNORE
    | mavutil.mavlink.POSITION_TARGET_TYPEMASK_YAW_IGNORE
    | mavutil.mavlink.POSITION_TARGET_TYPEMASK_YAW_RATE_IGNORE
)


class _PyMAVLinkBase(DroneController):
    """Implements all pymavlink flight operations.

    Subclasses only need to override ``connect()`` (and ``close()`` for
    backends that own additional resources such as a SITL process).
    """

    def __init__(self, *, heartbeat_timeout: float = 30.0) -> None:
        self._heartbeat_timeout = heartbeat_timeout
        self._master: Optional["mavutil.mavfile"] = None
        self._reader: Optional[MAVLinkReader] = None
        self._active_connection: Optional[str] = None

    @property
    def master(self) -> "mavutil.mavfile":
        if not self._master:
            raise RuntimeError("Vehicle connection has not been established.")
        return self._master

    @property
    def active_connection(self) -> Optional[str]:
        return self._active_connection

    def close(self) -> None:
        if self._reader is not None:
            self._reader.stop()
            self._reader = None
        if self._master is not None:
            LOG.info("Closing vehicle connection.")
            self._master.close()
            self._master = None
        self._active_connection = None

    def status_lines(self) -> List[str]:
        master = self.master
        hb = master.messages.get("HEARTBEAT")
        sys_status = master.messages.get("SYS_STATUS")
        gps = master.messages.get("GPS_RAW_INT")
        pos = master.messages.get("GLOBAL_POSITION_INT")
        att = master.messages.get("ATTITUDE")

        mode_name = master.flightmode or "unknown"
        armed = bool(hb and (hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED))

        return [
            "=== Vehicle snapshot ===",
            f"Mode: {mode_name}",
            f"Armed: {armed}",
            f"GPS fix: {self._format_gps_fix(gps)}",
            f"Location: {self._format_location(pos)} ({self._format_relative_altitude(pos)})",
            f"Attitude: {self._format_attitude(att)}",
            f"Velocity: {self._format_velocity(pos)}",
            f"Battery: {self._format_battery(sys_status)}",
        ]

    def arm_and_takeoff(self, target_altitude: float) -> None:
        if target_altitude <= 0:
            raise ValueError("Altitude must be greater than 0 meters")

        master = self.master
        self._wait_for_condition(self._is_armable, timeout=60)
        self._wait_for_mode("GUIDED", timeout=45.0)
        self._ensure_armed(timeout=45.0)
        time.sleep(1.0)
        master.mav.command_long_send(
            master.target_system,
            master.target_component,
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
            0,
            0, 0, 0, 0, 0, 0,
            target_altitude,
        )

    def land(self) -> None:
        self._wait_for_mode("LAND", timeout=30.0)

    def set_altitude(self, target_altitude: float) -> None:
        if target_altitude <= 0:
            raise ValueError("Altitude must be greater than 0 meters")

        self._ensure_guided_and_armed("change altitude")
        pos = self.master.messages.get("GLOBAL_POSITION_INT")
        if pos is None:
            raise RuntimeError("No position data received yet")
        self._send_position_target(pos.lat / 1e7, pos.lon / 1e7, target_altitude)

    def move_forward(self, distance_m: float) -> None:
        if distance_m <= 0:
            raise ValueError("Distance must be greater than 0 meters")
        self._move(distance_m, forward=True)

    def move_back(self, distance_m: float) -> None:
        if distance_m <= 0:
            raise ValueError("Distance must be greater than 0 meters")
        self._move(distance_m, forward=False)

    def rotate_left(self, degrees: float) -> None:
        if degrees <= 0:
            raise ValueError("Degrees must be greater than 0")
        self._rotate(degrees, clockwise=False)

    def rotate_right(self, degrees: float) -> None:
        if degrees <= 0:
            raise ValueError("Degrees must be greater than 0")
        self._rotate(degrees, clockwise=True)

    # ------------------------------------------------------------------
    # Shared connection setup
    # ------------------------------------------------------------------

    def _open_master(self, conn_str: str, proxy: Optional[GCSProxy] = None) -> None:
        """Connect mavutil to *conn_str* and start the background reader.

        Shared by both concrete backends: ArduPilot doesn't stream GPS/
        position/attitude/battery messages unless asked, and pymavlink has no
        listener dispatch of its own — nothing populates ``master.messages``/
        ``master.flightmode`` unless a reader thread keeps draining the
        connection. See ``MAVLinkReader`` for why.
        """
        self._active_connection = conn_str

        self._master = mavutil.mavlink_connection(conn_str)
        if not self._master.wait_heartbeat(timeout=self._heartbeat_timeout):
            raise TimeoutError(f"No heartbeat received from {conn_str}")

        self._master.mav.request_data_stream_send(
            self._master.target_system,
            self._master.target_component,
            mavutil.mavlink.MAV_DATA_STREAM_ALL,
            4,
            1,
        )

        self._reader = MAVLinkReader(
            self._master,
            on_frame=proxy.forward if proxy is not None else None,
        )
        self._reader.start()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _move(self, distance_m: float, forward: bool) -> None:
        self._ensure_guided_and_armed("move")
        att = self.master.messages.get("ATTITUDE")
        pos = self.master.messages.get("GLOBAL_POSITION_INT")
        if att is None or pos is None:
            raise RuntimeError("No attitude/position data received yet")

        yaw = att.yaw  # radians; 0 = North, CW positive
        lat_rad = math.radians(pos.lat / 1e7)
        sign = 1 if forward else -1
        d_lat = sign * distance_m * math.cos(yaw) / 111_320
        d_lon = sign * distance_m * math.sin(yaw) / (111_320 * math.cos(lat_rad))

        self._send_position_target(
            pos.lat / 1e7 + d_lat,
            pos.lon / 1e7 + d_lon,
            pos.relative_alt / 1000.0,
        )

    def _rotate(self, degrees: float, clockwise: bool) -> None:
        self._ensure_guided_and_armed("rotate")
        master = self.master
        direction = 1 if clockwise else -1
        master.mav.command_long_send(
            master.target_system,
            master.target_component,
            mavutil.mavlink.MAV_CMD_CONDITION_YAW,
            0,
            degrees,      # param1: angle in degrees
            0,            # param2: angular speed (0 = default)
            direction,    # param3: 1 CW, -1 CCW
            1,            # param4: 1 = relative offset
            0, 0, 0,
        )

    def _ensure_guided_and_armed(self, action: str) -> None:
        master = self.master
        hb = master.messages.get("HEARTBEAT")
        armed = bool(hb and (hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED))
        if not armed:
            raise RuntimeError(f"Vehicle must be armed and airborne to {action}")
        if master.flightmode != "GUIDED":
            self._wait_for_mode("GUIDED", timeout=30.0)

    def _send_position_target(self, lat: float, lon: float, alt: float) -> None:
        master = self.master
        master.mav.set_position_target_global_int_send(
            0,
            master.target_system,
            master.target_component,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
            _POSITION_ONLY_TYPEMASK,
            int(lat * 1e7),
            int(lon * 1e7),
            alt,
            0, 0, 0,
            0, 0, 0,
            0, 0,
        )

    def _wait_for_condition(self, predicate, timeout: float, poll_interval: float = 1.0) -> None:
        start = time.time()
        while not predicate():
            if time.time() - start > timeout:
                raise TimeoutError("Timed out waiting for condition")
            time.sleep(poll_interval)

    def _wait_for_mode(self, target_mode: str, timeout: float = 30.0) -> None:
        master = self.master
        normalized = target_mode.upper()
        start = time.time()
        last_set = 0.0

        while True:
            now = time.time()
            if now - last_set >= 1.0:
                self._set_mode(normalized)
                last_set = now

            if (master.flightmode or "").upper() == normalized:
                return

            if now - start > timeout:
                raise TimeoutError(f"Failed to enter {normalized} mode")

            time.sleep(0.5)

    def _set_mode(self, mode_name: str) -> None:
        # Deliberately not mavutil's set_mode_apm(): current pymavlink sends
        # MAV_CMD_DO_SET_MODE via COMMAND_LONG, which the ArduCopter 3.3 SITL
        # binary dronekit_sitl bundles rejects (COMMAND_ACK result=3,
        # unsupported) — that firmware only understands the legacy SET_MODE
        # message, so we send it directly.
        master = self.master
        mode_map = master.mode_mapping()
        if mode_map is None or mode_name not in mode_map:
            raise RuntimeError(f"Unknown flight mode {mode_name!r}")
        master.mav.set_mode_send(
            master.target_system,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            mode_map[mode_name],
        )

    def _ensure_armed(self, timeout: float = 45.0) -> None:
        master = self.master
        start = time.time()
        last_arm = 0.0

        while True:
            hb = master.messages.get("HEARTBEAT")
            armed = bool(hb and (hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED))
            if armed:
                return

            now = time.time()
            if now - last_arm >= 1.0:
                master.arducopter_arm()
                last_arm = now

            if now - start > timeout:
                raise TimeoutError("Failed to arm vehicle")

            time.sleep(0.5)

    def _is_armable(self) -> bool:
        # Simplified stand-in for DroneKit's `is_armable`: GPS 3D fix and at
        # least one heartbeat seen, rather than a full EKF/prearm-bit check.
        gps = self.master.messages.get("GPS_RAW_INT")
        hb = self.master.messages.get("HEARTBEAT")
        return bool(gps and gps.fix_type >= 3 and hb is not None)

    @staticmethod
    def _format_attitude(att) -> str:
        if att is None:
            return "unknown"
        return "roll={:.2f}, pitch={:.2f}, yaw={:.2f}".format(att.roll, att.pitch, att.yaw)

    @staticmethod
    def _format_gps_fix(gps) -> str:
        if gps is None:
            return "unknown"
        fix_types = {0: "no GPS", 1: "no fix", 2: "2D", 3: "3D", 4: "DGPS", 5: "RTK-float", 6: "RTK-fixed"}
        return fix_types.get(gps.fix_type, f"type={gps.fix_type}")

    @staticmethod
    def _format_location(pos) -> str:
        if pos is None:
            return "unknown"
        return f"lat={pos.lat / 1e7:.6f}, lon={pos.lon / 1e7:.6f}, alt={pos.alt / 1000.0:.1f}m"

    @staticmethod
    def _format_relative_altitude(pos) -> str:
        if pos is None:
            return "agl=unknown"
        return f"agl={pos.relative_alt / 1000.0:.1f}m"

    @staticmethod
    def _format_velocity(pos) -> str:
        # cm/s, NED frame — not normalized to DroneKit's velocity tuple ordering.
        if pos is None:
            return "unknown"
        return f"vx={pos.vx / 100.0:.2f}m/s, vy={pos.vy / 100.0:.2f}m/s, vz={pos.vz / 100.0:.2f}m/s"

    @staticmethod
    def _format_battery(sys_status) -> str:
        if sys_status is None:
            return "unknown"
        voltage = sys_status.voltage_battery / 1000.0
        current = sys_status.current_battery / 100.0 if sys_status.current_battery != -1 else None
        level = sys_status.battery_remaining if sys_status.battery_remaining != -1 else "unknown"
        current_str = f"{current:.1f}A" if current is not None else "unknown"
        return f"voltage={voltage:.1f}V, current={current_str}, level={level}"
