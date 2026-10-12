"""Test doubles shared across the suite. Python 3.7 compatible."""

from __future__ import annotations

import socket
import sys
import threading
import time
import types
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional

from dyodrone.core.controller import DroneController
from dyodrone.core.targets import Target

ARMED_FLAG = 128  # MAV_MODE_FLAG_SAFETY_ARMED


def wait_for(predicate: Callable[[], bool], timeout: float = 3.0, interval: float = 0.01) -> bool:
    """Poll *predicate* until it is true or *timeout* seconds pass."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeController(DroneController):
    """Records every call; optionally blocks or fails to exercise the console."""

    def __init__(self, connect_error: Optional[Exception] = None, block_takeoff: bool = False) -> None:
        self.calls: List[tuple] = []
        self.connect_error = connect_error
        self.release_takeoff = threading.Event()
        if not block_takeoff:
            self.release_takeoff.set()
        self.connected = False
        self.closed = False
        self._conn: Optional[str] = None

    @property
    def active_connection(self) -> Optional[str]:
        return self._conn

    def connect(self) -> None:
        self.calls.append(("connect",))
        if self.connect_error is not None:
            raise self.connect_error
        self.connected = True
        self._conn = "fake:0"

    def close(self) -> None:
        self.calls.append(("close",))
        self.closed = True
        self.connected = False
        self._conn = None

    def status_lines(self) -> List[str]:
        return ["=== Vehicle snapshot ===", "Mode: GUIDED", "Armed: True"]

    def arm_and_takeoff(self, target_altitude: float) -> None:
        self.release_takeoff.wait(5)
        self.calls.append(("arm_and_takeoff", target_altitude))

    def land(self) -> None:
        self.calls.append(("land",))

    def set_altitude(self, target_altitude: float) -> None:
        self.calls.append(("set_altitude", target_altitude))

    def move_forward(self, distance_m: float) -> None:
        self.calls.append(("move_forward", distance_m))

    def move_back(self, distance_m: float) -> None:
        self.calls.append(("move_back", distance_m))

    def rotate_left(self, degrees: float) -> None:
        self.calls.append(("rotate_left", degrees))

    def rotate_right(self, degrees: float) -> None:
        self.calls.append(("rotate_right", degrees))


class FakeTarget(Target):
    """A target that only records acquire/release, optionally into a shared log."""

    name = "fake"

    def __init__(self, connection: str = "tcp:127.0.0.1:5760", log: Optional[List[str]] = None) -> None:
        self.connection = connection
        self.log = log if log is not None else []

    def acquire(self) -> str:
        self.log.append("acquire")
        return self.connection

    def release(self) -> None:
        self.log.append("release")


class FakeMav:
    """Stands in for ``master.mav``: records every ``*_send`` call in order."""

    def __init__(self, log: List[tuple], on_call: Optional[Callable[[str, tuple], None]] = None) -> None:
        self._log = log
        self._on_call = on_call

    def __getattr__(self, name: str):
        def record(*args: Any, **kwargs: Any) -> None:
            self._log.append((name, args))
            if self._on_call is not None:
                self._on_call(name, args)

        return record


class FakeMaster:
    """Minimal ``mavutil.mavfile``: message cache, flight mode, arming, heartbeat."""

    MODES = {"STABILIZE": 0, "ACRO": 1, "ALT_HOLD": 2, "AUTO": 3, "GUIDED": 4, "LOITER": 5, "RTL": 6, "LAND": 9}

    def __init__(self, heartbeat: bool = True) -> None:
        self.target_system = 1
        self.target_component = 1
        self.flightmode = "STABILIZE"
        self.heartbeat_ok = heartbeat
        self.closed = False
        self.calls: List[tuple] = []  # every mav call and arm, in order
        self.messages: Dict[str, Any] = {"HEARTBEAT": SimpleNamespace(base_mode=0)}
        self.mav = FakeMav(self.calls, self._on_mav)

    def _on_mav(self, name: str, args: tuple) -> None:
        if name == "set_mode_send":  # (target_system, base_mode, custom_mode)
            by_number = {v: k for k, v in self.MODES.items()}
            self.flightmode = by_number[args[2]]

    # -- mavutil surface used by the drivers -----------------------------
    def wait_heartbeat(self, timeout: Optional[float] = None) -> bool:
        return self.heartbeat_ok

    def mode_mapping(self) -> Dict[str, int]:
        return dict(self.MODES)

    def arducopter_arm(self) -> None:
        self.calls.append(("arducopter_arm", ()))
        self.messages["HEARTBEAT"] = SimpleNamespace(base_mode=ARMED_FLAG)

    def recv_msg(self):
        time.sleep(0.005)
        return None

    def close(self) -> None:
        self.closed = True

    # -- helpers for tests ----------------------------------------------
    def arm(self) -> None:
        self.messages["HEARTBEAT"] = SimpleNamespace(base_mode=ARMED_FLAG)

    def set_position(self, lat: float, lon: float, relative_alt_m: float = 10.0, yaw: float = 0.0) -> None:
        self.messages["GLOBAL_POSITION_INT"] = SimpleNamespace(
            lat=int(lat * 1e7), lon=int(lon * 1e7), alt=int((relative_alt_m + 584) * 1000),
            relative_alt=int(relative_alt_m * 1000), vx=0, vy=0, vz=0,
        )
        self.messages["ATTITUDE"] = SimpleNamespace(roll=0.0, pitch=0.0, yaw=yaw)

    def names(self) -> List[str]:
        return [c[0] for c in self.calls]


def install_fake_dronekit_sitl(monkeypatch, connection: str = "tcp:127.0.0.1:5760"):
    """Put a fake ``dronekit_sitl`` module in ``sys.modules``; returns its call log."""
    log: List[str] = []

    class _Sitl:
        def connection_string(self) -> str:
            return connection

        def stop(self) -> None:
            log.append("stop")

    module = types.ModuleType("dronekit_sitl")

    def start_default() -> _Sitl:
        log.append("start")
        return _Sitl()

    module.start_default = start_default  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "dronekit_sitl", module)
    return log
