from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_docker_image_runs_web_ui_as_non_root_user():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM python:3.12-slim" in dockerfile
    assert "USER agent" in dockerfile
    assert '"--host", "0.0.0.0"' in dockerfile
    assert '"--session-dir", "/data/sessions"' in dockerfile


def test_container_build_context_excludes_local_secrets_and_sessions():
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    for pattern in (".agent_sessions/", ".env", "*.key", "*.secret", "README.txt"):
        assert pattern in ignored


def test_compose_binds_web_to_loopback_and_mounts_workspace_and_sessions():
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert '"127.0.0.1:8765:8765"' in compose
    assert "${SSINCHA_WORKSPACE:-./examples/demo_project}:/workspace" in compose
    assert "agent_sessions:/data/sessions" in compose
