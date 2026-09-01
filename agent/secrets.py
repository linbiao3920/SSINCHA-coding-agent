"""Credential loading and redaction for the provider client."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Mapping, Iterable


MAX_SECRET_FILE_BYTES = 16_384
_SECRET_TOKEN_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")


class SecretError(ValueError):
    """Raised when provider credentials are missing or unsafe to load."""


@dataclass(frozen=True)
class ProviderCredentials:
    api_key: str
    model: str
    source: str


def load_provider_credentials(
    environ: Mapping[str, str] | None = None,
    *,
    cwd: str | Path | None = None,
) -> ProviderCredentials:
    """Load credentials without writing them to process or project state.

    Precedence is explicit environment variable, key file, then a local .env
    file.  The optional ``DEEPSEEK_ENV_FILE`` selects the dotenv file.
    """
    env = os.environ if environ is None else environ
    root = Path.cwd() if cwd is None else Path(cwd)
    values = dict(env)
    dotenv_name = values.get("DEEPSEEK_ENV_FILE")
    dotenv_path = Path(dotenv_name) if dotenv_name else root / ".env"
    if not dotenv_name and not dotenv_path.is_file():
        dotenv_path = None
    if dotenv_path is not None:
        values = {**_read_dotenv(dotenv_path), **values}

    api_key = values.get("DEEPSEEK_API_KEY", "").strip()
    source = "DEEPSEEK_API_KEY"
    if not api_key:
        key_file_name = values.get("DEEPSEEK_API_KEY_FILE", "").strip()
        if key_file_name:
            api_key = _read_secret_file(Path(key_file_name)).strip()
            source = "DEEPSEEK_API_KEY_FILE"
    if not api_key:
        raise SecretError(
            "missing DeepSeek API key; set DEEPSEEK_API_KEY or DEEPSEEK_API_KEY_FILE"
        )
    _validate_secret(api_key)
    model = values.get("DEEPSEEK_MODEL", "deepseek-v4-pro").strip()
    if not model:
        raise SecretError("DEEPSEEK_MODEL must be a non-empty string")
    return ProviderCredentials(api_key=api_key, model=model, source=source)


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    """Remove known credentials and OpenAI-style key tokens from diagnostics."""
    result = text
    for secret in secrets:
        if isinstance(secret, str) and len(secret) >= 4:
            result = result.replace(secret, "<redacted>")
    return _SECRET_TOKEN_RE.sub("<redacted>", result)


def _validate_secret(value: str) -> None:
    if any(character.isspace() for character in value) or len(value) > 4096:
        raise SecretError("DeepSeek API key must be a single bounded token")


def _read_secret_file(path: Path) -> str:
    try:
        resolved = path.expanduser().resolve()
        if not resolved.is_file() or resolved.stat().st_size > MAX_SECRET_FILE_BYTES:
            raise SecretError("DEEPSEEK_API_KEY_FILE must be a small regular file")
        return resolved.read_text(encoding="utf-8")
    except SecretError:
        raise
    except (OSError, UnicodeError) as exc:
        raise SecretError("cannot read DEEPSEEK_API_KEY_FILE") from exc


def _read_dotenv(path: Path) -> dict[str, str]:
    try:
        if not path.is_file() or path.stat().st_size > MAX_SECRET_FILE_BYTES:
            return {}
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return {}
    values: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        key, separator, value = stripped.partition("=")
        if separator and key.strip() in {
            "DEEPSEEK_API_KEY",
            "DEEPSEEK_API_KEY_FILE",
            "DEEPSEEK_MODEL",
            "DEEPSEEK_ENV_FILE",
        }:
            values[key.strip()] = value.strip().strip("\"'")
    return values
