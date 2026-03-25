"""Drugs MCP Server — ChEMBL, OpenFDA, DailyMed."""

import httpx
from fastmcp import FastMCP

from virtual_biotech.mcp_servers._sources import make_source

mcp = FastMCP("drugs")

CHEMBL_BASE = "https://www.ebi.ac.uk/chembl/api/data"
OPENFDA_BASE = "https://api.fda.gov"


@mcp.tool()
def search_drugs_by_target(gene_symbol: str) -> dict:
    """Search ChEMBL for drugs and compounds targeting a specific gene/protein.

    Args:
        gene_symbol: Gene or protein target name.

    Returns:
        Dictionary with approved drugs, clinical candidates, and tool compounds.
    """
    # Search ChEMBL targets
    url = f"{CHEMBL_BASE}/target/search.json"
    params = {"q": gene_symbol, "limit": 10}
    try:
        response = httpx.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        targets = data.get("targets", [])
    except Exception:
        targets = []

    target_chembl_ids = [t.get("target_chembl_id") for t in targets if t.get("target_chembl_id")]

    # Get activities for each target
    drugs = []
    for target_id in target_chembl_ids[:3]:
        act_url = f"{CHEMBL_BASE}/activity.json"
        act_params = {"target_chembl_id": target_id, "limit": 50, "pchembl_value__isnull": False}
        try:
            response = httpx.get(act_url, params=act_params, timeout=30)
            response.raise_for_status()
            activities = response.json().get("activities", [])
        except Exception:
            activities = []

        drugs.extend(
            {
                "molecule_chembl_id": act.get("molecule_chembl_id"),
                "molecule_name": act.get("molecule_pref_name"),
                "pchembl_value": act.get("pchembl_value"),
                "standard_type": act.get("standard_type"),
                "standard_value": act.get("standard_value"),
                "standard_units": act.get("standard_units"),
                "assay_type": act.get("assay_type"),
            }
            for act in activities
        )

    return {
        "gene_symbol": gene_symbol,
        "target_chembl_ids": target_chembl_ids,
        "compounds": drugs,
        "compound_count": len(drugs),
        "_sources": [
            make_source(
                "ChEMBL",
                url=f"https://www.ebi.ac.uk/chembl/target_report_card/{tid}",
                identifiers={"target_chembl_id": tid},
            )
            for tid in target_chembl_ids[:3]
        ]
        or [make_source("ChEMBL", url="https://www.ebi.ac.uk/chembl/")],
    }


@mcp.tool()
def get_drug_mechanism(drug_name: str) -> dict:
    """Get mechanism of action for a drug from ChEMBL.

    Args:
        drug_name: Drug name (e.g., "imatinib", "pembrolizumab").

    Returns:
        Dictionary with mechanism of action, target, and action type.
    """
    # First search for the molecule
    mol_url = f"{CHEMBL_BASE}/molecule/search.json"
    params = {"q": drug_name, "limit": 5}
    try:
        response = httpx.get(mol_url, params=params, timeout=30)
        response.raise_for_status()
        molecules = response.json().get("molecules", [])
    except Exception:
        molecules = []

    if not molecules:
        return {
            "drug_name": drug_name,
            "error": "Drug not found in ChEMBL",
            "_sources": [make_source("ChEMBL", url="https://www.ebi.ac.uk/chembl/")],
        }

    mol_chembl_id = molecules[0].get("molecule_chembl_id")

    # Get mechanism
    mech_url = f"{CHEMBL_BASE}/mechanism.json"
    mech_params = {"molecule_chembl_id": mol_chembl_id}
    try:
        response = httpx.get(mech_url, params=mech_params, timeout=30)
        response.raise_for_status()
        mechanisms = response.json().get("mechanisms", [])
    except Exception:
        mechanisms = []

    return {
        "drug_name": drug_name,
        "molecule_chembl_id": mol_chembl_id,
        "mechanisms": [
            {
                "mechanism_of_action": m.get("mechanism_of_action"),
                "action_type": m.get("action_type"),
                "target_chembl_id": m.get("target_chembl_id"),
                "target_name": m.get("target_name"),
            }
            for m in mechanisms
        ],
        "_sources": [
            make_source(
                "ChEMBL",
                url=f"https://www.ebi.ac.uk/chembl/compound_report_card/{mol_chembl_id}",
                identifiers={"molecule_chembl_id": mol_chembl_id},
            ),
        ],
    }


@mcp.tool()
def query_fda_adverse_events(drug_name: str, limit: int = 100) -> dict:
    """Query OpenFDA for adverse event reports associated with a drug.

    Args:
        drug_name: Drug brand or generic name.
        limit: Maximum number of results. Default 100.

    Returns:
        Dictionary with adverse event counts by reaction type and organ system.
    """
    url = f"{OPENFDA_BASE}/drug/event.json"
    params = {
        "search": f'patient.drug.openfda.generic_name:"{drug_name}"',
        "count": "patient.reaction.reactionmeddrapt.exact",
        "limit": limit,
    }
    try:
        response = httpx.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])
    except Exception:
        results = []

    return {
        "drug_name": drug_name,
        "adverse_events": [{"reaction": r.get("term", ""), "count": r.get("count", 0)} for r in results],
        "total_unique_reactions": len(results),
        "_sources": [make_source("OpenFDA", url="https://open.fda.gov/apis/drug/event/")],
    }


@mcp.tool()
def get_drug_label(drug_name: str) -> dict:
    """Retrieve drug label information including black box warnings and contraindications.

    Args:
        drug_name: Drug brand or generic name.

    Returns:
        Dictionary with boxed warnings, contraindications, warnings/precautions,
        and adverse reactions from the drug label.
    """
    url = f"{OPENFDA_BASE}/drug/label.json"
    params = {
        "search": f'openfda.generic_name:"{drug_name}"',
        "limit": 1,
    }
    try:
        response = httpx.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])
    except Exception:
        results = []

    if not results:
        return {
            "drug_name": drug_name,
            "error": "Drug label not found",
            "_sources": [make_source("OpenFDA", url="https://open.fda.gov/apis/drug/label/")],
        }

    label = results[0]
    return {
        "drug_name": drug_name,
        "boxed_warning": label.get("boxed_warning", []),
        "contraindications": label.get("contraindications", []),
        "warnings_and_precautions": label.get("warnings_and_precautions", []),
        "adverse_reactions": label.get("adverse_reactions", []),
        "drug_interactions": label.get("drug_interactions", []),
        "indications_and_usage": label.get("indications_and_usage", []),
        "_sources": [
            make_source("OpenFDA", url=f"https://dailymed.nlm.nih.gov/dailymed/search.cfm?query={drug_name}"),
        ],
    }


@mcp.tool()
def search_chembl_compounds(target_id: str, activity_type: str = "IC50", max_results: int = 50) -> dict:
    """Search ChEMBL for bioactive compounds against a specific target.

    Args:
        target_id: ChEMBL target ID (e.g., "CHEMBL203").
        activity_type: Activity measurement type. Default "IC50".
        max_results: Maximum results to return. Default 50.

    Returns:
        Dictionary with compounds, activity values, and selectivity data.
    """
    url = f"{CHEMBL_BASE}/activity.json"
    params = {
        "target_chembl_id": target_id,
        "standard_type": activity_type,
        "limit": max_results,
        "pchembl_value__isnull": False,
    }
    try:
        response = httpx.get(url, params=params, timeout=30)
        response.raise_for_status()
        activities = response.json().get("activities", [])
    except Exception:
        activities = []

    compounds = [
        {
            "molecule_chembl_id": act.get("molecule_chembl_id"),
            "molecule_name": act.get("molecule_pref_name"),
            "pchembl_value": act.get("pchembl_value"),
            "standard_value": act.get("standard_value"),
            "standard_units": act.get("standard_units"),
            "assay_description": act.get("assay_description"),
        }
        for act in activities
    ]

    return {
        "target_id": target_id,
        "activity_type": activity_type,
        "compounds": compounds,
        "compound_count": len(compounds),
        "_sources": [
            make_source(
                "ChEMBL",
                url=f"https://www.ebi.ac.uk/chembl/target_report_card/{target_id}",
                identifiers={"target_chembl_id": target_id},
            ),
        ],
    }


if __name__ == "__main__":
    mcp.run()
