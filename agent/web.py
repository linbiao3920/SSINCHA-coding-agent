"""Small local web UI for the SSINCHA coding agent.

Run with ``python -m agent.web`` and open http://127.0.0.1:8765/.
"""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .cli import exit_code_for_state, run_task
from .llm import LLMError, RealLLMClient
from .secrets import redact
from .session import SessionError, SessionStore


MAX_BODY_BYTES = 1_000_000
STATIC_DIR = Path(__file__).with_name("static")


def _redact_value(value: object, api_key: str) -> object:
    if isinstance(value, str):
        return redact(value, [api_key])
    if isinstance(value, dict):
        return {key: _redact_value(item, api_key) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_value(item, api_key) for item in value]
    return value


def _state_payload(state, api_key: str) -> dict[str, object]:
    return {
        "task": redact(state.task, [api_key]),
        "steps": state.step_count,
        "exit_code": exit_code_for_state(state),
        "trajectory": [
            {
                "action": _redact_value(step.action.to_dict(), api_key),
                "observation": redact(step.observation, [api_key]),
                "success": step.success,
            }
            for step in state.trajectory
        ],
        "errors": [
            {
                "source": error.source,
                "message": redact(error.message, [api_key]),
                "category": error.category,
                "error_type": error.error_type,
                "location": error.location,
            }
            for error in state.error_logs
        ],
    }


class AgentWebHandler(BaseHTTPRequestHandler):
    server_version = "SSINCHA-Web/1.0"

    @property
    def store(self) -> SessionStore:
        return self.server.session_store  # type: ignore[attr-defined]

    def _json(self, status: HTTPStatus, payload: object) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _read_json(self) -> dict[str, object] | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid content length"})
            return None
        if length <= 0 or length > MAX_BODY_BYTES:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "request body is invalid"})
            return None
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "request must be JSON"})
            return None
        if type(value) is not dict:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "request must be an object"})
            return None
        return value

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            try:
                content = (STATIC_DIR / "index.html").read_bytes()
            except OSError:
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "UI unavailable"})
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        if parsed.path == "/api/sessions":
            self._json(HTTPStatus.OK, {"sessions": self.store.list_names()})
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/run" and self.path != "/api/sessions":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        data = self._read_json()
        if data is None:
            return
        if self.path == "/api/sessions":
            self._create_session(data)
            return
        self._run_task(data)

    def do_DELETE(self) -> None:  # noqa: N802
        prefix = "/api/sessions/"
        if not self.path.startswith(prefix):
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        name = unquote(self.path[len(prefix) :])
        try:
            deleted = self.store.delete(name)
        except SessionError as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._json(HTTPStatus.OK, {"deleted": deleted, "sessions": self.store.list_names()})

    def _create_session(self, data: dict[str, object]) -> None:
        name = data.get("name")
        workspace = data.get("workspace")
        if type(name) is not str or type(workspace) is not str:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "name and workspace are required"})
            return
        try:
            if self.store.exists(name):
                self._json(HTTPStatus.CONFLICT, {"error": "session already exists"})
                return
            self.store.save(name, workspace, [])
        except (SessionError, ValueError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._json(HTTPStatus.CREATED, {"name": name, "sessions": self.store.list_names()})

    def _run_task(self, data: dict[str, object]) -> None:
        api_key = data.get("api_key")
        workspace = data.get("workspace")
        task = data.get("task")
        session = data.get("session")
        if any(type(value) is not str or not value.strip() for value in (api_key, workspace, task)):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "api_key, workspace and task are required"})
            return
        if session is not None and (type(session) is not str or not session.strip()):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "session must be a valid name"})
            return
        try:
            state = run_task(
                task,
                workspace,
                session=session,
                session_store=self.store,
                llm=RealLLMClient(api_key=api_key),
            )
        except (LLMError, SessionError, ValueError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": redact(str(exc), [api_key])})
            return
        self._json(HTTPStatus.OK, _state_payload(state, api_key))

    def log_message(self, format: str, *args: object) -> None:
        # Keep request bodies (which may contain credentials) out of logs.
        super().log_message(format, *args)


def create_server(host: str = "127.0.0.1", port: int = 8765, session_dir: str | Path | None = None):
    server = ThreadingHTTPServer((host, port), AgentWebHandler)
    server.session_store = SessionStore(session_dir) if session_dir else SessionStore()  # type: ignore[attr-defined]
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local SSINCHA web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--session-dir", default=None)
    args = parser.parse_args(argv)
    server = create_server(args.host, args.port, args.session_dir)
    print(f"SSINCHA UI: http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
