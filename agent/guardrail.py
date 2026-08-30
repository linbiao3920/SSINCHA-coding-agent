"""Deterministic safety checks for agent actions."""

from __future__ import annotations

from dataclasses import dataclass
import re
import shlex
from pathlib import Path

from .action import Action
from .tools import Toolbox, PathBoundaryError


_INJECTION_RE = re.compile(r"[;&|`\n\r]")


@dataclass(frozen=True)
class GuardrailResult:
    allowed: bool
    reason: str = ""


class Guardrail:
    """Reject obviously unsafe actions before any tool is executed."""

    def __init__(self, workspace: str | Path):
        self._toolbox = Toolbox(workspace)

    @property
    def workspace(self) -> Path:
        return self._toolbox.workspace

    def inspect(self, action: Action) -> GuardrailResult:
        if not isinstance(action, Action):
            return GuardrailResult(False, "action must be an Action")
        if action.type in {"Read_File", "Write_File"}:
            try:
                self._toolbox.resolve_path(action.params["path"])
            except (KeyError, TypeError, PathBoundaryError) as exc:
                return GuardrailResult(False, f"path rejected: {exc}")
            return GuardrailResult(True)
        if action.type == "Execute_Test":
            command = action.params.get("cmd")
            if type(command) is not str or not command.strip():
                return GuardrailResult(False, "command must be a non-empty string")
            if _INJECTION_RE.search(command):
                return GuardrailResult(False, "command contains forbidden shell characters")
            try:
                parts = shlex.split(command)
            except ValueError:
                return GuardrailResult(False, "command quoting is invalid")
            if not parts or parts[0] not in {"pytest", "npm"}:
                return GuardrailResult(False, "only pytest and npm test are allowed")
            if parts[0] == "npm" and (len(parts) < 2 or parts[1] != "test"):
                return GuardrailResult(False, "npm command must start with npm test")
            return GuardrailResult(True)
        return GuardrailResult(True)
