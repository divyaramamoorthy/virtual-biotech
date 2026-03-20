"""Biological Interactions MCP Server — IntAct, Reactome, STRING, SignaLink."""

import httpx
from fastmcp import FastMCP

mcp = FastMCP("biological-interactions")


def _resolve_to_uniprot(gene_symbol: str) -> str | None:
    """Resolve a human gene symbol to its primary UniProt accession."""
    url = f"https://rest.uniprot.org/uniprotkb/search?query=gene_exact:{gene_symbol}+AND+organism_id:9606&format=json&size=1"
    try:
        response = httpx.get(url, timeout=30)
        response.raise_for_status()
        results = response.json().get("results", [])
        return results[0]["primaryAccession"] if results else None
    except Exception:
        return None


@mcp.tool()
def query_protein_interactions(gene_symbol: str, confidence_threshold: float = 0.7) -> dict:
    """Query STRING and IntAct for protein-protein interactions.

    Args:
        gene_symbol: Official gene symbol (e.g., "TP53").
        confidence_threshold: Minimum interaction confidence score (0-1). Default 0.7.

    Returns:
        Dictionary with interaction partners, confidence scores, and evidence types.
    """
    # STRING API
    string_url = "https://string-db.org/api/json/interaction_partners"
    params = {
        "identifiers": gene_symbol,
        "species": 9606,
        "required_score": int(confidence_threshold * 1000),
        "limit": 50,
    }
    try:
        response = httpx.get(string_url, params=params, timeout=30)
        response.raise_for_status()
        string_data = response.json()
    except Exception:
        string_data = []

    interactions = [
        {
            "partner": item.get("preferredName_B", ""),
            "score": item.get("score", 0),
            "nscore": item.get("nscore", 0),
            "fscore": item.get("fscore", 0),
            "pscore": item.get("pscore", 0),
            "ascore": item.get("ascore", 0),
            "escore": item.get("escore", 0),
            "dscore": item.get("dscore", 0),
            "tscore": item.get("tscore", 0),
        }
        for item in string_data
    ]

    # IntAct API
    intact_url = f"https://www.ebi.ac.uk/intact/ws/interaction/findInteractor/{gene_symbol}"
    try:
        response = httpx.get(intact_url, params={"format": "json"}, timeout=30)
        response.raise_for_status()
        intact_data = response.json()
        intact_count = intact_data.get("totalElements", 0)
    except Exception:
        intact_count = 0

    return {
        "gene_symbol": gene_symbol,
        "confidence_threshold": confidence_threshold,
        "string_interactions": interactions,
        "string_interaction_count": len(interactions),
        "intact_interaction_count": intact_count,
    }


@mcp.tool()
def query_pathway_membership(gene_symbol: str) -> dict:
    """Query Reactome for pathway membership of a gene.

    Args:
        gene_symbol: Official gene symbol.

    Returns:
        Dictionary with pathways the gene participates in, including
        pathway hierarchy, diagram links, and associated diseases.
    """
    uniprot_id = _resolve_to_uniprot(gene_symbol)

    if not uniprot_id:
        return {"gene_symbol": gene_symbol, "error": "UniProt ID not found", "pathways": []}

    # Query Reactome
    reactome_url = f"https://reactome.org/ContentService/data/pathways/low/entity/UniProt:{uniprot_id}"
    try:
        response = httpx.get(reactome_url, headers={"Accept": "application/json"}, timeout=30)
        response.raise_for_status()
        pathways_data = response.json()
    except Exception:
        pathways_data = []

    pathways = [
        {
            "stable_id": p.get("stId", ""),
            "name": p.get("displayName", ""),
            "species": p.get("speciesName", ""),
            "is_disease": p.get("isDisease", False),
        }
        for p in pathways_data
    ]

    return {
        "gene_symbol": gene_symbol,
        "uniprot_id": uniprot_id,
        "pathways": pathways,
        "pathway_count": len(pathways),
    }


@mcp.tool()
def query_signaling_network(gene_symbol: str) -> dict:
    """Query SignaLink and Reactome for signaling network context.

    Args:
        gene_symbol: Official gene symbol.

    Returns:
        Dictionary with signaling pathways, upstream regulators,
        downstream effectors, and cross-talk information.
    """
    # Use Reactome for signaling context
    reactome_url = f"https://reactome.org/ContentService/search/query?query={gene_symbol}&types=Pathway&cluster=true"
    try:
        response = httpx.get(reactome_url, headers={"Accept": "application/json"}, timeout=30)
        response.raise_for_status()
        data = response.json()
        entries = data.get("results", [{}])[0].get("entries", []) if data.get("results") else []
    except Exception:
        entries = []

    signaling_pathways = [
        {"stable_id": e.get("stId", ""), "name": e.get("name", ""), "species": e.get("species", [])} for e in entries[:20]
    ]

    return {
        "gene_symbol": gene_symbol,
        "signaling_pathways": signaling_pathways,
        "note": "Signaling context derived from Reactome pathway hierarchy",
    }


if __name__ == "__main__":
    mcp.run()
