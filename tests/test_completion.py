import pytest

from agent.action import Action
from agent.completion import CompletionGate


def test_gate_allows_read_only_stop():
    gate = CompletionGate()

    assert gate.inspect_stop().allowed is True


def test_gate_requires_test_after_successful_write():
    gate = CompletionGate()
    write = Action("Write_File", {"path": "main.py", "content": "x"})
    test = Action("Execute_Test", {"cmd": "pytest"})

    gate.observe(write, success=True)
    assert gate.inspect_stop().allowed is False
    gate.observe(test, success=False)
    assert gate.inspect_stop().allowed is False
    gate.observe(test, success=True)
    assert gate.inspect_stop().allowed is True


def test_new_write_invalidates_previous_test():
    gate = CompletionGate()
    write = Action("Write_File", {"path": "main.py", "content": "x"})
    test = Action("Execute_Test", {"cmd": "pytest"})

    gate.observe(write, success=True)
    gate.observe(test, success=True)
    assert gate.inspect_stop().allowed is True
    gate.observe(write, success=True)
    decision = gate.inspect_stop()
    assert decision.allowed is False
    assert "after the latest successful write" in decision.reason


@pytest.mark.parametrize("success", [True, False])
def test_gate_rejects_invalid_action_result_types(success):
    gate = CompletionGate()

    with pytest.raises(ValueError):
        gate.observe("not an action", success=success)


def test_gate_snapshot_restores_pending_validation():
    gate = CompletionGate()
    write = Action("Write_File", {"path": "main.py", "content": "x"})
    test = Action("Execute_Test", {"cmd": "pytest"})

    gate.observe(write, success=True)
    restored = CompletionGate.from_snapshot(gate.snapshot())

    assert restored.inspect_stop().allowed is False
    restored.observe(test, success=True)
    assert restored.inspect_stop().allowed is True
