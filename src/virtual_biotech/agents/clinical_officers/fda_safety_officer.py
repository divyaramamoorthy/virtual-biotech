"""FDA Safety Officer agent (Clinical Officers division) — re-exports from target_safety."""

# The FDA Safety Officer serves both the Target Safety and Clinical Officers divisions.
# Re-export the agent definition from target_safety.
from virtual_biotech.agents.target_safety.fda_safety_officer import fda_safety_officer_agent

__all__ = ["fda_safety_officer_agent"]
