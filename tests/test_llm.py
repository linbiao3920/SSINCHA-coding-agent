import pytest

from agent.action import ActionValidationError
from agent.llm import parse_action_response


def test_parse_action_response_accepts_json_and_fenced_json():
    expected = {"type": "Read_File", "params": {"path": "main.py"}}
    assert parse_action_response('{"type":"Read_File","params":{"path":"main.py"}}').to_dict() == expected
    assert parse_action_response('```json\n{"type":"Stop","params":{"reason":"done"}}\n```').type == "Stop"


def test_parse_action_response_rejects_prose_and_multiple_objects():
    with pytest.raises(ActionValidationError):
        parse_action_response("I will read the file: {\"type\":\"Read_File\",\"params\":{\"path\":\"x\"}}")
    with pytest.raises(ActionValidationError):
        parse_action_response('{"type":"Stop","params":{"reason":"one"}} {"type":"Stop","params":{"reason":"two"}}')

