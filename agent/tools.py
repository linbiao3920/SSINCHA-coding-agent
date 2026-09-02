"""Local file and restricted test execution tools."""

from __future__ import annotations

from dataclasses import dataclass
import re
import shlex
from pathlib import Path
import subprocess
from typing import Any

from .action import Action


@dataclass(frozen=True)
class ToolOutput:
    """Normalized result returned by a local tool."""

    observation: str
    success: bool
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "observation": self.observation,
            "success": self.success,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


class ToolError(ValueError):
    """Raised when an action is invalid for local execution."""


class PathBoundaryError(ToolError):
    """Raised when a path leaves the configured workspace."""


_INJECTION_RE = re.compile(r"[;&|`\n\r]")
_ALLOWED_TEST_BASES = frozenset({"pytest", "npm"})


class Toolbox:
    """Execute the small, deliberately restricted tool set used by the agent."""

    def __init__(self, workspace: str | Path, timeout_seconds: int = 60):
        self.workspace = Path(workspace).resolve()
        if not self.workspace.is_dir():
            raise ValueError("workspace must be an existing directory")
        if type(timeout_seconds) is not int or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a positive integer")
        self.timeout_seconds = timeout_seconds

    def execute(self, action: Action) -> dict[str, Any]:
        if not isinstance(action, Action):
            raise ToolError("toolbox accepts only Action values")
        if action.type == "Read_File":
            return self.read_file(action.params["path"]).as_dict()
        if action.type == "Write_File":
            return self.write_file(action.params["path"], action.params["content"]).as_dict()
        if action.type == "Execute_Test":
            return self.execute_test(action.params["cmd"]).as_dict()
        raise ToolError(f"action cannot be executed by toolbox: {action.type}")

    def resolve_path(self, relative_path: str) -> Path:
        """Resolve a workspace-relative path without allowing boundary escape."""
        if type(relative_path) is not str or not relative_path.strip():
            raise PathBoundaryError("path must be a non-empty string")
        if "\x00" in relative_path:
            raise PathBoundaryError("path must not contain NUL")
        candidate = (self.workspace / relative_path).resolve()
        try:
            candidate.relative_to(self.workspace)
        except ValueError as exc:
            raise PathBoundaryError("path escapes workspace") from exc
        return candidate

    def read_file(self, relative_path: str) -> ToolOutput:
        try:
            target = self.resolve_path(relative_path)
            if not target.exists():
                return ToolOutput(f"file not found: {relative_path}", False)
            if not target.is_file():
                return ToolOutput(f"not a file: {relative_path}", False)
            content = target.read_text(encoding="utf-8")
            return ToolOutput(content, True, stdout=content)
        except (OSError, UnicodeError, ToolError) as exc:
            return ToolOutput(f"read failed: {exc}", False)

    def write_file(self, relative_path: str, content: str) -> ToolOutput:
        if type(content) is not str:
            return ToolOutput("content must be a string", False)
        try:
            target = self.resolve_path(relative_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return ToolOutput(f"wrote {len(content)} characters to {relative_path}", True)
        except (OSError, UnicodeError, ToolError) as exc:
            return ToolOutput(f"write failed: {exc}", False)

    def execute_test(self, command: str) -> ToolOutput:
        try:
            parts = self.validate_test_command(command)
        except ToolError as exc:
            return ToolOutput(f"command rejected: {exc}", False, exit_code=-1, stderr=str(exc))

        try:
            result = subprocess.run(
                parts,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ToolOutput("test command timed out", False, exit_code=-1, stderr="timeout")
        except OSError as exc:
            return ToolOutput(f"test command failed to start: {exc}", False, exit_code=-1, stderr=str(exc))

        stdout = result.stdout or ""
        stderr = result.stderr or ""
        observation = f"exit_code={result.returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}"
        return ToolOutput(observation, result.returncode == 0, result.returncode, stdout, stderr)

    def validate_test_command(self, command: str) -> list[str]:
        """Validate a test command and keep all path arguments in workspace."""
        if type(command) is not str or not command.strip():
            raise ToolError("command must be a non-empty string")
        if _INJECTION_RE.search(command):
            raise ToolError("command contains forbidden shell characters")
        try:
            parts = shlex.split(command)
        except ValueError as exc:
            raise ToolError("command quoting is invalid") from exc
        if not parts or parts[0] not in _ALLOWED_TEST_BASES:
            raise ToolError("only pytest and npm test are allowed")
        if parts[0] == "npm" and (len(parts) < 2 or parts[1] != "test"):
            raise ToolError("npm command must start with npm test")
        for target in self._test_path_arguments(parts):
            try:
                self.resolve_path(target)
            except PathBoundaryError as exc:
                raise ToolError(f"test path rejected: {exc}") from exc
        return parts

    @staticmethod
    def _test_path_arguments(parts: list[str]) -> list[str]:
        """Return path-like positional values and long-option values.

        Pytest accepts paths both directly and through options such as
        ``--rootdir=...``.  Every path-like value is checked before spawning a
        process so changing the process cwd cannot be used to escape workspace.
        """
        targets: list[str] = []
        for part in parts[1:]:
            value = part.split("=", 1)[1] if part.startswith("--") and "=" in part else part
            value = value.split("::", 1)[0]
            if Toolbox._looks_like_test_path(value):
                targets.append(value)
        return targets

    @staticmethod
    def _looks_like_test_path(value: str) -> bool:
        return (
            bool(value)
            and (
                Path(value).is_absolute()
                or "/" in value
                or "\\" in value
                or value in {".", ".."}
                or value.startswith(".")
                or value.lower().endswith((".py", ".js", ".ts", ".tsx"))
            )
        )
