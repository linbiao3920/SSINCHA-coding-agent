import pytest

from agent.feedback import (
    FeedbackTracker,
    StructuredError,
    extract_test_error,
    format_structured_feedback,
)


def test_extracts_traceback_error_with_location_and_category():
    output = '''
E       assert 2 == 5
E       AssertionError: expected 5, got 2
File "tests/test_calculator.py", line 8
'''

    error = extract_test_error(output)

    assert error == StructuredError(
        category="assertion",
        error_type="AssertionError",
        message="expected 5, got 2",
        location="tests/test_calculator.py:8",
    )
    assert "[structured-feedback]" in format_structured_feedback(error)


def test_extracts_missing_test_as_collection_error():
    error = extract_test_error("ERROR: file or directory not found: missing_test.py")

    assert error is not None
    assert error.category == "collection"
    assert error.error_type == "TestCollectionError"


def test_non_test_output_is_not_misclassified():
    assert extract_test_error("some unrelated tool output") is None


def test_tracker_stops_on_three_consecutive_identical_failures():
    tracker = FeedbackTracker()
    assert tracker.observe(success=False, observation="pytest failed") is False
    assert tracker.observe(success=False, observation="pytest failed") is False
    assert tracker.observe(success=False, observation="pytest failed") is True
    assert tracker.count == 3


def test_tracker_resets_after_success_or_new_error():
    tracker = FeedbackTracker()
    tracker.observe(success=False, observation="first")
    tracker.observe(success=False, observation="second")
    assert tracker.count == 1
    tracker.observe(success=True, observation="passed")
    assert tracker.count == 0


def test_tracker_validates_limit_and_inputs():
    with pytest.raises(ValueError):
        FeedbackTracker(limit=0)
    tracker = FeedbackTracker()
    with pytest.raises(ValueError):
        tracker.observe(success=False, observation=123)
