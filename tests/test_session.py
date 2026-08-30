import json
from pathlib import Path

import pytest

from agent.action import Action
from agent.completion import CompletionGate
from agent.session import SessionError, SessionStore
from agent.state import Message


def test_session_store_round_trips_history(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    store = SessionStore(tmp_path / "sessions")
    history = [
        Message("system", "return JSON"),
        Message("user", "create a file"),
        Message("assistant", '{"type":"Stop","params":{"reason":"done"}}'),
    ]
    gate = CompletionGate()
    gate.observe(
        Action("Write_File", {"path": "main.py", "content": "x"}),
        success=True,
    )

    path = store.save("demo-1", workspace, history, completion=gate.snapshot())

    assert path.is_file()
    assert store.load("demo-1", workspace) == history
    data = store.load_data("demo-1", workspace)
    assert data.completion == gate.snapshot()


def test_session_store_rejects_different_workspace(tmp_path: Path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    store = SessionStore(tmp_path / "sessions")
    store.save("demo", first, [Message("user", "task")])

    with pytest.raises(SessionError, match="different workspace"):
        store.load("demo", second)


@pytest.mark.parametrize("name", ["../escape", "has space", "", "a" * 65])
def test_session_store_rejects_unsafe_names(tmp_path: Path, name: str):
    store = SessionStore(tmp_path / "sessions")

    with pytest.raises(SessionError, match="session name"):
        store.path_for(name)


def test_session_store_rejects_corrupt_history(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    store = SessionStore(tmp_path / "sessions")
    store.root.mkdir()
    payload = {
        "version": 1,
        "name": "demo",
        "workspace": str(workspace.resolve()),
        "history": ["not a message"],
    }
    store.path_for("demo").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SessionError, match="invalid message"):
        store.load("demo", workspace)
