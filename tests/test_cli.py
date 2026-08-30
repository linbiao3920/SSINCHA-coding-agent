from pathlib import Path

import pytest

from agent.action import Action
from agent import cli
from agent.cli import build_parser
from agent.session import SessionStore


def test_cli_parser_requires_task():
    args = build_parser().parse_args(["fix the bug", "--workspace", "project"])
    assert args.task == "fix the bug"
    assert args.workspace == "project"


def test_cli_parser_accepts_session_options():
    args = build_parser().parse_args(
        ["next task", "--workspace", "project", "--session", "demo", "--reset-session"]
    )

    assert args.session == "demo"
    assert args.reset_session is True


class RecordingLLM:
    def __init__(self):
        self.calls = []

    def complete(self, messages):
        self.calls.append(list(messages))
        return Action("Stop", {"reason": "done"}).to_json()


def test_run_task_continues_and_resets_a_persisted_session(
    tmp_path: Path, monkeypatch
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    store = SessionStore(tmp_path / "sessions")

    first_llm = RecordingLLM()
    monkeypatch.setattr(cli.RealLLMClient, "from_environment", lambda: first_llm)
    cli.run_task("create unknown.py", workspace, session="demo", session_store=store)

    second_llm = RecordingLLM()
    monkeypatch.setattr(cli.RealLLMClient, "from_environment", lambda: second_llm)
    continued = cli.run_task("a", workspace, session="demo", session_store=store)
    continued_contents = [message.content for message in second_llm.calls[0]]

    assert "create unknown.py" in continued_contents
    assert "a" in continued_contents
    assert continued.step_count == 1

    reset_llm = RecordingLLM()
    monkeypatch.setattr(cli.RealLLMClient, "from_environment", lambda: reset_llm)
    cli.run_task(
        "new task",
        workspace,
        session="demo",
        reset_session=True,
        session_store=store,
    )
    reset_contents = [message.content for message in reset_llm.calls[0]]

    assert "new task" in reset_contents
    assert "create unknown.py" not in reset_contents
    assert "a" not in reset_contents


def test_run_task_rejects_reset_without_session():
    with pytest.raises(ValueError, match="requires --session"):
        cli.run_task("task", reset_session=True)


class ScriptedActionsLLM:
    def __init__(self, actions):
        self.actions = iter(actions)

    def complete(self, _messages):
        return next(self.actions).to_json()


def test_session_restores_a_verified_completion_gate(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    store = SessionStore(tmp_path / "sessions")
    write = Action("Write_File", {"path": "main.py", "content": "value = 1\n"})
    test = Action("Execute_Test", {"cmd": "pytest --version"})
    stop = Action("Stop", {"reason": "verified"})

    first_llm = ScriptedActionsLLM([write, test, stop])
    monkeypatch.setattr(cli.RealLLMClient, "from_environment", lambda: first_llm)
    first = cli.run_task("write and verify", workspace, session="demo", session_store=store)
    assert first.trajectory[-1].success is True

    second_llm = ScriptedActionsLLM([stop])
    monkeypatch.setattr(cli.RealLLMClient, "from_environment", lambda: second_llm)
    second = cli.run_task("finish", workspace, session="demo", session_store=store)

    assert second.trajectory[0].action.type == "Stop"
    assert second.trajectory[0].success is True
