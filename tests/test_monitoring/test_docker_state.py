"""Unit tests for Docker container condition evaluation."""

import pytest

from squire.monitoring.docker_state import evaluate_container_condition


@pytest.mark.parametrize(
    ("state", "condition", "expected_outcome", "snippet"),
    [
        (
            {"Running": True, "Status": "running", "ExitCode": 0},
            "running",
            "met",
            "running",
        ),
        (
            {"Running": False, "Status": "exited", "ExitCode": 0},
            "exited",
            "met",
            "stopped",
        ),
        (
            {"Running": False, "Status": "created", "ExitCode": 0},
            "running",
            "pending",
            "Not running yet",
        ),
        (
            {"Running": True, "Status": "running", "Health": {"Status": "healthy"}},
            "healthy",
            "met",
            "healthy",
        ),
        (
            {"Running": True, "Status": "starting", "Health": {"Status": "starting"}},
            "healthy",
            "pending",
            "Health status",
        ),
        (
            {"Running": True, "Status": "running"},
            "healthy",
            "failed",
            "no health check",
        ),
        (
            {"Running": True, "Status": "running", "Health": {"Status": "unhealthy"}},
            "healthy",
            "failed",
            "unhealthy",
        ),
    ],
)
def test_evaluate_container_condition(state, condition, expected_outcome, snippet):
    outcome, detail = evaluate_container_condition(state, condition)
    assert outcome == expected_outcome
    assert snippet.lower() in detail.lower()
