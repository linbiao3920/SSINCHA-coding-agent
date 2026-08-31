"""Conversation history and execution state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .action import Action


MessageRole = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class Message:
    role: MessageRole
    content: str

    def __post_init__(self) -> None:
        if self.role not in {"system", "user", "assistant", "tool"}:
            raise ValueError(f"unknown message role: {self.role!r}")
        if type(self.content) is not str:
            raise ValueError("message content must be a string")


@dataclass(frozen=True)
class ErrorRecord:
    message: str
    source: str = "tool"
    category: str | None = None
    error_type: str | None = None
    location: str | None = None

    def __post_init__(self) -> None:
        if type(self.message) is not str or not self.message:
            raise ValueError("error message must be non-empty")
        if type(self.source) is not str or not self.source:
            raise ValueError("error source must be non-empty")
        for name in ("category", "error_type", "location"):
            value = getattr(self, name)
            if value is not None and (type(value) is not str or not value.strip()):
                raise ValueError(f"error {name} must be a non-empty string or None")


@dataclass(frozen=True)
class ExecutionStep:
    action: Action
    observation: str = ""
    success: bool | None = None

    def __post_init__(self) -> None:
        if type(self.observation) is not str:
            raise ValueError("observation must be a string")
        if self.success is not None and type(self.success) is not bool:
            raise ValueError("success must be a boolean or None")


@dataclass
class AgentState:
    """Mutable state for one coding task run."""

    task: str
    history: list[Message] = field(default_factory=list)
    trajectory: list[ExecutionStep] = field(default_factory=list)
    error_logs: list[ErrorRecord] = field(default_factory=list)
    step_count: int = 0

    def __post_init__(self) -> None:
        if type(self.task) is not str or not self.task.strip():
            raise ValueError("task must be a non-empty string")
        if type(self.step_count) is not int or self.step_count < 0:
            raise ValueError("step_count must be a non-negative integer")

    def add_message(self, role: MessageRole, content: str) -> None:
        self.history.append(Message(role=role, content=content))

    def add_step(
        self,
        action: Action,
        observation: str = "",
        success: bool | None = None,
    ) -> None:
        self.trajectory.append(
            ExecutionStep(action=action, observation=observation, success=success)
        )
        self.step_count += 1

    def record_error(
        self,
        message: str,
        source: str = "tool",
        *,
        category: str | None = None,
        error_type: str | None = None,
        location: str | None = None,
    ) -> None:
        self.error_logs.append(
            ErrorRecord(
                message=message,
                source=source,
                category=category,
                error_type=error_type,
                location=location,
            )
        )
