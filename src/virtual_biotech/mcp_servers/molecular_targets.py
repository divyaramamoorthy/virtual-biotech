"""Molecular Targets MCP Server — Mouse KO phenotypes, HPA, tractability, chemical probes."""

import httpx
from fastmcp import FastMCP

from virtual_biotech.mcp_servers._sources import make_source

mcp = FastMCP("molecular-targets")

OT_GRAPHQL = "https://api.platform.opentargets.org/api/v4/graphql"


def _ot_search_ensembl(gene_symbol: str) -> str | None:
    """Resolve a gene symbol to its Ensembl ID via Open Targets."""
    query = """
    query SearchTarget($queryString: String!) {
        search(queryString: $queryString, entityNames: ["target"], page: {size: 1, index: 0}) {
            hits { id }
        }
    }
    """
    try:
        response = httpx.post(OT_GRAPHQL, json={"query": query, "variables": {"queryString": gene_symbol}}, timeout=30)
        response.raise_for_status()
        hits = response.json().get("data", {}).get("search", {}).get("hits", [])
        return hits[0]["id"] if hits else None
    except Exception:
        return None


@mcp.tool()
def get_protein_atlas_summary(gene_symbol: str) -> dict:
    """Get Human Protein Atlas summary including subcellular localization and expression.

    Args:
        gene_symbol: Official gene symbol.

    Returns:
        Dictionary with subcellular localization, tissue expression,
        RNA expression, and protein expression data.
    """
    url = f"https://www.proteinatlas.org/{gene_symbol}.json"
    try:
        response = httpx.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception:
        # Try alternative Ensembl-based lookup
        data = {}

    if not data:
        # Use Open Targets for protein info
        query = """
        query TargetInfo($symbol: String!) {
            search(queryString: $symbol, entityNames: ["target"], page: {size: 1, index: 0}) {
                hits { id name description entity }
            }
        }
        """
        try:
            response = httpx.post(OT_GRAPHQL, json={"query": query, "variables": {"symbol": gene_symbol}}, timeout=30)
            response.raise_for_status()
            hits = response.json().get("data", {}).get("search", {}).get("hits", [])
            if hits:
                data = {"source": "open_targets", "info": hits[0]}
        except Exception:
            pass

    return {
        "gene_symbol": gene_symbol,
        "protein_atlas_data": data,
        "_sources": [
            make_source("Human Protein Atlas", url=f"https://www.proteinatlas.org/{gene_symbol}"),
            make_source("Open Targets Platform", url="https://platform.opentargets.org"),
        ],
    }


@mcp.tool()
def get_tractability_assessment(gene_symbol: str) -> dict:
    """Assess target tractability for different modalities.

    Args:
        gene_symbol: Official gene symbol.

    Returns:
        Dictionary with tractability assessments for small molecule,
        antibody, PROTAC, and other modalities.
    """
    ensembl_id = _ot_search_ensembl(gene_symbol)

    if not ensembl_id:
        return {
            "gene_symbol": gene_symbol,
            "error": "Target not found",
            "_sources": [make_source("Open Targets Platform", url="https://platform.opentargets.org")],
        }

    # Get tractability data
    tract_query = """
    query TargetTractability($ensemblId: String!) {
        target(ensemblId: $ensemblId) {
            approvedSymbol
            tractability {
                label
                modality
                value
            }
        }
    }
    """
    try:
        response = httpx.post(OT_GRAPHQL, json={"query": tract_query, "variables": {"ensemblId": ensembl_id}}, timeout=30)
        response.raise_for_status()
        target_data = response.json().get("data", {}).get("target", {})
        tractability = target_data.get("tractability", [])
    except Exception:
        tractability = []

    # Organize by modality
    by_modality: dict[str, list[dict]] = {}
    for t in tractability:
        by_modality.setdefault(t.get("modality", "unknown"), []).append({"label": t.get("label"), "value": t.get("value")})

    return {
        "gene_symbol": gene_symbol,
        "ensembl_id": ensembl_id,
        "tractability_by_modality": by_modality,
        "_sources": [
            make_source(
                "Open Targets Platform", url=f"https://platform.opentargets.org/target/{ensembl_id}", identifiers={"ensembl_id": ensembl_id}
            )
        ],
    }


@mcp.tool()
def get_mouse_ko_phenotypes(gene_symbol: str) -> dict:
    """Get mouse knockout phenotype data from IMPC/MGI.

    Args:
        gene_symbol: Official gene symbol (human).

    Returns:
        Dictionary with mouse KO phenotypes, viability, and organ-level effects.
    """
    # Query IMPC (International Mouse Phenotyping Consortium)
    url = "https://www.ebi.ac.uk/mi/impc/solr/genotype-phenotype/select"
    params = {
        "q": f'marker_symbol:"{gene_symbol}"',
        "rows": 100,
        "wt": "json",
    }
    try:
        response = httpx.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        docs = data.get("response", {}).get("docs", [])
    except Exception:
        docs = []

    phenotypes = [
        {
            "mp_term_name": doc.get("mp_term_name"),
            "mp_term_id": doc.get("mp_term_id"),
            "top_level_mp_term": doc.get("top_level_mp_term_name"),
            "p_value": doc.get("p_value"),
            "effect_size": doc.get("effect_size"),
            "zygosity": doc.get("zygosity"),
        }
        for doc in docs
    ]

    return {
        "gene_symbol": gene_symbol,
        "phenotypes": phenotypes,
        "phenotype_count": len(phenotypes),
        "_sources": [make_source("IMPC", url=f"https://www.mousephenotype.org/data/genes/{gene_symbol}")],
    }


@mcp.tool()
def get_chemical_probes(gene_symbol: str) -> dict:
    """Get high-quality chemical probes for a target from Probes & Drugs.

    Args:
        gene_symbol: Official gene symbol.

    Returns:
        Dictionary with recommended probes, selectivity data, and usage notes.
    """
    ensembl_id = _ot_search_ensembl(gene_symbol)

    if not ensembl_id:
        return {
            "gene_symbol": gene_symbol,
            "error": "Target not found",
            "_sources": [make_source("Open Targets Platform", url="https://platform.opentargets.org")],
        }

    probe_query = """
    query TargetProbes($ensemblId: String!) {
        target(ensemblId: $ensemblId) {
            approvedSymbol
            chemicalProbes {
                rows {
                    chemicalProbe
                    isHighQuality
                    mechanismOfAction
                    urls { niceName url }
                }
            }
        }
    }
    """
    try:
        response = httpx.post(OT_GRAPHQL, json={"query": probe_query, "variables": {"ensemblId": ensembl_id}}, timeout=30)
        response.raise_for_status()
        target_data = response.json().get("data", {}).get("target", {})
        probes = target_data.get("chemicalProbes", {}).get("rows", [])
    except Exception:
        probes = []

    return {
        "gene_symbol": gene_symbol,
        "ensembl_id": ensembl_id,
        "chemical_probes": probes,
        "probe_count": len(probes),
        "_sources": [
            make_source(
                "Open Targets Platform", url=f"https://platform.opentargets.org/target/{ensembl_id}", identifiers={"ensembl_id": ensembl_id}
            )
        ],
    }


if __name__ == "__main__":
    mcp.run()
