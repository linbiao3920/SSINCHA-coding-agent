"""Agent decision and execution loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .action import Action
from .completion import CompletionGate
from .guardrail import Guardrail
from .feedback import FeedbackTracker
from .llm import LLMClient, LLMError, parse_action_response
from .state import AgentState


MAX_STEPS = 30


SYSTEM_PROMPT = """You are SSINCHA, a coding agent that can work only through JSON actions.

Return exactly one JSON object and no prose. Valid actions:
- {"type":"Read_File","params":{"path":"relative/path.py"}}
- {"type":"Write_File","params":{"path":"relative/path.py","content":"full file content"}}
- {"type":"Execute_Test","params":{"cmd":"pytest"}}
- {"type":"Stop","params":{"reason":"short reason"}}

Rules:
- Use workspace-relative paths only.
- Read files before changing them.
- Prefer running tests after changes.
- If tests fail, use the tool output to choose a different next action.
- If a new user message follows an earlier Stop action, treat it as a continuation of that session.
- After a successful Write_File, run Execute_Test successfully before returning Stop.
- If Stop is blocked by completion validation, follow the safety feedback and run a test.
- Stop only when the requested task is complete or safely blocked.
"""
@dataclass(frozen=True)
class ToolResult:
    observation: str
    success: bool


class ToolExecutor(Protocol):
    def execute(self, action: Action) -> ToolResult | dict[str, Any] | str:
        """Execute one already-parsed action locally."""


class AgentLoop:
    """Run the model/tool feedback loop with deterministic stopping rules."""

    def __init__(
        self,
        llm: LLMClient,
        tools: ToolExecutor,
        guardrail: Guardrail | None = None,
        max_steps: int = MAX_STEPS,
        completion_gate: CompletionGate | None = None,
    ):
        if max_steps <= 0 or max_steps > MAX_STEPS:
            raise ValueError(f"max_steps must be between 1 and {MAX_STEPS}")
        self._llm = llm
        self._tools = tools
        self._guardrail = guardrail
        self._max_steps = max_steps
        self._completion_gate = completion_gate

    def run(self, state: AgentState) -> AgentState:
        if not state.history:
            state.add_message("system", SYSTEM_PROMPT)
            state.add_message("user", state.task)
        feedback = FeedbackTracker()
        completion = self._completion_gate or CompletionGate()
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
                decision = completion.inspect_stop()
                if not decision.allowed:
                    state.add_step(action, observation=decision.reason, success=False)
                    state.add_message("tool", decision.reason)
                    state.record_error(decision.reason, source="completion")
                    last_action = action
                    continue
                state.add_step(action, observation=action.params["reason"], success=True)
                break

            if self._guardrail is not None:
                decision = self._guardrail.inspect(action)
                if not decision.allowed:
                    observation = f"guardrail blocked: {decision.reason}"
                    state.add_step(action, observation=observation, success=False)
                    state.add_message("tool", observation)
                    state.record_error(observation, source="guardrail")
                    continue

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
            completion.observe(action, success=success)

            if not success:
                state.record_error(observation)
                if feedback.observe(success=False, observation=observation):
                    state.add_message("tool", "stopped: repeated identical errors")
                    break
            else:
                feedback.observe(success=True, observation=observation)

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
