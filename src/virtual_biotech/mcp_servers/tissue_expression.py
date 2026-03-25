"""Tissue Expression MCP Server — GTEx v8."""

import httpx
from fastmcp import FastMCP

from virtual_biotech.mcp_servers._sources import make_source

mcp = FastMCP("tissue-expression")

GTEX_BASE = "https://gtexportal.org/api/v2"


@mcp.tool()
def query_tissue_expression(gene_symbol: str) -> dict:
    """Query GTEx v8 for median TPM expression across 54 tissues.

    Args:
        gene_symbol: Official gene symbol (e.g., "TP53", "BRCA1").

    Returns:
        Dictionary with median TPM per tissue, sorted by expression level,
        plus tissue specificity summary.
    """
    url = f"{GTEX_BASE}/expression/medianGeneExpression"
    params = {
        "gencodeId": gene_symbol,
        "datasetId": "gtex_v8",
    }

    # First try with gene symbol directly
    try:
        response = httpx.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception:
        data = {}

    # If no results, search for the gene first
    if not data.get("medianGeneExpression"):
        search_url = f"{GTEX_BASE}/reference/gene"
        search_params = {"geneId": gene_symbol, "datasetId": "gtex_v8"}
        try:
            response = httpx.get(search_url, params=search_params, timeout=30)
            response.raise_for_status()
            gene_data = response.json()
            genes = gene_data.get("gene", [])
            if genes:
                gencode_id = genes[0].get("gencodeId", "")
                params["gencodeId"] = gencode_id
                response = httpx.get(url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
        except Exception:
            pass

    expression_data = data.get("medianGeneExpression", [])

    tissue_expression = {}
    for entry in expression_data:
        tissue = entry.get("tissueSiteDetailId", "")
        median_tpm = entry.get("median", 0)
        tissue_expression[tissue] = median_tpm

    # Sort by expression level
    sorted_tissues = dict(sorted(tissue_expression.items(), key=lambda x: x[1], reverse=True))

    # Compute simple stats
    values = list(tissue_expression.values())
    max_expr = max(values) if values else 0
    mean_expr = sum(values) / len(values) if values else 0
    expressing_tissues = sum(1 for v in values if v > 1.0)

    return {
        "gene_symbol": gene_symbol,
        "tissue_expression_tpm": sorted_tissues,
        "n_tissues": len(tissue_expression),
        "max_tpm": max_expr,
        "mean_tpm": mean_expr,
        "expressing_tissues_above_1tpm": expressing_tissues,
        "_sources": [make_source("GTEx Portal", url=f"https://gtexportal.org/home/gene/{gene_symbol}", version="v8")],
    }


if __name__ == "__main__":
    mcp.run()
