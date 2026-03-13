"""Configuration for Virtual Biotech agents and MCP servers."""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Model configuration
SCIENTIST_MODEL = "claude-sonnet-4-6"
STAFF_MODEL = "claude-haiku-4-6"

# API configuration — routes through LiteLLM proxy at Formation Bio
LITELLM_PROXY_API_KEY = os.environ.get("LITELLM_PROXY_API_KEY", "")
ANTHROPIC_BASE_URL = None

if not LITELLM_PROXY_API_KEY:
    raise ValueError("LITELLM_PROXY_API_KEY environment variable is required.")

# MCP server commands — each server is launched as a subprocess via `uv run`
MCP_SERVER_BASE = [sys.executable, "-m"]


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

# Parallel trial extraction settings
MAX_CONCURRENT_TRIAL_AGENTS = 100
