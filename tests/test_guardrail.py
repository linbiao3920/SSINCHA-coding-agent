from pathlib import Path

from agent.action import Action
from agent.guardrail import Guardrail


def test_guardrail_allows_valid_file_and_test_actions(tmp_path: Path):
    guardrail = Guardrail(tmp_path)

    assert guardrail.inspect(Action("Read_File", {"path": "src/app.py"})).allowed is True
    assert guardrail.inspect(Action("Write_File", {"path": "src/app.py", "content": "x"})).allowed is True
    assert guardrail.inspect(Action("Execute_Test", {"cmd": "pytest --version"})).allowed is True


def test_guardrail_blocks_escape_and_shell_injection(tmp_path: Path):
    guardrail = Guardrail(tmp_path)

    blocked_path = guardrail.inspect(Action("Read_File", {"path": "../secret.txt"}))
    blocked_cmd = guardrail.inspect(Action("Execute_Test", {"cmd": "pytest && whoami"}))
    blocked_test_path = guardrail.inspect(
        Action("Execute_Test", {"cmd": "pytest ../outside.py"})
    )

    assert blocked_path.allowed is False
    assert "path rejected" in blocked_path.reason
    assert blocked_cmd.allowed is False
    assert "forbidden shell characters" in blocked_cmd.reason
    assert blocked_test_path.allowed is False
    assert "escapes workspace" in blocked_test_path.reason
