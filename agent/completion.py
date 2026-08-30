"""Evidence requirements for accepting an agent Stop action."""

from __future__ import annotations

from dataclasses import dataclass

from .action import Action


@dataclass(frozen=True)
class CompletionDecision:
    allowed: bool
    reason: str = ""


@dataclass(frozen=True)
class CompletionSnapshot:
    requires_test: bool
    latest_test_success: bool | None


class CompletionGate:
    """Require a passing test after the latest successful file write."""

    def __init__(self) -> None:
        self._write_requires_test = False
        self._latest_test_success: bool | None = None

    @property
    def requires_test(self) -> bool:
        return self._write_requires_test

    @property
    def latest_test_success(self) -> bool | None:
        return self._latest_test_success

    def snapshot(self) -> CompletionSnapshot:
        return CompletionSnapshot(
            requires_test=self._write_requires_test,
            latest_test_success=self._latest_test_success,
        )

    @classmethod
    def from_snapshot(cls, snapshot: CompletionSnapshot | None) -> "CompletionGate":
        gate = cls()
        if snapshot is not None:
            if type(snapshot) is not CompletionSnapshot:
                raise ValueError("completion snapshot has an invalid type")
            if type(snapshot.requires_test) is not bool:
                raise ValueError("completion snapshot requires_test must be boolean")
            if snapshot.latest_test_success not in {None, True, False}:
                raise ValueError("completion snapshot test result is invalid")
            gate._write_requires_test = snapshot.requires_test
            gate._latest_test_success = snapshot.latest_test_success
        return gate

    def observe(self, action: Action, *, success: bool) -> None:
        if not isinstance(action, Action) or type(success) is not bool:
            raise ValueError("completion evidence input types are invalid")
        if action.type == "Write_File" and success:
            self._write_requires_test = True
            self._latest_test_success = None
        elif action.type == "Execute_Test" and self._write_requires_test:
            self._latest_test_success = success

    def inspect_stop(self) -> CompletionDecision:
        if not self._write_requires_test:
            return CompletionDecision(True)
        if self._latest_test_success is True:
            return CompletionDecision(True)
        if self._latest_test_success is False:
            return CompletionDecision(
                False,
                "stop blocked: latest test after the latest write did not pass",
            )
        return CompletionDecision(
            False,
            "stop blocked: run tests after the latest successful write",
        )
