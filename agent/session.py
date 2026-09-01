"""Persistent local conversation sessions for CLI invocations."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
from typing import Sequence

from dataclasses import dataclass
from .completion import CompletionSnapshot
from .state import Message
from .test_target import TestTargetBinder, TestTargetSnapshot
from .secrets import redact


SESSION_VERSION = 1
MAX_SESSION_BYTES = 10_000_000
DEFAULT_SESSION_DIR = Path(__file__).resolve().parent.parent / ".agent_sessions"
_SESSION_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class SessionError(ValueError):
    """Raised when a persisted session is invalid or unsafe to use."""


@dataclass(frozen=True)
class SessionData:
    history: list[Message]
    completion: CompletionSnapshot | None = None
    test_targets: TestTargetSnapshot | None = None


class SessionStore:
    """Load and atomically save conversation state outside the workspace."""

    def __init__(self, root: str | Path = DEFAULT_SESSION_DIR):
        self.root = Path(root).resolve()

    def path_for(self, name: str) -> Path:
        self._validate_name(name)
        return self.root / f"{name}.json"

    def exists(self, name: str) -> bool:
        return self.path_for(name).is_file()

    def load_data(self, name: str, workspace: str | Path) -> SessionData:
        path = self.path_for(name)
        if path.is_symlink():
            raise SessionError("session path must be a regular file")
        if not path.exists():
            return SessionData(history=[])
        if not path.is_file():
            raise SessionError("session path must be a regular file")
        if path.stat().st_size > MAX_SESSION_BYTES:
            raise SessionError("session file exceeds the size limit")

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise SessionError(f"cannot load session {name!r}") from exc

        if type(payload) is not dict or payload.get("version") != SESSION_VERSION:
            raise SessionError("unsupported session format")
        if payload.get("name") != name:
            raise SessionError("session name does not match its file")

        expected_workspace = Path(workspace).resolve()
        stored_workspace = payload.get("workspace")
        if type(stored_workspace) is not str:
            raise SessionError("session workspace is missing")
        if Path(stored_workspace).resolve() != expected_workspace:
            raise SessionError("session belongs to a different workspace")

        raw_history = payload.get("history")
        if type(raw_history) is not list:
            raise SessionError("session history must be a list")
        if any(type(item) is not dict for item in raw_history):
            raise SessionError("session history contains an invalid message")
        try:
            history = [
                Message(role=item["role"], content=item["content"])
                for item in raw_history
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise SessionError("session history contains an invalid message") from exc
        raw_completion = payload.get("completion")
        completion = None
        if raw_completion is not None:
            if type(raw_completion) is not dict:
                raise SessionError("session completion state is invalid")
            requires_test = raw_completion.get("requires_test")
            latest_test_success = raw_completion.get("latest_test_success")
            if type(requires_test) is not bool or (
                latest_test_success is not None
                and type(latest_test_success) is not bool
            ):
                raise SessionError("session completion state is invalid")
            completion = CompletionSnapshot(requires_test, latest_test_success)
        raw_test_targets = payload.get("test_targets")
        test_targets = None
        if raw_test_targets is not None:
            if type(raw_test_targets) is not dict:
                raise SessionError("session test target state is invalid")
            modified_paths = raw_test_targets.get("modified_paths")
            if type(modified_paths) is not list or any(
                type(path) is not str for path in modified_paths
            ):
                raise SessionError("session test target state is invalid")
            try:
                test_targets = TestTargetBinder.from_snapshot(
                    expected_workspace,
                    TestTargetSnapshot(tuple(modified_paths)),
                ).snapshot()
            except ValueError as exc:
                raise SessionError("session test target state is invalid") from exc
        return SessionData(
            history=history,
            completion=completion,
            test_targets=test_targets,
        )

    def load(self, name: str, workspace: str | Path) -> list[Message]:
        """Load only history for callers that do not need completion state."""
        return self.load_data(name, workspace).history

    def save(
        self,
        name: str,
        workspace: str | Path,
        history: Sequence[Message],
        completion: CompletionSnapshot | None = None,
        test_targets: TestTargetSnapshot | None = None,
    ) -> Path:
        path = self.path_for(name)
        payload = {
            "version": SESSION_VERSION,
            "name": name,
            "workspace": str(Path(workspace).resolve()),
            "history": [
                {"role": message.role, "content": redact(message.content)}
                for message in history
            ],
        }
        if completion is not None:
            if type(completion) is not CompletionSnapshot:
                raise SessionError("completion state has an invalid type")
            payload["completion"] = {
                "requires_test": completion.requires_test,
                "latest_test_success": completion.latest_test_success,
            }
        if test_targets is not None:
            try:
                validated_targets = TestTargetBinder.from_snapshot(
                    workspace, test_targets
                ).snapshot()
            except ValueError as exc:
                raise SessionError("test target state has an invalid value") from exc
            payload["test_targets"] = {
                "modified_paths": list(validated_targets.modified_paths),
            }
        encoded = json.dumps(payload, ensure_ascii=False, indent=2)
        if len(encoded.encode("utf-8")) > MAX_SESSION_BYTES:
            raise SessionError("session data exceeds the size limit")

        self.root.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.root,
                prefix=f".{name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
                temporary_path = Path(handle.name)
            os.replace(temporary_path, path)
        except OSError as exc:
            raise SessionError(f"cannot save session {name!r}") from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return path

    @staticmethod
    def _validate_name(name: str) -> None:
        if type(name) is not str or not _SESSION_NAME_RE.fullmatch(name):
            raise SessionError(
                "session name must contain 1-64 letters, numbers, underscores, or hyphens"
            )
