"""Spatial immune neighborhood analysis."""

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from statsmodels.regression.mixed_linear_model import MixedLM


def spatial_neighborhood_analysis(
    adata_spatial,
    gene: str,
    k: int = 6,
    min_spots: int = 25,
) -> dict[str, dict]:
    """Mixed-effects analysis of immune cell depletion near gene-expressing spots.

    For each sample:
    1. Build k-NN graph from spatial coordinates
    2. Stratify spots into top/bottom expression quartiles
    3. Compute mean neighbor immune cell abundance
    4. Fit mixed-effects model across all samples

    Args:
        adata_spatial: AnnData with spatial coordinates in obsm["spatial"]
            and Cell2Location proportions in obsm["cell2location"].
        gene: Gene symbol to analyze.
        k: Number of nearest neighbors. Default 6.
        min_spots: Minimum expressing spots per sample. Default 25.

    Returns:
        Dictionary mapping immune cell type to model results
        (beta, p-value, confidence interval).
    """
    immune_cell_types = ["T cell", "macrophage", "monocyte", "dendritic cell", "B cell"]
    results = {}

    for immune_cell_type in immune_cell_types:
        all_data = []

        for sample_id in adata_spatial.obs["sample_id"].unique():
            sample_mask = adata_spatial.obs["sample_id"] == sample_id
            sample = adata_spatial[sample_mask]

            gene_expr = sample[:, gene].X.toarray().flatten()
            expressing_mask = gene_expr > 0

            if expressing_mask.sum() < min_spots:
                continue

            coords = sample.obsm["spatial"]
            tree = cKDTree(coords)

            expr_values = gene_expr[expressing_mask]
            q75 = np.percentile(expr_values, 75)
            q25 = np.percentile(expr_values, 25)

            high_mask = gene_expr >= q75
            low_mask = (gene_expr > 0) & (gene_expr <= q25)

            # Compute z-scores for covariates
            total_umi = np.array(sample.X.sum(axis=1)).flatten()
            umi_z = (total_umi - total_umi.mean()) / (total_umi.std() + 1e-8)

            cell2loc = sample.obsm["cell2location"]
            fibroblast_vals = cell2loc["fibroblast"].values if hasattr(cell2loc, "values") else np.array(cell2loc["fibroblast"])
            epithelial_vals = cell2loc["epithelial"].values if hasattr(cell2loc, "values") else np.array(cell2loc["epithelial"])
            endothelial_vals = cell2loc["endothelial"].values if hasattr(cell2loc, "values") else np.array(cell2loc["endothelial"])

            fibroblast_z = (fibroblast_vals - fibroblast_vals.mean()) / (fibroblast_vals.std() + 1e-8)
            epithelial_z = (epithelial_vals - epithelial_vals.mean()) / (epithelial_vals.std() + 1e-8)
            endothelial_z = (endothelial_vals - endothelial_vals.mean()) / (endothelial_vals.std() + 1e-8)

            for i in range(len(sample)):
                if not (high_mask[i] or low_mask[i]):
                    continue

                _, idx = tree.query(coords[i], k=k + 1)
                neighbors = idx[1:]  # exclude self

                immune_vals = cell2loc[immune_cell_type]
                if hasattr(immune_vals, "iloc"):
                    neighbor_immune = immune_vals.iloc[neighbors].mean()
                else:
                    neighbor_immune = np.array(immune_vals)[neighbors].mean()

                all_data.append(
                    {
                        "immune_abundance": neighbor_immune,
                        "gene_high": 1 if high_mask[i] else 0,
                        "umi_z": umi_z[i],
                        "fibroblast_z": fibroblast_z[i],
                        "epithelial_z": epithelial_z[i],
                        "endothelial_z": endothelial_z[i],
                        "sample_id": sample_id,
                    }
                )

        if len(all_data) < 10:
            results[immune_cell_type] = {
                "beta_gene_high": None,
                "pvalue": None,
                "ci_lower": None,
                "ci_upper": None,
                "error": "Insufficient data",
            }
            continue

        df = pd.DataFrame(all_data)

        formula = "immune_abundance ~ gene_high + umi_z + fibroblast_z + epithelial_z + endothelial_z"
        model = MixedLM.from_formula(formula, groups="sample_id", data=df)
        result = model.fit(reml=True)

        results[immune_cell_type] = {
            "beta_gene_high": float(result.params["gene_high"]),
            "pvalue": float(result.pvalues["gene_high"]),
            "ci_lower": float(result.conf_int().loc["gene_high", 0]),
            "ci_upper": float(result.conf_int().loc["gene_high", 1]),
        }

    return results
