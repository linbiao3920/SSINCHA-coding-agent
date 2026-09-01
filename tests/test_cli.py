from pathlib import Path

import pytest

from agent.action import Action
from agent import cli
from agent.cli import (
    EXIT_INCOMPLETE,
    EXIT_SUCCESS,
    build_parser,
    exit_code_for_state,
)
from agent.state import AgentState
from agent.session import SessionStore
from agent.test_target import TestTargetSnapshot


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


def test_exit_code_requires_a_final_successful_stop():
    completed = AgentState("done")
    completed.add_step(Action("Stop", {"reason": "done"}), success=True)
    incomplete = AgentState("failed")
    incomplete.record_error("LLM request failed", source="llm")
    exhausted = AgentState("keep working")
    exhausted.add_step(Action("Read_File", {"path": "main.py"}), success=True)

    assert exit_code_for_state(completed) == EXIT_SUCCESS
    assert exit_code_for_state(incomplete) == EXIT_INCOMPLETE
    assert exit_code_for_state(exhausted) == EXIT_INCOMPLETE


def test_main_returns_nonzero_when_loop_ends_with_llm_error(monkeypatch, tmp_path: Path):
    state = AgentState("fix the bug")
    state.record_error("LLM request failed", source="llm")
    monkeypatch.setattr(cli, "run_task", lambda *_args, **_kwargs: state)

    assert cli.main(["fix the bug", "--workspace", str(tmp_path)]) == EXIT_INCOMPLETE


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


class FiniteActionsLLM:
    """Return malformed output after scripted actions to end a partial run."""

    def __init__(self, actions):
        self.actions = iter(actions)

    def complete(self, _messages):
        try:
            return next(self.actions).to_json()
        except StopIteration:
            return "not JSON"


def test_session_restores_a_verified_completion_gate(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "test_main.py").write_text(
        "def test_main(): assert True\n", encoding="utf-8"
    )
    store = SessionStore(tmp_path / "sessions")
    write = Action("Write_File", {"path": "main.py", "content": "value = 1\n"})
    test = Action("Execute_Test", {"cmd": "pytest test_main.py"})
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


def test_session_restores_pending_test_targets(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "test_greet.py").write_text(
        "def test_greet(): assert True\n", encoding="utf-8"
    )
    (workspace / "test_blackjack.py").write_text(
        "def test_blackjack(): assert True\n", encoding="utf-8"
    )
    store = SessionStore(tmp_path / "sessions")
    write = Action("Write_File", {"path": "greet.py", "content": "print('hello')\n"})
    stop = Action("Stop", {"reason": "done"})

    monkeypatch.setattr(
        cli.RealLLMClient,
        "from_environment",
        lambda: FiniteActionsLLM([write, stop]),
    )
    first = cli.run_task("write greet", workspace, session="demo", session_store=store)
    assert first.trajectory[-1].success is False
    assert store.load_data("demo", workspace).test_targets is not None

    unrelated = Action("Execute_Test", {"cmd": "pytest test_blackjack.py"})
    focused = Action("Execute_Test", {"cmd": "pytest test_greet.py"})
    monkeypatch.setattr(
        cli.RealLLMClient,
        "from_environment",
        lambda: ScriptedActionsLLM([unrelated, focused, stop]),
    )
    second = cli.run_task("verify greet", workspace, session="demo", session_store=store)

    assert second.trajectory[0].success is False
    assert second.error_logs[0].source == "test_binding"
    assert second.trajectory[-1].action.type == "Stop"
    assert second.trajectory[-1].success is True
    assert store.load_data("demo", workspace).test_targets == TestTargetSnapshot(())


def test_reset_session_discards_pending_test_targets(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    store = SessionStore(tmp_path / "sessions")
    write = Action("Write_File", {"path": "main.py", "content": "value = 1\n"})
    stop = Action("Stop", {"reason": "done"})

    monkeypatch.setattr(
        cli.RealLLMClient,
        "from_environment",
        lambda: FiniteActionsLLM([write, stop]),
    )
    cli.run_task("write main", workspace, session="demo", session_store=store)
    assert store.load_data("demo", workspace).test_targets == TestTargetSnapshot(
        ("main.py",)
    )

    monkeypatch.setattr(
        cli.RealLLMClient,
        "from_environment",
        lambda: ScriptedActionsLLM([stop]),
    )
    reset = cli.run_task(
        "start over",
        workspace,
        session="demo",
        reset_session=True,
        session_store=store,
    )

    assert reset.trajectory[-1].success is True
    assert store.load_data("demo", workspace).test_targets == TestTargetSnapshot(())
