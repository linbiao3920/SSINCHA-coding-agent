import json
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread

from agent.action import Action
from agent.state import AgentState
from agent.session import SessionStore
from agent import web


def _request(server, method, path, payload=None):
    host, port = server.server_address
    connection = HTTPConnection(host, port, timeout=5)
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"} if body is not None else {}
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    data = response.read()
    connection.close()
    return response.status, json.loads(data) if data else None


def test_web_serves_ui_and_manages_sessions(tmp_path: Path):
    server = web.create_server(port=0, session_dir=tmp_path / "sessions")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        connection = HTTPConnection(host, port, timeout=5)
        connection.request("GET", "/")
        response = connection.getresponse()
        html = response.read().decode("utf-8")
        connection.close()
        assert response.status == 200
        assert "DeepSeek API Key" in html

        status, created = _request(
            server,
            "POST",
            "/api/sessions",
            {"name": "demo", "workspace": str(tmp_path)},
        )
        assert status == 201
        assert created["sessions"] == ["demo"]
        status, listed = _request(server, "GET", "/api/sessions")
        assert status == 200 and listed["sessions"] == ["demo"]
        status, deleted = _request(server, "DELETE", "/api/sessions/demo")
        assert status == 200 and deleted["deleted"] is True
        assert not SessionStore(tmp_path / "sessions").exists("demo")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_web_run_does_not_return_api_key(monkeypatch, tmp_path: Path):
    token = "sk-0123456789abcdef0123456789abcdef"
    state = AgentState(f"say hello with {token}")
    state.add_step(
        Action("Write_File", {"path": "note.py", "content": token}),
        observation=token,
        success=True,
    )
    state.add_step(Action("Stop", {"reason": "done"}), success=True)
    monkeypatch.setattr(web, "run_task", lambda *args, **kwargs: state)

    server = web.create_server(port=0, session_dir=tmp_path / "sessions")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, payload = _request(
            server,
            "POST",
            "/api/run",
            {
                "api_key": token,
                "workspace": str(tmp_path),
                "task": f"say hello with {token}",
            },
        )
        assert status == 200
        assert token not in json.dumps(payload)
        assert "<redacted>" in payload["trajectory"][0]["observation"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
