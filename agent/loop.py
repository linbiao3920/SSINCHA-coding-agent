"""Agent decision and execution loop."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Protocol

from .action import Action
from .llm import LLMClient, LLMError, parse_action_response
from .state import AgentState


MAX_STEPS = 30
REPEATED_ERROR_LIMIT = 3


@dataclass(frozen=True)
class ToolResult:
    observation: str
    success: bool


class ToolExecutor(Protocol):
    def execute(self, action: Action) -> ToolResult | dict[str, Any] | str:
        """Execute one already-parsed action locally."""


class AgentLoop:
    """Run the model/tool feedback loop with deterministic stopping rules."""

    def __init__(self, llm: LLMClient, tools: ToolExecutor, max_steps: int = MAX_STEPS):
        if max_steps <= 0 or max_steps > MAX_STEPS:
            raise ValueError(f"max_steps must be between 1 and {MAX_STEPS}")
        self._llm = llm
        self._tools = tools
        self._max_steps = max_steps

    def run(self, state: AgentState) -> AgentState:
        state.add_message("user", state.task)
        repeated_errors = 0
        last_error: str | None = None
        last_action: Action | None = None

        while state.step_count < self._max_steps:
            try:
                raw = self._llm.complete(state.history)
                action = parse_action_response(raw)
            except (LLMError, ValueError) as exc:
                state.record_error(str(exc), source="llm")
                state.add_message("tool", f"LLM error: {exc}")
                break

            state.add_message("assistant", raw)
            if action.type == "Stop":
                state.add_step(action, observation=action.params["reason"], success=True)
                break

            if last_action is not None and action == last_action:
                observation = "action blocked: repeated action"
                state.add_step(action, observation=observation, success=False)
                state.add_message("tool", observation)
                last_action = action
                continue

            try:
                result = self._tools.execute(action)
                observation, success = self._normalize_result(result)
            except Exception as exc:
                observation, success = f"tool error: {exc}", False

            state.add_step(action, observation=observation, success=success)
            state.add_message("tool", observation)
            last_action = action

            if not success:
                state.record_error(observation)
                if observation == last_error:
                    repeated_errors += 1
                else:
                    repeated_errors = 1
                    last_error = observation
                if repeated_errors >= REPEATED_ERROR_LIMIT:
                    state.add_message("tool", "stopped: repeated identical errors")
                    break
            else:
                repeated_errors = 0
                last_error = None

        return state

    @staticmethod
    def _normalize_result(result: ToolResult | dict[str, Any] | str) -> tuple[str, bool]:
        if isinstance(result, ToolResult):
            return result.observation, result.success
        if isinstance(result, str):
            return result, True
        if type(result) is dict:
            observation = result.get("observation", result.get("output", result.get("stderr", "")))
            success = result.get("success")
            if success is None and "exit_code" in result:
                success = result["exit_code"] == 0
            if type(observation) is not str or type(success) is not bool:
                raise ValueError("tool result must contain text and boolean success")
            return observation, success
        raise ValueError("unsupported tool result")
