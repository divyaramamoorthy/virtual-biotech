"""Tests for Pydantic schema validation."""

import pytest

from virtual_biotech.schemas.clinical_trial import (
    AdverseEventProfile,
    ClinicalTrialData,
    DataSourceTracking,
    EndpointResult,
    StopReasonCategory,
)


def _make_tracking() -> DataSourceTracking:
    return DataSourceTracking(primary_source="clinicaltrials.gov")


class TestClinicalTrialData:
    """Tests for ClinicalTrialData schema validation."""

    def test_completed_trial_valid(self):
        """Completed trial with all required fields passes validation."""
        trial = ClinicalTrialData(
            nct_id="NCT00000001",
            title="Test Trial",
            phase="Phase 3",
            status="Completed",
            conditions=["Lung Cancer"],
            interventions=["Drug A"],
            primary_endpoint_result=EndpointResult.POSITIVE,
            primary_endpoint_notes="Met primary endpoint",
            secondary_endpoint_result=EndpointResult.POSITIVE,
            secondary_endpoint_notes="Met secondary endpoint",
            data_source_tracking=_make_tracking(),
        )
        assert trial.nct_id == "NCT00000001"
        assert trial.primary_endpoint_result == EndpointResult.POSITIVE

    def test_completed_trial_missing_primary_endpoint(self):
        """Completed trial without primary endpoint result raises error."""
        with pytest.raises(ValueError, match="Completed trials must have primary_endpoint_result"):
            ClinicalTrialData(
                nct_id="NCT00000002",
                title="Test Trial",
                phase="Phase 3",
                status="Completed",
                conditions=["Lung Cancer"],
                interventions=["Drug A"],
                secondary_endpoint_result=EndpointResult.UNKNOWN,
                data_source_tracking=_make_tracking(),
            )

    def test_completed_trial_missing_secondary_endpoint(self):
        """Completed trial without secondary endpoint result raises error."""
        with pytest.raises(ValueError, match="Completed trials must have secondary_endpoint_result"):
            ClinicalTrialData(
                nct_id="NCT00000003",
                title="Test Trial",
                phase="Phase 3",
                status="Completed",
                conditions=["Lung Cancer"],
                interventions=["Drug A"],
                primary_endpoint_result=EndpointResult.POSITIVE,
                data_source_tracking=_make_tracking(),
            )

    def test_terminated_trial_valid(self):
        """Terminated trial with stop reason passes validation."""
        trial = ClinicalTrialData(
            nct_id="NCT00000004",
            title="Terminated Trial",
            phase="Phase 2",
            status="Terminated",
            conditions=["Breast Cancer"],
            interventions=["Drug B"],
            study_stop_reason="Lack of efficacy",
            study_stop_reason_categories=[StopReasonCategory.NEGATIVE_EFFICACY],
            data_source_tracking=_make_tracking(),
        )
        assert trial.study_stop_reason_categories == [StopReasonCategory.NEGATIVE_EFFICACY]

    def test_terminated_trial_missing_stop_reason(self):
        """Terminated trial without stop reason raises error."""
        with pytest.raises(ValueError, match="Stopped trials must have study_stop_reason"):
            ClinicalTrialData(
                nct_id="NCT00000005",
                title="Terminated Trial",
                phase="Phase 2",
                status="Terminated",
                conditions=["Breast Cancer"],
                interventions=["Drug B"],
                data_source_tracking=_make_tracking(),
            )

    def test_terminated_trial_too_many_categories(self):
        """Terminated trial with >2 stop reason categories raises error."""
        with pytest.raises(ValueError, match="Max 2 stop reason categories"):
            ClinicalTrialData(
                nct_id="NCT00000006",
                title="Terminated Trial",
                phase="Phase 1",
                status="Terminated",
                conditions=["Leukemia"],
                interventions=["Drug C"],
                study_stop_reason="Multiple reasons",
                study_stop_reason_categories=[
                    StopReasonCategory.SAFETY,
                    StopReasonCategory.NEGATIVE_EFFICACY,
                    StopReasonCategory.BUSINESS_ADMIN,
                ],
                data_source_tracking=_make_tracking(),
            )

    def test_active_trial_no_constraints(self):
        """Active/recruiting trial has no special field requirements."""
        trial = ClinicalTrialData(
            nct_id="NCT00000007",
            title="Active Trial",
            phase="Phase 1",
            status="Recruiting",
            conditions=["Asthma"],
            interventions=["Drug D"],
            data_source_tracking=_make_tracking(),
        )
        assert trial.status == "Recruiting"

    def test_adverse_event_profile(self):
        """AdverseEventProfile stores AE data correctly."""
        profile = AdverseEventProfile(
            total_serious_ae_rate=0.15,
            ae_rates_by_organ_system={"Gastrointestinal": 0.3, "Nervous system": 0.1},
        )
        assert profile.total_serious_ae_rate == 0.15

    def test_stop_reason_categories_enum(self):
        """All 16 stop reason categories are defined."""
        assert len(StopReasonCategory) == 16

    def test_endpoint_result_enum(self):
        """All 3 endpoint result values are defined."""
        assert len(EndpointResult) == 3
