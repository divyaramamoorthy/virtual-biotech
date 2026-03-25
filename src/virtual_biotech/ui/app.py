"""Streamlit UI for the Virtual Biotech multi-agent drug discovery platform.

Implements the full 3-phase orchestrator workflow:
  Phase 1: Chief of Staff briefing + CSO clarification questions (parallel)
  Phase 2: User answers clarification questions (blocking)
  Phase 3: CSO delegates to specialist sub-agents, streams synthesis

Launch with:
    uv run streamlit run src/virtual_biotech/ui/app.py
"""

from __future__ import annotations

import asyncio
import os
import re
import threading
import time
from enum import Enum

import streamlit as st
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
from claude_agent_sdk.types import AssistantMessage, TextBlock
from streamlit.delta_generator import DeltaGenerator

from virtual_biotech.agents.chief_of_staff import CHIEF_OF_STAFF_PROMPT
from virtual_biotech.agents.cso import CSO_SUB_AGENTS, CSO_SYSTEM_PROMPT
from virtual_biotech.config import (
    ANTHROPIC_BASE_URL,
    LITELLM_PROXY_API_KEY,
    MCP_SERVER_TOOLS,
    MCP_SERVERS,
    SCIENTIST_MODEL,
    STAFF_MODEL,
    tools_for_mcp_servers,
)
from virtual_biotech.orchestrator import AuditTracker, _TaskRecord
from virtual_biotech.ui.message_handler import StreamlitMessageHandler
from virtual_biotech.ui.pages import mcp_overview

# ---------------------------------------------------------------------------
# SDK environment
# ---------------------------------------------------------------------------

os.environ.pop("CLAUDECODE", None)

_SDK_ENV = {
    **os.environ,
    "ANTHROPIC_API_KEY": LITELLM_PROXY_API_KEY,
    "ANTHROPIC_BASE_URL": ANTHROPIC_BASE_URL,
}

_STATUS_ICONS = {"running": "[...]", "completed": "[OK]", "failed": "[FAIL]", "stopped": "[STOP]"}


# ---------------------------------------------------------------------------
# Session state enum for the 3-phase workflow
# ---------------------------------------------------------------------------


class Phase(str, Enum):
    IDLE = "idle"
    PHASE1 = "phase1"  # briefing + clarification running
    PHASE2 = "phase2"  # waiting for user clarification
    PHASE3 = "phase3"  # CSO orchestration running
    DONE = "done"
    ERROR = "error"  # recoverable error state
    FOLLOWUP = "followup"  # follow-up conversation mode


def _init_session() -> None:
    defaults: dict[str, object] = {
        "messages": [],
        "phase": Phase.IDLE,
        "user_query": "",
        "briefing": "",
        "questions": "",
        "clarified_intent": "",
        "handler": None,
        "result": "",
        "agent_reports": [],  # list of {"name": str, "icon": str, "output": str, "log": list[str]}
        "selected_report": None,  # index into agent_reports, or None for chat view
        "errors": [],  # list of {"phase": str, "detail": str}
        "report_panel_open": False,  # persist layout choice across reruns
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default


# ---------------------------------------------------------------------------
# Phase runners (async)
# ---------------------------------------------------------------------------


async def _run_chief_of_staff(user_query: str, tracker: AuditTracker, handler: StreamlitMessageHandler) -> str:
    options = ClaudeAgentOptions(
        system_prompt=CHIEF_OF_STAFF_PROMPT,
        model=STAFF_MODEL,
        disallowed_tools=["Bash", "Read", "Write", "Edit", "Glob", "Grep", "NotebookEdit", "Agent"],
        allowed_tools=["WebSearch", "WebFetch"],
        max_turns=1,
        env=_SDK_ENV,
    )

    briefing = ""
    duration_ms = 0
    async for message in query(prompt=user_query, options=options):
        tracker.handle_message(message)
        handler.handle(message)
        if isinstance(message, ResultMessage):
            duration_ms = message.duration_ms
            if message.subtype == "success":
                briefing = message.result or ""

    rec = _TaskRecord(
        task_id="chief_of_staff",
        description="Chief of Staff intelligence briefing",
        started_at=0,
        started_wall=time.strftime("%H:%M:%S"),
        status="completed" if briefing else "failed",
        duration_secs=duration_ms / 1000,
        summary="Rapid intelligence briefing for CSO",
        output=briefing or None,
    )
    tracker._completed.append(rec)
    tracker._write_agent_report(rec)
    return briefing


async def _run_cso_clarification(user_query: str, tracker: AuditTracker, handler: StreamlitMessageHandler) -> str:
    prompt = (
        f"A user has submitted the following research query:\n\n"
        f"{user_query}\n\n"
        f"Before launching any analyses, generate 2-4 focused clarification questions "
        f"that will help you decompose this into the right sub-tasks. Ask about:\n"
        f"- Specific targets, genes, or pathways of interest\n"
        f"- Therapeutic area or disease context\n"
        f"- Desired scope (quick scan vs. deep dive)\n"
        f"- Preferred output format or focus areas\n\n"
        f"Output ONLY the numbered questions. Do not answer them or provide analysis."
    )

    clarification_system = (
        "You are the Chief Scientific Officer of a virtual biotech. "
        "You have deep expertise in drug discovery, target validation, and clinical development. "
        "Your task right now is ONLY to ask clarification questions. Do NOT perform any analysis."
    )

    options = ClaudeAgentOptions(
        system_prompt=clarification_system,
        model=SCIENTIST_MODEL,
        allowed_tools=[],
        max_turns=3,
        env=_SDK_ENV,
    )

    questions = ""
    async for message in query(prompt=prompt, options=options):
        tracker.handle_message(message)
        handler.handle(message)
        if isinstance(message, ResultMessage):
            if message.subtype == "success":
                questions = message.result or ""

    return questions


def _make_report_callback(container: DeltaGenerator) -> callable:
    """Create a callback that writes agent report expanders into a Streamlit container."""
    reports_ref: list[dict] = st.session_state.agent_reports

    def on_report(name: str, icon: str, output: str, log: list[str]) -> None:
        reports_ref.append({"name": name, "icon": icon, "output": output, "log": log})
        with container.expander(f"{icon} **{name}** Report", expanded=False):
            st.markdown(output)

    return on_report


async def _run_phase1(user_query: str, reports_container: DeltaGenerator) -> tuple[str, str]:
    """Run Phase 1: parallel briefing + clarification. Returns (briefing, questions)."""
    tracker = AuditTracker()
    on_report = _make_report_callback(reports_container)
    handler = StreamlitMessageHandler(on_report=on_report)
    st.session_state.handler = handler

    briefing_task = asyncio.create_task(asyncio.wait_for(_run_chief_of_staff(user_query, tracker, handler), timeout=120))
    try:
        questions = await _run_cso_clarification(user_query, tracker, handler)
    except Exception as e:
        questions = ""
        st.session_state.errors.append({"phase": "phase1", "detail": f"CSO clarification failed: {e}"})

    try:
        briefing = await briefing_task
    except Exception as e:
        briefing = "Chief of Staff briefing unavailable. Proceed with your own assessment."
        st.session_state.errors.append({"phase": "phase1", "detail": f"Chief of Staff briefing failed: {e}"})

    # Save CoS briefing as a report so it's visible immediately
    if briefing:
        on_report("Chief of Staff Briefing", "", briefing, [])

    return briefing, questions


async def _run_phase3(
    user_query: str, briefing: str, clarified_intent: str, handler: StreamlitMessageHandler, reports_container: DeltaGenerator
) -> str:
    """Run Phase 3: CSO orchestration with full context."""
    tracker = AuditTracker()

    cso_sub_agents = {k: v for k, v in CSO_SUB_AGENTS.items() if k != "chief_of_staff"}

    context_parts = [user_query, ""]
    context_parts.append("--- CHIEF OF STAFF INTELLIGENCE BRIEFING ---")
    context_parts.append(briefing)
    context_parts.append("--- END BRIEFING ---")
    context_parts.append("")

    if clarified_intent:
        context_parts.append("--- USER CLARIFIED INTENT ---")
        context_parts.append(clarified_intent)
        context_parts.append("--- END CLARIFIED INTENT ---")
        context_parts.append("")

    context_parts.append(
        "Phase 1 (briefing + clarification) is complete. "
        "Proceed directly to PHASE 2: task decomposition and agent routing. "
        "Do NOT dispatch the Chief of Staff again. "
        "Do NOT ask additional clarification questions — the user has already responded."
    )

    cso_prompt = "\n".join(context_parts)

    all_mcp_tools = tools_for_mcp_servers(list(MCP_SERVER_TOOLS.keys()))
    options = ClaudeAgentOptions(
        system_prompt=CSO_SYSTEM_PROMPT,
        model=SCIENTIST_MODEL,
        allowed_tools=["Agent", *all_mcp_tools],
        agents=cso_sub_agents,
        mcp_servers=MCP_SERVERS,
        max_turns=50,
        env=_SDK_ENV,
    )

    result_text = ""
    async for message in query(prompt=cso_prompt, options=options):
        tracker.handle_message(message)
        handler.handle(message)
        if isinstance(message, AssistantMessage) and message.parent_tool_use_id is None:
            for block in message.content:
                if isinstance(block, TextBlock) and block.text.strip():
                    handler.cso_text_blocks.append(block.text)
        if isinstance(message, ResultMessage):
            if message.subtype == "success":
                result_text = message.result
            else:
                result_text = f"Error: subtype={message.subtype} stop_reason={message.stop_reason} result={message.result}"

    cso_output = max(handler.cso_text_blocks, key=len) if handler.cso_text_blocks else result_text

    cso_rec = _TaskRecord(
        task_id="cso_synthesis",
        description="CSO synthesized report",
        started_at=0,
        started_wall=time.strftime("%H:%M:%S"),
        status="completed" if result_text and not result_text.startswith("Error:") else "failed",
        duration_secs=0,
        summary="Final CSO synthesis integrating all sub-agent analyses",
        output=cso_output or None,
    )
    tracker._completed.append(cso_rec)
    tracker._write_agent_report(cso_rec)
    tracker.write_summary()

    return result_text


async def _run_followup(user_query: str, previous_synthesis: str, agent_reports: list[dict], handler: StreamlitMessageHandler) -> str:
    """Run a follow-up query using previous context without sub-agents."""
    context_parts = [
        "The user has a follow-up question based on a previous analysis.",
        "",
        "--- PREVIOUS CSO SYNTHESIS ---",
        previous_synthesis,
        "--- END PREVIOUS SYNTHESIS ---",
        "",
    ]

    for report in agent_reports:
        context_parts.append(f"--- {report['name']} REPORT ---")
        context_parts.append(report["output"])
        context_parts.append(f"--- END {report['name']} REPORT ---")
        context_parts.append("")

    context_parts.append("--- FOLLOW-UP QUESTION ---")
    context_parts.append(user_query)
    context_parts.append("--- END FOLLOW-UP QUESTION ---")
    context_parts.append("")
    context_parts.append(
        "Answer the follow-up question using the previous analysis context above. "
        "Be specific and reference the data from the agent reports. "
        "Do NOT launch sub-agents or perform new analyses."
    )

    followup_prompt = "\n".join(context_parts)

    options = ClaudeAgentOptions(
        system_prompt=CSO_SYSTEM_PROMPT,
        model=SCIENTIST_MODEL,
        allowed_tools=[],
        max_turns=5,
        env=_SDK_ENV,
    )

    result_text = ""
    async for message in query(prompt=followup_prompt, options=options):
        handler.handle(message)
        if isinstance(message, ResultMessage):
            if message.subtype == "success":
                result_text = message.result or ""
            else:
                result_text = f"Error: {message.result}"

    return result_text


# ---------------------------------------------------------------------------
# Live activity feed helpers
# ---------------------------------------------------------------------------


def _build_activity_markdown(handler: StreamlitMessageHandler) -> str:
    """Build a markdown string showing live agent activity grouped by division."""
    tasks = dict(handler.tasks)  # snapshot for thread safety
    log = list(handler.status_log)  # snapshot

    if not tasks:
        return "Starting analysis..."

    # Group tasks by division
    divisions: dict[str, list] = {}
    for task in tasks.values():
        div_key = f"{task.division_icon} {task.division}"
        if div_key not in divisions:
            divisions[div_key] = []
        divisions[div_key].append(task)

    groups: list[str] = []
    for div_header, div_tasks in divisions.items():
        group_lines = [f"**{div_header}**"]
        for task in div_tasks:
            icon = _STATUS_ICONS.get(task.status, "[...]")
            elapsed = f"({task.elapsed:.0f}s)"
            if task.status == "running":
                tool_info = f" — running: `{task.last_tool}`" if task.last_tool else ""
                group_lines.append(f"&emsp;{icon} {task.display_name} {elapsed}{tool_info}")
            elif task.status == "completed":
                tool_count = len(task.tools_used)
                group_lines.append(f"&emsp;{icon} {task.display_name} {elapsed} — {tool_count} tools used")
            else:
                group_lines.append(f"&emsp;{icon} {task.display_name} {elapsed} — {task.status}")
        groups.append("  \n".join(group_lines))

    parts: list[str] = groups

    # Recent activity log (last 5 entries)
    if log:
        activity_lines = ["**Recent activity:**"]
        for entry in log[-5:]:
            activity_lines.append(f"&emsp;{entry}")
        parts.append("  \n".join(activity_lines))

    return "\n\n".join(parts)


def _parse_questions(questions_text: str) -> list[str]:
    """Parse numbered questions from CSO output."""
    parts = re.split(r"\d+\.\s+", questions_text)
    return [q.strip() for q in parts if q.strip()]


# ---------------------------------------------------------------------------
# Sidebar: agent activity panel
# ---------------------------------------------------------------------------


def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown("## Virtual Biotech")
        st.caption("Multi-agent AI drug discovery platform")
        st.divider()

        # Reports section with count badge
        reports = st.session_state.agent_reports
        report_header = f"### Reports ({len(reports)})" if reports else "### Reports"
        st.markdown(report_header)

        if st.session_state.phase == Phase.PHASE3:
            st.info("Reports will be available after analysis completes.")
        elif reports:
            for i, report in enumerate(reports):
                label = report["name"]
                is_selected = st.session_state.selected_report == i
                btn_type = "primary" if is_selected else "secondary"
                if st.button(label, key=f"report_{i}", use_container_width=True, type=btn_type):
                    # Toggle: click again to close the panel
                    st.session_state.selected_report = None if is_selected else i
                    st.session_state.report_panel_open = st.session_state.selected_report is not None
                    st.rerun()

        # Run stats section
        st.divider()
        st.markdown("### Run Stats")
        handler = st.session_state.get("handler")
        if handler and handler.tasks:
            col1, col2 = st.columns(2)
            col1.metric("Agents", len(handler.tasks))
            col2.metric("Turns", handler.total_turns or "—")

            failed = [t for t in handler.tasks.values() if t.status == "failed"]
            if failed:
                st.error(f"{len(failed)} agent(s) failed")
        else:
            st.caption("No data yet — submit a query to begin.")

        # Clear session at the very bottom with confirmation
        st.divider()
        with st.popover("Clear Session", use_container_width=True):
            st.warning("This will clear all results and reports.")
            if st.button("Confirm Clear", type="primary", key="confirm_clear"):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()


# ---------------------------------------------------------------------------
# Main chat UI
# ---------------------------------------------------------------------------


def _render_chat() -> None:
    st.caption("AI-powered drug discovery — ask the CSO anything about target validation, safety, modality, or clinical strategy.")

    # Display message history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    phase = st.session_state.phase

    # Phase ERROR: show error detail with retry option
    if phase == Phase.ERROR:
        with st.chat_message("assistant"):
            st.error("An error occurred during analysis.")
            for err in st.session_state.errors:
                st.warning(f"**{err['phase']}:** {err['detail']}")
            if st.button("Retry", type="primary"):
                st.session_state.errors.clear()
                st.session_state.phase = Phase.PHASE1
                st.rerun()
        return

    # Phase 2: structured clarification form
    if phase == Phase.PHASE2:
        with st.chat_message("assistant"):
            # Show briefing context in a collapsible expander
            if st.session_state.briefing:
                with st.expander("Intelligence Briefing Context", expanded=False):
                    st.markdown(st.session_state.briefing)

            st.markdown(f"**The CSO has some questions before proceeding:**\n\n{st.session_state.questions}")

        clarification = st.chat_input("Answer the CSO's questions (or press Enter to skip)...")
        if clarification is not None:
            st.session_state.clarified_intent = clarification
            if clarification:
                st.session_state.messages.append({"role": "user", "content": clarification})
            st.session_state.phase = Phase.PHASE3
            st.rerun()
        return  # Wait for input

    # Phase 3: run CSO orchestration with live activity feed
    if phase == Phase.PHASE3:
        handler: StreamlitMessageHandler = st.session_state.handler
        # Reset handler for Phase 3 but keep existing reports from Phase 1
        handler.tasks.clear()
        handler.cso_text_blocks.clear()
        handler.status_log.clear()
        handler.done = False

        # Container for live report expanders — reports appear here as agents finish
        reports_container = st.container()

        # Re-render existing reports from Phase 1
        for report in st.session_state.agent_reports:
            with reports_container.expander(f"**{report['name']}** Report", expanded=False):
                st.markdown(report["output"])

        # Don't wire up on_report for threaded execution — we emit reports from the main thread
        handler._on_report = None
        handler._emitted_reports.clear()

        with st.chat_message("assistant"):
            chat_container = st.empty()
            with st.status("CSO is analyzing and routing to specialist agents...", expanded=True) as status:
                activity_container = st.empty()

                # Run Phase 3 in a background thread to enable live polling
                result_holder: list[str] = []
                error_holder: list[Exception] = []

                # Capture session state before thread starts — st.session_state
                # is tied to Streamlit's thread-local ScriptRunContext and is not
                # accessible from background threads.
                _user_query = st.session_state.user_query
                _briefing = st.session_state.briefing
                _clarified_intent = st.session_state.clarified_intent

                def _run_in_thread() -> None:
                    try:
                        r = asyncio.run(
                            _run_phase3(
                                _user_query,
                                _briefing,
                                _clarified_intent,
                                handler,
                                reports_container,
                            )
                        )
                        result_holder.append(r)
                    except Exception as e:
                        error_holder.append(e)

                thread = threading.Thread(target=_run_in_thread, daemon=True)
                thread.start()

                # Poll handler state and render live activity feed + emit reports
                emitted_task_ids: set[str] = set()
                while thread.is_alive():
                    activity_md = _build_activity_markdown(handler)
                    activity_container.markdown(activity_md)

                    # Emit reports for newly completed tasks from main thread
                    tasks_snapshot = dict(handler.tasks)
                    for tid, task in tasks_snapshot.items():
                        if (
                            tid not in emitted_task_ids
                            and task.status in ("completed", "failed")
                            and task.output
                            and len(task.output) > 100
                        ):
                            emitted_task_ids.add(tid)
                            st.session_state.agent_reports.append(
                                {"name": task.display_name, "icon": task.division_icon, "output": task.output, "log": list(task.log)}
                            )
                            with reports_container.expander(f"{task.division_icon} **{task.display_name}** Report", expanded=False):
                                st.markdown(task.output)

                    time.sleep(0.5)

                thread.join()

                # Final sweep: render any remaining activity and emit late reports
                activity_md = _build_activity_markdown(handler)
                activity_container.markdown(activity_md)

                tasks_snapshot = dict(handler.tasks)
                for tid, task in tasks_snapshot.items():
                    if tid not in emitted_task_ids and task.status in ("completed", "failed") and task.output and len(task.output) > 100:
                        emitted_task_ids.add(tid)
                        st.session_state.agent_reports.append(
                            {"name": task.display_name, "icon": task.division_icon, "output": task.output, "log": list(task.log)}
                        )
                        with reports_container.expander(f"{task.division_icon} **{task.display_name}** Report", expanded=False):
                            st.markdown(task.output)

                if error_holder:
                    st.session_state.errors.append({"phase": "phase3", "detail": str(error_holder[0])})
                    status.update(label="CSO analysis failed", state="error")
                    result = ""
                else:
                    result = result_holder[0] if result_holder else ""
                    status.update(label="CSO analysis complete", state="complete")

            # Show warnings for failed agents
            failed_tasks = [t for t in handler.tasks.values() if t.status == "failed"]
            if failed_tasks:
                failed_names = ", ".join(t.display_name for t in failed_tasks)
                st.warning(f"{len(failed_tasks)} agent(s) failed: {failed_names}")

            synthesis = handler.get_cso_synthesis() or result
            chat_container.markdown("Analysis complete — see the **Final Report** in the sidebar.")

            # Add synthesis as the first report entry so it's prominent in the sidebar
            st.session_state.agent_reports.insert(
                0, {"name": "Final Report", "icon": "", "output": synthesis, "log": []}
            )
            # Auto-open the final report panel
            st.session_state.selected_report = 0
            st.session_state.report_panel_open = True

        st.session_state.messages.append({"role": "assistant", "content": synthesis})
        st.session_state.phase = Phase.DONE
        st.session_state.result = synthesis
        st.rerun()
        return

    # Phase FOLLOWUP: run follow-up query without sub-agents
    if phase == Phase.FOLLOWUP:
        handler = st.session_state.handler
        if handler:
            handler.cso_text_blocks.clear()
            handler.done = False
        else:
            handler = StreamlitMessageHandler()
            st.session_state.handler = handler

        with st.chat_message("assistant"):
            chat_container = st.empty()
            with st.status("CSO is answering your follow-up...", expanded=True) as status:
                result = asyncio.run(
                    _run_followup(
                        st.session_state.user_query,
                        st.session_state.result,
                        st.session_state.agent_reports,
                        handler,
                    )
                )
                status.update(label="Follow-up complete", state="complete")

            chat_container.markdown(result)

        st.session_state.messages.append({"role": "assistant", "content": result})
        st.session_state.phase = Phase.DONE
        st.session_state.result = result
        st.rerun()
        return

    # IDLE / DONE: accept new query
    is_running = phase == Phase.PHASE1

    # Adaptive chat input placeholder
    placeholder = {
        Phase.DONE: "Ask a follow-up or start a new analysis...",
        Phase.IDLE: "Ask the CSO a question about a drug target...",
    }.get(phase, "Ask the CSO a question...")

    # Follow-up vs new analysis toggle when DONE
    if phase == Phase.DONE:
        followup_mode = st.session_state.get("followup_mode", True)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Ask follow-up", type="primary" if followup_mode else "secondary", use_container_width=True):
                st.session_state.followup_mode = True
                st.rerun()
        with col2:
            if st.button("Start new analysis", type="primary" if not followup_mode else "secondary", use_container_width=True):
                st.session_state.followup_mode = False
                st.rerun()

    if user_input := st.chat_input(placeholder, disabled=is_running):
        st.session_state.messages.append({"role": "user", "content": user_input})
        st.session_state.user_query = user_input

        with st.chat_message("user"):
            st.markdown(user_input)

        # Determine if this is a follow-up or new analysis
        is_followup = phase == Phase.DONE and st.session_state.get("followup_mode", True) and st.session_state.result

        if is_followup:
            st.session_state.phase = Phase.FOLLOWUP
            st.rerun()
        else:
            # New analysis — preserve reports on retry
            user_lower = user_input.lower().strip()
            if not any(kw in user_lower for kw in ("retry", "try again", "redo")):
                st.session_state.agent_reports = []

            st.session_state.phase = Phase.PHASE1
            st.session_state.errors = []

            # Container for live report expanders — CoS briefing appears here as soon as it's ready
            reports_container = st.container()

            with st.chat_message("assistant"):
                with st.status("Phase 1: Intelligence briefing + clarification...", expanded=True) as status:
                    briefing, questions = asyncio.run(_run_phase1(user_input, reports_container))
                    st.session_state.briefing = briefing
                    st.session_state.questions = questions
                    status.update(label="Phase 1 complete", state="complete")

            # Check if Phase 1 failed completely
            phase1_errors = [e for e in st.session_state.errors if e["phase"] == "phase1"]
            if not questions and len(phase1_errors) >= 2:
                st.session_state.phase = Phase.ERROR
            elif questions:
                st.session_state.phase = Phase.PHASE2
            else:
                st.session_state.phase = Phase.PHASE3
                st.session_state.clarified_intent = ""
            st.rerun()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _render_report_panel() -> None:
    """Render the selected report as the main content area."""
    idx = st.session_state.selected_report
    reports = st.session_state.agent_reports
    if idx is None or idx >= len(reports):
        return
    report = reports[idx]
    if st.button("← Back to chat", type="secondary"):
        st.session_state.selected_report = None
        st.session_state.report_panel_open = False
        st.rerun()
    st.markdown(f"## {report['name']}")
    st.divider()
    st.markdown(report["output"])


def _analysis_page() -> None:
    """Main analysis page — chat + reports."""
    _init_session()
    _render_sidebar()

    has_report_open = st.session_state.report_panel_open and st.session_state.selected_report is not None and st.session_state.agent_reports
    if has_report_open:
        _render_report_panel()
    else:
        _render_chat()


def main() -> None:
    st.set_page_config(page_title="Virtual Biotech", page_icon="🔍", layout="wide", initial_sidebar_state="expanded")

    pages = st.navigation([
        st.Page(_analysis_page, title="Analysis", icon=":material/science:", default=True),
        st.Page(mcp_overview.render, title="MCP Overview", icon=":material/database:"),
    ])
    pages.run()


if __name__ == "__main__":
    main()
