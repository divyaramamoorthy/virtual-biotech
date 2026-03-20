"""Tests for agent definition configuration."""

from claude_agent_sdk import AgentDefinition


class TestAgentDefinitions:
    """Verify that agent definitions are properly configured."""

    def test_cso_has_all_sub_agents(self):
        """CSO has all expected sub-agents configured."""
        from virtual_biotech.agents.cso import CSO_SUB_AGENTS

        expected_agents = {
            "chief_of_staff",
            "scientific_reviewer",
            "statistical_genetics",
            "functional_genomics",
            "single_cell_atlas",
            "bio_pathways_ppi",
            "safety_single_cell",
            "fda_safety_officer",
            "target_biologist",
            "pharmacologist",
            "clinical_trialist",
        }
        assert set(CSO_SUB_AGENTS.keys()) == expected_agents

    def test_all_sub_agents_are_agent_definitions(self):
        """All CSO sub-agents are AgentDefinition instances."""
        from virtual_biotech.agents.cso import CSO_SUB_AGENTS

        for name, agent in CSO_SUB_AGENTS.items():
            assert isinstance(agent, AgentDefinition), f"{name} is not an AgentDefinition"

    def test_staff_agents_use_haiku(self):
        """Chief of Staff and Scientific Reviewer use Haiku model."""
        from virtual_biotech.agents.chief_of_staff import chief_of_staff_agent
        from virtual_biotech.agents.scientific_reviewer import scientific_reviewer_agent

        assert chief_of_staff_agent.model == "haiku"
        assert scientific_reviewer_agent.model == "haiku"

    def test_scientist_agents_use_sonnet(self):
        """All scientist agents use Sonnet model."""
        from virtual_biotech.agents.clinical_officers.clinical_trialist import clinical_trialist_agent
        from virtual_biotech.agents.modality_selection.pharmacologist import pharmacologist_agent
        from virtual_biotech.agents.modality_selection.target_biologist import target_biologist_agent
        from virtual_biotech.agents.target_id.functional_genomics import functional_genomics_agent
        from virtual_biotech.agents.target_id.single_cell_atlas import single_cell_atlas_agent
        from virtual_biotech.agents.target_id.statistical_genetics import statistical_genetics_agent
        from virtual_biotech.agents.target_safety.bio_pathways_ppi import bio_pathways_ppi_agent
        from virtual_biotech.agents.target_safety.fda_safety_officer import fda_safety_officer_agent

        agents = [
            statistical_genetics_agent,
            functional_genomics_agent,
            single_cell_atlas_agent,
            bio_pathways_ppi_agent,
            fda_safety_officer_agent,
            target_biologist_agent,
            pharmacologist_agent,
            clinical_trialist_agent,
        ]
        for agent in agents:
            assert agent.model == "sonnet", f"{agent.description} does not use sonnet"

    def test_cso_has_no_data_tools(self):
        """CSO agent definition has no direct data access tools."""
        from virtual_biotech.agents.cso import cso_agent

        assert cso_agent.tools == []

    def test_scientific_reviewer_has_no_tools(self):
        """Scientific Reviewer has no data access tools."""
        from virtual_biotech.agents.scientific_reviewer import scientific_reviewer_agent

        assert scientific_reviewer_agent.tools == []

    def test_clinical_trialist_has_web_tools(self):
        """Clinical Trialist has web search and fetch tools."""
        from virtual_biotech.agents.clinical_officers.clinical_trialist import clinical_trialist_agent

        assert "WebSearch" in clinical_trialist_agent.tools
        assert "WebFetch" in clinical_trialist_agent.tools

    def test_fda_safety_shared_between_divisions(self):
        """FDA Safety Officer is shared between target_safety and clinical_officers."""
        from virtual_biotech.agents.clinical_officers.fda_safety_officer import fda_safety_officer_agent as clinical_fda
        from virtual_biotech.agents.target_safety.fda_safety_officer import fda_safety_officer_agent as safety_fda

        assert clinical_fda is safety_fda

    def test_all_agents_have_descriptions(self):
        """All agents have non-empty descriptions."""
        from virtual_biotech.agents.cso import CSO_SUB_AGENTS

        for name, agent in CSO_SUB_AGENTS.items():
            assert agent.description, f"{name} has no description"
            assert len(agent.description) > 10, f"{name} description too short"


class TestMCPToolNaming:
    """Verify MCP tools use the SDK-namespaced mcp__<server>__<tool> convention."""

    def test_tools_for_mcp_servers_uses_namespaced_format(self):
        """tools_for_mcp_servers returns mcp__<server>__<tool> names."""
        from virtual_biotech.config import tools_for_mcp_servers

        tools = tools_for_mcp_servers(["human_genetics"])
        assert len(tools) > 0
        for tool in tools:
            assert tool.startswith("mcp__human_genetics__"), f"Tool {tool} missing mcp__ namespace prefix"

    def test_all_sub_agent_mcp_tools_are_namespaced(self):
        """Every MCP tool in sub-agent definitions uses the mcp__ prefix."""
        from virtual_biotech.agents.cso import CSO_SUB_AGENTS

        non_mcp_tools = {"Bash", "WebSearch", "WebFetch"}
        for name, agent in CSO_SUB_AGENTS.items():
            for tool in agent.tools:
                if tool not in non_mcp_tools:
                    assert tool.startswith("mcp__"), (
                        f"Agent '{name}' has non-namespaced MCP tool: '{tool}'. "
                        f"Expected format: mcp__<server>__<tool>"
                    )

    def test_sub_agent_mcp_tools_reference_valid_servers(self):
        """MCP tools in sub-agents reference servers that exist in MCP_SERVERS."""
        from virtual_biotech.agents.cso import CSO_SUB_AGENTS
        from virtual_biotech.config import MCP_SERVERS

        non_mcp_tools = {"Bash", "WebSearch", "WebFetch"}
        for name, agent in CSO_SUB_AGENTS.items():
            for tool in agent.tools:
                if tool in non_mcp_tools:
                    continue
                # Extract server name from mcp__<server>__<tool>
                parts = tool.split("__")
                assert len(parts) == 3, f"Agent '{name}' tool '{tool}' doesn't match mcp__<server>__<tool>"
                server = parts[1]
                assert server in MCP_SERVERS, (
                    f"Agent '{name}' references MCP server '{server}' which is not in MCP_SERVERS"
                )

    def test_cso_agent_definition_has_no_mcp_tools(self):
        """CSO AgentDefinition has no tools — it only delegates via Agent tool."""
        from virtual_biotech.agents.cso import cso_agent

        assert cso_agent.tools == [], "CSO should have no tools in its AgentDefinition"
        for tool in cso_agent.tools:
            assert not tool.startswith("mcp__"), "CSO must not have MCP tools"
