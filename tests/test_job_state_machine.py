"""Unit tests for job state machine transitions (ADR-003)."""

import pytest

from load_gear.models.control import JobStatus
from load_gear.services.job_service import VALID_TRANSITIONS, validate_transition


class TestValidTransitions:
    """Test that valid transitions are accepted."""

    @pytest.mark.parametrize("current,target", [
        (JobStatus.PENDING, JobStatus.INGESTING),
        (JobStatus.PENDING, JobStatus.FAILED),
        (JobStatus.INGESTING, JobStatus.QA_RUNNING),
        (JobStatus.INGESTING, JobStatus.FAILED),
        (JobStatus.QA_RUNNING, JobStatus.ANALYSIS_RUNNING),
        (JobStatus.QA_RUNNING, JobStatus.DONE),
        (JobStatus.QA_RUNNING, JobStatus.WARN),
        (JobStatus.QA_RUNNING, JobStatus.FAILED),
        (JobStatus.ANALYSIS_RUNNING, JobStatus.FORECAST_RUNNING),
        (JobStatus.ANALYSIS_RUNNING, JobStatus.DONE),
        (JobStatus.ANALYSIS_RUNNING, JobStatus.WARN),
        (JobStatus.ANALYSIS_RUNNING, JobStatus.FAILED),
        (JobStatus.FORECAST_RUNNING, JobStatus.DONE),
        (JobStatus.FORECAST_RUNNING, JobStatus.WARN),
        (JobStatus.FORECAST_RUNNING, JobStatus.FAILED),
    ])
    def test_valid_transition_accepted(self, current: JobStatus, target: JobStatus) -> None:
        assert validate_transition(current, target) is True


class TestInvalidTransitions:
    """Test that invalid transitions are rejected."""

    @pytest.mark.parametrize("current,target", [
        # Cannot skip states
        (JobStatus.PENDING, JobStatus.DONE),
        (JobStatus.PENDING, JobStatus.QA_RUNNING),
        (JobStatus.PENDING, JobStatus.ANALYSIS_RUNNING),
        (JobStatus.INGESTING, JobStatus.DONE),
        (JobStatus.INGESTING, JobStatus.ANALYSIS_RUNNING),
        # Cannot go backwards
        (JobStatus.QA_RUNNING, JobStatus.INGESTING),
        (JobStatus.QA_RUNNING, JobStatus.PENDING),
        (JobStatus.ANALYSIS_RUNNING, JobStatus.QA_RUNNING),
        (JobStatus.FORECAST_RUNNING, JobStatus.ANALYSIS_RUNNING),
        # Terminal states cannot transition
        (JobStatus.DONE, JobStatus.PENDING),
        (JobStatus.DONE, JobStatus.FAILED),
        (JobStatus.WARN, JobStatus.DONE),
        (JobStatus.FAILED, JobStatus.PENDING),
        (JobStatus.FAILED, JobStatus.INGESTING),
    ])
    def test_invalid_transition_rejected(self, current: JobStatus, target: JobStatus) -> None:
        assert validate_transition(current, target) is False


class TestTerminalStates:
    """Test that terminal states have no valid transitions."""

    @pytest.mark.parametrize("terminal", [JobStatus.DONE, JobStatus.WARN, JobStatus.FAILED])
    def test_terminal_state_has_no_transitions(self, terminal: JobStatus) -> None:
        assert VALID_TRANSITIONS[terminal] == set()


class TestAllStatesHaveEntries:
    """Ensure every JobStatus has an entry in VALID_TRANSITIONS."""

    def test_all_states_covered(self) -> None:
        for status in JobStatus:
            assert status in VALID_TRANSITIONS, f"{status} missing from VALID_TRANSITIONS"
