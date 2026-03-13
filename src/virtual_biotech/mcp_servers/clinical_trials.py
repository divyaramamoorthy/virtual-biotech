"""Clinical Trials MCP Server — ClinicalTrials.gov API v2."""

import httpx
from fastmcp import FastMCP

mcp = FastMCP("clinical-trials")

BASE_URL = "https://clinicaltrials.gov/api/v2"


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

    interventions = []
    for intervention in arms_module.get("interventions", []):
        interventions.append(
            {
                "type": intervention.get("type"),
                "name": intervention.get("name"),
                "description": intervention.get("description"),
            }
        )

    primary_outcomes = []
    for outcome in outcomes_module.get("primaryOutcomes", []):
        primary_outcomes.append(
            {
                "measure": outcome.get("measure"),
                "timeFrame": outcome.get("timeFrame"),
                "description": outcome.get("description"),
            }
        )

    secondary_outcomes = []
    for outcome in outcomes_module.get("secondaryOutcomes", []):
        secondary_outcomes.append(
            {
                "measure": outcome.get("measure"),
                "timeFrame": outcome.get("timeFrame"),
                "description": outcome.get("description"),
            }
        )

    # Extract adverse events if results are posted
    adverse_events = {}
    ae_module = results_section.get("adverseEventsModule", {})
    if ae_module:
        serious_events = []
        for event_group in ae_module.get("seriousEvents", []):
            serious_events.append(
                {
                    "term": event_group.get("term"),
                    "organ_system": event_group.get("organSystem"),
                    "stats": event_group.get("stats", []),
                }
            )
        other_events = []
        for event_group in ae_module.get("otherEvents", []):
            other_events.append(
                {
                    "term": event_group.get("term"),
                    "organ_system": event_group.get("organSystem"),
                    "stats": event_group.get("stats", []),
                }
            )
        adverse_events = {
            "serious_events": serious_events,
            "other_events": other_events,
            "frequency_threshold": ae_module.get("frequencyThreshold"),
            "time_frame": ae_module.get("timeFrame"),
        }

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
        "primary_outcomes": primary_outcomes,
        "secondary_outcomes": secondary_outcomes,
        "results": bool(results_section),
        "adverse_events": adverse_events,
        "why_stopped": status_module.get("whyStopped"),
        "enrollment": protocol.get("designModule", {}).get("enrollmentInfo", {}).get("count"),
        "start_date": status_module.get("startDateStruct", {}).get("date"),
        "completion_date": status_module.get("completionDateStruct", {}).get("date"),
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

        trials.append(
            {
                "nct_id": id_module.get("nctId", ""),
                "title": id_module.get("briefTitle", ""),
                "status": status_module.get("overallStatus", ""),
                "phase": design_module.get("phases", []),
                "conditions": conditions_module.get("conditions", []),
                "start_date": status_module.get("startDateStruct", {}).get("date"),
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

    results_section = data.get("resultsSection", {})
    ae_module = results_section.get("adverseEventsModule", {})

    if not ae_module:
        return {"nct_id": nct_id, "has_results": False, "adverse_events": {}}

    serious_events = []
    for event in ae_module.get("seriousEvents", []):
        serious_events.append(
            {
                "term": event.get("term"),
                "organ_system": event.get("organSystem"),
                "stats": event.get("stats", []),
            }
        )

    other_events = []
    for event in ae_module.get("otherEvents", []):
        other_events.append(
            {
                "term": event.get("term"),
                "organ_system": event.get("organSystem"),
                "stats": event.get("stats", []),
            }
        )

    return {
        "nct_id": nct_id,
        "has_results": True,
        "adverse_events": {
            "serious_events": serious_events,
            "other_events": other_events,
            "frequency_threshold": ae_module.get("frequencyThreshold"),
            "time_frame": ae_module.get("timeFrame"),
        },
    }


if __name__ == "__main__":
    mcp.run()
