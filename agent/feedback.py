"""Failure tracking and loop termination rules."""

from __future__ import annotations

from dataclasses import dataclass


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
