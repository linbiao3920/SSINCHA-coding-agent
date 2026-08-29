"""Structured actions proposed by the language model."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Literal


ActionType = Literal["Read_File", "Write_File", "Execute_Test", "Stop"]
_ACTION_TYPES = frozenset({"Read_File", "Write_File", "Execute_Test", "Stop"})


class ActionValidationError(ValueError):
    """Raised when a model-proposed action does not match the wire contract."""


def _require_text(params: dict[str, Any], name: str) -> None:
    value = params.get(name)
    if type(value) is not str or not value.strip():
        raise ActionValidationError(f"{name} must be a non-empty string")


@dataclass(frozen=True)
class Action:
    """One validated action selected by the agent."""

    type: ActionType
    params: dict[str, Any]

    def __post_init__(self) -> None:
        if type(self.type) is not str or self.type not in _ACTION_TYPES:
            raise ActionValidationError(f"unknown action type: {self.type!r}")
        if type(self.params) is not dict:
            raise ActionValidationError("params must be an object")

        params = dict(self.params)
        if self.type == "Read_File":
            _require_text(params, "path")
        elif self.type == "Write_File":
            _require_text(params, "path")
            if type(params.get("content")) is not str:
                raise ActionValidationError("content must be a string")
        elif self.type == "Execute_Test":
            _require_text(params, "cmd")
        else:
            _require_text(params, "reason")

        object.__setattr__(self, "params", params)

    @classmethod
    def from_dict(cls, value: object) -> "Action":
        if type(value) is not dict:
            raise ActionValidationError("action must be an object")
        return cls(type=value.get("type"), params=value.get("params", {}))

    @classmethod
    def from_json(cls, value: str) -> "Action":
        if type(value) is not str:
            raise ActionValidationError("JSON action must be a string")
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ActionValidationError("action is not valid JSON") from exc
        return cls.from_dict(decoded)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "params": dict(self.params)}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)
