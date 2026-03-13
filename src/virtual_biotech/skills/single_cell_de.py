"""Pseudobulk differential expression analysis workflow."""

PSEUDOBULK_DE_WORKFLOW = """
# Pseudobulk Differential Expression Analysis Workflow

## Prerequisites
- QC-filtered and normalized AnnData object
- Cell type annotations in `adata.obs["cell_type"]`
- Donor/sample IDs in `adata.obs["donor_id"]`
- Condition labels in `adata.obs["condition"]` (e.g., "disease" vs "normal")

## Step 1: Pseudobulk Aggregation
Aggregate raw counts by donor and cell type:
```python
import pandas as pd
import numpy as np
import anndata

def create_pseudobulk(adata, groupby_cols=["donor_id", "cell_type", "condition"]):
    \"\"\"Aggregate raw counts into pseudobulk samples.\"\"\"
    pseudobulk_data = []
    pseudobulk_obs = []

    for name, group in adata.obs.groupby(groupby_cols):
        if len(group) < 20:  # Minimum 20 cells
            continue

        donor, cell_type, condition = name
        counts = adata[group.index].X.toarray().sum(axis=0)

        pseudobulk_data.append(counts)
        pseudobulk_obs.append({
            "donor_id": donor,
            "cell_type": cell_type,
            "condition": condition,
            "n_cells": len(group),
        })

    pb_adata = anndata.AnnData(
        X=np.array(pseudobulk_data),
        obs=pd.DataFrame(pseudobulk_obs),
        var=adata.var.copy(),
    )
    return pb_adata

pb = create_pseudobulk(adata)
```

## Step 2: Filter Pseudobulk Samples
Ensure sufficient donors per condition:
```python
def filter_pseudobulk(pb, min_donors=3):
    \"\"\"Keep cell types with >=min_donors per condition.\"\"\"
    keep_ct = []
    for ct in pb.obs["cell_type"].unique():
        ct_data = pb.obs[pb.obs["cell_type"] == ct]
        donors_per_cond = ct_data.groupby("condition")["donor_id"].nunique()
        if all(donors_per_cond >= min_donors):
            keep_ct.append(ct)
    return pb[pb.obs["cell_type"].isin(keep_ct)].copy()

pb = filter_pseudobulk(pb)
```

## Step 3: Run PyDESeq2
```python
from pydeseq2.dds import DeseqDataSet
from pydeseq2.ds import DeseqStats

def run_deseq2(pb, cell_type):
    \"\"\"Run DESeq2 for a specific cell type.\"\"\"
    ct_mask = pb.obs["cell_type"] == cell_type
    ct_pb = pb[ct_mask].copy()

    dds = DeseqDataSet(
        counts=pd.DataFrame(ct_pb.X, columns=ct_pb.var_names),
        metadata=ct_pb.obs[["condition"]],
        design="~condition",
    )
    dds.deseq2()

    stat_res = DeseqStats(dds, contrast=("condition", "disease", "normal"))
    stat_res.summary()

    results = stat_res.results_df
    return results

# Run for each cell type
de_results = {}
for ct in pb.obs["cell_type"].unique():
    try:
        de_results[ct] = run_deseq2(pb, ct)
    except Exception as e:
        print(f"Failed for {ct}: {e}")
```

## Step 4: Apply Significance Thresholds
```python
def filter_significant(results_df, fdr_threshold=0.05, lfc_threshold=0.5):
    \"\"\"Filter for significant DE genes.\"\"\"
    sig = results_df[
        (results_df["padj"] < fdr_threshold) &
        (results_df["log2FoldChange"].abs() > lfc_threshold)
    ].copy()
    return sig.sort_values("padj")

sig_genes = {}
for ct, results in de_results.items():
    sig_genes[ct] = filter_significant(results)
    print(f"{ct}: {len(sig_genes[ct])} significant genes")
```
"""


def get_de_workflow() -> str:
    """Return the pseudobulk DE workflow as a string."""
    return PSEUDOBULK_DE_WORKFLOW
