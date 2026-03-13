"""Spatial transcriptomics analysis workflow."""

SPATIAL_ANALYSIS_WORKFLOW = """
# Spatial Transcriptomics Analysis Workflow

## Step 1: Cell2Location Deconvolution

### Train Reference Model
```python
import cell2location
import scanpy as sc

# Prepare reference single-cell data
sc_adata = sc.read_h5ad("reference_atlas.h5ad")

# CRITICAL: Exclude gene of interest from deconvolution to avoid circularity
genes_to_exclude = ["GENE_OF_INTEREST"]
sc_adata = sc_adata[:, ~sc_adata.var_names.isin(genes_to_exclude)].copy()

# Train reference model (250 epochs)
cell2location.models.RegressionModel.setup_anndata(
    sc_adata, labels_key="cell_type"
)
ref_model = cell2location.models.RegressionModel(sc_adata)
ref_model.train(max_epochs=250, use_gpu=True)

# Export reference signatures
adata_ref = ref_model.export_posterior(
    sc_adata, sample_kwargs={"num_samples": 1000, "batch_size": 2500}
)
```

### Spatial Mapping
```python
# Prepare spatial data
sp_adata = sc.read_h5ad("spatial_data.h5ad")

# Train spatial mapping model (10,000 epochs)
cell2location.models.Cell2location.setup_anndata(sp_adata)
sp_model = cell2location.models.Cell2location(
    sp_adata,
    cell_state_df=adata_ref.uns["mod"]["factor_names"],
    N_cells_per_location=8,  # Expected 8 cells per spot
)
sp_model.train(max_epochs=10000, use_gpu=True)

# Export results
sp_adata = sp_model.export_posterior(
    sp_adata, sample_kwargs={"num_samples": 1000, "batch_size": 2500}
)
# Cell type proportions stored in sp_adata.obsm["q05_cell_abundance_w_sf"]
```

## Step 2: Neighborhood Analysis (k=6 NN)
```python
import numpy as np
from scipy.spatial import cKDTree

def compute_neighborhood_composition(sp_adata, k=6):
    \"\"\"Compute mean cell type composition in k-NN neighborhoods.\"\"\"
    coords = sp_adata.obsm["spatial"]
    tree = cKDTree(coords)
    cell_type_cols = sp_adata.obsm["q05_cell_abundance_w_sf"]

    neighborhood_means = np.zeros_like(cell_type_cols)
    for i in range(len(sp_adata)):
        _, idx = tree.query(coords[i], k=k+1)
        neighbors = idx[1:]  # Exclude self
        neighborhood_means[i] = cell_type_cols[neighbors].mean(axis=0)

    sp_adata.obsm["neighborhood_composition"] = neighborhood_means
    return sp_adata

sp_adata = compute_neighborhood_composition(sp_adata)
```

## Step 3: Expression Quartile Stratification
```python
def stratify_by_expression(sp_adata, gene):
    \"\"\"Stratify spots into high/low expression quartiles.\"\"\"
    expr = sp_adata[:, gene].X.toarray().flatten()
    expressing = expr > 0

    if expressing.sum() < 25:
        raise ValueError(f"Too few expressing spots ({expressing.sum()}) for {gene}")

    q75 = np.percentile(expr[expressing], 75)
    q25 = np.percentile(expr[expressing], 25)

    sp_adata.obs[f"{gene}_quartile"] = "middle"
    sp_adata.obs.loc[expr >= q75, f"{gene}_quartile"] = "high"
    sp_adata.obs.loc[(expr > 0) & (expr <= q25), f"{gene}_quartile"] = "low"

    return sp_adata
```

## Step 4: Mixed-Effects Model for Immune Depletion
```python
import statsmodels.api as sm
from statsmodels.regression.mixed_linear_model import MixedLM
import pandas as pd

# See virtual_biotech.analysis.spatial.spatial_neighborhood_analysis()
# for the full implementation with covariates:
# - gene_high (binary: top quartile vs bottom quartile)
# - umi_z (z-scored total UMI count)
# - fibroblast_z (z-scored fibroblast proportion)
# - epithelial_z (z-scored epithelial proportion)
# - endothelial_z (z-scored endothelial proportion)
# - sample_id (random intercept)

# Formula:
# immune_abundance ~ gene_high + umi_z + fibroblast_z + epithelial_z + endothelial_z
# with random intercept for sample_id

# A negative beta for gene_high indicates immune depletion near
# high-expressing spots (consistent with immune exclusion).
```
"""


def get_spatial_workflow() -> str:
    """Return the spatial analysis workflow as a string."""
    return SPATIAL_ANALYSIS_WORKFLOW
