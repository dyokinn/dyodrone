"""dyopilot against a live ArduCopter 3.3 SITL. Opt in with ``pytest -m sitl``."""

from __future__ import annotations

import subprocess
import threading

import pytest
from fakes import wait_for
from marks import needs_pymavlink

pytestmark = [pytest.mark.sitl, pytest.mark.dyopilot, needs_pymavlink]

pytest.importorskip("dronekit_sitl")


def simulator_running() -> bool:
    return subprocess.run(["pgrep", "-f", r"\.dronekit/sitl"], capture_output=True).returncode == 0


def agl(controller) -> float:
    pos = controller.master.messages.get("GLOBAL_POSITION_INT")
    return pos.relative_alt / 1000.0 if pos is not None else 0.0


def test_takeoff_land_and_clean_shutdown():
    from dyodrone.core.targets import SitlTarget
    from dyodrone.drivers.dyopilot_driver import DyopilotController

    ctrl = DyopilotController(SitlTarget())
    ctrl.connect()
    try:
        assert wait_for(lambda: ctrl.master.messages.get("GPS_RAW_INT") is not None, timeout=30)
        ctrl.arm_and_takeoff(10)
        assert wait_for(lambda: agl(ctrl) >= 9.0, timeout=40), "never reached 9 m"
        assert "Mode: GUIDED" in ctrl.status_lines()
        ctrl.land()
        assert wait_for(lambda: ctrl.master.flightmode == "LAND", timeout=10)
    finally:
        ctrl.close()
    assert wait_for(lambda: not simulator_running(), timeout=10), "simulator process was left running"


def test_pixhawk_controller_drives_a_standalone_simulator():
    import dronekit_sitl

    from dyodrone.core.targets import ExternalTarget
    from dyodrone.drivers.dyopilot_driver import DyopilotController

    sitl = dronekit_sitl.start_default()
    try:
        ctrl = DyopilotController(ExternalTarget(sitl.connection_string()))
        ctrl.connect()
        try:
            assert wait_for(lambda: ctrl.master.messages.get("HEARTBEAT") is not None, timeout=10)
            assert ctrl.active_connection == sitl.connection_string()
        finally:
            ctrl.close()
    finally:
        sitl.stop()


def test_web_console_flies_the_simulator():
    import http.client
    import json

    from dyodrone.gui.server import ConsoleServer
    from dyodrone.gui.session import ConsoleSession

    session = ConsoleSession("dyopilot")
    server = ConsoleServer(("127.0.0.1", 0), session, token="t")
    threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True).start()
    port = server.server_address[1]

    def call(method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request(method, path, json.dumps(body) if body is not None else None, {"X-Token": "t"})
        data = json.loads(conn.getresponse().read().decode())
        conn.close()
        return data

    try:
        call("POST", "/api/connect", {"target": "sitl", "gcs_port": 0})
        assert wait_for(lambda: call("GET", "/api/state")["status"] == "connected", timeout=60)
        call("POST", "/api/command", {"line": "takeoff 10"})
        assert wait_for(lambda: any("Takeoff initiated" in e["text"] for e in call("GET", "/api/state")["log"]), timeout=60)
        assert wait_for(lambda: "Armed: True" in call("GET", "/api/state")["telemetry"], timeout=20)
        call("POST", "/api/command", {"line": "land"})
        call("POST", "/api/disconnect", {})
        assert wait_for(lambda: call("GET", "/api/state")["status"] == "disconnected", timeout=20)
    finally:
        session.close()
        server.shutdown()
        server.server_close()
    assert wait_for(lambda: not simulator_running(), timeout=10)
