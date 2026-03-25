"""MCP Overview page — shows which MCP servers and tools are enabled per division."""

from __future__ import annotations

import html

import streamlit as st

from virtual_biotech.config import MCP_SERVER_TOOLS
from virtual_biotech.ui.agent_display import (
    _mcp_server_display_name,
    division_mcp_map,
)

_TABLE_CSS = """
<style>
.mcp-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.mcp-table th { text-align: left; padding: 6px 10px; border-bottom: 2px solid #ddd; }
.mcp-table td { padding: 5px 10px; border-bottom: 1px solid #eee; }
.mcp-table .tool-name {
    cursor: help;
    text-decoration: underline dotted;
    position: relative;
    display: inline-block;
}
.mcp-table .tool-name .tooltip {
    visibility: hidden;
    opacity: 0;
    position: absolute;
    bottom: 125%;
    left: 0;
    background: #333;
    color: #fff;
    padding: 6px 10px;
    border-radius: 4px;
    font-size: 12px;
    max-width: 400px;
    white-space: normal;
    z-index: 1000;
    transition: opacity 0.15s;
    pointer-events: none;
}
.mcp-table .tool-name:hover .tooltip {
    visibility: visible;
    opacity: 1;
}
.mcp-table .status-ok { color: #2e7d32; }
.mcp-table .status-err { color: #c62828; font-weight: bold; }
.mcp-table .status-fast { color: #2e7d32; }
.mcp-table .status-medium { color: #f57f17; }
.mcp-table .status-slow { color: #c62828; }
</style>
"""

# MCP tool name -> external database(s) queried
_TOOL_DATABASE: dict[str, str] = {
    # human_genetics
    "query_gwas_associations": "Open Targets",
    "query_credible_sets": "Open Targets",
    "query_l2g_scores": "Open Targets",
    "query_qtl_colocalization": "GTEx + Open Targets",
    "query_rare_variants": "gnomAD + ClinVar",
    "query_pharmacogenomics": "PharmGKB",
    "query_enhancer_gene": "ENCODE",
    # drugs
    "search_drugs_by_target": "ChEMBL",
    "get_drug_mechanism": "ChEMBL",
    "query_fda_adverse_events": "OpenFDA",
    "get_drug_label": "OpenFDA",
    "search_chembl_compounds": "ChEMBL",
    # clinical_trials
    "get_clinical_trial_details": "ClinicalTrials.gov",
    "search_trials_by_target": "ClinicalTrials.gov",
    "get_trial_adverse_events": "ClinicalTrials.gov",
    # molecular_targets
    "get_protein_atlas_summary": "HPA + Open Targets",
    "get_tractability_assessment": "Open Targets",
    "get_mouse_ko_phenotypes": "IMPC",
    "get_chemical_probes": "Open Targets",
    # biological_pathways
    "get_reactome_pathways": "Reactome",
    "get_gene_ontology": "QuickGO",
    "get_pathway_enrichment": "Reactome",
    # biological_interactions
    "query_protein_interactions": "STRING + IntAct",
    "query_pathway_membership": "Reactome",
    "query_signaling_network": "Reactome",
    # tissue_expression
    "query_tissue_expression": "GTEx",
    # single_cell_atlas
    "query_cellxgene_census": "CELLxGENE Census",
    "download_atlas": "CELLxGENE Census",
    "compute_tau_specificity": "Local",
    "compute_bimodality": "Local",
    # functional_genomics
    "query_crispr_essentiality": "DepMap + Open Targets",
    "query_tahoe_perturbation": "Local",
    "compute_hallmark_scores": "Local",
    # diseases
    "get_disease_associations": "Open Targets",
    "get_disease_ontology": "Open Targets",
}

# MCP tool name -> one-line description (shown on hover)
_TOOL_DESCRIPTIONS: dict[str, str] = {
    # human_genetics
    "query_gwas_associations": "Query GWAS catalog and Open Targets for variant-disease associations at a gene locus.",
    "query_credible_sets": "Retrieve fine-mapped credible sets from SuSiE/SuSiE-inf via Open Targets Genetics.",
    "query_l2g_scores": "Get locus-to-gene (L2G) machine learning causal gene predictions.",
    "query_qtl_colocalization": "Query eQTL/pQTL/sQTL colocalization results.",
    "query_rare_variants": "Retrieve gnomAD constraint metrics and ClinVar pathogenic variants.",
    "query_pharmacogenomics": "Query PharmGKB for pharmacogenomic variant annotations.",
    "query_enhancer_gene": "Get ENCODE E2G enhancer-to-gene predictions for a locus in specified tissue.",
    # drugs
    "search_drugs_by_target": "Search ChEMBL for drugs and compounds targeting a specific gene/protein.",
    "get_drug_mechanism": "Get mechanism of action for a drug from ChEMBL.",
    "query_fda_adverse_events": "Query OpenFDA for adverse event reports associated with a drug.",
    "get_drug_label": "Retrieve drug label information including black box warnings and contraindications.",
    "search_chembl_compounds": "Search ChEMBL for bioactive compounds against a specific target.",
    # clinical_trials
    "get_clinical_trial_details": "Retrieve comprehensive clinical trial record from ClinicalTrials.gov.",
    "search_trials_by_target": "Search ClinicalTrials.gov for trials targeting a specific gene/protein.",
    "get_trial_adverse_events": "Extract adverse event data from a clinical trial's posted results.",
    # molecular_targets
    "get_protein_atlas_summary": "Get Human Protein Atlas summary including subcellular localization and expression.",
    "get_tractability_assessment": "Assess target tractability for different modalities.",
    "get_mouse_ko_phenotypes": "Get mouse knockout phenotype data from IMPC/MGI.",
    "get_chemical_probes": "Get high-quality chemical probes for a target from Probes & Drugs.",
    # biological_pathways
    "get_reactome_pathways": "Get Reactome pathway annotations for a gene.",
    "get_gene_ontology": "Get Gene Ontology annotations for a gene.",
    "get_pathway_enrichment": "Run Reactome pathway enrichment analysis on a gene list.",
    # biological_interactions
    "query_protein_interactions": "Query STRING and IntAct for protein-protein interactions.",
    "query_pathway_membership": "Query Reactome for pathway membership of a gene.",
    "query_signaling_network": "Query SignaLink and Reactome for signaling network context.",
    # tissue_expression
    "query_tissue_expression": "Query GTEx v8 for median TPM expression across 54 tissues.",
    # single_cell_atlas
    "query_cellxgene_census": "Query CELLxGENE Census for single-cell expression data.",
    "download_atlas": "Download a single-cell atlas from CELLxGENE Census as AnnData.",
    "compute_tau_specificity": "Compute tau cell-type specificity index for a gene across cell types.",
    "compute_bimodality": "Compute expression bimodality coefficient across cell types.",
    # functional_genomics
    "query_crispr_essentiality": "Query DepMap CRISPR essentiality screens for a gene.",
    "query_tahoe_perturbation": "Query Tahoe-100M pseudobulked log-fold change values for a drug perturbation.",
    "compute_hallmark_scores": "Compute 6 hallmark pathway scores from drug perturbation LFC values.",
    # diseases
    "get_disease_associations": "Get disease associations for a gene from Open Targets and OMIM.",
    "get_disease_ontology": "Get disease ontology information including EFO, MONDO, and Orphanet mappings.",
}


def _run_health_checks() -> None:
    """Run health checks for all MCP tools and store results in session state."""
    from virtual_biotech.mcp_servers.health_check import get_checks, run_check

    checks = get_checks()
    total = sum(len(tools) for tools in checks.values())

    progress = st.progress(0, text="Running health checks...")
    results: dict[str, dict[str, tuple[float, str]]] = {}
    completed = 0

    for server, tools in checks.items():
        server_results: dict[str, tuple[float, str]] = {}
        for tool_name, fn in tools:
            progress.progress(completed / total, text=f"Checking {_mcp_server_display_name(server)}: {tool_name}...")
            elapsed, status = run_check(fn)
            server_results[tool_name] = (elapsed, status)
            completed += 1
        results[server] = server_results

    progress.progress(1.0, text="Health checks complete.")
    st.session_state["mcp_health_results"] = results


def _build_server_to_agents() -> dict[str, list[str]]:
    """Build a mapping of MCP server name -> list of agent display names that use it."""
    mapping = division_mcp_map()
    server_agents: dict[str, list[str]] = {}
    for agents in mapping.values():
        for agent_name, server_names in agents.items():
            for server in server_names:
                server_agents.setdefault(server, []).append(agent_name)
    return server_agents


def _latency_cell(elapsed: float, status: str) -> str:
    """Render a latency table cell with color coding."""
    if status != "OK":
        return f'<span class="status-err">ERR {elapsed:.2f}s</span>'
    if elapsed < 0.5:
        css = "status-fast"
    elif elapsed < 1.0:
        css = "status-medium"
    else:
        css = "status-slow"
    return f'<span class="{css}">{elapsed:.2f}s</span>'


def render() -> None:
    st.header("MCP Servers")
    st.caption("Each MCP server, its tools, databases, and which agents use it.")

    if st.button("Run Health Check", type="primary"):
        _run_health_checks()

    health: dict[str, dict[str, tuple[float, str]]] | None = st.session_state.get("mcp_health_results")

    # Summary metrics after health check
    if health:
        all_checks = [(tool, elapsed, status) for server_checks in health.values() for tool, (elapsed, status) in server_checks.items()]
        ok_count = sum(1 for *_, s in all_checks if s == "OK")
        err_count = len(all_checks) - ok_count
        times = [e for _, e, _ in all_checks]
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Tools checked", len(all_checks))
        col2.metric("Passed", ok_count)
        col3.metric("Failed", err_count)
        col4.metric("Median latency", f"{sorted(times)[len(times) // 2]:.2f}s")

    st.divider()

    # One expander per MCP server
    server_agents = _build_server_to_agents()
    has_health = health is not None

    for server in sorted(MCP_SERVER_TOOLS):
        display = _mcp_server_display_name(server)
        agents = server_agents.get(server, [])
        agent_str = ", ".join(agents) if agents else "—"
        tools = MCP_SERVER_TOOLS.get(server, [])

        # Build expander label with status indicator if health check ran
        label = f"**{display}** — {len(tools)} tools — used by: {agent_str}"
        if has_health and server in health:
            server_checks = health[server]
            all_ok = all(s == "OK" for _, s in server_checks.values())
            label = f"{'OK' if all_ok else 'ERR'} {label}"

        with st.expander(label, expanded=False):
            # Table header
            header = "<tr><th>Tool</th><th>Database</th>"
            if has_health:
                header += "<th>Latency</th><th>Status</th>"
            header += "</tr>"

            table_rows: list[str] = []
            server_health = health.get(server, {}) if has_health else {}
            for tool in tools:
                desc = html.escape(_TOOL_DESCRIPTIONS.get(tool, ""))
                db = html.escape(_TOOL_DATABASE.get(tool, "—"))
                row = (
                    f'<tr><td><span class="tool-name"><code>{html.escape(tool)}</code>'
                    f'<span class="tooltip">{desc}</span></span></td>'
                    f"<td>{db}</td>"
                )
                if has_health:
                    if tool in server_health:
                        elapsed, status = server_health[tool]
                        row += f"<td>{_latency_cell(elapsed, status)}</td>"
                        status_label = "OK" if status == "OK" else html.escape(status)
                        row += f"<td>{status_label}</td>"
                    else:
                        row += "<td>—</td><td>—</td>"
                row += "</tr>"
                table_rows.append(row)

            rows_html = "\n".join(table_rows)
            st.html(
                f'{_TABLE_CSS}<table class="mcp-table">'
                f"{header}{rows_html}</table>"
            )

    st.divider()
    total_tools = sum(len(t) for t in MCP_SERVER_TOOLS.values())
    st.markdown(f"**{len(MCP_SERVER_TOOLS)} MCP servers** — {total_tools} tools total")
