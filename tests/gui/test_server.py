"""Web console HTTP server: routes, validation and the token/Host/Origin checks."""

from __future__ import annotations

import http.client
import json
import threading
from types import SimpleNamespace

import pytest
from fakes import FakeController, wait_for

from dyodrone.gui import session as session_module
from dyodrone.gui.server import ConsoleServer
from dyodrone.gui.session import ConsoleSession

TOKEN = "test-token"


@pytest.fixture
def stack(monkeypatch):
    controller = FakeController()
    monkeypatch.setattr(session_module, "create_controller", lambda *a, **k: controller)
    session = ConsoleSession("dyopilot")
    server = ConsoleServer(("127.0.0.1", 0), session, token=TOKEN)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.02), daemon=True)
    thread.start()
    port = server.server_address[1]

    def request(method, path, body=None, headers=None, token=TOKEN, raw=None):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        hdrs = {}
        if token is not None:
            hdrs["X-Token"] = token
        hdrs.update(headers or {})
        data = raw if raw is not None else (json.dumps(body) if body is not None else None)
        if data is not None:
            hdrs.setdefault("Content-Type", "application/json")
        conn.request(method, path, body=data, headers=hdrs)
        resp = conn.getresponse()
        payload = resp.read()
        conn.close()
        return resp.status, resp.getheader("Content-Type"), payload

    class Stack:
        pass

    s = Stack()
    s.request, s.port, s.session, s.controller, s.server = request, port, session, controller, server
    yield s
    server.shutdown()
    server.server_close()
    session.close()


def json_of(response):
    return json.loads(response[2].decode())


# -- authorization ---------------------------------------------------------


@pytest.mark.parametrize(
    "method, path",
    [("GET", "/api/state"), ("POST", "/api/connect"), ("POST", "/api/disconnect"), ("POST", "/api/command")],
)
@pytest.mark.parametrize("token", [None, "wrong", ""])
def test_api_requires_the_token(stack, method, path, token):
    assert stack.request(method, path, {}, token=token)[0] == 403


def test_api_rejects_a_foreign_host_header(stack):
    assert stack.request("GET", "/api/state", headers={"Host": "evil.example:%d" % stack.port})[0] == 403


def test_api_rejects_a_foreign_origin(stack):
    status = stack.request("POST", "/api/command", {"line": "land"}, headers={"Origin": "http://evil.example"})[0]
    assert status == 403
    assert stack.controller.calls == []


def test_api_accepts_the_servers_own_origin(stack):
    origin = "http://127.0.0.1:%d" % stack.port
    assert stack.request("POST", "/api/command", {"line": "help"}, headers={"Origin": origin})[0] == 200


def test_page_rejects_a_foreign_host_header(stack):
    assert stack.request("GET", "/", headers={"Host": "evil.example"})[0] == 403


# -- static ----------------------------------------------------------------


def test_index_page_is_served_without_a_token(stack):
    status, ctype, body = stack.request("GET", "/", token=None)
    assert status == 200 and ctype.startswith("text/html")
    assert b"dyodrone" in body and b"X-Token" in body


def test_unknown_paths_are_404(stack):
    assert stack.request("GET", "/nope", token=None)[0] == 404
    assert stack.request("POST", "/api/nope", {})[0] == 404


def test_favicon_is_empty(stack):
    assert stack.request("GET", "/favicon.ico", token=None)[0] == 204


# -- state and actions -----------------------------------------------------


def test_state_has_the_fields_the_page_uses(stack):
    state = json_of(stack.request("GET", "/api/state"))
    assert {"driver", "python", "target", "connection", "gcs_port", "status", "busy", "queued",
            "telemetry", "details", "log", "last_id"} <= set(state)
    assert state["status"] == "disconnected" and state["driver"] == "dyopilot"


def test_state_since_parameter_filters_the_log(stack):
    last = json_of(stack.request("GET", "/api/state"))["last_id"]
    assert json_of(stack.request("GET", "/api/state?since=%d" % last))["log"] == []
    assert json_of(stack.request("GET", "/api/state?since=junk"))["log"]  # falls back to everything


def test_connect_command_disconnect_cycle(stack):
    assert stack.request("POST", "/api/connect", {"target": "sitl", "gcs_port": 0})[0] == 200
    assert wait_for(lambda: json_of(stack.request("GET", "/api/state"))["status"] == "connected")

    assert stack.request("POST", "/api/command", {"line": "takeoff 10"})[0] == 200
    assert wait_for(lambda: ("arm_and_takeoff", 10.0) in stack.controller.calls)
    state = json_of(stack.request("GET", "/api/state"))
    assert state["telemetry"][1] == "Mode: GUIDED"
    assert any(e["text"] == "Takeoff initiated to 10.0 m" for e in state["log"])

    assert stack.request("POST", "/api/disconnect", {})[0] == 200
    assert wait_for(lambda: json_of(stack.request("GET", "/api/state"))["status"] == "disconnected")
    assert stack.controller.closed


def test_second_connect_is_a_conflict(stack):
    stack.request("POST", "/api/connect", {"target": "sitl"})
    assert wait_for(lambda: json_of(stack.request("GET", "/api/state"))["status"] == "connected")
    status, _, body = stack.request("POST", "/api/connect", {"target": "sitl"})
    assert status == 409 and "error" in json.loads(body.decode())


@pytest.mark.parametrize("body", [{"target": "warp"}, {"target": "sitl", "gcs_port": 99999}, {"target": "sitl", "gcs_port": "x"}])
def test_invalid_connect_bodies_are_400(stack, body):
    assert stack.request("POST", "/api/connect", body)[0] == 400


def test_malformed_json_is_400(stack):
    assert stack.request("POST", "/api/command", raw="not json")[0] == 400
    assert stack.request("POST", "/api/command", raw="[1, 2]")[0] == 400


def test_oversized_bodies_are_rejected(stack):
    assert stack.request("POST", "/api/command", {"line": "x" * 70000})[0] == 400


# -- input switches, emergency, plans ----------------------------------------


def test_inputs_endpoint_flips_switches_and_state_reports_them(stack):
    status, _, body = stack.request("POST", "/api/inputs", {"voice": True, "plan": True})
    assert status == 200
    assert json_of(stack.request("GET", "/api/state"))["inputs"] == {"console": True, "plan": True, "voice": True}
    stack.request("POST", "/api/inputs", {"plan": False})
    assert json_of(stack.request("GET", "/api/state"))["inputs"]["plan"] is False


@pytest.mark.parametrize("body", [{"gamepad": True}, {"voice": "yes"}])
def test_inputs_endpoint_validates(stack, body):
    assert stack.request("POST", "/api/inputs", body)[0] == 400


def test_a_command_from_a_switched_off_console_is_a_conflict(stack):
    stack.request("POST", "/api/inputs", {"console": False})
    status, _, body = stack.request("POST", "/api/command", {"line": "help"})
    assert status == 409 and "Console input is off" in json.loads(body.decode())["error"]


def test_emergency_endpoint_needs_a_connection_then_lands(stack):
    assert stack.request("POST", "/api/emergency", {})[0] == 409
    stack.request("POST", "/api/connect", {"target": "sitl"})
    assert wait_for(lambda: json_of(stack.request("GET", "/api/state"))["status"] == "connected")
    assert stack.request("POST", "/api/emergency", {})[0] == 200
    assert wait_for(lambda: ("land",) in stack.controller.calls)


def test_plan_endpoint_validates_and_returns_steps(stack):
    status, _, body = stack.request("POST", "/api/plan", {"text": "takeoff 10\nland\n"})
    assert status == 200
    assert [s["command"] for s in json.loads(body.decode())["steps"]] == ["takeoff 10", "land"]
    assert json_of(stack.request("GET", "/api/state"))["plan"]["total"] == 2


def test_plan_endpoint_reports_every_error_with_its_line(stack):
    status, _, body = stack.request("POST", "/api/plan", {"text": "takeoff\nflip 3\nland"})
    data = json.loads(body.decode())
    assert status == 400 and [e["line"] for e in data["errors"]] == [1, 2]
    assert "line 1" in data["error"]


def test_plan_run_is_refused_until_the_plan_switch_is_on(stack):
    stack.request("POST", "/api/plan", {"text": "land"})
    assert stack.request("POST", "/api/plan/run", {})[0] == 409
    for action in ("pause", "resume", "stop"):
        assert stack.request("POST", "/api/plan/" + action, {})[0] == 409


def test_history_endpoint_requires_the_token_and_returns_plan_text(stack):
    assert stack.request("GET", "/api/plan/history", token=None)[0] == 403
    stack.request("POST", "/api/connect", {"target": "sitl"})
    assert wait_for(lambda: json_of(stack.request("GET", "/api/state"))["status"] == "connected")
    stack.request("POST", "/api/command", {"line": "takeoff 10"})
    assert wait_for(lambda: json_of(stack.request("GET", "/api/plan/history"))["count"] == 1)
    assert "takeoff 10" in json_of(stack.request("GET", "/api/plan/history"))["text"]


@pytest.mark.parametrize("path", ["/api/inputs", "/api/emergency", "/api/plan", "/api/plan/run", "/api/plan/stop"])
def test_new_endpoints_are_behind_the_same_authorization(stack, path):
    assert stack.request("POST", path, {}, token="wrong")[0] == 403
    assert stack.request("POST", path, {}, headers={"Origin": "http://evil.example"})[0] == 403


# -- voice endpoints ---------------------------------------------------------


@pytest.fixture
def vstack(monkeypatch):
    from fakes import FakeEngine, FakeTimer
    from dyodrone.gui.voice_engine import SpeechResult

    FakeTimer.created = []
    engine = FakeEngine()
    monkeypatch.setattr(session_module, "create_controller", lambda *a, **k: FakeController())
    session = ConsoleSession("dyopilot", engine_factory=lambda p: engine, timer_factory=FakeTimer)
    server = ConsoleServer(("127.0.0.1", 0), session, token=TOKEN)
    threading.Thread(target=lambda: server.serve_forever(poll_interval=0.02), daemon=True).start()
    port = server.server_address[1]

    def post(path, data, headers=None, content_type="application/octet-stream"):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        hdrs = {"X-Token": TOKEN, "Content-Type": content_type}
        hdrs.update(headers or {})
        conn.request("POST", path, body=data, headers=hdrs)
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp.status, body

    def state():
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/api/state", headers={"X-Token": TOKEN})
        out = json.loads(conn.getresponse().read().decode())
        conn.close()
        return out

    yield SimpleNamespace(post=post, state=state, session=session, engine=engine, SpeechResult=SpeechResult, timers=FakeTimer.created)
    server.shutdown()
    server.server_close()
    session.close()


def test_audio_is_refused_until_voice_is_on_and_ready(vstack):
    assert vstack.post("/api/voice/audio", b"\0\0")[0] == 409
    vstack.session.set_inputs(voice=True)
    assert wait_for(lambda: vstack.state()["voice"]["status"] == "listening")
    status, body = vstack.post("/api/voice/audio", b"\0\0")
    assert status == 200 and json.loads(body.decode())["status"] == "listening"
    assert vstack.engine.chunks == [b"\0\0"]


def test_audio_results_show_up_as_partials_and_pending_commands(vstack):
    vstack.session.set_inputs(voice=True)
    assert wait_for(lambda: vstack.state()["voice"]["status"] == "listening")
    vstack.engine.script.append(vstack.SpeechResult(partial="takeoff"))
    assert json.loads(vstack.post("/api/voice/audio", b"x")[1].decode())["partial"] == "takeoff"
    vstack.engine.script.append(vstack.SpeechResult(finals=["forward five"]))
    vstack.post("/api/voice/audio", b"x")
    assert [p["command"] for p in vstack.state()["voice"]["pending"]] == ["forward 5"]


def test_audio_endpoint_requires_authorization_and_limits_size(vstack):
    vstack.session.set_inputs(voice=True)
    assert wait_for(lambda: vstack.state()["voice"]["status"] == "listening")
    assert vstack.post("/api/voice/audio", b"x", headers={"X-Token": "wrong"})[0] == 403
    assert vstack.post("/api/voice/audio", b"x", headers={"Origin": "http://evil.example"})[0] == 403
    assert vstack.post("/api/voice/audio", b"\0" * (130 * 1024))[0] == 400


def test_cancel_endpoint(vstack):
    vstack.session.set_inputs(voice=True)
    assert wait_for(lambda: vstack.state()["voice"]["status"] == "listening")
    vstack.engine.script.append(vstack.SpeechResult(finals=["forward five back two"]))
    vstack.post("/api/voice/audio", b"x")
    pending = vstack.state()["voice"]["pending"]
    assert vstack.post("/api/voice/cancel", json.dumps({"id": pending[0]["id"]}), content_type="application/json")[0] == 200
    assert len(vstack.state()["voice"]["pending"]) == 1
    assert vstack.post("/api/voice/cancel", json.dumps({"id": 99}), content_type="application/json")[0] == 409
    assert vstack.post("/api/voice/cancel", "{}", content_type="application/json")[0] == 200
    assert vstack.state()["voice"]["pending"] == []
