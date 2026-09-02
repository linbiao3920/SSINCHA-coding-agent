from pathlib import Path

from agent.action import Action
from agent.tools import Toolbox


def test_file_tools_read_and_write_inside_workspace(tmp_path: Path):
    toolbox = Toolbox(tmp_path)

    written = toolbox.execute(Action("Write_File", {"path": "src/app.py", "content": "print(1)"}))
    read = toolbox.execute(Action("Read_File", {"path": "src/app.py"}))

    assert written["success"] is True
    assert read["success"] is True
    assert read["observation"] == "print(1)"


def test_file_tools_block_escape_and_symlink_escape(tmp_path: Path):
    toolbox = Toolbox(tmp_path)
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    escaped = toolbox.execute(Action("Read_File", {"path": "../outside.txt"}))
    assert escaped["success"] is False
    assert "escapes workspace" in escaped["observation"]

    link = tmp_path / "link.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        return
    linked = toolbox.execute(Action("Read_File", {"path": "link.txt"}))
    assert linked["success"] is False
    assert "escapes workspace" in linked["observation"]


def test_test_command_is_restricted_and_runs_in_workspace(tmp_path: Path):
    toolbox = Toolbox(tmp_path)
    result = toolbox.execute(Action("Execute_Test", {"cmd": "pytest --version"}))
    assert result["exit_code"] == 0

    for command in ("python exploit.py", "pytest; whoami", "pytest && whoami", "npm install"):
        rejected = toolbox.execute(Action("Execute_Test", {"cmd": command}))
        assert rejected["success"] is False
        assert rejected["exit_code"] == -1


def test_test_command_rejects_workspace_escape_without_starting_pytest(tmp_path: Path):
    toolbox = Toolbox(tmp_path)

    rejected = toolbox.execute(Action("Execute_Test", {"cmd": "pytest ../outside.py"}))

    assert rejected["success"] is False
    assert rejected["exit_code"] == -1
    assert "test path rejected: path escapes workspace" in rejected["observation"]
