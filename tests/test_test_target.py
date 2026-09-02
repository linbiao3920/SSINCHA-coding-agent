from pathlib import Path

import pytest

from agent.test_target import TestTargetBinder, TestTargetSnapshot


def test_binder_allows_focused_test_for_modified_source(tmp_path: Path):
    (tmp_path / "calculator.py").write_text("def add(a, b): return a + b\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_calculator.py").write_text(
        "from calculator import add\n\ndef test_add(): assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    binder = TestTargetBinder(tmp_path)
    binder.observe_write("calculator.py")

    assert binder.inspect("pytest tests/test_calculator.py").allowed is True
    assert binder.inspect("pytest tests/test_calculator.py::test_add").allowed is True
    assert binder.inspect("pytest tests").allowed is True


def test_binder_blocks_unrelated_test_target(tmp_path: Path):
    (tmp_path / "greet.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "test_blackjack.py").write_text(
        "def test_game(): assert True\n", encoding="utf-8"
    )
    binder = TestTargetBinder(tmp_path)
    binder.observe_write("greet.py")

    decision = binder.inspect("pytest test_blackjack.py")

    assert decision.allowed is False
    assert "greet.py" in decision.reason


def test_binder_returns_a_rejection_for_workspace_escape(tmp_path: Path):
    binder = TestTargetBinder(tmp_path)
    binder.observe_write("main.py")

    decision = binder.inspect("pytest ../outside.py")

    assert decision.allowed is False
    assert decision.reason == "test target escapes workspace"


def test_binder_requires_explicit_target_for_broad_pytest(tmp_path: Path):
    (tmp_path / "greet.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "test_greet.py").write_text(
        "def test_greet(): assert True\n", encoding="utf-8"
    )
    binder = TestTargetBinder(tmp_path)
    binder.observe_write("greet.py")

    decision = binder.inspect("pytest")

    assert decision.allowed is False
    assert "test_greet.py" in decision.reason
    assert binder.inspect("pytest test_greet.py").allowed is True


def test_successful_test_clears_modified_targets(tmp_path: Path):
    binder = TestTargetBinder(tmp_path)
    binder.observe_write("main.py")
    binder.observe_test(success=True)

    assert binder.modified_paths == frozenset()


def test_binder_snapshot_round_trips_canonical_modified_paths(tmp_path: Path):
    binder = TestTargetBinder(tmp_path)
    binder.observe_write("src/app.py")
    binder.observe_write("main.py")

    snapshot = binder.snapshot()
    restored = TestTargetBinder.from_snapshot(tmp_path, snapshot)

    assert snapshot == TestTargetSnapshot(("main.py", "src/app.py"))
    assert restored.modified_paths == frozenset({"main.py", "src/app.py"})


@pytest.mark.parametrize(
    "snapshot",
    [
        TestTargetSnapshot(("../outside.py",)),
        TestTargetSnapshot(("src\\app.py",)),
        TestTargetSnapshot(("src/../app.py",)),
        TestTargetSnapshot(("main.py", "main.py")),
    ],
)
def test_binder_rejects_unsafe_or_noncanonical_snapshots(
    tmp_path: Path, snapshot: TestTargetSnapshot
):
    with pytest.raises(ValueError, match="snapshot"):
        TestTargetBinder.from_snapshot(tmp_path, snapshot)
