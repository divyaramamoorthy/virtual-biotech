"""Biological Pathways MCP Server — Reactome, Gene Ontology."""

import httpx
from fastmcp import FastMCP

mcp = FastMCP("biological-pathways")


@mcp.tool()
def get_reactome_pathways(gene_symbol: str) -> dict:
    """Get Reactome pathway annotations for a gene.

    Args:
        gene_symbol: Official gene symbol.

    Returns:
        Dictionary with pathway hierarchy, top-level categories,
        and pathway details.
    """
    # Resolve to UniProt
    uniprot_url = f"https://rest.uniprot.org/uniprotkb/search?query=gene_exact:{gene_symbol}+AND+organism_id:9606&format=json&size=1"
    try:
        response = httpx.get(uniprot_url, timeout=30)
        response.raise_for_status()
        results = response.json().get("results", [])
        uniprot_id = results[0]["primaryAccession"] if results else None
    except Exception:
        uniprot_id = None

    if not uniprot_id:
        return {"gene_symbol": gene_symbol, "error": "UniProt ID not found"}

    # Get pathways
    reactome_url = f"https://reactome.org/ContentService/data/pathways/low/entity/UniProt:{uniprot_id}"
    try:
        response = httpx.get(reactome_url, headers={"Accept": "application/json"}, timeout=30)
        response.raise_for_status()
        pathways = response.json()
    except Exception:
        pathways = []

    # Get top-level pathways
    top_level = set()
    pathway_details = []
    for p in pathways:
        pathway_details.append(
            {
                "id": p.get("stId", ""),
                "name": p.get("displayName", ""),
                "is_disease": p.get("isDisease", False),
            }
        )
        # Try to get top-level parent
        try:
            hier_url = f"https://reactome.org/ContentService/data/pathways/top/{p.get('stId', '')}"
            hier_resp = httpx.get(hier_url, headers={"Accept": "application/json"}, timeout=10)
            if hier_resp.status_code == 200:
                for parent in hier_resp.json():
                    top_level.add(parent.get("displayName", ""))
        except Exception:
            pass

    return {
        "gene_symbol": gene_symbol,
        "uniprot_id": uniprot_id,
        "pathways": pathway_details,
        "top_level_categories": list(top_level),
        "total_pathways": len(pathway_details),
    }


@mcp.tool()
def get_gene_ontology(gene_symbol: str) -> dict:
    """Get Gene Ontology annotations for a gene.

    Args:
        gene_symbol: Official gene symbol.

    Returns:
        Dictionary with GO terms organized by ontology aspect
        (biological process, molecular function, cellular component).
    """
    url = "https://www.ebi.ac.uk/QuickGO/services/annotation/search"
    params = {
        "geneProductId": gene_symbol,
        "taxonId": "9606",
        "limit": 100,
    }
    try:
        response = httpx.get(url, params=params, headers={"Accept": "application/json"}, timeout=30)
        response.raise_for_status()
        data = response.json()
        annotations = data.get("results", [])
    except Exception:
        annotations = []

    go_terms: dict[str, list[dict]] = {
        "biological_process": [],
        "molecular_function": [],
        "cellular_component": [],
    }
    seen = set()

    for ann in annotations:
        go_id = ann.get("goId", "")
        if go_id in seen:
            continue
        seen.add(go_id)

        aspect = ann.get("goAspect", "")
        aspect_key = {
            "biological_process": "biological_process",
            "molecular_function": "molecular_function",
            "cellular_component": "cellular_component",
        }.get(aspect, "")

        if aspect_key:
            go_terms[aspect_key].append(
                {
                    "go_id": go_id,
                    "name": ann.get("goName", ""),
                    "evidence": ann.get("goEvidence", ""),
                    "qualifier": ann.get("qualifier", ""),
                }
            )

    return {
        "gene_symbol": gene_symbol,
        "go_annotations": go_terms,
        "total_annotations": sum(len(v) for v in go_terms.values()),
    }


@mcp.tool()
def get_pathway_enrichment(gene_list: list[str]) -> dict:
    """Run Reactome pathway enrichment analysis on a gene list.

    Args:
        gene_list: List of gene symbols to analyze for pathway enrichment.

    Returns:
        Dictionary with enriched pathways, p-values, and FDR corrections.
    """
    url = "https://reactome.org/AnalysisService/identifiers/projection/"
    payload = "\n".join(gene_list)
    try:
        response = httpx.post(
            url,
            content=payload,
            headers={"Content-Type": "text/plain", "Accept": "application/json"},
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        return {"gene_list": gene_list, "error": str(e)}

    pathways = []
    for p in data.get("pathways", [])[:30]:
        pathways.append(
            {
                "stable_id": p.get("stId", ""),
                "name": p.get("name", ""),
                "p_value": p.get("entities", {}).get("pValue"),
                "fdr": p.get("entities", {}).get("fdr"),
                "found": p.get("entities", {}).get("found"),
                "total": p.get("entities", {}).get("total"),
            }
        )

    return {
        "gene_list": gene_list,
        "enriched_pathways": pathways,
        "total_enriched": len(data.get("pathways", [])),
    }


if __name__ == "__main__":
    mcp.run()
