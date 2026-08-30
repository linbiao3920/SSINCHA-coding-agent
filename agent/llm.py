"""LLM client boundary and response parsing."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Protocol, Sequence

from .action import Action, ActionValidationError
from .state import Message


MAX_RESPONSE_CHARS = 32_768


class LLMError(RuntimeError):
    """Raised when the provider cannot produce a usable response."""


class LLMClient(Protocol):
    def complete(self, messages: Sequence[Message]) -> str:
        """Return the model's next action response as text."""


def _build_responses_request(
    messages: Sequence[Message],
) -> tuple[str | None, list[dict[str, object]]]:
    """Split instructions from message history for the Responses API."""

    instructions: list[str] = []
    input_messages: list[dict[str, object]] = []
    for message in messages:
        if message.role in {"system", "developer"}:
            instructions.append(message.content)
            continue
        role = message.role
        content = message.content
        if message.role == "tool":
            role = "user"
            content = f"[tool]\n{message.content}"
        input_messages.append({"type": "message", "role": role, "content": content})
    instructions_text = "\n\n".join(instructions).strip() or None
    return instructions_text, input_messages


def parse_action_response(raw: str) -> Action:
    """Parse exactly one JSON action from a model response.

    A fenced JSON object is accepted for practical provider compatibility, but
    arbitrary prose or multiple JSON objects are rejected.
    """
    if type(raw) is not str or not raw.strip():
        raise ActionValidationError("model response must be non-empty text")
    if len(raw) > MAX_RESPONSE_CHARS:
        raise ActionValidationError("model response exceeds the size limit")

    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) < 3 or not lines[-1].strip().startswith("```"):
            raise ActionValidationError("unterminated JSON code fence")
        text = "\n".join(lines[1:-1]).strip()
        if text.lower().startswith("json\n"):
            text = text[5:].lstrip()

    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ActionValidationError("model response must be one JSON object") from exc
    return Action.from_dict(value)


@dataclass
class RealLLMClient:
    """DeepSeek client with environment-only credential loading."""

    api_key: str
    model: str = "deepseek-v4-pro"
    base_url: str = "https://api.deepseek.com"
    timeout: float = 60.0

    def __post_init__(self) -> None:
        if type(self.api_key) is not str or not self.api_key.strip():
            raise ValueError("api_key must be a non-empty string")
        if type(self.model) is not str or not self.model.strip():
            raise ValueError("model must be a non-empty string")
        if type(self.base_url) is not str or not self.base_url.strip():
            raise ValueError("base_url must be a non-empty string")
        if type(self.timeout) not in (int, float) or self.timeout <= 0:
            raise ValueError("timeout must be positive")

    @classmethod
    def from_environment(cls) -> "RealLLMClient":
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise LLMError("set DEEPSEEK_API_KEY before running")
        return cls(
            api_key=api_key,
            model=os.getenv("DEEPSEEK_MODEL") or "deepseek-v4-pro",
        )

    def complete(self, messages: Sequence[Message]) -> str:
        if not messages:
            raise LLMError("at least one message is required")
        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
            )
            instructions, input_messages = _build_responses_request(messages)
            response = client.responses.create(
                model=self.model,
                instructions=instructions,
                input=input_messages,
                temperature=0,
                max_output_tokens=1024,
            )
            content = response.output_text
        except Exception as exc:
            raise LLMError(f"LLM request failed: {type(exc).__name__}: {exc}") from exc
        if type(content) is not str or not content.strip():
            raise LLMError("LLM returned an empty response")
        if len(content) > MAX_RESPONSE_CHARS:
            raise LLMError("LLM response exceeds the size limit")
        return content

    def __repr__(self) -> str:
        return f"RealLLMClient(model={self.model!r}, base_url={self.base_url!r})"
