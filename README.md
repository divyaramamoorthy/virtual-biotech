# Virtual Biotech
Minimal implementation of the paper: https://www.biorxiv.org/content/10.64898/2026.02.23.707551v1

Description: Multi-agent AI framework for computational drug discovery. Uses a hierarchical orchestration model where a CSO (Chief Scientific Officer) agent coordinates domain-specialized scientist agents across four research divisions.

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

## Architecture

```
src/virtual_biotech/
├── orchestrator.py              # Main entry point
├── config.py                    # Models, API keys, MCP server configs
├── agents/
│   ├── cso.py                   # CSO orchestrator (delegates, never accesses data)
│   ├── chief_of_staff.py        # Intelligence briefings (Haiku)
│   ├── scientific_reviewer.py   # QA/review (Haiku)
│   ├── target_id/               # Statistical genetics, functional genomics, single-cell
│   ├── target_safety/           # Pathways/PPI, off-target expression, FDA safety
│   ├── modality_selection/      # Target biology, pharmacology
│   └── clinical_officers/       # Clinical trialist, FDA safety (shared)
├── mcp_servers/                 # 10 FastMCP tool servers (human genetics, drugs, etc.)
├── schemas/                     # Pydantic models (clinical trial, agent outputs)
├── analysis/                    # Tau specificity, hallmark scores, spatial, statistics
└── skills/                      # Workflow guidance (QC, DE, spatial)
```

### Agent hierarchy

- **CSO** (Sonnet) orchestrates all agents, never accesses data directly
- **Office of the CSO**: Chief of Staff (Haiku, web search), Scientific Reviewer (Haiku, no tools)
- **Target ID Division**: Statistical Genetics, Functional Genomics, Single Cell Atlas
- **Target Safety Division**: Bio Pathways/PPI, Single Cell Atlas (safety), FDA Safety Officer
- **Modality Selection Division**: Target Biologist, Pharmacologist
- **Clinical Officers Division**: Clinical Trialist, FDA Safety Officer (shared)

### MCP servers

Each server exposes domain-specific tools via FastMCP (stdio subprocess):

| Server | Tools | Data sources |
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
