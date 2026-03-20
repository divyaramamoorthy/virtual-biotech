"""Configuration for Virtual Biotech agents and MCP servers."""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Model configuration
SCIENTIST_MODEL = "claude-sonnet-4-6"
STAFF_MODEL = "claude-haiku-4-5-20251001"

# API configuration — routes through LiteLLM proxy
LITELLM_PROXY_API_KEY = os.environ.get("LITELLM_PROXY_API_KEY", "")
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")

if not LITELLM_PROXY_API_KEY:
    raise ValueError("LITELLM_PROXY_API_KEY environment variable is required.")


def mcp_server_config(module_name: str) -> dict:
    """Build an MCP server stdio config for a given module within virtual_biotech.mcp_servers."""
    return {
        "command": sys.executable,
        "args": ["-m", f"virtual_biotech.mcp_servers.{module_name}"],
    }


# Named MCP server configurations
MCP_SERVERS = {
    "human_genetics": mcp_server_config("human_genetics"),
    "clinical_trials": mcp_server_config("clinical_trials"),
    "single_cell_atlas": mcp_server_config("single_cell_atlas"),
    "biological_interactions": mcp_server_config("biological_interactions"),
    "biological_pathways": mcp_server_config("biological_pathways"),
    "drugs": mcp_server_config("drugs"),
    "functional_genomics": mcp_server_config("functional_genomics"),
    "molecular_targets": mcp_server_config("molecular_targets"),
    "tissue_expression": mcp_server_config("tissue_expression"),
    "diseases": mcp_server_config("diseases"),
}

# Mapping from MCP server name to the tool names it exposes.
# Used to build agent tool whitelists so sub-agents can call MCP tools.
MCP_SERVER_TOOLS: dict[str, list[str]] = {
    "human_genetics": [
        "query_gwas_associations",
        "query_credible_sets",
        "query_l2g_scores",
        "query_qtl_colocalization",
        "query_rare_variants",
        "query_pharmacogenomics",
        "query_enhancer_gene",
    ],
    "clinical_trials": [
        "get_clinical_trial_details",
        "search_trials_by_target",
        "get_trial_adverse_events",
    ],
    "single_cell_atlas": [
        "query_cellxgene_census",
        "download_atlas",
        "compute_tau_specificity",
        "compute_bimodality",
    ],
    "biological_interactions": [
        "query_protein_interactions",
        "query_pathway_membership",
        "query_signaling_network",
    ],
    "biological_pathways": [
        "get_reactome_pathways",
        "get_gene_ontology",
        "get_pathway_enrichment",
    ],
    "drugs": [
        "search_drugs_by_target",
        "get_drug_mechanism",
        "query_fda_adverse_events",
        "get_drug_label",
        "search_chembl_compounds",
    ],
    "functional_genomics": [
        "query_crispr_essentiality",
        "query_tahoe_perturbation",
        "compute_hallmark_scores",
    ],
    "molecular_targets": [
        "get_protein_atlas_summary",
        "get_tractability_assessment",
        "get_mouse_ko_phenotypes",
        "get_chemical_probes",
    ],
    "tissue_expression": [
        "query_tissue_expression",
    ],
    "diseases": [
        "get_disease_associations",
        "get_disease_ontology",
    ],
}


def tools_for_mcp_servers(server_names: list[str]) -> list[str]:
    """Return the union of namespaced MCP tool names for the given server names.

    Tool names follow the SDK convention: mcp__<server>__<tool>
    """
    tools: list[str] = []
    for name in server_names:
        for tool in MCP_SERVER_TOOLS.get(name, []):
            tools.append(f"mcp__{name}__{tool}")
    return tools


# Parallel trial extraction settings
MAX_CONCURRENT_TRIAL_AGENTS = 100

# Tracing — set via VIRTUAL_BIOTECH_TRACE=1 or --trace CLI flag
TRACE_ENABLED = os.environ.get("VIRTUAL_BIOTECH_TRACE", "0") == "1"

# Audit logging — agent reports are written to this directory per run
AUDIT_LOG_DIR = os.environ.get("VIRTUAL_BIOTECH_AUDIT_DIR", "audit_logs")

# Emit a warning when an agent has been running longer than this (seconds)
AGENT_TIMEOUT_WARNING_SECS = int(os.environ.get("VIRTUAL_BIOTECH_AGENT_TIMEOUT", "120"))
