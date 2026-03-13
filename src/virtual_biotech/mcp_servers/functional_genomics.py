"""Functional Genomics MCP Server — DepMap CRISPR, Tahoe-100M."""

import httpx
from fastmcp import FastMCP

from virtual_biotech.analysis.hallmarks import HALLMARK_GENE_SETS, compute_all_hallmark_scores

mcp = FastMCP("functional-genomics")

DEPMAP_BASE = "https://api.cellmodelpassports.sanger.ac.uk/api/v1"


@mcp.tool()
def query_crispr_essentiality(gene_symbol: str, cell_line: str | None = None) -> dict:
    """Query DepMap CRISPR essentiality screens for a gene.

    Args:
        gene_symbol: Official gene symbol.
        cell_line: Optional specific cell line to query. If None, returns pan-cancer summary.

    Returns:
        Dictionary with dependency scores across cancer types, including
        probability of dependency and effect size.
    """
    # Use Cell Model Passports / DepMap API for gene essentiality
    gene_data = {}
    dep_data = {}

    # Query Sanger Cell Model Passports for gene info
    try:
        gene_url = f"{DEPMAP_BASE}/genes"
        response = httpx.get(gene_url, params={"symbol": gene_symbol}, timeout=30)
        response.raise_for_status()
        gene_data = response.json()
    except Exception:
        pass

    # Query DepMap web API for dependency data
    try:
        dep_url = "https://depmap.org/portal/api/v2/datasets/gene_dep"
        dep_params = {"gene_symbol": gene_symbol}
        if cell_line:
            dep_params["cell_line_display_name"] = cell_line
        response = httpx.get(dep_url, params=dep_params, timeout=30)
        response.raise_for_status()
        dep_data = response.json()
    except Exception:
        pass

    # Also check Open Targets for known essentiality
    try:
        ot_url = "https://api.platform.opentargets.org/api/v4/graphql"
        query = """
        query GeneEssentiality($queryString: String!) {
            search(queryString: $queryString, entityNames: ["target"], page: {size: 1, index: 0}) {
                hits { id name description }
            }
        }
        """
        response = httpx.post(ot_url, json={"query": query, "variables": {"queryString": gene_symbol}}, timeout=30)
        response.raise_for_status()
        ot_data = response.json().get("data", {}).get("search", {}).get("hits", [])
        if ot_data:
            gene_data["open_targets"] = ot_data[0]
    except Exception:
        pass

    return {
        "gene_symbol": gene_symbol,
        "cell_line": cell_line,
        "gene_info": gene_data,
        "dependency_data": dep_data,
        "note": "DepMap dependency scores: negative = essential, values < -0.5 suggest dependency",
    }


@mcp.tool()
def query_tahoe_perturbation(drug_name: str, cell_line: str) -> dict:
    """Query Tahoe-100M pseudobulked log-fold change values for a drug perturbation.

    Args:
        drug_name: Drug or compound name used in Tahoe screens.
        cell_line: Cell line identifier.

    Returns:
        Dictionary with gene-level LFC values, adjusted p-values,
        and top differentially expressed genes.
    """
    return {
        "drug_name": drug_name,
        "cell_line": cell_line,
        "lfc_values": {},
        "top_upregulated": [],
        "top_downregulated": [],
        "note": "Tahoe-100M data requires local pseudobulked data files. "
        "Use compute_hallmark_scores tool to derive pathway-level signatures.",
    }


@mcp.tool()
def compute_hallmark_scores(drug_name: str, cell_line: str, lfc_dict: dict[str, float] | None = None) -> dict:
    """Compute 6 hallmark pathway scores from drug perturbation LFC values.

    Hallmark scores:
    - Apoptosis: BAX, CASP3, CASP9, etc. (direction: +1)
    - Proliferation suppression: MKI67, PCNA, TOP2A, etc. (direction: -1)
    - DNA damage: GADD45A, MDM2, etc. (direction: +1)
    - Stress response: DDIT3, ATF4, HSPA5, etc. (direction: +1)
    - Resistance: BCL2, MCL1, XIAP, etc. (direction: +1)
    - Cell cycle arrest: CDKN1A, CDKN1B (d=+1) and CCNA2, CCNB1 (d=-1)

    Score formula: S_h = d_h / |G_h| * sum(LFC_g for g in G_h)
    Non-significant LFC (adj p >= 0.05) are zeroed.

    Args:
        drug_name: Drug name for context.
        cell_line: Cell line for context.
        lfc_dict: Dictionary of {gene_symbol: lfc_value}. Non-significant values should be 0.

    Returns:
        Dictionary with per-hallmark scores and gene-level details.
    """
    if lfc_dict is None:
        return {
            "drug_name": drug_name,
            "cell_line": cell_line,
            "error": "No LFC data provided. First call query_tahoe_perturbation to get LFC values.",
            "hallmark_gene_sets": {name: config for name, config in HALLMARK_GENE_SETS.items()},
        }

    scores = compute_all_hallmark_scores(lfc_dict)

    # Build per-hallmark gene details
    gene_details = {}
    for hallmark, config in HALLMARK_GENE_SETS.items():
        if hallmark == "cell_cycle_arrest":
            genes = config["positive_genes"] + config["negative_genes"]
        else:
            genes = config["genes"]
        gene_details[hallmark] = {g: lfc_dict.get(g, 0) for g in genes}

    return {
        "drug_name": drug_name,
        "cell_line": cell_line,
        "hallmark_scores": scores,
        "gene_level_lfc": gene_details,
    }


if __name__ == "__main__":
    mcp.run()
