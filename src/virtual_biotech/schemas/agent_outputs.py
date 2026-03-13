"""Pydantic schemas for agent output validation."""

from pydantic import BaseModel


class GeneticEvidenceSummary(BaseModel):
    """Output schema for the Statistical Genetics agent."""

    gene_symbol: str
    disease: str
    gwas_associations: list[dict] = []
    credible_sets: list[dict] = []
    l2g_score: float | None = None
    l2g_rank: int | None = None
    qtl_colocalization: list[dict] = []
    constraint_metrics: dict | None = None
    enhancer_gene_links: list[dict] = []
    pharmacogenomics: list[dict] = []
    evidence_strength: str = "unknown"
    summary: str = ""


class SingleCellExpressionProfile(BaseModel):
    """Output schema for the Single Cell Atlas agent."""

    gene_symbol: str
    tissue: str | None = None
    disease: str | None = None
    cell_type_expression: dict[str, float] = {}
    tau_specificity: float | None = None
    bimodality_coefficient: float | None = None
    differential_expression: list[dict] = []
    cell_cell_communication: list[dict] = []
    spatial_analysis: dict | None = None
    summary: str = ""


class FunctionalGenomicsProfile(BaseModel):
    """Output schema for the Functional Genomics agent."""

    gene_symbol: str
    crispr_essentiality: list[dict] = []
    hallmark_scores: dict[str, float] = {}
    perturbation_data: list[dict] = []
    summary: str = ""


class SafetyAssessment(BaseModel):
    """Output schema for safety-related agents."""

    gene_symbol: str
    pathway_involvement: list[dict] = []
    protein_interactions: list[dict] = []
    off_target_expression: list[dict] = []
    fda_adverse_events: list[dict] = []
    mouse_ko_phenotypes: list[dict] = []
    drug_label_warnings: list[str] = []
    overall_risk: str = "unknown"
    summary: str = ""


class ModalityRecommendation(BaseModel):
    """Output schema for modality selection agents."""

    gene_symbol: str
    subcellular_localization: str | None = None
    protein_family: str | None = None
    tractability: dict[str, str] = {}
    existing_drugs: list[dict] = []
    chemical_probes: list[dict] = []
    recommended_modalities: list[str] = []
    summary: str = ""


class ClinicalLandscape(BaseModel):
    """Output schema for the Clinical Trialist agent."""

    gene_symbol: str | None = None
    disease: str | None = None
    trials: list[dict] = []
    survival_analysis: dict | None = None
    competitive_landscape: list[dict] = []
    summary: str = ""


class IntelligenceBriefing(BaseModel):
    """Output schema for the Chief of Staff agent."""

    field_context: str = ""
    data_availability: str = ""
    recent_developments: str = ""
    key_questions: list[str] = []
    feasibility_notes: str = ""


class ScientificReview(BaseModel):
    """Output schema for the Scientific Reviewer agent."""

    executive_summary: str = ""
    critical_issues: list[dict] = []
    strengths: list[str] = []
    weaknesses: list[str] = []
    recommendations: list[str] = []
    verdict: str = "PENDING"
