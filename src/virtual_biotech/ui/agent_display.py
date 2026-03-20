"""Agent metadata for display in UI and CLI.

Pure data module with no UI framework dependency — shared by Chainlit app
and CLI orchestrator.
"""

from __future__ import annotations

from virtual_biotech.agents.cso import CSO_SUB_AGENTS

# Agent key -> (friendly name, division)
AGENT_DISPLAY: dict[str, tuple[str, str]] = {
    "chief_of_staff": ("Chief of Staff", "Office of the CSO"),
    "scientific_reviewer": ("Scientific Reviewer", "Office of the CSO"),
    "statistical_genetics": ("Statistical Genetics", "Target Identification"),
    "functional_genomics": ("Functional Genomics", "Target Identification"),
    "single_cell_atlas": ("Single Cell Atlas", "Target Identification"),
    "bio_pathways_ppi": ("Bio Pathways & PPI", "Target Safety"),
    "safety_single_cell": ("Single Cell (Safety)", "Target Safety"),
    "fda_safety_officer": ("FDA Safety Officer", "Target Safety"),
    "target_biologist": ("Target Biologist", "Modality Selection"),
    "pharmacologist": ("Pharmacologist", "Modality Selection"),
    "clinical_trialist": ("Clinical Trialist", "Clinical Officers"),
}

DIVISION_ICONS: dict[str, str] = {
    "Office of the CSO": "🏛️",
    "Target Identification": "🎯",
    "Target Safety": "🛡️",
    "Modality Selection": "💊",
    "Clinical Officers": "🏥",
}

# Reverse lookups for agent key resolution
_DESCRIPTION_TO_KEY: dict[str, str] = {agent.description: key for key, agent in CSO_SUB_AGENTS.items()}
_NORMALISED_KEYS: list[tuple[str, str]] = [(key, key.replace("_", " ")) for key in CSO_SUB_AGENTS]


def resolve_agent_key(description: str, task_type: str | None = None) -> str:
    """Best-effort resolution of which CSO sub-agent a task belongs to."""
    if task_type and task_type in CSO_SUB_AGENTS:
        return task_type
    if description in _DESCRIPTION_TO_KEY:
        return _DESCRIPTION_TO_KEY[description]
    desc_lower = description.lower()
    for key, normalised in _NORMALISED_KEYS:
        if normalised in desc_lower:
            return key
    return ""


def display_name(agent_key: str, fallback: str = "") -> str:
    """Return the friendly display name for an agent key."""
    name, _ = AGENT_DISPLAY.get(agent_key, (fallback or agent_key, "Other"))
    return name


def division_for(agent_key: str) -> str:
    """Return the division name for an agent key."""
    _, div = AGENT_DISPLAY.get(agent_key, ("", "Other"))
    return div


def division_icon(division: str) -> str:
    """Return the emoji icon for a division."""
    return DIVISION_ICONS.get(division, "🔬")
