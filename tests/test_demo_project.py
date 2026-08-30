from pathlib import Path


def test_demo_project_contains_real_failing_task_files():
    root = Path("examples/demo_project")
    assert (root / "calculator.py").is_file()
    assert (root / "tests/test_calculator.py").is_file()
    assert "return left - right" in (root / "calculator.py").read_text(encoding="utf-8")
