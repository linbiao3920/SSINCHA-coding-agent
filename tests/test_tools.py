import agent.tools as tools_module
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


def test_npm_test_requires_an_approved_local_test_runner(tmp_path: Path):
    (tmp_path / "package.json").write_text(
        '{"scripts": {"test": "vitest run"}}', encoding="utf-8"
    )
    toolbox = Toolbox(tmp_path)

    allowed = toolbox.validate_test_command("npm test")

    assert allowed == ["npm", "test"]


def test_npm_test_rejects_shell_and_command_execution_scripts(tmp_path: Path):
    toolbox = Toolbox(tmp_path)
    cases = [
        '{"scripts": {"test": "jest && whoami"}}',
        '{"scripts": {"test": "node -e \\\"process.exit(0)\\\""}}',
        '{"scripts": {"test": "npm run verify"}}',
    ]

    for package in cases:
        (tmp_path / "package.json").write_text(package, encoding="utf-8")
        rejected = toolbox.execute(Action("Execute_Test", {"cmd": "npm test"}))
        assert rejected["success"] is False
        assert rejected["exit_code"] == -1
        assert "npm scripts.test" in rejected["observation"]


def test_npm_test_rejects_missing_or_invalid_manifest_script(tmp_path: Path):
    toolbox = Toolbox(tmp_path)
    for package in ('{}', '{"scripts": {"test": ""}}', '{not json'):
        (tmp_path / "package.json").write_text(package, encoding="utf-8")
        rejected = toolbox.execute(Action("Execute_Test", {"cmd": "npm test"}))
        assert rejected["success"] is False
        assert rejected["exit_code"] == -1


def test_npm_test_bypasses_lifecycle_hooks_and_runs_validated_runner_directly(
    tmp_path: Path, monkeypatch
):
    (tmp_path / "package.json").write_text(
        '{"scripts": {"pretest": "python write_marker.py", '
        '"test": "node --test tests/example.js", '
        '"posttest": "python write_marker.py"}}',
        encoding="utf-8",
    )
    calls = []

    def fake_run(parts, **kwargs):
        calls.append((parts, kwargs))
        return type("Result", (), {"stdout": "ok", "stderr": "", "returncode": 0})()

    monkeypatch.setattr(tools_module.subprocess, "run", fake_run)
    result = Toolbox(tmp_path).execute(Action("Execute_Test", {"cmd": "npm test"}))

    assert result["success"] is True
    assert calls[0][0] == ["node", "--test", "tests/example.js"]
    assert str(tmp_path / "node_modules" / ".bin") in calls[0][1]["env"]["PATH"]


def test_npm_test_rejects_script_path_escape(tmp_path: Path):
    (tmp_path / "package.json").write_text(
        '{"scripts": {"test": "node --test ../outside.js"}}', encoding="utf-8"
    )

    rejected = Toolbox(tmp_path).execute(Action("Execute_Test", {"cmd": "npm test"}))

    assert rejected["success"] is False
    assert rejected["exit_code"] == -1
    assert "npm test path rejected" in rejected["observation"]
