from agent.llm import RealLLMClient, _build_responses_request
from agent.state import Message


def test_from_environment_uses_deepseek_defaults(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

    client = RealLLMClient.from_environment()

    assert client.api_key == "key"
    assert client.model == "deepseek-v4-flash"
    assert client.base_url == "https://api.deepseek.com"


def test_credentials_can_be_loaded_from_key_file_without_exposing_contents(tmp_path):
    from agent.secrets import load_provider_credentials, redact

    key = "sk-0123456789abcdef0123456789abcdef"
    key_file = tmp_path / "deepseek.key"
    key_file.write_text(key + "\n", encoding="utf-8")

    credentials = load_provider_credentials(
        {"DEEPSEEK_API_KEY_FILE": str(key_file)}, cwd=tmp_path
    )

    assert credentials.api_key == key
    assert credentials.source == "DEEPSEEK_API_KEY_FILE"
    assert redact(f"request failed for {key}", [key]) == "request failed for <redacted>"


def test_environment_key_takes_precedence_over_dotenv(tmp_path):
    from agent.secrets import load_provider_credentials

    (tmp_path / ".env").write_text(
        "DEEPSEEK_API_KEY=sk-dotenv-0123456789abcdef\n", encoding="utf-8"
    )
    credentials = load_provider_credentials(
        {"DEEPSEEK_API_KEY": "sk-env-0123456789abcdef"}, cwd=tmp_path
    )

    assert credentials.api_key == "sk-env-0123456789abcdef"
    assert credentials.source == "DEEPSEEK_API_KEY"


def test_credentials_fall_back_to_local_dotenv(tmp_path):
    from agent.secrets import load_provider_credentials

    (tmp_path / ".env").write_text(
        "DEEPSEEK_API_KEY=sk-dotenv-0123456789abcdef\n"
        "DEEPSEEK_MODEL=deepseek-v4-flash\n",
        encoding="utf-8",
    )

    credentials = load_provider_credentials({}, cwd=tmp_path)

    assert credentials.api_key == "sk-dotenv-0123456789abcdef"
    assert credentials.model == "deepseek-v4-flash"
    assert credentials.source == "DEEPSEEK_API_KEY"


def test_missing_credentials_has_safe_diagnostic(tmp_path):
    import pytest
    from agent.secrets import SecretError, load_provider_credentials

    with pytest.raises(SecretError, match="DEEPSEEK_API_KEY"):
        load_provider_credentials({}, cwd=tmp_path)


def test_responses_request_separates_instructions_and_tool_history():
    instructions, items = _build_responses_request(
        [
            Message("system", "stay in JSON"),
            Message("user", "fix the bug"),
            Message("tool", "read file output"),
            Message("assistant", '{"type":"Stop","params":{"reason":"done"}}'),
        ]
    )

    assert instructions == "stay in JSON"
    assert items[0]["role"] == "user"
    assert items[1]["role"] == "user"
    assert items[1]["content"].startswith("[tool]\n")
    assert items[2]["role"] == "assistant"
