"""Tests for MCP server tool registration."""

import asyncio

import pytest

from virtual_biotech.mcp_servers.biological_interactions import mcp as bio_interactions_mcp
from virtual_biotech.mcp_servers.biological_pathways import mcp as bio_pathways_mcp
from virtual_biotech.mcp_servers.clinical_trials import mcp as clinical_trials_mcp
from virtual_biotech.mcp_servers.diseases import mcp as diseases_mcp
from virtual_biotech.mcp_servers.drugs import mcp as drugs_mcp
from virtual_biotech.mcp_servers.functional_genomics import mcp as functional_genomics_mcp
from virtual_biotech.mcp_servers.human_genetics import mcp as human_genetics_mcp
from virtual_biotech.mcp_servers.molecular_targets import mcp as molecular_targets_mcp
from virtual_biotech.mcp_servers.single_cell_atlas import mcp as single_cell_atlas_mcp
from virtual_biotech.mcp_servers.tissue_expression import mcp as tissue_expression_mcp


def _get_tool_names(mcp_server) -> list[str]:
    """Extract registered tool names from a FastMCP server."""
    tools = asyncio.get_event_loop().run_until_complete(mcp_server.list_tools())
    return [t.name for t in tools]


class TestMCPServerRegistration:
    """Verify that all MCP servers have the expected tools registered."""

    @pytest.fixture(autouse=True)
    def _setup_event_loop(self):
        """Ensure event loop exists for async tool listing."""
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

    def test_human_genetics_tools(self):
        """Human genetics server has 7 tools."""
        tools = _get_tool_names(human_genetics_mcp)
        assert len(tools) == 7
        expected = {
            "query_gwas_associations",
            "query_credible_sets",
            "query_l2g_scores",
            "query_qtl_colocalization",
            "query_rare_variants",
            "query_pharmacogenomics",
            "query_enhancer_gene",
        }
        assert set(tools) == expected

    def test_clinical_trials_tools(self):
        """Clinical trials server has 3 tools."""
        tools = _get_tool_names(clinical_trials_mcp)
        assert len(tools) == 3
        expected = {"get_clinical_trial_details", "search_trials_by_target", "get_trial_adverse_events"}
        assert set(tools) == expected

    def test_drugs_tools(self):
        """Drugs server has 5 tools."""
        tools = _get_tool_names(drugs_mcp)
        assert len(tools) == 5

    def test_bio_interactions_tools(self):
        """Biological interactions server has 3 tools."""
        tools = _get_tool_names(bio_interactions_mcp)
        assert len(tools) == 3

    def test_bio_pathways_tools(self):
        """Biological pathways server has 3 tools."""
        tools = _get_tool_names(bio_pathways_mcp)
        assert len(tools) == 3

    def test_molecular_targets_tools(self):
        """Molecular targets server has 4 tools."""
        tools = _get_tool_names(molecular_targets_mcp)
        assert len(tools) == 4

    def test_tissue_expression_tools(self):
        """Tissue expression server has 1 tool."""
        tools = _get_tool_names(tissue_expression_mcp)
        assert len(tools) == 1

    def test_functional_genomics_tools(self):
        """Functional genomics server has 3 tools."""
        tools = _get_tool_names(functional_genomics_mcp)
        assert len(tools) == 3
        expected = {"query_crispr_essentiality", "query_tahoe_perturbation", "compute_hallmark_scores"}
        assert set(tools) == expected

    def test_single_cell_atlas_tools(self):
        """Single cell atlas server has 4 tools."""
        tools = _get_tool_names(single_cell_atlas_mcp)
        assert len(tools) == 4
        expected = {"query_cellxgene_census", "download_atlas", "compute_tau_specificity", "compute_bimodality"}
        assert set(tools) == expected

    def test_diseases_tools(self):
        """Diseases server has 2 tools."""
        tools = _get_tool_names(diseases_mcp)
        assert len(tools) == 2


class TestMCPServerNames:
    """Verify that MCP servers have correct names."""

    def test_server_names(self):
        """Each server has its expected name."""
        assert human_genetics_mcp.name == "human-genetics"
        assert clinical_trials_mcp.name == "clinical-trials"
        assert drugs_mcp.name == "drugs"
        assert bio_interactions_mcp.name == "biological-interactions"
        assert bio_pathways_mcp.name == "biological-pathways"
        assert molecular_targets_mcp.name == "molecular-targets"
        assert tissue_expression_mcp.name == "tissue-expression"
        assert diseases_mcp.name == "diseases"
        assert functional_genomics_mcp.name == "functional-genomics"
        assert single_cell_atlas_mcp.name == "single-cell-atlas"
