# Virtual Biotech

Multi-agent AI framework for computational drug discovery. Uses a hierarchical orchestration model where a CSO (Chief Scientific Officer) agent coordinates domain-specialized scientist agents across four research divisions.

Based on the paper: [Virtual Biotech](https://www.biorxiv.org/content/10.64898/2026.02.23.707551v1)

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- `LITELLM_PROXY_API_KEY` environment variable set

## Setup

```bash
# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate
uv sync --dev

# For single-cell analysis features (scanpy, cellxgene-census, etc.)
uv sync --extra bio
```

## Running

### Single query

```bash
uv run python -m virtual_biotech.orchestrator "Evaluate PCSK9 as a drug target for hypercholesterolemia"
```

### Interactive session

```bash
uv run python -m virtual_biotech.orchestrator
```

### Streamlit UI

```bash
uv run streamlit run src/virtual_biotech/ui/app.py
```

### Programmatic usage

```python
import asyncio
from virtual_biotech.orchestrator import run_virtual_biotech

result = asyncio.run(run_virtual_biotech("Assess safety profile of targeting IL-17A"))
print(result)
```

### Parallel trial extraction

```python
import asyncio
from virtual_biotech.orchestrator import extract_trial_outcomes

nct_ids = ["NCT06137183", "NCT04000165", "NCT03170960"]
results = asyncio.run(extract_trial_outcomes(nct_ids))
```

## How It Works

The orchestrator runs a three-phase workflow:

1. **Phase 1 (parallel)** — Chief of Staff performs a web search for competitive landscape context while the CSO generates clarification questions about scope, targets, and disease context
2. **Phase 2 (blocking)** — User responds to the clarification questions
3. **Phase 3 (orchestration)** — CSO receives the enriched prompt (user query + briefing + clarified intent), decomposes tasks, and delegates to scientist sub-agents who call MCP tools to access biological data. The CSO synthesizes findings into evidence-based recommendations. A Scientific Reviewer optionally assesses quality and flags gaps for re-delegation

All sub-agent outputs are logged to timestamped markdown reports in `audit_logs/`.

## Architecture

```
src/virtual_biotech/
├── orchestrator.py              # Main entry point (3-phase workflow)
├── config.py                    # Models, API keys, MCP server configs
├── agents/
│   ├── cso.py                   # CSO orchestrator (Sonnet, delegate-only)
│   ├── chief_of_staff.py        # Intelligence briefings (Haiku, web search)
│   ├── scientific_reviewer.py   # QA/review (Haiku, no tools)
│   ├── target_id/               # Statistical genetics, functional genomics, single-cell
│   ├── target_safety/           # Pathways/PPI, off-target expression, FDA safety
│   ├── modality_selection/      # Target biology, pharmacology
│   └── clinical_officers/       # Clinical trialist, FDA safety (shared)
├── mcp_servers/                 # 10 FastMCP tool servers
├── schemas/                     # Pydantic models (clinical trial, agent outputs)
├── analysis/                    # Tau specificity, hallmark scores, spatial, statistics
├── skills/                      # Workflow guidance (QC, DE, spatial)
└── ui/                          # Streamlit interactive interface
```

### Agent Hierarchy

```
CSO (Sonnet) — orchestrates all agents, never accesses data directly
├── Office of the CSO
│   ├── Chief of Staff (Haiku) — web search, competitive landscape briefings
│   └── Scientific Reviewer (Haiku) — QA/review, gap detection
├── Target ID Division
│   ├── Statistical Genetics — GWAS, fine-mapping, L2G, QTL colocalization, constraint
│   ├── Functional Genomics — DepMap CRISPR essentiality, Tahoe-100M perturbation, hallmark scoring
│   └── Single Cell Atlas — CELLxGENE expression, DE, cell-cell communication, spatial
├── Target Safety Division
│   ├── Bio Pathways & PPI — STRING/IntAct networks, Reactome/GO pathways, collateral damage
│   ├── Single Cell Atlas (safety) — off-target expression in vital organs, immune cells
│   └── FDA Safety Officer — OpenFDA adverse events, drug labels, mouse KO phenotypes (IMPC)
├── Modality Selection Division
│   ├── Target Biologist — subcellular localization (HPA), tractability assessment
│   └── Pharmacologist — ChEMBL drug-target interactions, SAR, competitive landscape
└── Clinical Officers Division
    ├── Clinical Trialist — ClinicalTrials.gov, endpoint analysis, survival analysis
    └── FDA Safety Officer (shared)
```

### MCP Servers

Each server exposes domain-specific tools via FastMCP (stdio subprocess):

| Server | Tools | Data Sources |
|--------|-------|-------------|
| human_genetics | 7 | Open Targets, gnomAD, ClinVar, PharmGKB, ENCODE |
| clinical_trials | 3 | ClinicalTrials.gov v2 API |
| single_cell_atlas | 4 | CELLxGENE Census |
| biological_interactions | 3 | STRING, IntAct, Reactome |
| biological_pathways | 3 | Reactome, Gene Ontology (QuickGO) |
| drugs | 5 | ChEMBL, OpenFDA |
| functional_genomics | 3 | DepMap, Tahoe-100M, hallmark scoring |
| molecular_targets | 4 | Human Protein Atlas, Open Targets, IMPC |
| tissue_expression | 1 | GTEx v8 |
| diseases | 2 | Open Targets |

### Analysis Modules

- **Specificity** — tau index (cell-type specificity, 0=ubiquitous, 1=perfectly specific) and bimodality coefficient (expression heterogeneity, BC > 0.555 indicates bimodal)
- **Hallmark signatures** — six drug response gene sets: apoptosis, proliferation suppression, DNA damage, stress response, resistance, cell cycle arrest
- **Spatial** — Cell2Location deconvolution, k-NN neighborhood composition, expression quartile stratification, mixed-effects modeling
- **Statistics** — logistic regression, permutation testing, beta regression, Cox proportional hazards

## Development

```bash
# Linting
uv run ruff check .
uv run ruff check --fix .

# Formatting
uv run ruff format .

# Tests
uv run pytest

# Verify package imports
uv run python -c "import virtual_biotech; print('OK')"
```
