"""Deterministic safety checks for agent actions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .action import Action
from .tools import Toolbox, PathBoundaryError, ToolError


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
            try:
                self._toolbox.validate_test_command(command)
            except ToolError as exc:
                return GuardrailResult(False, str(exc))
            return GuardrailResult(True)
        return GuardrailResult(True)
