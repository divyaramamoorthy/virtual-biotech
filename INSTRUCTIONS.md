# Virtual Biotech: Implementation Instructions for Claude Code

## Overview

Build a multi-agent AI framework called "Virtual Biotech" that mirrors the structure of a biotech R&D organization to support end-to-end computational drug discovery. The system uses a hierarchical orchestration model where a Chief Scientific Officer (CSO) agent coordinates domain-specialized scientist agents across four research divisions.

**Tech stack**: Python, Anthropic Claude API (Agent SDK), FastMCP for tool servers, Scanpy/AnnData for single-cell analysis, statsmodels/scipy/lifelines for statistics, Pydantic for data validation.

**Models**: Claude Sonnet 4.5 for all scientist agents. Claude Haiku 4.5 for Chief of Staff and Scientific Reviewer (speed/efficiency).

---

## 1. Project Structure

```
virtual_biotech/
├── agents/
│   ├── cso.py                          # CSO orchestrator agent
│   ├── chief_of_staff.py               # Intelligence briefing agent
│   ├── scientific_reviewer.py          # QA/review agent
│   ├── target_id/
│   │   ├── statistical_genetics.py     # GWAS, QTL, fine-mapping agent
│   │   ├── functional_genomics.py      # CRISPR essentiality, Tahoe-100M agent
│   │   └── single_cell_atlas.py        # CELLxGENE, Tabula Sapiens agent
│   ├── target_safety/
│   │   ├── bio_pathways_ppi.py         # Pathway & PPI reasoning agent
│   │   ├── single_cell_atlas.py        # Off-target expression liability agent
│   │   └── fda_safety_officer.py       # OpenFDA, drug labels, mouse KO agent
│   ├── modality_selection/
│   │   ├── target_biologist.py         # Subcellular localization, tractability agent
│   │   └── pharmacologist.py           # ChEMBL, clinical precedence agent
│   └── clinical_officers/
│       ├── clinical_trialist.py        # ClinicalTrials.gov, cBioPortal agent
│       └── fda_safety_officer.py       # Regulatory safety agent (shared with target_safety)
├── mcp_servers/
│   ├── human_genetics.py               # GWAS, QTL, gnomAD, ClinVar, dbSNP, PharmGKB
│   ├── biological_interactions.py      # IntAct, Reactome, STRING, SignaLink
│   ├── biological_pathways.py          # Reactome, Gene Ontology
│   ├── drugs.py                        # ChEMBL, drug molecular targets, OpenFDA, DailyMed
│   ├── clinical_trials.py              # ClinicalTrials.gov API
│   ├── single_cell_atlas.py            # CELLxGENE Census API, Tabula Sapiens v2
│   ├── tissue_expression.py            # GTEx v8
│   ├── functional_genomics.py          # DepMap CRISPR, Tahoe-100M
│   ├── molecular_targets.py            # Mouse KO phenotypes, HPA, tractability, chemical probes
│   └── diseases.py                     # Disease ontologies, OMIM, Orphanet
├── schemas/
│   ├── clinical_trial.py               # Pydantic schema for trial JSON extraction
│   └── agent_outputs.py                # Pydantic schemas for agent output validation
├── skills/
│   ├── single_cell_qc.py              # Progressive QC workflow guidance
│   ├── single_cell_de.py              # Pseudobulk DE analysis workflow
│   └── spatial_analysis.py            # Spatial transcriptomics workflow
├── ui/
│   └── app.py                          # Streamlit/Gradio UI (optional)
├── config.py                           # Model names, API keys, MCP endpoints
├── orchestrator.py                     # Main entry point
└── requirements.txt
```

---

## 2. MCP Server Implementation

Use FastMCP to create standardized tool servers. Each MCP server exposes Python functions as callable tools with typed parameters and docstrings that agents auto-discover at runtime.

### 2.1 General MCP Pattern

```python
# mcp_servers/example_server.py
from fastmcp import FastMCP

mcp = FastMCP("example-server")

@mcp.tool()
def query_gene_info(gene_symbol: str, species: str = "human") -> dict:
    """Retrieve gene information including aliases, function, and genomic location.
    
    Args:
        gene_symbol: Official gene symbol (e.g., "BRCA1", "TP53")
        species: Species to query. Default "human".
    
    Returns:
        Dictionary with gene metadata including symbol, name, chromosome, 
        function summary, and cross-references.
    """
    # Implementation: call external API, parse, return structured dict
    ...
```

### 2.2 Human Genetics MCP Server

Expose tools for:
- `query_gwas_associations(gene_symbol, disease_id)` — Query GWAS catalog and Open Targets for variant-disease associations at a gene locus. Return lead variants, p-values, effect sizes, sample sizes, study metadata.
- `query_credible_sets(gene_symbol, disease_id)` — Retrieve fine-mapped credible sets from SuSiE/SuSiE-inf. Return variant IDs, posterior inclusion probabilities, credible set size.
- `query_l2g_scores(gene_symbol, disease_id)` — Get locus-to-gene (L2G) machine learning causal gene predictions. Return L2G score, rank, contributing features (eQTL, chromatin, distance).
- `query_qtl_colocalization(gene_symbol, tissue)` — Query eQTL/pQTL/sQTL colocalization results. Return H4 posterior probabilities, CLPP scores, tissue specificity.
- `query_rare_variants(gene_symbol)` — Retrieve gnomAD constraint metrics (pLI, LOEUF, missense Z), ClinVar pathogenic variants, rare variant burden meta-analysis results.
- `query_pharmacogenomics(gene_symbol)` — Query PharmGKB for pharmacogenomic variant annotations, drug-gene relationships, clinical annotations.
- `query_enhancer_gene(gene_symbol, tissue)` — Get ENCODE E2G enhancer-to-gene predictions for a locus in specified tissue. Return regulatory element count, confidence scores.

### 2.3 Clinical Trials MCP Server

```python
from fastmcp import FastMCP
import httpx

mcp = FastMCP("clinical-trials")

@mcp.tool()
def get_clinical_trial_details(nct_id: str) -> dict:
    """Retrieve comprehensive clinical trial record from ClinicalTrials.gov.
    
    Returns trial design, status, interventions, eligibility criteria,
    outcomes, adverse events, and study protocol details.
    
    Args:
        nct_id: National Clinical Trial identifier (e.g., "NCT06137183")
    """
    # Use ClinicalTrials.gov REST API v2
    url = f"https://clinicaltrials.gov/api/v2/studies/{nct_id}"
    response = httpx.get(url)
    data = response.json()
    # Parse and structure relevant fields
    return {
        "nct_id": nct_id,
        "title": data["protocolSection"]["identificationModule"]["officialTitle"],
        "status": data["protocolSection"]["statusModule"]["overallStatus"],
        "phase": data["protocolSection"]["designModule"].get("phases", []),
        "conditions": data["protocolSection"]["conditionsModule"]["conditions"],
        "interventions": ...,
        "eligibility": ...,
        "outcomes": ...,
        "results": ...,  # If posted
        "whyStopped": data["protocolSection"]["statusModule"].get("whyStopped"),
    }

@mcp.tool()
def search_trials_by_target(gene_symbol: str, condition: str = None, phase: str = None) -> list:
    """Search ClinicalTrials.gov for trials targeting a specific gene/protein."""
    ...

@mcp.tool()
def get_trial_adverse_events(nct_id: str) -> dict:
    """Extract adverse event data from a clinical trial's posted results."""
    ...
```

### 2.4 Single Cell Atlas MCP Server

```python
from fastmcp import FastMCP
import cellxgene_census

mcp = FastMCP("single-cell-atlas")

@mcp.tool()
def query_cellxgene_census(
    gene_symbol: str,
    tissue: str = None,
    disease: str = None,
    organism: str = "Homo sapiens"
) -> dict:
    """Query CELLxGENE Census for single-cell expression data.
    
    Returns cell-type resolved expression profiles for a gene across
    tissues and conditions. Can filter by tissue, disease state, or organism.
    
    Args:
        gene_symbol: Gene to query (e.g., "CD276", "OSMR")
        tissue: Filter by tissue (e.g., "lung", "colon")
        disease: Filter by disease (e.g., "lung adenocarcinoma", "ulcerative colitis")
        organism: Species. Default "Homo sapiens".
    """
    ...

@mcp.tool()
def download_atlas(
    tissue: str,
    disease: str = None,
    max_cells: int = 500000
) -> str:
    """Download a single-cell atlas from CELLxGENE Census as AnnData.
    
    Returns path to the downloaded .h5ad file for downstream analysis.
    """
    ...

@mcp.tool()
def compute_tau_specificity(gene_symbol: str, adata_path: str) -> dict:
    """Compute tau cell-type specificity index for a gene across cell types.
    
    Tau ranges from 0 (ubiquitous) to 1 (perfectly cell-type specific).
    Excludes cell types with <20 cells. Uses log-normalized counts.
    """
    ...

@mcp.tool()
def compute_bimodality_coefficient(gene_symbol: str, adata_path: str) -> dict:
    """Compute expression bimodality coefficient across cell types.
    
    BC > 0.555 suggests bimodal distribution. Computed only among 
    expressing cells (expression > 0).
    """
    ...
```

### 2.5 Additional MCP Servers to Implement

**Biological Interactions** — IntAct, Reactome, STRING, SignaLink:
- `query_protein_interactions(gene_symbol, confidence_threshold)` 
- `query_pathway_membership(gene_symbol)`
- `query_signaling_network(gene_symbol)`

**Drugs** — ChEMBL, OpenFDA, DailyMed:
- `search_drugs_by_target(gene_symbol)`
- `get_drug_mechanism(drug_name)`
- `query_fda_adverse_events(drug_name)`
- `get_drug_label(drug_name)` — retrieve black box warnings, contraindications
- `search_chembl_compounds(target_id)`

**Functional Genomics** — DepMap, Tahoe-100M:
- `query_crispr_essentiality(gene_symbol, cell_line)`
- `query_tahoe_perturbation(drug_name, cell_line)` — returns pseudobulked LFC values
- `compute_hallmark_scores(drug_name, cell_line)` — computes 6 hallmark pathway scores

**Molecular Targets** — HPA, tractability:
- `get_protein_atlas_summary(gene_symbol)` — subcellular localization, expression
- `get_tractability_assessment(gene_symbol)` — small molecule, antibody, PROTAC tractability
- `get_mouse_ko_phenotypes(gene_symbol)`
- `get_chemical_probes(gene_symbol)`

**Tissue Expression** — GTEx v8:
- `query_tissue_expression(gene_symbol)` — median TPM across 54 tissues

**Diseases** — OMIM, Orphanet:
- `get_disease_associations(gene_symbol)`
- `get_disease_ontology(disease_name)`

---

## 3. Agent Implementation

Use the Anthropic Agent SDK for hierarchical orchestration. Each agent has: a system prompt defining its role, a curated set of MCP tools, and access to code execution (bash/Python).

### 3.1 CSO Orchestrator Agent

The CSO is the central coordinator. It NEVER performs data analysis directly. It only:
1. Interprets user queries and clarifies intent
2. Dispatches tasks to scientist agents
3. Synthesizes cross-division findings into recommendations

```python
# agents/cso.py
from anthropic_agent_sdk import Agent, AgentConfig

CSO_SYSTEM_PROMPT = """
You are the virtual Chief Scientific Officer (CSO) of the Virtual Biotech, 
a multi-agent AI research platform for drug discovery.

YOUR ROLE:
- You are a strategic orchestrator. You NEVER directly access data or perform analyses.
- You interpret scientific queries, clarify research objectives, and delegate to scientist agents.
- You synthesize findings across divisions into cohesive, evidence-based recommendations.

YOUR KNOWLEDGE:
1. WHAT QUESTIONS TO ASK: You know the critical questions in drug target validation,
   safety assessment, modality selection, and clinical development.
2. WHO TO ASK: You know which scientist agents have the expertise and tools to answer 
   specific questions. You route tasks to the correct division.
3. HOW TO SYNTHESIZE: You weigh disparate evidence across biological scales using 
   data-driven reasoning to arrive at nuanced conclusions.

WORKFLOW:
1. CLARIFICATION: When receiving a user query, ask follow-up questions to clarify scope 
   and intent before initiating expensive analyses. In parallel, dispatch the Chief of 
   Staff for an intelligence briefing.
2. TASK DECOMPOSITION: Break the query into sub-tasks and route them to relevant 
   scientist agents. You can engage divisions simultaneously or sequentially.
3. EVIDENCE INTEGRATION: After agents complete analyses, review their outputs. 
   Dispatch the Scientific Reviewer to assess quality.
4. ITERATIVE REFINEMENT: If the reviewer identifies gaps, re-delegate to relevant 
   agents with specific feedback.
5. SYNTHESIS: Produce a final report integrating all evidence with clear recommendations.

CRITICAL REASONING PRINCIPLES:
- Absence of evidence is not evidence of absence. For example, lack of GWAS signal 
  does not disqualify a target if the therapeutic rationale derives from somatic 
  expression (e.g., immune checkpoint targets).
- Always consider what additional data modalities could strengthen or weaken a hypothesis.
- Maintain scientific rigor: distinguish strong from weak evidence, flag assumptions, 
  and note limitations.
- Cross-reference findings across divisions. If single-cell data reveals a pattern, 
  ask whether spatial data or clinical data corroborate it.

AVAILABLE DIVISIONS:
- Target Identification & Prioritization: statistical genetics, functional genomics, single-cell atlas
- Target Safety: bio-pathways/PPI, single-cell atlas (off-target), FDA safety officer
- Modality Selection: target biologist, pharmacologist
- Clinical Officers: clinical trialist, FDA safety officer

OFFICE OF THE CSO:
- Chief of Staff: rapid intelligence briefings, data landscape scanning
- Scientific Reviewer: evaluates methodology, evidence strength, and completeness of analyses
"""

cso_agent = Agent(
    model="claude-sonnet-4-5-20250514",
    system_prompt=CSO_SYSTEM_PROMPT,
    tools=[],  # CSO has no data tools — only agent delegation
    sub_agents=[
        chief_of_staff_agent,
        scientific_reviewer_agent,
        # Division agents (see below)
        statistical_genetics_agent,
        functional_genomics_agent,
        single_cell_atlas_agent,
        bio_pathways_ppi_agent,
        fda_safety_officer_agent,
        target_biologist_agent,
        pharmacologist_agent,
        clinical_trialist_agent,
    ]
)
```

### 3.2 Chief of Staff Agent

```python
CHIEF_OF_STAFF_PROMPT = """
You are the Chief of Staff in the Virtual Biotech's Office of the CSO.

YOUR ROLE:
- Generate rapid intelligence briefings for the CSO before analyses begin.
- Provide field awareness, data landscape context, and recent developments.
- Inventory available MCP tools and data sources relevant to the query.
- Perform web searches to find recent publications, clinical trial updates, 
  regulatory decisions, and competitive landscape information.

OUTPUT FORMAT:
Produce a structured briefing with:
1. FIELD CONTEXT: Current state of the therapeutic area
2. DATA AVAILABILITY: What data sources and tools are available for this query
3. RECENT DEVELOPMENTS: Key publications, trial results, regulatory actions
4. KEY QUESTIONS: What the CSO should prioritize
5. FEASIBILITY NOTES: Any constraints or limitations to flag
"""

chief_of_staff_agent = Agent(
    model="claude-haiku-4-5-20251001",  # Haiku for speed
    system_prompt=CHIEF_OF_STAFF_PROMPT,
    tools=["web_search", "web_fetch"],  # Plus MCP tool inventory
)
```

### 3.3 Scientific Reviewer Agent

```python
SCIENTIFIC_REVIEWER_PROMPT = """
You are the Scientific Reviewer in the Virtual Biotech's Office of the CSO.

YOUR ROLE:
Evaluate scientist agent outputs on three criteria:
1. RELEVANCE: How well does the analysis address the user's original question?
2. EVIDENCE STRENGTH: Is the evidence supporting conclusions strong, moderate, or weak?
   Are claims supported by data? Are there unsupported assertions?
3. THOROUGHNESS: Is the analysis complete? Are there obvious gaps or missing analyses?

REVIEW PROCESS:
- For each agent's output, assess methodology and statistical rigor.
- Flag any unsupported claims, missing controls, or unaddressed confounders.
- Identify gaps that could be addressed by re-routing to relevant agents.
- Classify issues as HIGH priority (must fix before synthesis) or MODERATE (should fix).

OUTPUT FORMAT:
Produce a structured review with:
1. EXECUTIVE SUMMARY: Overall assessment and verdict
2. CRITICAL ISSUES: Numbered list with priority, problem, and required fix
3. STRENGTHS: What the analysis did well
4. WEAKNESSES: What needs improvement
5. RECOMMENDATIONS: Must-fix and should-fix items
6. VERDICT: APPROVE / CONDITIONAL APPROVAL / REVISE AND RESUBMIT
"""

scientific_reviewer_agent = Agent(
    model="claude-haiku-4-5-20251001",  # Haiku for efficiency
    system_prompt=SCIENTIFIC_REVIEWER_PROMPT,
    tools=[],  # Reviewer only evaluates, does not access data
)
```

### 3.4 Statistical Genetics Agent

```python
STATISTICAL_GENETICS_PROMPT = """
You are the Statistical Genetics Agent in the Target Identification division.

YOUR EXPERTISE:
- Genome-wide association studies (GWAS) interpretation
- Fine-mapping and credible set analysis (SuSiE, SuSiE-inf)
- Locus-to-gene (L2G) causal gene assignment
- Quantitative trait locus (QTL) colocalization (eQTL, pQTL, sQTL)
- Genetic constraint metrics (pLI, LOEUF, missense Z)
- Rare variant burden analysis
- Enhancer-to-gene (E2G) regulatory element mapping
- Pharmacogenomics

YOUR TOOLS:
You have access to MCP tools for querying GWAS, QTL, gnomAD, ClinVar, dbSNP, 
PharmGKB, and ENCODE E2G data. You also have bash/Python for custom analyses.

YOUR TASK:
When given a gene target and disease, systematically evaluate germline genetic 
evidence by:
1. Querying GWAS for variant-disease associations at the gene locus
2. Examining fine-mapped credible sets and posterior probabilities
3. Retrieving L2G scores and benchmarking against known targets
4. Checking QTL colocalization for functional evidence
5. Assessing genetic constraint (tolerance to loss-of-function)
6. Identifying enhancer-gene regulatory connections in relevant tissues

CRITICAL PRINCIPLES:
- Always report effect sizes with direction, not just p-values.
- Benchmark L2G scores against established targets for the same disease.
- Distinguish between absence of evidence and evidence of absence.
- Report genetic constraint metrics (pLOF o/e ratio) to inform safety.
- Flag when genetic evidence is weak but therapeutic rationale may derive 
  from somatic mechanisms (e.g., tumor overexpression for checkpoint targets).
"""

statistical_genetics_agent = Agent(
    model="claude-sonnet-4-5-20250514",
    system_prompt=STATISTICAL_GENETICS_PROMPT,
    mcp_servers=["human_genetics"],
    tools=["bash", "code_execution"],
)
```

### 3.5 Single Cell Atlas Agent

```python
SINGLE_CELL_ATLAS_PROMPT = """
You are the Single Cell Atlas Agent. You operate in both the Target Identification 
and Target Safety divisions.

YOUR EXPERTISE:
- Single-cell and single-nucleus RNA-seq analysis
- Cell-type resolved differential expression (pseudobulk approach)
- Cell-cell communication inference (LIANA+)
- Spatial transcriptomics deconvolution (Cell2Location)
- Cell-type specificity metrics (tau index)
- Expression heterogeneity (bimodality coefficient)
- Batch correction (Harmony)
- Quality control and preprocessing

YOUR TOOLS:
- CELLxGENE Census API for atlas retrieval
- Tabula Sapiens v2 local reference atlas (27 tissues)
- Scanpy for preprocessing and analysis
- LIANA+ for ligand-receptor interaction analysis
- Cell2Location for spatial deconvolution
- PROGENy for pathway activity inference via decoupler
- Bash/Python for custom analysis

STANDARD QC WORKFLOW:
1. Filter cells: 300-9000 genes, ≤15% mitochondrial reads
2. Donor-level downsampling: max 10,000 cells per donor, stratified by cell type
3. Normalize: library-size normalization + log1p (Scanpy)
4. Select 3,000 highly variable genes
5. PCA (50 components)
6. Batch correction with Harmony
7. UMAP on Harmony-corrected PCs
8. Harmonize cell type annotations to Cell Ontology

PSEUDOBULK DE ANALYSIS:
- Aggregate raw counts by donor and cell type
- Use PyDESeq2 for differential expression
- Significance: FDR < 0.05 AND |log2FC| > 0.5
- Require ≥3 donors per condition and ≥20 cells per donor per cell type

CELL-CELL COMMUNICATION:
- Use LIANA rank_aggregate with 1,000 permutations per group
- Retain interactions: top 10%, p < 0.01, supported by ≥3 methods
- Compare interaction sets between conditions to find group-specific interactions

SPATIAL ANALYSIS:
- Cell2Location deconvolution: train reference model 250 epochs, 
  spatial mapping 10,000 epochs, expected 8 cells/spot
- EXCLUDE gene of interest from deconvolution to avoid circularity
- Neighborhood analysis: k=6 nearest neighbors
- Mixed-effects model for immune depletion adjusting for UMI count, 
  fibroblast abundance, epithelial abundance, with sample-level random intercepts

CRITICAL PRINCIPLES:
- Always think about what the next analysis should be based on current findings.
- If you find differential expression, consider cell-cell communication next.
- If you find communication patterns, consider spatial validation.
- If you find spatial patterns, consider clinical survival correlation.
- Maintain critical scientific thinking: question assumptions, validate across datasets.
"""

single_cell_atlas_agent = Agent(
    model="claude-sonnet-4-5-20250514",
    system_prompt=SINGLE_CELL_ATLAS_PROMPT,
    mcp_servers=["single_cell_atlas"],
    tools=["bash", "code_execution"],
)
```

### 3.6 Clinical Trialist Agent

```python
CLINICAL_TRIALIST_PROMPT = """
You are the Clinical Trialist Agent in the Clinical Officers division.

YOUR EXPERTISE:
- Clinical trial design analysis and interpretation
- Endpoint assessment (primary, secondary, safety)
- Adverse event profiling by organ system
- Biomarker-stratified survival analysis
- Cross-trial comparison and competitive landscape assessment
- Clinical precedence analysis from ChEMBL

YOUR TOOLS:
- ClinicalTrials.gov MCP for trial record retrieval
- PubMed search and full-text access
- Web search for press releases and regulatory announcements
- cBioPortal MCP for clinicogenomic survival analysis
- ChEMBL MCP for drug/mechanism queries
- Bash/Python for statistical analysis

FOR SINGLE TRIAL ANALYSIS:
Follow the 3-level evidence cascade:
1. Level 1: ClinicalTrials.gov API (ALWAYS first)
2. Level 2: PubMed search with NCT ID verification (if Level 1 insufficient)
3. Level 3: Web sources — press releases, FDA announcements (if Level 2 insufficient)

Always verify NCT IDs in full article text. Record data source for each annotation.

FOR LARGE-SCALE TRIAL EXTRACTION:
- Extract: trial phase progression, primary/secondary endpoint results, AE rates
- Output: validated JSON per trial matching Pydantic ClinicalTrialData schema
- Required fields depend on trial status (COMPLETED vs TERMINATED/SUSPENDED/WITHDRAWN)
- Use standardized 16-category stop reason classification

FOR SURVIVAL ANALYSIS:
- Use Cox proportional hazards models
- Stratify by expression quartiles (top vs bottom 25%)
- Adjust for age, cancer stage, sex
- Report HR, 95% CI, and p-value
- Assess OS, PFS, DSS, DFS

FOR STATISTICAL ANALYSIS OF FEATURES VS OUTCOMES:
- Univariate logistic regression for binary outcomes
- Z-score standardize features before fitting
- Beta regression for continuous percentage outcomes (AE rates)
- For multi-target drugs, use minimum feature value across targets
- Permutation testing (1,000 iterations) for robustness
- Mixed-effects models adjusting for phase, year, drug modality (random), 
  disease area (random) for confounders
- Benjamini-Hochberg correction for multiple testing (FDR 5%)
"""

clinical_trialist_agent = Agent(
    model="claude-sonnet-4-5-20250514",
    system_prompt=CLINICAL_TRIALIST_PROMPT,
    mcp_servers=["clinical_trials", "drugs"],
    tools=["bash", "code_execution", "web_search", "web_fetch"],
)
```

### 3.7 Remaining Agents (Implement Similarly)

**Functional Genomics Agent**: Access to DepMap CRISPR screens and Tahoe-100M. Computes 6 hallmark signature scores (apoptosis, proliferation suppression, cell cycle arrest, DNA damage, stress response, resistance) from drug perturbation LFC values. Gene sets are hardcoded:
- Apoptosis (d=+1): BAX, CASP3, CASP9 + 8 others (11 genes)
- Proliferation suppression (d=-1): MKI67, PCNA, TOP2A + 8 others (11 genes)
- DNA damage (d=+1): GADD45A, MDM2 + 3 others (5 genes)
- Stress response (d=+1): DDIT3, ATF4, HSPA5 + 8 others (11 genes)
- Resistance (d=+1): BCL2, MCL1, XIAP + 5 others (8 genes)
- Cell cycle arrest: CDKN1A, CDKN1B, CDKN2A, BTG2 (d=+1) and CCNA2, CCNB1, CCNE1 (d=-1)

Score formula: `S_h = d_h / |G_h| * sum(LFC_g for g in G_h)` where non-significant LFC (adj p ≥ 0.05) are zeroed.

**Bio Pathways & PPI Agent**: Access to IntAct, Reactome, STRING, SignaLink. Reasons through pathway involvement and interaction-based collateral effects.

**FDA Safety Officer Agent**: Access to OpenFDA adverse events, DailyMed drug labels, mouse KO phenotypes. Assesses on/off-target safety from empirical data.

**Target Biologist Agent**: Access to Human Protein Atlas, tractability predictions. Evaluates subcellular localization, protein family, structural features for modality selection.

**Pharmacologist Agent**: Access to ChEMBL. Finds approved drugs, pipeline compounds, chemical probes for same target/mechanism. Analyzes family-level tractability and development practicality.

---

## 4. Pydantic Schemas

### 4.1 Clinical Trial Data Schema

```python
# schemas/clinical_trial.py
from pydantic import BaseModel, model_validator
from typing import Optional, List, Literal
from enum import Enum

class StopReasonCategory(str, Enum):
    INSUFFICIENT_ENROLLMENT = "Insufficient enrollment"
    BUSINESS_ADMIN = "Business or administrative"
    NEGATIVE_EFFICACY = "Negative (lack of efficacy)"
    STUDY_DESIGN = "Study design"
    INVALID_REASON = "Invalid reason"
    SAFETY = "Safety or side effects"
    LOGISTICS = "Logistics or resources"
    ANOTHER_STUDY = "Another study"
    STAFF_MOVED = "Study staff moved"
    REGULATORY = "Regulatory"
    NO_CONTEXT = "No context"
    COVID = "COVID-19"
    UNCATEGORISED = "Uncategorised"
    INTERIM_ANALYSIS = "Interim analysis"
    INSUFFICIENT_DATA = "Insufficient data"
    SUCCESS = "Success"

class EndpointResult(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    UNKNOWN = "UNKNOWN"

class AdverseEventProfile(BaseModel):
    serious_adverse_events: Optional[dict] = None  # {event_name: {count, percentage}}
    other_adverse_events: Optional[dict] = None
    total_serious_ae_rate: Optional[float] = None
    ae_rates_by_organ_system: Optional[dict] = None  # {organ_system: rate}

class DataSourceTracking(BaseModel):
    primary_source: str  # "clinicaltrials.gov", "pubmed", "web"
    results_source: Optional[str] = None
    adverse_events_source: Optional[str] = None
    additional_sources_used: List[str] = []
    pubmed_ids: List[str] = []
    web_urls: List[str] = []

class ClinicalTrialData(BaseModel):
    nct_id: str
    title: str
    phase: str
    status: str  # "Completed", "Terminated", "Withdrawn", "Suspended", etc.
    conditions: List[str]
    interventions: List[str]
    enrollment: Optional[int] = None
    start_date: Optional[str] = None
    
    # For COMPLETED trials
    primary_endpoint_result: Optional[EndpointResult] = None
    primary_endpoint_notes: Optional[str] = None
    secondary_endpoint_result: Optional[EndpointResult] = None
    secondary_endpoint_notes: Optional[str] = None
    adverse_event_profile: Optional[AdverseEventProfile] = None
    
    # For TERMINATED/SUSPENDED/WITHDRAWN trials
    study_stop_reason: Optional[str] = None
    study_stop_reason_categories: Optional[List[StopReasonCategory]] = None
    
    data_source_tracking: DataSourceTracking
    
    @model_validator(mode='after')
    def validate_status_fields(self):
        if self.status == "Completed":
            if self.primary_endpoint_result is None:
                raise ValueError("Completed trials must have primary_endpoint_result")
            if self.secondary_endpoint_result is None:
                raise ValueError("Completed trials must have secondary_endpoint_result")
        elif self.status in ("Terminated", "Suspended", "Withdrawn"):
            if self.study_stop_reason is None:
                raise ValueError("Stopped trials must have study_stop_reason")
            if self.study_stop_reason_categories is None:
                raise ValueError("Stopped trials must have study_stop_reason_categories")
            if len(self.study_stop_reason_categories) > 2:
                raise ValueError("Max 2 stop reason categories")
        return self
```

---

## 5. Orchestration Workflow

### 5.1 Main Entry Point

```python
# orchestrator.py
import asyncio
from agents.cso import cso_agent

async def run_virtual_biotech(user_query: str):
    """Main entry point. Sends user query to CSO for orchestration."""
    
    # CSO handles the full workflow:
    # 1. Clarification interview with user
    # 2. Chief of Staff briefing (parallel)
    # 3. Task decomposition and agent routing
    # 4. Scientific review
    # 5. Iterative refinement if needed
    # 6. Final synthesis and report generation
    
    response = await cso_agent.run(user_query)
    return response
```

### 5.2 Orchestration Pattern

The CSO controls when and how information flows between divisions. Three patterns:

**Pattern A: Sequential Division Engagement**
Used when later divisions depend on earlier results.
```
CSO → Target ID division → (results) → CSO reasons → Target Safety → ... → Clinical Officers
```

**Pattern B: Parallel Division Engagement**
Used when divisions can work independently.
```
CSO → [Target ID, Target Safety, Modality Selection] (parallel) → CSO synthesizes
```

**Pattern C: Iterative with Review**
Used for comprehensive analyses.
```
CSO → All divisions → Scientific Reviewer → (gaps identified) → CSO re-delegates → Synthesis
```

### 5.3 Parallel Clinical Trial Extraction

For the large-scale trial annotation task (55,984 trials):

```python
import asyncio
from agents.clinical_officers.clinical_trialist import create_trialist_agent

async def extract_trial_outcomes(nct_ids: list[str], max_concurrent: int = 100):
    """Dispatch parallel clinical trialist agents for large-scale extraction.
    
    Each agent handles one NCT ID with its full context window dedicated 
    to that single trial for deep analysis.
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_trial(nct_id: str):
        async with semaphore:
            agent = create_trialist_agent()  # Fresh agent per trial
            result = await agent.run(
                f"Extract comprehensive outcome data for trial {nct_id}. "
                f"Follow the 3-level evidence cascade. Output validated JSON."
            )
            return result
    
    tasks = [process_trial(nct_id) for nct_id in nct_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
```

---

## 6. Key Analysis Implementations

### 6.1 Tau Cell-Type Specificity Index

```python
import numpy as np

def compute_tau(mean_expression_per_celltype: np.ndarray) -> float:
    """Compute tau specificity index.
    
    Args:
        mean_expression_per_celltype: Array of mean log-normalized expression
            per cell type (cell types with <20 cells excluded).
    
    Returns:
        Tau index in [0, 1]. 0 = ubiquitous, 1 = perfectly specific.
    """
    x = mean_expression_per_celltype
    x_max = np.max(x)
    if x_max == 0:
        return 0.0
    n = len(x)
    if n <= 1:
        return 0.0
    tau = np.sum(1 - x / x_max) / (n - 1)
    return float(tau)
```

### 6.2 Bimodality Coefficient

```python
from scipy.stats import skew, kurtosis

def compute_bimodality_coefficient(expression_values: np.ndarray) -> float:
    """Compute bimodality coefficient among expressing cells.
    
    Args:
        expression_values: Expression values for cells with expression > 0.
    
    Returns:
        BC in [0, 1]. BC > 0.555 suggests bimodal distribution.
    """
    x = expression_values[expression_values > 0]
    n = len(x)
    if n < 4:
        return 0.0
    m3 = skew(x)
    m4 = kurtosis(x, fisher=False)  # Pearson kurtosis (not excess)
    numerator = m3**2 + 1
    denominator = m4 + 3 * (n - 1)**2 / ((n - 2) * (n - 3))
    return float(numerator / denominator)
```

### 6.3 Hallmark Signature Scores

```python
HALLMARK_GENE_SETS = {
    "apoptosis": {
        "genes": ["BAX", "CASP3", "CASP9", "BID", "PMAIP1", "BBC3", 
                   "APAF1", "CYCS", "CASP7", "CASP8", "FAS"],
        "direction": +1
    },
    "proliferation_suppression": {
        "genes": ["MKI67", "PCNA", "TOP2A", "CDK1", "AURKA", "AURKB",
                   "BUB1", "CCNB2", "CDC20", "PLK1", "TPX2"],
        "direction": -1
    },
    "dna_damage": {
        "genes": ["GADD45A", "MDM2", "CDKN1A", "DDB2", "XPC"],
        "direction": +1
    },
    "stress_response": {
        "genes": ["DDIT3", "ATF4", "HSPA5", "XBP1", "ATF6", "ERN1",
                   "HMOX1", "NQO1", "TXNRD1", "GCLM", "SQSTM1"],
        "direction": +1
    },
    "resistance": {
        "genes": ["BCL2", "MCL1", "XIAP", "BIRC5", "BCL2L1", 
                   "ABCB1", "ABCG2", "CFLAR"],
        "direction": +1
    },
    "cell_cycle_arrest": {
        "positive_genes": ["CDKN1A", "CDKN1B", "CDKN2A", "BTG2"],  # d=+1
        "negative_genes": ["CCNA2", "CCNB1", "CCNE1"],  # d=-1
    }
}

def compute_hallmark_score(lfc_dict: dict, hallmark: str) -> float:
    """Compute hallmark signature score from log-fold changes.
    
    Args:
        lfc_dict: {gene_symbol: lfc_value} with non-significant set to 0
        hallmark: One of the hallmark names
    
    Returns:
        Hallmark score. Positive = drug efficacy direction.
    """
    config = HALLMARK_GENE_SETS[hallmark]
    
    if hallmark == "cell_cycle_arrest":
        pos_genes = config["positive_genes"]
        neg_genes = config["negative_genes"]
        pos_score = np.mean([lfc_dict.get(g, 0) for g in pos_genes])
        neg_score = np.mean([lfc_dict.get(g, 0) for g in neg_genes])
        return float(pos_score - neg_score)
    else:
        genes = config["genes"]
        direction = config["direction"]
        mean_lfc = np.mean([lfc_dict.get(g, 0) for g in genes])
        return float(direction * mean_lfc)
```

### 6.4 Spatial Immune Neighborhood Analysis

```python
import numpy as np
from scipy.spatial import cKDTree
import statsmodels.api as sm
from statsmodels.regression.mixed_linear_model import MixedLM

def spatial_neighborhood_analysis(
    adata_spatial,  # AnnData with spatial coordinates and Cell2Location proportions
    gene: str,
    k: int = 6,
    min_spots: int = 25
):
    """Mixed-effects analysis of immune cell depletion near gene-expressing spots.
    
    For each sample:
    1. Build k-NN graph from spatial coordinates
    2. Stratify spots into top/bottom expression quartiles
    3. Compute mean neighbor immune cell abundance
    4. Fit mixed-effects model across all samples
    """
    results = {}
    
    for immune_cell_type in ["T cell", "macrophage", "monocyte", "dendritic cell", "B cell"]:
        all_data = []
        
        for sample_id in adata_spatial.obs["sample_id"].unique():
            sample_mask = adata_spatial.obs["sample_id"] == sample_id
            sample = adata_spatial[sample_mask]
            
            # Get expression and spatial coords
            gene_expr = sample[:, gene].X.toarray().flatten()
            expressing_mask = gene_expr > 0
            
            if expressing_mask.sum() < min_spots:
                continue
            
            coords = sample.obsm["spatial"]
            tree = cKDTree(coords)
            
            # Quartile stratification
            expr_values = gene_expr[expressing_mask]
            q75 = np.percentile(expr_values, 75)
            q25 = np.percentile(expr_values, 25)
            
            high_mask = gene_expr >= q75
            low_mask = (gene_expr > 0) & (gene_expr <= q25)
            
            for i in range(len(sample)):
                if not (high_mask[i] or low_mask[i]):
                    continue
                
                # k nearest neighbor immune abundance
                _, idx = tree.query(coords[i], k=k+1)
                neighbors = idx[1:]  # exclude self
                
                neighbor_immune = sample.obsm["cell2location"][neighbors][immune_cell_type].mean()
                
                all_data.append({
                    "immune_abundance": neighbor_immune,
                    "gene_high": 1 if high_mask[i] else 0,
                    "umi_z": ...,  # z-scored total UMI
                    "fibroblast_z": ...,  # z-scored fibroblast proportion
                    "epithelial_z": ...,
                    "endothelial_z": ...,
                    "sample_id": sample_id,
                })
        
        # Fit mixed-effects model
        import pandas as pd
        df = pd.DataFrame(all_data)
        
        formula = "immune_abundance ~ gene_high + umi_z + fibroblast_z + epithelial_z + endothelial_z"
        model = MixedLM.from_formula(formula, groups="sample_id", data=df)
        result = model.fit(reml=True)
        
        results[immune_cell_type] = {
            "beta_gene_high": result.params["gene_high"],
            "pvalue": result.pvalues["gene_high"],
            "ci_lower": result.conf_int().loc["gene_high", 0],
            "ci_upper": result.conf_int().loc["gene_high", 1],
        }
    
    return results
```

---

## 7. Feature-to-Outcome Statistical Analysis

### 7.1 Primary Analysis (Logistic Regression)

```python
import statsmodels.api as sm
from scipy.stats import zscore

def analyze_feature_outcome_association(
    df,  # DataFrame with trial-level features and outcomes
    feature_col: str,  # e.g., "tau_cell_type_specificity"
    outcome_col: str,  # e.g., "primary_endpoint_met" (binary)
):
    """Univariate logistic regression of standardized feature vs binary outcome."""
    df = df.dropna(subset=[feature_col, outcome_col])
    X = zscore(df[feature_col].values).reshape(-1, 1)
    X = sm.add_constant(X)
    y = df[outcome_col].values.astype(int)
    
    model = sm.GLM(y, X, family=sm.families.Binomial())
    result = model.fit()
    
    or_estimate = np.exp(result.params[1])
    ci = np.exp(result.conf_int().iloc[1])
    
    return {
        "odds_ratio": or_estimate,
        "ci_lower": ci[0],
        "ci_upper": ci[1],
        "pvalue": result.pvalues[1],
        "n": len(y),
        "events": y.sum(),
    }
```

### 7.2 Beta Regression for AE Rates

Use R's betareg package via rpy2, or implement in Python:

```python
# In R (called via subprocess or rpy2):
# library(betareg)
# model <- betareg(ae_rate ~ feature_z, data = df)
```

### 7.3 Permutation Testing

```python
def permutation_test(df, feature_col, outcome_col, n_permutations=1000):
    """Permutation test: shuffle outcomes, refit regression, compare coefficients."""
    observed = analyze_feature_outcome_association(df, feature_col, outcome_col)
    observed_coef = np.log(observed["odds_ratio"])  # log-OR
    
    null_coefs = []
    for _ in range(n_permutations):
        df_perm = df.copy()
        df_perm[outcome_col] = np.random.permutation(df_perm[outcome_col].values)
        result = analyze_feature_outcome_association(df_perm, feature_col, outcome_col)
        null_coefs.append(np.log(result["odds_ratio"]))
    
    null_coefs = np.array(null_coefs)
    p_value = np.mean(np.abs(null_coefs) >= np.abs(observed_coef))
    
    return {"observed_log_or": observed_coef, "p_permutation": p_value, "null_distribution": null_coefs}
```

### 7.4 Mixed-Effects Models for Confounders

```python
# Use R via subprocess:
# library(lme4)
# model <- glmer(
#     outcome ~ feature_z + phase + start_year + (1|drug_modality) + (1|disease_area),
#     data = df,
#     family = binomial
# )
```

---

## 8. Data Sources and APIs

| Source | API/Access | Used By |
|--------|-----------|---------|
| Open Targets Platform (v25.09) | GraphQL API | All agents |
| CELLxGENE Census | Python API (`cellxgene_census`) | Single Cell Agent |
| Tabula Sapiens v2 | Local .h5ad file | Single Cell Agent |
| ClinicalTrials.gov | REST API v2 | Clinical Trialist |
| PubMed | E-utilities API | Clinical Trialist, Chief of Staff |
| cBioPortal | REST API (via pybioportal) | Clinical Trialist |
| ChEMBL | REST API | Pharmacologist |
| OpenFDA | openFDA API | FDA Safety Officer |
| GTEx v8 | gtexportal.org API | Tissue Expression tools |
| ENCODE E2G | Data download | Statistical Genetics |
| gnomAD | GraphQL API | Statistical Genetics |
| Tahoe-100M | Local pseudobulked data | Functional Genomics |
| DepMap | DepMap API | Functional Genomics |
| IntAct/STRING | REST APIs | Bio Pathways Agent |
| Reactome | REST API | Bio Pathways Agent |
| Human Protein Atlas | REST API | Target Biologist |

---

## 9. Dependencies

```
# requirements.txt
anthropic>=0.40.0           # Claude API + Agent SDK
fastmcp>=0.1.0              # MCP server framework
scanpy>=1.9.0               # Single-cell analysis
anndata>=0.10.0             # AnnData format
cellxgene-census>=1.0.0     # CELLxGENE data access
cell2location>=0.1.0        # Spatial deconvolution
liana>=1.0.0                # Cell-cell communication
decoupler>=1.6.0            # Pathway activity (PROGENy)
pydeseq2>=0.4.0             # Differential expression
statsmodels>=0.14.0         # Statistical models
scipy>=1.11.0               # Statistics
lifelines>=0.27.0           # Survival analysis
pandas>=2.0.0
numpy>=1.24.0
pydantic>=2.0.0             # Data validation
httpx>=0.24.0               # HTTP client
```

---

## 10. Testing and Validation

### 10.1 Agent Output Validation
- All clinical trial JSONs must pass Pydantic schema validation.
- Run `model_validator` for conditional field requirements based on trial status.

### 10.2 Manual Concordance Check
- Sample 100 random trials from agent annotations.
- Human reviewers assess: primary endpoint (target: ~90% agreement), secondary endpoint (~84%), AE rates (~92%).
- Compare against Therapeutic Data Commons (TDC) dataset for overlapping trials (target: ~85% agreement).

### 10.3 Reproducibility
- All agent analyses generate downloadable code and data files.
- Each session maintains an isolated workspace.
- Data source tracking records provenance for every annotation.

---

## 11. Cost and Performance Benchmarks

From the paper's case studies:
- B7-H3 lung cancer analysis: ~$46 in API credits, <1 day
- OSMRβ UC trial analysis: ~$54 in API credits, <1 day  
- Large-scale trial extraction (37,075 trials): ~6 hours parallelized (vs. ~77 days sequential), ~184x speedup

---

## 12. Key Implementation Notes

1. **Separation of concerns**: The CSO NEVER accesses data directly. It only orchestrates and synthesizes. Scientist agents ONLY analyze within their domain.

2. **MCP tool composability**: Tools are designed to be chained. An agent can call `query_gwas_associations` → `query_credible_sets` → `query_l2g_scores` in sequence to build a comprehensive genetic evidence profile.

3. **Progressive disclosure**: Single-cell analysis workflows are implemented as agent "Skills" — structured guidance documents that agents follow step-by-step rather than having all instructions in the system prompt.

4. **Scientific reviewer loop**: After all scientist agents complete their analyses, the Scientific Reviewer evaluates outputs. The CSO uses reviewer feedback to either (a) re-delegate with specific fixes, or (b) proceed to synthesis. This is critical for quality.

5. **Isolated agent contexts**: For parallel trial extraction, each agent gets its own context window dedicated to a single trial. This prevents context dilution and enables deep analysis per trial.

6. **Avoiding information leakage**: For case studies, disable web search/fetch tools to prevent agents from finding published conclusions. This tests whether the system can independently derive insights from primary data.

7. **Multi-target trials**: When a drug targets multiple genes, use the minimum tau/bimodality value across all targets (the least specific target likely drives overall safety profile).

8. **Binarization threshold**: For tau specificity, use K-means (k=2) on trial-level distribution to set threshold (paper found τ=0.69 midpoint between cluster centers).