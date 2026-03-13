"""Single Cell Atlas MCP Server — CELLxGENE Census API, Tabula Sapiens v2."""

from pathlib import Path

import numpy as np
from fastmcp import FastMCP

mcp = FastMCP("single-cell-atlas")


@mcp.tool()
def query_cellxgene_census(
    gene_symbol: str,
    tissue: str | None = None,
    disease: str | None = None,
    organism: str = "Homo sapiens",
) -> dict:
    """Query CELLxGENE Census for single-cell expression data.

    Returns cell-type resolved expression profiles for a gene across
    tissues and conditions. Can filter by tissue, disease state, or organism.

    Args:
        gene_symbol: Gene to query (e.g., "CD276", "OSMR").
        tissue: Filter by tissue (e.g., "lung", "colon").
        disease: Filter by disease (e.g., "lung adenocarcinoma", "ulcerative colitis").
        organism: Species. Default "Homo sapiens".
    """
    import cellxgene_census

    with cellxgene_census.open_soma() as census:
        # Build value filter
        filters = ["is_primary_data == True"]
        if tissue:
            filters.append(f'tissue_general == "{tissue}"')
        if disease:
            filters.append(f'disease == "{disease}"')

        value_filter = " and ".join(filters)

        # Query expression data
        adata = cellxgene_census.get_anndata(
            census,
            organism=organism,
            var_value_filter=f'feature_name == "{gene_symbol}"',
            obs_value_filter=value_filter,
            obs_column_names=["cell_type", "tissue", "disease", "donor_id"],
        )

    if adata.n_obs == 0:
        return {"gene_symbol": gene_symbol, "error": "No data found", "cell_types": {}}

    # Compute per-cell-type statistics
    cell_type_stats = {}
    for ct in adata.obs["cell_type"].unique():
        mask = adata.obs["cell_type"] == ct
        n_cells = int(mask.sum())
        if n_cells < 20:
            continue
        expr = adata[mask].X.toarray().flatten()
        cell_type_stats[ct] = {
            "n_cells": n_cells,
            "mean_expression": float(np.mean(expr)),
            "fraction_expressing": float(np.mean(expr > 0)),
            "median_expression": float(np.median(expr[expr > 0])) if np.any(expr > 0) else 0.0,
        }

    return {
        "gene_symbol": gene_symbol,
        "organism": organism,
        "tissue": tissue,
        "disease": disease,
        "total_cells": int(adata.n_obs),
        "cell_types": cell_type_stats,
    }


@mcp.tool()
def download_atlas(
    tissue: str,
    disease: str | None = None,
    max_cells: int = 500000,
) -> str:
    """Download a single-cell atlas from CELLxGENE Census as AnnData.

    Returns path to the downloaded .h5ad file for downstream analysis.

    Args:
        tissue: Tissue to download (e.g., "lung", "colon").
        disease: Optional disease filter.
        max_cells: Maximum number of cells to download. Default 500,000.
    """
    import cellxgene_census

    with cellxgene_census.open_soma() as census:
        filters = ["is_primary_data == True", f'tissue_general == "{tissue}"']
        if disease:
            filters.append(f'disease == "{disease}"')

        value_filter = " and ".join(filters)

        adata = cellxgene_census.get_anndata(
            census,
            organism="Homo sapiens",
            obs_value_filter=value_filter,
            obs_column_names=[
                "cell_type",
                "tissue",
                "disease",
                "donor_id",
                "assay",
                "sex",
                "development_stage",
            ],
        )

    # Subsample if too large
    if adata.n_obs > max_cells:
        import scanpy as sc

        sc.pp.subsample(adata, n_obs=max_cells)

    output_dir = Path("data/atlases")
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{tissue}"
    if disease:
        filename += f"_{disease.replace(' ', '_')}"
    filename += ".h5ad"
    output_path = output_dir / filename

    adata.write_h5ad(output_path)
    return str(output_path)


@mcp.tool()
def compute_tau_specificity(gene_symbol: str, adata_path: str) -> dict:
    """Compute tau cell-type specificity index for a gene across cell types.

    Tau ranges from 0 (ubiquitous) to 1 (perfectly cell-type specific).
    Excludes cell types with <20 cells. Uses log-normalized counts.

    Args:
        gene_symbol: Gene symbol to compute tau for.
        adata_path: Path to .h5ad file with log-normalized expression data.
    """
    import scanpy as sc

    from virtual_biotech.analysis.specificity import compute_tau

    adata = sc.read_h5ad(adata_path)

    if gene_symbol not in adata.var_names:
        return {"gene_symbol": gene_symbol, "error": "Gene not found in dataset"}

    mean_per_ct = {}
    for ct in adata.obs["cell_type"].unique():
        mask = adata.obs["cell_type"] == ct
        if mask.sum() < 20:
            continue
        expr = adata[mask, gene_symbol].X.toarray().flatten()
        mean_per_ct[ct] = float(np.mean(expr))

    if not mean_per_ct:
        return {"gene_symbol": gene_symbol, "error": "No cell types with >=20 cells"}

    values = np.array(list(mean_per_ct.values()))
    tau = compute_tau(values)

    # Find top expressing cell type
    top_ct = max(mean_per_ct, key=mean_per_ct.get)

    return {
        "gene_symbol": gene_symbol,
        "tau": tau,
        "n_cell_types": len(mean_per_ct),
        "top_cell_type": top_ct,
        "top_cell_type_mean_expression": mean_per_ct[top_ct],
        "cell_type_means": mean_per_ct,
    }


@mcp.tool()
def compute_bimodality(gene_symbol: str, adata_path: str) -> dict:
    """Compute expression bimodality coefficient across cell types.

    BC > 0.555 suggests bimodal distribution. Computed only among
    expressing cells (expression > 0).

    Args:
        gene_symbol: Gene symbol.
        adata_path: Path to .h5ad file.
    """
    import scanpy as sc

    from virtual_biotech.analysis.specificity import compute_bimodality_coefficient

    adata = sc.read_h5ad(adata_path)

    if gene_symbol not in adata.var_names:
        return {"gene_symbol": gene_symbol, "error": "Gene not found in dataset"}

    bc_per_ct = {}
    for ct in adata.obs["cell_type"].unique():
        mask = adata.obs["cell_type"] == ct
        if mask.sum() < 20:
            continue
        expr = adata[mask, gene_symbol].X.toarray().flatten()
        bc = compute_bimodality_coefficient(expr)
        bc_per_ct[ct] = {
            "bimodality_coefficient": bc,
            "is_bimodal": bc > 0.555,
            "n_expressing": int(np.sum(expr > 0)),
            "fraction_expressing": float(np.mean(expr > 0)),
        }

    return {
        "gene_symbol": gene_symbol,
        "cell_type_bimodality": bc_per_ct,
    }


if __name__ == "__main__":
    mcp.run()
