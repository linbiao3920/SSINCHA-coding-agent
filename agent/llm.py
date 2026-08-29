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
    """OpenAI-compatible client with environment-only credential loading."""

    api_key: str
    model: str = "gpt-4o-mini"
    base_url: str | None = None
    timeout: float = 60.0

    def __post_init__(self) -> None:
        if type(self.api_key) is not str or not self.api_key.strip():
            raise ValueError("api_key must be a non-empty string")
        if type(self.model) is not str or not self.model.strip():
            raise ValueError("model must be a non-empty string")
        if self.base_url is not None and (
            type(self.base_url) is not str or not self.base_url.strip()
        ):
            raise ValueError("base_url must be a non-empty string")
        if type(self.timeout) not in (int, float) or self.timeout <= 0:
            raise ValueError("timeout must be positive")

    @classmethod
    def from_environment(cls) -> "RealLLMClient":
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
        if not api_key:
            raise LLMError("set OPENAI_API_KEY or LLM_API_KEY before running")
        return cls(
            api_key=api_key,
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            base_url=os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL"),
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
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": message.role, "content": message.content} for message in messages],
                temperature=0,
            )
            content = response.choices[0].message.content
        except Exception as exc:
            raise LLMError("LLM request failed") from exc
        if type(content) is not str or not content.strip():
            raise LLMError("LLM returned an empty response")
        if len(content) > MAX_RESPONSE_CHARS:
            raise LLMError("LLM response exceeds the size limit")
        return content

    def __repr__(self) -> str:
        return f"RealLLMClient(model={self.model!r}, base_url={self.base_url!r})"
