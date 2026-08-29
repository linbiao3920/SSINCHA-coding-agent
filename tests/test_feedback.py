import pytest

from agent.feedback import FeedbackTracker


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
