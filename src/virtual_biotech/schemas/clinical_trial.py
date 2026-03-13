"""Pydantic schema for clinical trial JSON extraction."""

from enum import StrEnum

from pydantic import BaseModel, model_validator


class StopReasonCategory(StrEnum):
    INSUFFICIENT_ENROLLMENT = "Insufficient enrollment"
    BUSINESS_ADMIN = "Business or administrative"
    NEGATIVE_EFFICACY = "Negative (lack of efficacy)"
    STUDY_DESIGN = "Study design"
    INVALID_REASON = "Invalid reason"
    SAFETY = "Safety or side effects"
    LOGISTICS = "Logistics or resources"
    ANOTHER_STUDY = "Another study"
    STAFF_MOVED = "Study staff moved"
    REGULATORY = "Regulatory"
    NO_CONTEXT = "No context"
    COVID = "COVID-19"
    UNCATEGORISED = "Uncategorised"
    INTERIM_ANALYSIS = "Interim analysis"
    INSUFFICIENT_DATA = "Insufficient data"
    SUCCESS = "Success"


class EndpointResult(StrEnum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    UNKNOWN = "UNKNOWN"


class AdverseEventProfile(BaseModel):
    serious_adverse_events: dict | None = None
    other_adverse_events: dict | None = None
    total_serious_ae_rate: float | None = None
    ae_rates_by_organ_system: dict | None = None


class DataSourceTracking(BaseModel):
    primary_source: str
    results_source: str | None = None
    adverse_events_source: str | None = None
    additional_sources_used: list[str] = []
    pubmed_ids: list[str] = []
    web_urls: list[str] = []


class ClinicalTrialData(BaseModel):
    nct_id: str
    title: str
    phase: str
    status: str
    conditions: list[str]
    interventions: list[str]
    enrollment: int | None = None
    start_date: str | None = None

    # For COMPLETED trials
    primary_endpoint_result: EndpointResult | None = None
    primary_endpoint_notes: str | None = None
    secondary_endpoint_result: EndpointResult | None = None
    secondary_endpoint_notes: str | None = None
    adverse_event_profile: AdverseEventProfile | None = None

    # For TERMINATED/SUSPENDED/WITHDRAWN trials
    study_stop_reason: str | None = None
    study_stop_reason_categories: list[StopReasonCategory] | None = None

    data_source_tracking: DataSourceTracking

    @model_validator(mode="after")
    def validate_status_fields(self) -> "ClinicalTrialData":
        if self.status == "Completed":
            if self.primary_endpoint_result is None:
                raise ValueError("Completed trials must have primary_endpoint_result")
            if self.secondary_endpoint_result is None:
                raise ValueError("Completed trials must have secondary_endpoint_result")
        elif self.status in ("Terminated", "Suspended", "Withdrawn"):
            if self.study_stop_reason is None:
                raise ValueError("Stopped trials must have study_stop_reason")
            if self.study_stop_reason_categories is None:
                raise ValueError("Stopped trials must have study_stop_reason_categories")
            if len(self.study_stop_reason_categories) > 2:
                raise ValueError("Max 2 stop reason categories")
        return self
