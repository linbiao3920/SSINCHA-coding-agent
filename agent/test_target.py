"""Deterministic binding between modified files and focused test targets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import shlex


_NPM_TEST_SUFFIXES = frozenset({".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"})
_NPM_TEST_FILENAMES = frozenset({"package.json", "package-lock.json", "npm-shrinkwrap.json"})


@dataclass(frozen=True)
class TargetDecision:
    allowed: bool
    reason: str = ""


@dataclass(frozen=True)
class TestTargetSnapshot:
    """Serializable record of files awaiting a focused test."""

    __test__ = False

    modified_paths: tuple[str, ...]


class TestTargetBinder:
    """Require test commands to name tests relevant to modified files."""

    __test__ = False

    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace).resolve()
        if not self.workspace.is_dir():
            raise ValueError("workspace must be an existing directory")
        self._modified: set[str] = set()

    @property
    def modified_paths(self) -> frozenset[str]:
        return frozenset(self._modified)

    def snapshot(self) -> TestTargetSnapshot:
        """Return canonical workspace-relative paths in a stable order."""
        return TestTargetSnapshot(tuple(sorted(self._modified)))

    @classmethod
    def from_snapshot(
        cls,
        workspace: str | Path,
        snapshot: TestTargetSnapshot | None,
    ) -> "TestTargetBinder":
        """Restore validated pending test targets for one workspace."""
        binder = cls(workspace)
        if snapshot is None:
            return binder
        if type(snapshot) is not TestTargetSnapshot:
            raise ValueError("test target snapshot has an invalid type")
        if type(snapshot.modified_paths) is not tuple:
            raise ValueError("test target snapshot paths must be a tuple")

        restored: set[str] = set()
        for path in snapshot.modified_paths:
            if type(path) is not str or not path:
                raise ValueError("test target snapshot path must be a non-empty string")
            if "\\" in path or PurePosixPath(path).is_absolute():
                raise ValueError("test target snapshot path must be workspace-relative")
            try:
                normalized = binder._relative(path)
            except ValueError as exc:
                raise ValueError("test target snapshot path escapes workspace") from exc
            if normalized == "." or normalized != path:
                raise ValueError("test target snapshot path is not canonical")
            if normalized in restored:
                raise ValueError("test target snapshot contains duplicate paths")
            restored.add(normalized)
        binder._modified = restored
        return binder

    def observe_write(self, path: str) -> None:
        target = self._relative(path)
        self._modified.add(target)

    def observe_test(self, *, success: bool) -> None:
        if type(success) is not bool:
            raise ValueError("test result must be boolean")
        if success:
            self._modified.clear()

    def inspect(self, command: str) -> TargetDecision:
        if type(command) is not str or not command.strip():
            raise ValueError("test command must be a non-empty string")
        try:
            parts = shlex.split(command)
        except ValueError:
            return TargetDecision(False, "test target command quoting is invalid")
        targets = set()
        for part in parts[1:]:
            if part.startswith("-") or not self._looks_like_path(part):
                continue
            # Pytest node IDs append ::test_name to a file path.
            path_part = part.split("::", 1)[0]
            try:
                targets.add(self._relative(path_part))
            except ValueError:
                return TargetDecision(False, "test target escapes workspace")

        if not self._modified:
            return TargetDecision(True)

        missing: list[str] = []
        for modified in sorted(self._modified):
            if self._requires_npm_test(modified):
                if not self._is_npm_test(parts):
                    missing.append(f"{modified} -> npm test")
                continue

            expected = self._expected_tests(modified)
            if not expected:
                if PurePosixPath(modified).suffix == ".py":
                    expected = {self._display_candidate(modified)}
                else:
                    # A non-code asset has no conventionally derivable focused test.
                    # CompletionGate still requires a successful test after the write.
                    continue
            if not any(
                self._target_matches(target, candidate)
                for target in targets
                for candidate in expected
            ):
                missing.append(f"{modified} -> {', '.join(sorted(expected))}")
        if missing:
            return TargetDecision(
                False,
                "test target mismatch: explicitly run the focused tests for "
                + "; ".join(missing),
            )
        return TargetDecision(True)

    @staticmethod
    def _requires_npm_test(modified: str) -> bool:
        path = PurePosixPath(modified)
        return path.suffix.lower() in _NPM_TEST_SUFFIXES or path.name in _NPM_TEST_FILENAMES

    @staticmethod
    def _is_npm_test(parts: list[str]) -> bool:
        return len(parts) >= 2 and parts[0] == "npm" and parts[1] == "test"

    def _expected_tests(self, modified: str) -> set[str]:
        path = PurePosixPath(modified)
        if path.name.startswith("test_") or path.name.endswith("_test.py"):
            return {modified}
        if path.suffix != ".py":
            return set()

        stem = path.stem
        candidates = {
            path.parent / f"test_{stem}.py",
            path.parent / f"{stem}_test.py",
            PurePosixPath("tests") / f"test_{stem}.py",
            PurePosixPath("tests") / f"{stem}_test.py",
        }
        existing = {
            self._relative(str(candidate))
            for candidate in candidates
            if (self.workspace / Path(str(candidate))).is_file()
        }
        if existing:
            return existing

        # Also recognize tests that import a source file under a different name.
        for test_path in self._test_files():
            try:
                content = test_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            if self._references_source(content, path):
                existing.add(self._relative(str(test_path)))
        return existing

    def _test_files(self) -> list[Path]:
        return [
            path
            for path in self.workspace.rglob("*.py")
            if path.name.startswith("test_") or path.name.endswith("_test.py")
        ]

    @staticmethod
    def _references_source(content: str, source: PurePosixPath) -> bool:
        stem = source.stem
        return (
            f"import {stem}" in content
            or f"from {stem} import" in content
            or f"{source.name}" in content
        )

    @staticmethod
    def _looks_like_path(value: str) -> bool:
        lowered = value.lower()
        return (
            lowered.endswith((".py", ".js", ".ts", ".tsx"))
            or "/" in value
            or "\\" in value
            or value.startswith("test")
        )

    def _relative(self, path: str) -> str:
        candidate = (self.workspace / Path(path)).resolve()
        try:
            relative = candidate.relative_to(self.workspace)
        except ValueError as exc:
            raise ValueError("test target escapes workspace") from exc
        return PurePosixPath(relative.as_posix()).as_posix()

    @staticmethod
    def _display_candidate(modified: str) -> str:
        path = PurePosixPath(modified)
        return f"tests/test_{path.stem}.py"

    @staticmethod
    def _target_matches(target: str, expected: str) -> bool:
        if target == ".":
            return True
        return target == expected or expected.startswith(target.rstrip("/") + "/")
