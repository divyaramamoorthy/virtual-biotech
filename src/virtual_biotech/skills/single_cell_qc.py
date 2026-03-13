"""Progressive QC workflow guidance for single-cell analysis."""

SINGLE_CELL_QC_WORKFLOW = """
# Single-Cell RNA-seq Quality Control Workflow

## Step 1: Initial Filtering
Filter cells based on gene count and mitochondrial content:
```python
import scanpy as sc

# Calculate QC metrics
adata.var["mt"] = adata.var_names.str.startswith("MT-")
sc.pp.calculate_qc_metrics(adata, qc_vars=["mt"], inplace=True)

# Filter cells
sc.pp.filter_cells(adata, min_genes=300)
sc.pp.filter_cells(adata, max_genes=9000)
adata = adata[adata.obs["pct_counts_mt"] <= 15].copy()
```

## Step 2: Donor-Level Downsampling
Subsample to max 10,000 cells per donor, stratified by cell type:
```python
import pandas as pd

def downsample_by_donor(adata, max_cells=10000, stratify_col="cell_type"):
    keep_idx = []
    for donor in adata.obs["donor_id"].unique():
        donor_mask = adata.obs["donor_id"] == donor
        donor_data = adata.obs[donor_mask]
        if len(donor_data) <= max_cells:
            keep_idx.extend(donor_data.index.tolist())
        else:
            sampled = donor_data.groupby(stratify_col, group_keys=False).apply(
                lambda x: x.sample(
                    n=min(len(x), int(max_cells * len(x) / len(donor_data))),
                    random_state=42
                )
            )
            keep_idx.extend(sampled.index.tolist())
    return adata[keep_idx].copy()

adata = downsample_by_donor(adata)
```

## Step 3: Normalization
Library-size normalization and log transformation:
```python
sc.pp.normalize_total(adata, target_sum=1e4)
sc.pp.log1p(adata)
```

## Step 4: Highly Variable Gene Selection
Select 3,000 HVGs:
```python
sc.pp.highly_variable_genes(adata, n_top_genes=3000, flavor="seurat_v3")
```

## Step 5: PCA
Compute 50 principal components:
```python
sc.tl.pca(adata, n_comps=50, use_highly_variable=True)
```

## Step 6: Batch Correction with Harmony
```python
import harmonypy

harmony_out = harmonypy.run_harmony(
    adata.obsm["X_pca"],
    adata.obs,
    "donor_id",
    max_iter_harmony=20
)
adata.obsm["X_pca_harmony"] = harmony_out.Z_corr.T
```

## Step 7: UMAP
Compute UMAP on Harmony-corrected PCs:
```python
sc.pp.neighbors(adata, use_rep="X_pca_harmony", n_neighbors=15)
sc.tl.umap(adata)
```

## Step 8: Cell Type Annotation Harmonization
Harmonize annotations to Cell Ontology terms:
```python
# Map dataset-specific annotations to Cell Ontology
# This is dataset-dependent and should be done with reference to
# the Cell Ontology (CL) hierarchy
```
"""


def get_qc_workflow() -> str:
    """Return the progressive QC workflow as a string."""
    return SINGLE_CELL_QC_WORKFLOW
