"""Health check for MCP server tools — shared by CLI bench script and Streamlit UI."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


def get_checks() -> dict[str, list[tuple[str, Callable]]]:
    """Return MCP tool health checks grouped by server name.

    Each entry is (tool_name, callable) where callable invokes the tool
    with a known-good test input (BRCA1 / breast cancer).
    """
    from virtual_biotech.mcp_servers import (
        biological_interactions,
        biological_pathways,
        clinical_trials,
        diseases,
        drugs,
        functional_genomics,
        human_genetics,
        molecular_targets,
        tissue_expression,
    )

    GENE = "BRCA1"
    DISEASE_ID = "EFO_0000305"  # breast carcinoma

    return {
        "diseases": [
            ("get_disease_associations", lambda: diseases.get_disease_associations(GENE)),
            ("get_disease_ontology", lambda: diseases.get_disease_ontology("breast carcinoma")),
        ],
        "tissue_expression": [
            ("query_tissue_expression", lambda: tissue_expression.query_tissue_expression(GENE)),
        ],
        "molecular_targets": [
            ("get_tractability_assessment", lambda: molecular_targets.get_tractability_assessment(GENE)),
            ("get_protein_atlas_summary", lambda: molecular_targets.get_protein_atlas_summary(GENE)),
            ("get_mouse_ko_phenotypes", lambda: molecular_targets.get_mouse_ko_phenotypes(GENE)),
            ("get_chemical_probes", lambda: molecular_targets.get_chemical_probes(GENE)),
        ],
        "drugs": [
            ("search_drugs_by_target", lambda: drugs.search_drugs_by_target(GENE)),
            ("get_drug_mechanism", lambda: drugs.get_drug_mechanism("olaparib")),
            ("query_fda_adverse_events", lambda: drugs.query_fda_adverse_events("olaparib")),
            ("get_drug_label", lambda: drugs.get_drug_label("olaparib")),
            ("search_chembl_compounds", lambda: drugs.search_chembl_compounds("CHEMBL1862", activity_type="IC50", max_results=5)),
        ],
        "human_genetics": [
            ("query_gwas_associations", lambda: human_genetics.query_gwas_associations(GENE, DISEASE_ID)),
            ("query_credible_sets", lambda: human_genetics.query_credible_sets(GENE, DISEASE_ID)),
            ("query_l2g_scores", lambda: human_genetics.query_l2g_scores(GENE, DISEASE_ID)),
            ("query_qtl_colocalization", lambda: human_genetics.query_qtl_colocalization(GENE, "Breast_Mammary_Tissue")),
            ("query_rare_variants", lambda: human_genetics.query_rare_variants(GENE)),
            ("query_pharmacogenomics", lambda: human_genetics.query_pharmacogenomics(GENE)),
            ("query_enhancer_gene", lambda: human_genetics.query_enhancer_gene(GENE, "breast")),
        ],
        "biological_pathways": [
            ("get_reactome_pathways", lambda: biological_pathways.get_reactome_pathways(GENE)),
            ("get_gene_ontology", lambda: biological_pathways.get_gene_ontology(GENE)),
            ("get_pathway_enrichment", lambda: biological_pathways.get_pathway_enrichment(["BRCA1", "BRCA2", "TP53", "ATM", "CHEK2"])),
        ],
        "biological_interactions": [
            ("query_protein_interactions", lambda: biological_interactions.query_protein_interactions(GENE)),
            ("query_pathway_membership", lambda: biological_interactions.query_pathway_membership(GENE)),
            ("query_signaling_network", lambda: biological_interactions.query_signaling_network(GENE)),
        ],
        "clinical_trials": [
            ("search_trials_by_target", lambda: clinical_trials.search_trials_by_target(GENE)),
            ("get_clinical_trial_details", lambda: clinical_trials.get_clinical_trial_details("NCT02000622")),
            ("get_trial_adverse_events", lambda: clinical_trials.get_trial_adverse_events("NCT02000622")),
        ],
        "functional_genomics": [
            ("query_crispr_essentiality", lambda: functional_genomics.query_crispr_essentiality(GENE)),
            ("query_tahoe_perturbation", lambda: functional_genomics.query_tahoe_perturbation("olaparib", "MCF7")),
            ("compute_hallmark_scores", lambda: functional_genomics.compute_hallmark_scores("olaparib", "MCF7")),
        ],
    }


def run_check(fn: Callable) -> tuple[float, str]:
    """Run a single health check. Returns (elapsed_seconds, status)."""
    t0 = time.perf_counter()
    try:
        result = fn()
        if asyncio.iscoroutine(result):
            asyncio.get_event_loop().run_until_complete(result)
        elapsed = time.perf_counter() - t0
        return elapsed, "OK"
    except Exception as e:
        elapsed = time.perf_counter() - t0
        return elapsed, f"ERR: {type(e).__name__}: {e}"
