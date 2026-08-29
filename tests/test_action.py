import pytest

from agent.action import Action, ActionValidationError


def test_valid_actions_round_trip_as_json():
    actions = [
        Action("Read_File", {"path": "main.py"}),
        Action("Write_File", {"path": "main.py", "content": "print(1)"}),
        Action("Execute_Test", {"cmd": "pytest"}),
        Action("Stop", {"reason": "task complete"}),
    ]

    for action in actions:
        assert Action.from_json(action.to_json()) == action


def test_unknown_action_is_rejected():
    with pytest.raises(ActionValidationError):
        Action("Delete_Database", {})


def test_action_parameters_are_checked_by_type():
    with pytest.raises(ActionValidationError):
        Action("Read_File", {"path": ""})
    with pytest.raises(ActionValidationError):
        Action("Write_File", {"path": "a.py", "content": 123})
    with pytest.raises(ActionValidationError):
        Action("Execute_Test", {"command": "pytest"})
    with pytest.raises(ActionValidationError):
        Action("Stop", {})


def test_from_json_rejects_malformed_payload():
    with pytest.raises(ActionValidationError):
        Action.from_json("not json")

