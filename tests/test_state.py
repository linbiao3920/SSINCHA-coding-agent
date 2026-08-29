import pytest

from agent.action import Action
from agent.state import AgentState, ErrorRecord, Message


def test_initial_state_is_empty_but_has_task():
    state = AgentState(task="fix the failing test")

    assert state.task == "fix the failing test"
    assert state.history == []
    assert state.trajectory == []
    assert state.error_logs == []
    assert state.step_count == 0


def test_state_records_messages_steps_and_errors():
    state = AgentState(task="fix the failing test")
    action = Action("Read_File", {"path": "test_app.py"})

    state.add_message("user", state.task)
    state.add_step(action, observation="assert False", success=True)
    state.record_error("test failed", source="pytest")

    assert state.history == [Message("user", "fix the failing test")]
    assert state.trajectory[0].action == action
    assert state.trajectory[0].observation == "assert False"
    assert state.trajectory[0].success is True
    assert state.error_logs == [ErrorRecord("test failed", "pytest")]
    assert state.step_count == 1


def test_invalid_state_inputs_are_rejected():
    with pytest.raises(ValueError):
        AgentState(task="")
    with pytest.raises(ValueError):
        Message(role="developer", content="x")
