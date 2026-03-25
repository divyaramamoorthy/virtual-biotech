"""Clinical Trials MCP Server — ClinicalTrials.gov API v2."""

import httpx
from fastmcp import FastMCP

from virtual_biotech.mcp_servers._sources import make_source

mcp = FastMCP("clinical-trials")

BASE_URL = "https://clinicaltrials.gov/api/v2"


def _parse_event_list(events: list[dict]) -> list[dict]:
    """Extract term, organ system, and stats from a list of AE event groups."""
    return [{"term": e.get("term"), "organ_system": e.get("organSystem"), "stats": e.get("stats", [])} for e in events]


def _parse_adverse_events(ae_module: dict) -> dict:
    """Parse an adverseEventsModule into a normalized dict."""
    return {
        "serious_events": _parse_event_list(ae_module.get("seriousEvents", [])),
        "other_events": _parse_event_list(ae_module.get("otherEvents", [])),
        "frequency_threshold": ae_module.get("frequencyThreshold"),
        "time_frame": ae_module.get("timeFrame"),
    }


def _parse_outcomes(outcomes: list[dict]) -> list[dict]:
    """Extract measure, timeFrame, and description from outcome entries."""
    return [{"measure": o.get("measure"), "timeFrame": o.get("timeFrame"), "description": o.get("description")} for o in outcomes]


@mcp.tool()
def get_clinical_trial_details(nct_id: str) -> dict:
    """Retrieve comprehensive clinical trial record from ClinicalTrials.gov.

    Returns trial design, status, interventions, eligibility criteria,
    outcomes, adverse events, and study protocol details.

    Args:
        nct_id: National Clinical Trial identifier (e.g., "NCT06137183").
    """
    url = f"{BASE_URL}/studies/{nct_id}"
    response = httpx.get(url, timeout=30)
    response.raise_for_status()
    data = response.json()

    protocol = data.get("protocolSection", {})
    id_module = protocol.get("identificationModule", {})
    status_module = protocol.get("statusModule", {})
    design_module = protocol.get("designModule", {})
    conditions_module = protocol.get("conditionsModule", {})
    arms_module = protocol.get("armsInterventionsModule", {})
    eligibility_module = protocol.get("eligibilityModule", {})
    outcomes_module = protocol.get("outcomesModule", {})
    results_section = data.get("resultsSection", {})

    interventions = [
        {"type": i.get("type"), "name": i.get("name"), "description": i.get("description")} for i in arms_module.get("interventions", [])
    ]

    ae_module = results_section.get("adverseEventsModule", {})
    adverse_events = _parse_adverse_events(ae_module) if ae_module else {}

    return {
        "nct_id": nct_id,
        "title": id_module.get("officialTitle", id_module.get("briefTitle", "")),
        "status": status_module.get("overallStatus", ""),
        "phase": design_module.get("phases", []),
        "conditions": conditions_module.get("conditions", []),
        "interventions": interventions,
        "eligibility": {
            "criteria": eligibility_module.get("eligibilityCriteria", ""),
            "sex": eligibility_module.get("sex", ""),
            "minimum_age": eligibility_module.get("minimumAge", ""),
            "maximum_age": eligibility_module.get("maximumAge", ""),
        },
        "primary_outcomes": _parse_outcomes(outcomes_module.get("primaryOutcomes", [])),
        "secondary_outcomes": _parse_outcomes(outcomes_module.get("secondaryOutcomes", [])),
        "results": bool(results_section),
        "adverse_events": adverse_events,
        "why_stopped": status_module.get("whyStopped"),
        "enrollment": design_module.get("enrollmentInfo", {}).get("count"),
        "start_date": status_module.get("startDateStruct", {}).get("date"),
        "completion_date": status_module.get("completionDateStruct", {}).get("date"),
        "_sources": [make_source("ClinicalTrials.gov", url=f"https://clinicaltrials.gov/study/{nct_id}")],
    }


@mcp.tool()
def search_trials_by_target(gene_symbol: str, condition: str | None = None, phase: str | None = None) -> list[dict]:
    """Search ClinicalTrials.gov for trials targeting a specific gene/protein.

    Args:
        gene_symbol: Gene or protein target name.
        condition: Optional disease/condition filter.
        phase: Optional phase filter (e.g., "PHASE3").
    """
    params: dict = {
        "query.intr": gene_symbol,
        "pageSize": 50,
        "format": "json",
    }
    if condition:
        params["query.cond"] = condition
    if phase:
        params["filter.advanced"] = f"AREA[Phase]{phase}"

    url = f"{BASE_URL}/studies"
    response = httpx.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    trials = []
    for study in data.get("studies", []):
        protocol = study.get("protocolSection", {})
        id_module = protocol.get("identificationModule", {})
        status_module = protocol.get("statusModule", {})
        design_module = protocol.get("designModule", {})
        conditions_module = protocol.get("conditionsModule", {})

        nct = id_module.get("nctId", "")
        trials.append(
            {
                "nct_id": nct,
                "title": id_module.get("briefTitle", ""),
                "status": status_module.get("overallStatus", ""),
                "phase": design_module.get("phases", []),
                "conditions": conditions_module.get("conditions", []),
                "start_date": status_module.get("startDateStruct", {}).get("date"),
                "_sources": [make_source("ClinicalTrials.gov", url=f"https://clinicaltrials.gov/study/{nct}")] if nct else [],
            }
        )

    return trials


@mcp.tool()
def get_trial_adverse_events(nct_id: str) -> dict:
    """Extract adverse event data from a clinical trial's posted results.

    Args:
        nct_id: National Clinical Trial identifier.
    """
    url = f"{BASE_URL}/studies/{nct_id}"
    response = httpx.get(url, params={"fields": "ResultsSection"}, timeout=30)
    response.raise_for_status()
    data = response.json()

    ae_module = data.get("resultsSection", {}).get("adverseEventsModule", {})

    source = make_source("ClinicalTrials.gov", url=f"https://clinicaltrials.gov/study/{nct_id}")

    if not ae_module:
        return {"nct_id": nct_id, "has_results": False, "adverse_events": {}, "_sources": [source]}

    return {
        "nct_id": nct_id,
        "has_results": True,
        "adverse_events": _parse_adverse_events(ae_module),
        "_sources": [source],
    }


if __name__ == "__main__":
    mcp.run()
