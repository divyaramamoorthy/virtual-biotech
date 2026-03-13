"""Diseases MCP Server — Disease ontologies, OMIM, Orphanet."""

import httpx
from fastmcp import FastMCP

mcp = FastMCP("diseases")

OT_GRAPHQL = "https://api.platform.opentargets.org/api/v4/graphql"


@mcp.tool()
def get_disease_associations(gene_symbol: str) -> dict:
    """Get disease associations for a gene from Open Targets and OMIM.

    Args:
        gene_symbol: Official gene symbol.

    Returns:
        Dictionary with associated diseases, evidence scores,
        and data source breakdown.
    """
    # Resolve gene to Ensembl ID
    search_query = """
    query SearchTarget($queryString: String!) {
        search(queryString: $queryString, entityNames: ["target"], page: {size: 1, index: 0}) {
            hits { id }
        }
    }
    """
    try:
        response = httpx.post(OT_GRAPHQL, json={"query": search_query, "variables": {"queryString": gene_symbol}}, timeout=30)
        response.raise_for_status()
        hits = response.json().get("data", {}).get("search", {}).get("hits", [])
        ensembl_id = hits[0]["id"] if hits else None
    except Exception:
        ensembl_id = None

    if not ensembl_id:
        return {"gene_symbol": gene_symbol, "error": "Gene not found"}

    # Get associated diseases
    assoc_query = """
    query AssociatedDiseases($ensemblId: String!) {
        target(ensemblId: $ensemblId) {
            approvedSymbol
            associatedDiseases(page: {size: 50, index: 0}) {
                count
                rows {
                    disease { id name therapeuticAreas { id name } }
                    score
                    datatypeScores { id score }
                }
            }
        }
    }
    """
    try:
        response = httpx.post(OT_GRAPHQL, json={"query": assoc_query, "variables": {"ensemblId": ensembl_id}}, timeout=30)
        response.raise_for_status()
        data = response.json().get("data", {}).get("target", {})
        assoc_data = data.get("associatedDiseases", {})
    except Exception:
        assoc_data = {}

    diseases = []
    for row in assoc_data.get("rows", []):
        disease = row.get("disease", {})
        diseases.append(
            {
                "disease_id": disease.get("id"),
                "disease_name": disease.get("name"),
                "therapeutic_areas": [ta.get("name") for ta in disease.get("therapeuticAreas", [])],
                "overall_score": row.get("score"),
                "datatype_scores": {dt.get("id"): dt.get("score") for dt in row.get("datatypeScores", [])},
            }
        )

    return {
        "gene_symbol": gene_symbol,
        "ensembl_id": ensembl_id,
        "total_associated_diseases": assoc_data.get("count", 0),
        "diseases": diseases,
    }


@mcp.tool()
def get_disease_ontology(disease_name: str) -> dict:
    """Get disease ontology information including EFO, MONDO, and Orphanet mappings.

    Args:
        disease_name: Disease name to search (e.g., "ulcerative colitis",
            "lung adenocarcinoma").

    Returns:
        Dictionary with disease IDs, ontology parents, synonyms,
        and cross-references.
    """
    search_query = """
    query SearchDisease($queryString: String!) {
        search(queryString: $queryString, entityNames: ["disease"], page: {size: 10, index: 0}) {
            hits {
                id
                name
                description
                entity
            }
        }
    }
    """
    try:
        response = httpx.post(OT_GRAPHQL, json={"query": search_query, "variables": {"queryString": disease_name}}, timeout=30)
        response.raise_for_status()
        hits = response.json().get("data", {}).get("search", {}).get("hits", [])
    except Exception:
        hits = []

    if not hits:
        return {"disease_name": disease_name, "error": "Disease not found"}

    disease_id = hits[0]["id"]

    # Get detailed disease info
    detail_query = """
    query DiseaseDetail($efoId: String!) {
        disease(efoId: $efoId) {
            id
            name
            description
            synonyms { terms }
            parents { id name }
            therapeuticAreas { id name }
            dbXRefs
        }
    }
    """
    try:
        response = httpx.post(OT_GRAPHQL, json={"query": detail_query, "variables": {"efoId": disease_id}}, timeout=30)
        response.raise_for_status()
        disease_data = response.json().get("data", {}).get("disease", {})
    except Exception:
        disease_data = {}

    return {
        "disease_name": disease_name,
        "disease_id": disease_data.get("id"),
        "official_name": disease_data.get("name"),
        "description": disease_data.get("description"),
        "synonyms": disease_data.get("synonyms", {}).get("terms", []),
        "parent_diseases": [{"id": p.get("id"), "name": p.get("name")} for p in disease_data.get("parents", [])],
        "therapeutic_areas": [ta.get("name") for ta in disease_data.get("therapeuticAreas", [])],
        "cross_references": disease_data.get("dbXRefs", []),
    }


if __name__ == "__main__":
    mcp.run()
