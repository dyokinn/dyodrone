"""Local HTTP server for the web console (standard library only).

The page polls ``GET /api/state`` once a second and drives the vehicle with
``POST /api/connect``, ``/api/disconnect`` and ``/api/command``. Because these
calls can fly a drone, every ``/api/*`` request must carry the per-run token
and a ``Host``/``Origin`` that match the server — otherwise another web page
open in the same browser could POST to ``localhost`` and command the vehicle.
"""

from __future__ import annotations

import json
import secrets
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from dyodrone.core.plan import PlanError
from dyodrone.gui.session import ConsoleSession, SessionError

_INDEX = Path(__file__).resolve().parent / "static" / "index.html"
_MAX_BODY = 64 * 1024


class ConsoleServer(ThreadingHTTPServer):
    """HTTP server bound to one :class:`ConsoleSession` and one access token."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, session: ConsoleSession, token: Optional[str] = None) -> None:
        super().__init__(address, _Handler)
        self.session = session
        self.token = token or secrets.token_urlsafe(16)
        host, port = self.server_address[:2]
        self.allowed_hosts = {f"{host}:{port}", f"localhost:{port}", f"127.0.0.1:{port}"}

    @property
    def url(self) -> str:
        """URL to open in the browser, including the access token."""
        host, port = self.server_address[:2]
        return f"http://{host}:{port}/?token={self.token}"


class _Handler(BaseHTTPRequestHandler):
    server: ConsoleServer

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - keep the console quiet
        pass

    # -- helpers -------------------------------------------------------

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: Dict[str, Any]) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json")

    def _authorized(self) -> bool:
        if self.headers.get("Host", "") not in self.server.allowed_hosts:
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin != f"http://{self.headers.get('Host')}":
            return False
        token = self.headers.get("X-Token", "")
        return secrets.compare_digest(token.encode(), self.server.token.encode())

    def _body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length > _MAX_BODY:
            raise ValueError("Request body too large")
        if length == 0:
            return {}
        data = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    # -- routes --------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            if self.headers.get("Host", "") not in self.server.allowed_hosts:
                self._json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
                return
            self._send(HTTPStatus.OK, _INDEX.read_bytes(), "text/html; charset=utf-8")
        elif url.path == "/favicon.ico":
            self._send(HTTPStatus.NO_CONTENT, b"", "image/x-icon")
        elif url.path == "/api/plan/history":
            if not self._authorized():
                self._json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
                return
            self._json(HTTPStatus.OK, {"text": self.server.session.history_text(), "count": len(self.server.session._history)})
        elif url.path == "/api/state":
            if not self._authorized():
                self._json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
                return
            try:
                since = int(parse_qs(url.query).get("since", ["0"])[0])
            except ValueError:
                since = 0
            self._json(HTTPStatus.OK, self.server.session.snapshot(since))
        else:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if not self._authorized():
            self._json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
            return
        session = self.server.session
        try:
            body = self._body()
            if path == "/api/connect":
                gcs_port = body.get("gcs_port")
                session.connect(
                    str(body.get("target", "")),
                    body.get("connection"),
                    int(gcs_port) if gcs_port not in (None, "") else None,
                )
            elif path == "/api/disconnect":
                session.disconnect()
            elif path == "/api/command":
                session.submit(str(body.get("line", "")))
            elif path == "/api/inputs":
                session.set_inputs(**body)
            elif path == "/api/emergency":
                session.emergency_land()
            elif path == "/api/plan":
                steps = session.plan_validate(str(body.get("text", "")))
                self._json(HTTPStatus.OK, {"ok": True, "steps": steps})
                return
            elif path == "/api/plan/run":
                session.plan_run()
            elif path == "/api/plan/pause":
                session.plan_pause()
            elif path == "/api/plan/resume":
                session.plan_resume()
            elif path == "/api/plan/stop":
                session.plan_stop()
            else:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
        except SessionError as exc:
            self._json(HTTPStatus.CONFLICT, {"error": str(exc)})
            return
        except PlanError as exc:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"error": str(exc), "errors": [{"line": n, "message": m} for n, m in exc.errors]},
            )
            return
        except (ValueError, TypeError) as exc:  # includes json.JSONDecodeError
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._json(HTTPStatus.OK, {"ok": True})
