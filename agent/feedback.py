"""Structured test feedback and loop termination rules."""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class StructuredError:
    """A compact, deterministic representation of a test failure."""

    category: str
    error_type: str
    message: str
    location: str | None = None

    def __post_init__(self) -> None:
        for name in ("category", "error_type", "message"):
            value = getattr(self, name)
            if type(value) is not str or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.location is not None and (
            type(self.location) is not str or not self.location.strip()
        ):
            raise ValueError("location must be a non-empty string or None")


_LOCATION_RE = re.compile(r'File "([^"]+)", line (\d+)')
_EXCEPTION_RE = re.compile(
    r"^\s*(?:E\s+)?([A-Za-z_]\w*(?:Error|Exception|Failure)):\s*(.*?)\s*$",
    re.MULTILINE,
)
_PYTEST_FAILURE_RE = re.compile(
    r"^\s*(?:FAILED|ERROR)\s+([^\s]+?)(?:::\S+)?\s*(?:-\s*(.*))?$",
    re.MULTILINE,
)


def _category_for(error_type: str, output: str) -> str:
    normalized = error_type.lower()
    if "syntax" in normalized:
        return "syntax"
    if "import" in normalized or "module not found" in normalized:
        return "import"
    if "timeout" in normalized or "timed out" in output.lower():
        return "timeout"
    if "assert" in normalized or "failure" in normalized:
        return "assertion"
    if "collection" in output.lower() or "file or directory not found" in output.lower():
        return "collection"
    return "test_failure"


def extract_test_error(output: str) -> StructuredError | None:
    """Extract one concise error from pytest output without using an LLM.

    The parser accepts both Python traceback lines and pytest's short summary.
    It intentionally returns only the final actionable exception so feedback
    stays bounded and stable across retries.
    """

    if type(output) is not str or not output.strip():
        return None

    location_match = _LOCATION_RE.search(output)
    location = None
    if location_match:
        location = f"{location_match.group(1)}:{location_match.group(2)}"

    exception_match = list(_EXCEPTION_RE.finditer(output))
    if exception_match:
        match = exception_match[-1]
        error_type = match.group(1)
        message = match.group(2).strip() or "test failed"
        return StructuredError(
            category=_category_for(error_type, output),
            error_type=error_type,
            message=message[:400],
            location=location,
        )

    summary_match = _PYTEST_FAILURE_RE.search(output)
    if summary_match:
        summary_message = (summary_match.group(2) or "pytest reported a failure").strip()
        return StructuredError(
            category=_category_for("TestFailure", output),
            error_type="TestFailure",
            message=summary_message[:400],
            location=summary_match.group(1),
        )

    lowered = output.lower()
    if "file or directory not found" in lowered:
        return StructuredError(
            category="collection",
            error_type="TestCollectionError",
            message="pytest could not find the requested test path",
            location=None,
        )
    if "timed out" in lowered or "timeout" in lowered:
        return StructuredError(
            category="timeout",
            error_type="TimeoutError",
            message="test command timed out",
            location=None,
        )
    return None


def format_structured_feedback(error: StructuredError) -> str:
    """Format deterministic feedback for the next model turn."""

    if not isinstance(error, StructuredError):
        raise ValueError("error must be a StructuredError")
    location = error.location or "unknown"
    return (
        "[structured-feedback]\n"
        f"category: {error.category}\n"
        f"error_type: {error.error_type}\n"
        f"location: {location}\n"
        f"message: {error.message}\n"
        "Use this objective test feedback to choose the next action."
    )


REPEATED_ERROR_LIMIT = 3


@dataclass
class FeedbackTracker:
    """Detect consecutive identical tool failures without parsing stack traces."""

    limit: int = REPEATED_ERROR_LIMIT
    _last_error: str | None = None
    _count: int = 0

    def __post_init__(self) -> None:
        if type(self.limit) is not int or self.limit <= 0:
            raise ValueError("limit must be a positive integer")

    @property
    def count(self) -> int:
        return self._count

    def observe(self, *, success: bool, observation: str) -> bool:
        """Record one result and return whether the loop must stop."""
        if type(success) is not bool or type(observation) is not str:
            raise ValueError("feedback input types are invalid")
        if success:
            self.reset()
            return False
        if observation == self._last_error:
            self._count += 1
        else:
            self._last_error = observation
            self._count = 1
        return self._count >= self.limit

    def reset(self) -> None:
        self._last_error = None
        self._count = 0
