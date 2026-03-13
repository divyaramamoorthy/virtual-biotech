"""Streamlit UI for the Virtual Biotech multi-agent drug discovery platform."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path

import streamlit as st
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
from claude_agent_sdk.types import (
    AssistantMessage,
    TaskNotificationMessage,
    TaskProgressMessage,
    TaskStartedMessage,
    TextBlock,
    ToolUseBlock,
)
from streamlit.delta_generator import DeltaGenerator

from virtual_biotech.agents.cso import CSO_SUB_AGENTS, CSO_SYSTEM_PROMPT
from virtual_biotech.config import ANTHROPIC_BASE_URL, LITELLM_PROXY_API_KEY, SCIENTIST_MODEL

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SDK_ENV = {
    "ANTHROPIC_API_KEY": LITELLM_PROXY_API_KEY,
    "ANTHROPIC_BASE_URL": ANTHROPIC_BASE_URL,
}

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

_STATUS_ICONS: dict[str, str] = {
    "running": "🔄",
    "completed": "✅",
    "failed": "❌",
    "stopped": "⏹️",
}

# Reverse lookups for agent key resolution
_DESCRIPTION_TO_KEY: dict[str, str] = {agent.description: key for key, agent in CSO_SUB_AGENTS.items()}
_NORMALISED_KEYS: list[tuple[str, str]] = [(key, key.replace("_", " ")) for key in CSO_SUB_AGENTS]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class AgentTask:
    """Tracks a single agent task's lifecycle."""

    task_id: str
    description: str
    agent_key: str = ""
    status: str = "running"  # running | completed | failed | stopped
    summary: str = ""
    output: str = ""
    last_tool: str = ""
    start_time: float = field(default_factory=time.time)

    @property
    def display_name(self) -> str:
        name, _ = AGENT_DISPLAY.get(self.agent_key, (self.description[:50], "Other"))
        return name

    @property
    def division(self) -> str:
        _, div = AGENT_DISPLAY.get(self.agent_key, (self.description[:50], "Other"))
        return div


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

_SESSION_DEFAULTS: dict[str, object] = {
    "messages": [],
    "tasks": {},
    "total_cost": 0.0,
    "total_turns": 0,
    "running": False,
}


def _init_session() -> None:
    for key, default in _SESSION_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = default


# ---------------------------------------------------------------------------
# Agent key resolution
# ---------------------------------------------------------------------------


def _resolve_agent_key(message: TaskStartedMessage) -> str:
    """Best-effort resolution of which CSO sub-agent a task belongs to."""
    if message.task_type and message.task_type in CSO_SUB_AGENTS:
        return message.task_type
    if message.description in _DESCRIPTION_TO_KEY:
        return _DESCRIPTION_TO_KEY[message.description]
    desc_lower = message.description.lower()
    for key, normalised in _NORMALISED_KEYS:
        if normalised in desc_lower:
            return key
    return ""


# ---------------------------------------------------------------------------
# Async orchestrator bridge
# ---------------------------------------------------------------------------


async def _run_query(user_query: str, status_container: DeltaGenerator, chat_container: DeltaGenerator) -> str:
    """Run the CSO orchestrator and stream updates into *status_container* and *chat_container*."""
    options = ClaudeAgentOptions(
        system_prompt=CSO_SYSTEM_PROMPT,
        model=SCIENTIST_MODEL,
        allowed_tools=["Agent"],
        disallowed_tools=["Bash", "Write", "Edit", "Read", "Glob", "Grep", "NotebookEdit"],
        agents=CSO_SUB_AGENTS,
        max_turns=50,
        env=_SDK_ENV,
    )

    streaming_text = ""
    final_result = ""

    async for message in query(prompt=user_query, options=options):
        match message:
            case TaskStartedMessage():
                agent_key = _resolve_agent_key(message)
                task = AgentTask(task_id=message.task_id, description=message.description, agent_key=agent_key)
                st.session_state.tasks[message.task_id] = task
                status_container.write(f"▶ **Started:** {task.display_name}")

            case TaskProgressMessage():
                task = st.session_state.tasks.get(message.task_id)
                if task:
                    task.last_tool = message.last_tool_name or task.last_tool
                tool_info = f" — {message.last_tool_name}" if message.last_tool_name else ""
                status_container.update(label=f"Working: {message.description}{tool_info}")

            case TaskNotificationMessage():
                task = st.session_state.tasks.get(message.task_id)
                if task:
                    task.status = message.status
                    task.summary = message.summary or ""
                    if message.output_file:
                        output_path = Path(message.output_file)
                        if output_path.is_file():
                            task.output = output_path.read_text(encoding="utf-8")
                    if not task.output and task.summary:
                        task.output = task.summary
                icon = "✅" if message.status == "completed" else "❌"
                status_container.write(f"{icon} **{message.summary or message.status}**")

            case AssistantMessage():
                for block in message.content:
                    if isinstance(block, TextBlock):
                        streaming_text += block.text + "\n\n"
                        chat_container.markdown(streaming_text)
                    elif isinstance(block, ToolUseBlock):
                        status_container.write(f"🔧 Tool: `{block.name}`")

            case ResultMessage():
                if message.total_cost_usd:
                    st.session_state.total_cost += message.total_cost_usd
                st.session_state.total_turns += message.num_turns
                if message.subtype == "success":
                    final_result = message.result or ""
                else:
                    final_result = f"**Error:** {message.subtype} — {message.result}"
                duration_s = message.duration_ms / 1000
                cost = f" — ${message.total_cost_usd:.2f}" if message.total_cost_usd else ""
                status_container.update(state="complete", label=f"CSO completed in {duration_s:.1f}s{cost}")

    return final_result.strip() or streaming_text.strip()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------


def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown("## Virtual Biotech")
        st.caption("Multi-agent AI drug discovery platform")
        st.divider()

        col1, col2 = st.columns(2)
        col1.metric("Total Cost", f"${st.session_state.total_cost:.2f}")
        col2.metric("Turns", st.session_state.total_turns)
        st.divider()

        if st.session_state.tasks:
            st.markdown("### Agent Activity")

            # Group tasks by division
            divisions: dict[str, list[AgentTask]] = {}
            for task in st.session_state.tasks.values():
                divisions.setdefault(task.division, []).append(task)

            for division, tasks in divisions.items():
                icon = DIVISION_ICONS.get(division, "🔬")
                st.markdown(f"**{icon} {division}**")
                for task in tasks:
                    status_icon = _STATUS_ICONS.get(task.status, "❓")
                    if task.status == "running":
                        tool_info = f" — `{task.last_tool}`" if task.last_tool else ""
                        st.caption(f"{status_icon} {task.display_name}{tool_info}")
                    elif task.output:
                        with st.expander(f"{status_icon} {task.display_name}"):
                            st.markdown(task.output)
                    else:
                        st.caption(f"{status_icon} {task.display_name}")
        else:
            st.info("No agents dispatched yet. Submit a query to get started.")

        st.divider()

        with st.expander("Available Agents"):
            for key, (display_name, division) in AGENT_DISPLAY.items():
                icon = DIVISION_ICONS.get(division, "🔬")
                st.caption(f"{icon} **{display_name}** — {division}")

        if st.button("Clear Session", use_container_width=True):
            for key in _SESSION_DEFAULTS:
                st.session_state.pop(key, None)
            st.rerun()


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


def _render_chat() -> None:
    st.title("🧬 Virtual Biotech")
    st.caption("AI-powered drug discovery — ask the CSO anything about target validation, safety, modality, or clinical strategy.")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if user_input := st.chat_input("Ask the CSO a question...", disabled=st.session_state.running):
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        st.session_state.running = True
        st.session_state.tasks = {}

        with st.chat_message("assistant"):
            chat_container = st.empty()
            with st.status("CSO is orchestrating agents...", expanded=True) as status:
                result = asyncio.run(_run_query(user_input, status, chat_container))
            chat_container.markdown(result)

        st.session_state.messages.append({"role": "assistant", "content": result})
        st.session_state.running = False
        st.rerun()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(page_title="Virtual Biotech", page_icon="🧬", layout="wide", initial_sidebar_state="expanded")
    _init_session()
    _render_sidebar()
    _render_chat()


if __name__ == "__main__":
    main()
