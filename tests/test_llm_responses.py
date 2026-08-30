from agent.llm import RealLLMClient, _build_responses_request
from agent.state import Message


def test_from_environment_uses_deepseek_defaults(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

    client = RealLLMClient.from_environment()

    assert client.api_key == "key"
    assert client.model == "deepseek-v4-flash"
    assert client.base_url == "https://api.deepseek.com"


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
