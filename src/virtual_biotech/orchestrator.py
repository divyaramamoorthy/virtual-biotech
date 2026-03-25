"""Main entry point for the Virtual Biotech multi-agent system."""

import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage, query
from claude_agent_sdk.types import (
    AssistantMessage,
    TaskNotificationMessage,
    TaskProgressMessage,
    TaskStartedMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from virtual_biotech.agents.cso import CSO_SUB_AGENTS, CSO_SYSTEM_PROMPT
from virtual_biotech.config import (
    AGENT_TIMEOUT_WARNING_SECS,
    ANTHROPIC_BASE_URL,
    AUDIT_LOG_DIR,
    LITELLM_PROXY_API_KEY,
    MAX_CONCURRENT_TRIAL_AGENTS,
    MCP_SERVER_TOOLS,
    MCP_SERVERS,
    SCIENTIST_MODEL,
    STAFF_MODEL,
    TRACE_ENABLED,
    tools_for_mcp_servers,
)

# Environment variables forwarded to all Claude SDK subprocesses
# Clear CLAUDECODE so SDK subprocesses don't think they're nested inside Claude Code
# (VS Code extension sets this in all terminal sessions)
os.environ.pop("CLAUDECODE", None)

_SDK_ENV = {
    **os.environ,
    "ANTHROPIC_API_KEY": LITELLM_PROXY_API_KEY,
    "ANTHROPIC_BASE_URL": ANTHROPIC_BASE_URL,
}

# ANSI colors for terminal output
_DIM = "\033[2m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_BOLD = "\033[1m"
_RESET = "\033[0m"
_MAGENTA = "\033[35m"

# Mutable trace flag — set from config, can be overridden by --trace CLI flag
_trace = TRACE_ENABLED


def _log(icon: str, color: str, text: str) -> None:
    """Print a timestamped, colored status line to stderr."""
    ts = time.strftime("%H:%M:%S")
    print(f"{_DIM}{ts}{_RESET} {color}{icon}{_RESET} {text}", file=sys.stderr, flush=True)


def _log_trace(label: str, body: str) -> None:
    """Print a multi-line trace block to stderr (only when tracing is on)."""
    ts = time.strftime("%H:%M:%S")
    header = f"{_DIM}{ts}{_RESET} {_MAGENTA}[TRACE]{_RESET} {_BOLD}{label}{_RESET}"
    separator = f"{_MAGENTA}{'─' * 72}{_RESET}"
    print(f"{header}\n{separator}\n{body}\n{separator}", file=sys.stderr, flush=True)


def _read_output_file(path: str) -> str | None:
    """Read an agent output file and extract the final assistant text.

    The Claude Agent SDK writes JSONL conversation logs to output files.
    This function parses the JSONL and extracts text blocks from assistant
    messages, returning the longest one (typically the final analysis).
    Falls back to raw content if parsing fails.
    """
    try:
        with open(path) as f:
            raw = f.read()
    except (OSError, ValueError):
        return None

    if not raw.strip():
        return None

    # Try to parse as JSONL and extract assistant text blocks
    texts: list[str] = []
    for line in raw.strip().splitlines():
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("type") != "assistant":
            continue
        content = msg.get("message", {}).get("content", [])
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text", "").strip():
                texts.append(block["text"])

    if texts:
        # Return the longest text block — typically the final analysis/summary
        return max(texts, key=len)

    # Not JSONL or no text found — return raw content as fallback
    return raw


def _sanitize_filename(name: str) -> str:
    """Convert a description string into a safe filename component."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)[:80]


@dataclass
class _TaskRecord:
    """Tracks a single agent task from start to completion."""

    task_id: str
    description: str
    started_at: float  # time.monotonic()
    started_wall: str  # human-readable wall clock
    status: str = "running"
    duration_secs: float = 0.0
    summary: str = ""
    output: str | None = None


class AuditTracker:
    """Tracks agent tasks, logs reports to disk, and flags slow agents."""

    def __init__(self, audit_dir: str | None = None) -> None:
        ts = time.strftime("%Y-%m-%d_%H%M%S")
        base = audit_dir or AUDIT_LOG_DIR
        self.run_dir = Path(base) / ts
        self.run_dir.mkdir(parents=True, exist_ok=True)

        self._active: dict[str, _TaskRecord] = {}
        self._completed: list[_TaskRecord] = []

        # The SDK delivers sub-agent results as a UserMessage (with tool_use_result)
        # AFTER TaskNotificationMessage. We store completed records by tool_use_id
        # so the UserMessage handler can retroactively fill in the output.
        self._pending_output: dict[str, _TaskRecord] = {}  # tool_use_id → record

        _log(">>", _CYAN, f"Audit logs: {self.run_dir}")

    def handle_message(self, message: object) -> None:
        """Process an SDK message for audit tracking, then log it."""
        match message:
            case TaskStartedMessage():
                rec = _TaskRecord(
                    task_id=message.task_id,
                    description=message.description,
                    started_at=time.monotonic(),
                    started_wall=time.strftime("%H:%M:%S"),
                )
                self._active[message.task_id] = rec
                _log(">>", _CYAN, f"Task started: {message.description} [{message.task_id[:8]}]")

            case TaskProgressMessage():
                elapsed = ""
                rec = self._active.get(message.task_id)
                if rec:
                    secs = time.monotonic() - rec.started_at
                    elapsed = f" [{secs:.0f}s]"
                    if secs > AGENT_TIMEOUT_WARNING_SECS:
                        _log("!!", _RED, f"SLOW AGENT: {message.description} running for {secs:.0f}s [{message.task_id[:8]}]")
                tool_info = f" (last tool: {message.last_tool_name})" if message.last_tool_name else ""
                _log("..", _DIM, f"Working: {message.description}{tool_info}{elapsed}")

            case TaskNotificationMessage():
                rec = self._active.pop(message.task_id, None)
                duration_secs = 0.0
                if rec:
                    duration_secs = time.monotonic() - rec.started_at
                    rec.duration_secs = duration_secs
                    rec.status = message.status
                    rec.summary = message.summary
                elif message.usage and message.usage.get("duration_ms"):
                    duration_secs = message.usage["duration_ms"] / 1000

                icon, color = ("OK", _GREEN) if message.status == "completed" else ("X", _RED)
                _log(icon, color, f"Task {message.status}: {message.summary} ({duration_secs:.1f}s)")

                # Try output_file (usually empty for sub-agents)
                output_content: str | None = None
                if message.output_file:
                    output_content = _read_output_file(message.output_file)

                if rec:
                    rec.output = output_content
                    self._completed.append(rec)
                else:
                    rec = _TaskRecord(
                        task_id=message.task_id,
                        description=message.summary,
                        started_at=0,
                        started_wall="unknown",
                        status=message.status,
                        duration_secs=duration_secs,
                        summary=message.summary,
                        output=output_content,
                    )
                    self._completed.append(rec)

                # Register for retroactive update — the SDK delivers sub-agent
                # output as a UserMessage with tool_use_result AFTER this notification
                if message.tool_use_id and not output_content:
                    self._pending_output[message.tool_use_id] = rec

                self._write_agent_report(rec)

            case UserMessage() if isinstance(message.tool_use_result, dict):
                # SDK delivers sub-agent results as UserMessage with tool_use_result
                # after TaskNotificationMessage. Extract text and update the report.
                content_blocks = message.tool_use_result.get("content", [])
                texts = [b["text"] for b in content_blocks if isinstance(b, dict) and b.get("type") == "text" and b.get("text", "").strip()]
                if texts:
                    # Find the matching pending record via ToolResultBlock in message.content
                    tool_use_id: str | None = None
                    if isinstance(message.content, list):
                        for block in message.content:
                            if isinstance(block, ToolResultBlock) and block.tool_use_id in self._pending_output:
                                tool_use_id = block.tool_use_id
                                break

                    if tool_use_id:
                        rec = self._pending_output.pop(tool_use_id)
                        rec.output = max(texts, key=len)
                        self._write_agent_report(rec)
                        if _trace:
                            _log_trace(f"Agent output [{rec.task_id}]", rec.output)

            case AssistantMessage():
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        _log("->", _YELLOW, f"Tool call: {block.name}")
                        if _trace:
                            _log_trace(f"Tool input: {block.name}", json.dumps(block.input, indent=2))
                    elif isinstance(block, ToolResultBlock):
                        if _trace:
                            body = block.content if isinstance(block.content, str) else str(block.content)
                            error_tag = " [ERROR]" if block.is_error else ""
                            _log_trace(f"Tool result{error_tag}", body[:2000])
                    elif isinstance(block, TextBlock) and block.text.strip():
                        preview = block.text.strip().replace("\n", " ")[:120]
                        _log("--", _DIM, preview)

            case ResultMessage():
                duration_s = message.duration_ms / 1000
                cost = f" (${message.total_cost_usd:.2f})" if message.total_cost_usd else ""
                _log("==", _BOLD, f"Done in {duration_s:.1f}s, {message.num_turns} turns{cost}")

    def _write_agent_report(self, rec: _TaskRecord) -> None:
        """Write a single agent's report to the audit directory."""
        safe_name = _sanitize_filename(rec.description)
        filename = f"{rec.task_id[:8]}_{safe_name}.md"
        path = self.run_dir / filename

        lines = [
            f"# Agent Report: {rec.description}",
            "",
            f"- **Task ID**: {rec.task_id}",
            f"- **Status**: {rec.status}",
            f"- **Started**: {rec.started_wall}",
            f"- **Duration**: {rec.duration_secs:.1f}s",
            f"- **Summary**: {rec.summary}",
            "",
            "## Output",
            "",
            rec.output or "_No output captured._",
        ]

        path.write_text("\n".join(lines))
        _log(">>", _DIM, f"Audit report: {path}")

    def write_summary(self) -> None:
        """Write a summary of all agents to the audit directory."""
        path = self.run_dir / "summary.md"

        lines = [
            "# Run Summary",
            "",
            f"- **Timestamp**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **Agents completed**: {len(self._completed)}",
            "",
            "## Agent Results",
            "",
            "| Agent | Status | Duration | Summary |",
            "|-------|--------|----------|---------|",
        ]

        for rec in self._completed:
            lines.append(f"| {rec.description} | {rec.status} | {rec.duration_secs:.1f}s | {rec.summary[:80]} |")

        # Flag any still-active agents (potential hangs)
        if self._active:
            lines.extend(["", "## Still Running (potential hangs)", ""])
            for task_id, rec in self._active.items():
                elapsed = time.monotonic() - rec.started_at
                lines.append(f"- **{rec.description}** [{task_id[:8]}] — running for {elapsed:.0f}s")

        path.write_text("\n".join(lines))
        _log(">>", _CYAN, f"Run summary: {path}")


async def _run_chief_of_staff(user_query: str, tracker: AuditTracker) -> str:
    """Run the Chief of Staff briefing as a standalone first pass.

    Returns the briefing text, which is injected into the CSO prompt.
    """
    from virtual_biotech.agents.chief_of_staff import CHIEF_OF_STAFF_PROMPT

    _log(">>", _CYAN, "Running Chief of Staff briefing")

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
        if isinstance(message, ResultMessage):
            duration_ms = message.duration_ms
            if message.subtype == "success":
                briefing = message.result or ""
            else:
                _log("X", _RED, f"Chief of Staff failed: subtype={message.subtype} stop_reason={message.stop_reason}")

    # Write audit report manually — top-level query() emits ResultMessage, not TaskNotificationMessage
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


async def _run_cso_clarification(user_query: str, tracker: AuditTracker) -> str:
    """Run the CSO in clarification-only mode to generate questions for the user.

    The CSO uses its scientific expertise to formulate targeted clarification
    questions before any expensive analyses are launched.

    Returns the clarification questions text.
    """
    _log(">>", _CYAN, "CSO generating clarification questions")

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

    # Use a focused system prompt — the full CSO prompt mentions agent delegation
    # tools which can cause the model to attempt tool calls instead of producing text
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
        if isinstance(message, ResultMessage):
            if message.subtype == "success":
                questions = message.result or ""
            else:
                _log("X", _RED, f"CSO clarification failed: subtype={message.subtype} stop_reason={message.stop_reason}")

    return questions


def _collect_user_clarification(questions: str) -> str:
    """Present clarification questions and collect user responses via stdin.

    Returns the user's response text, or empty string if no input provided.
    """
    print(f"\n{'─' * 72}")
    print(f"{_BOLD}CSO requests clarification before proceeding:{_RESET}\n")
    print(questions)
    print(f"\n{'─' * 72}")
    print(f"{_BOLD}Your response (press Enter on empty line to submit):{_RESET}")

    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line == "" and lines:
            break
        lines.append(line)

    return "\n".join(lines).strip()


async def run_virtual_biotech(user_query: str) -> str:
    """Main entry point. Sends user query to CSO for orchestration.

    Enforces a strict two-gate workflow:
    1. Phase 1 (parallel): Chief of Staff intelligence briefing + CSO clarification questions
    2. Phase 2 (blocking): User answers clarification questions
    3. Phase 3: CSO receives briefing + clarified intent, then decomposes and delegates

    Args:
        user_query: The scientific question or task from the user.

    Returns:
        The CSO's final synthesized response.
    """
    tracker = AuditTracker()

    # ── Phase 1: Chief of Staff briefing + CSO clarification questions (parallel) ──
    # Both launch concurrently. Clarification finishes fast (~10s, 1 turn);
    # the user answers questions while the briefing continues in the background.
    _log(">>", _CYAN, "Phase 1: Intelligence briefing + intent clarification (parallel)")

    briefing_task = asyncio.create_task(asyncio.wait_for(_run_chief_of_staff(user_query, tracker), timeout=120))
    clarification_task = asyncio.create_task(_run_cso_clarification(user_query, tracker))

    # Wait for clarification questions first (fast) — don't block on briefing
    try:
        questions = await clarification_task
    except Exception as exc:
        _log("!!", _RED, f"CSO clarification failed — proceeding without it: {type(exc).__name__}: {exc}")
        questions = ""

    # ── Phase 2: Collect user clarification while briefing runs in background ──
    clarified_intent = ""
    if questions:
        clarified_intent = _collect_user_clarification(questions)
        if clarified_intent:
            _log("OK", _GREEN, "User clarification received")
        else:
            _log("..", _DIM, "No clarification provided — CSO will proceed with original query")

    # Now wait for the briefing to finish (may already be done while user was typing)
    try:
        briefing = await briefing_task
    except Exception as exc:
        _log("!!", _RED, f"Chief of Staff briefing failed — proceeding without it: {type(exc).__name__}: {exc}")
        briefing = "Chief of Staff briefing unavailable. Proceed with your own assessment."

    # ── Phase 3: CSO orchestration with full context ──
    _log(">>", _CYAN, "Phase 3: CSO task decomposition and agent routing")

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

    # CSO delegates via Agent tool; sub-agents need their MCP tools whitelisted
    # at the session level or the SDK permission gate blocks them.
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
    cso_text_blocks: list[str] = []
    async for message in query(prompt=cso_prompt, options=options):
        if _trace:
            _log_trace("SDK message", f"{type(message).__name__}: {str(message)[:500]}")
        tracker.handle_message(message)
        if isinstance(message, AssistantMessage) and message.parent_tool_use_id is None:
            # Capture top-level CSO text blocks (not sub-agent messages)
            for block in message.content:
                if isinstance(block, TextBlock) and block.text.strip():
                    cso_text_blocks.append(block.text)
        if isinstance(message, ResultMessage):
            if message.subtype == "success":
                result_text = message.result
            else:
                result_text = f"Error: subtype={message.subtype} stop_reason={message.stop_reason} result={message.result}"

    # Use the longest CSO text block as the synthesis (typically the full report),
    # falling back to the ResultMessage text if no substantial blocks were captured
    cso_output = max(cso_text_blocks, key=len) if cso_text_blocks else result_text

    # Write the CSO's final synthesized report to audit logs
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


async def run_interactive_session() -> None:
    """Run an interactive multi-turn session with the CSO.

    The first user query triggers the mandatory Phase 1 workflow:
    Chief of Staff briefing + clarification questions run in parallel,
    user responds, then the CSO proceeds with full context.
    Subsequent turns are free-form conversation with the CSO.
    """
    # CSO gets all sub-agents except chief_of_staff (handled by orchestrator on first turn)
    cso_sub_agents = {k: v for k, v in CSO_SUB_AGENTS.items() if k != "chief_of_staff"}

    # CSO delegates via Agent tool; sub-agents need their MCP tools whitelisted
    # at the session level or the SDK permission gate blocks them.
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

    tracker = AuditTracker()
    first_turn = True

    async with ClaudeSDKClient(options=options) as client:
        print("Virtual Biotech CSO ready. Type your query (or 'quit' to exit):")
        while True:
            user_input = input("\n> ")
            if user_input.strip().lower() in ("quit", "exit", "q"):
                break

            if first_turn:
                # ── Phase 1: briefing + clarification (parallel) ──
                _log(">>", _CYAN, "Phase 1: Intelligence briefing + intent clarification (parallel)")

                briefing_task = asyncio.create_task(asyncio.wait_for(_run_chief_of_staff(user_input, tracker), timeout=120))
                clarification_task = asyncio.create_task(_run_cso_clarification(user_input, tracker))

                try:
                    questions: str = await clarification_task
                except Exception as exc:
                    _log("!!", _RED, f"CSO clarification failed: {type(exc).__name__}: {exc}")
                    questions = ""

                # ── Phase 2: collect user clarification while briefing continues ──
                clarified_intent = ""
                if questions:
                    clarified_intent = _collect_user_clarification(questions)
                    if clarified_intent:
                        _log("OK", _GREEN, "User clarification received")
                    else:
                        _log("..", _DIM, "No clarification provided — CSO will proceed with original query")

                # Wait for briefing to finish (may already be done while user was typing)
                try:
                    briefing: str = await briefing_task
                except Exception as exc:
                    _log("!!", _RED, f"Chief of Staff briefing failed: {type(exc).__name__}: {exc}")
                    briefing = "Chief of Staff briefing unavailable. Proceed with your own assessment."

                # ── Phase 3: send enriched prompt to CSO ──
                _log(">>", _CYAN, "Phase 3: CSO task decomposition and agent routing")

                context_parts = [user_input, ""]
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

                enriched_prompt = "\n".join(context_parts)
                await client.query(enriched_prompt)
                first_turn = False
            else:
                await client.query(user_input)

            result_text = ""
            cso_text_blocks: list[str] = []
            async for msg in client.receive_response():
                tracker.handle_message(msg)
                if isinstance(msg, AssistantMessage) and msg.parent_tool_use_id is None:
                    for block in msg.content:
                        if isinstance(block, TextBlock) and block.text.strip():
                            cso_text_blocks.append(block.text)
                if isinstance(msg, ResultMessage):
                    result_text = msg.result or ""
                    print(f"\nCSO: {result_text}")

            # Use the longest CSO text block as the synthesis, falling back to ResultMessage
            cso_output = max(cso_text_blocks, key=len) if cso_text_blocks else result_text

            # Write the CSO's response to audit logs
            if cso_output:
                cso_rec = _TaskRecord(
                    task_id=f"cso_turn_{int(time.monotonic())}",
                    description="CSO synthesized report",
                    started_at=0,
                    started_wall=time.strftime("%H:%M:%S"),
                    status="completed",
                    duration_secs=0,
                    summary="CSO synthesis for interactive turn",
                    output=cso_output,
                )
                tracker._completed.append(cso_rec)
                tracker._write_agent_report(cso_rec)

    tracker.write_summary()


async def extract_trial_outcomes(nct_ids: list[str], max_concurrent: int | None = None) -> list:
    """Dispatch parallel clinical trialist agents for large-scale trial extraction.

    Each agent handles one NCT ID with its full context window dedicated
    to that single trial for deep analysis.

    Args:
        nct_ids: List of NCT IDs to extract outcomes for.
        max_concurrent: Maximum concurrent agents. Defaults to config value.

    Returns:
        List of extraction results (one per trial).
    """
    from virtual_biotech.agents.clinical_officers.clinical_trialist import clinical_trialist_agent
    from virtual_biotech.config import MCP_SERVERS

    if max_concurrent is None:
        max_concurrent = MAX_CONCURRENT_TRIAL_AGENTS

    semaphore = asyncio.Semaphore(max_concurrent)
    tracker = AuditTracker()

    async def process_trial(nct_id: str) -> dict:
        async with semaphore:
            trial_mcp_names = ["clinical_trials", "drugs"]
            options = ClaudeAgentOptions(
                system_prompt=clinical_trialist_agent.prompt,
                model=SCIENTIST_MODEL,
                allowed_tools=["Bash", "WebSearch", "WebFetch", *tools_for_mcp_servers(trial_mcp_names)],
                mcp_servers={name: MCP_SERVERS[name] for name in trial_mcp_names},
                max_turns=30,
                env=_SDK_ENV,
            )

            prompt = (
                f"Extract comprehensive outcome data for trial {nct_id}. "
                f"Follow the 3-level evidence cascade. Output validated JSON "
                f"matching the ClinicalTrialData schema."
            )

            result = {"nct_id": nct_id, "status": "error", "data": None}
            async for message in query(prompt=prompt, options=options):
                tracker.handle_message(message)
                if isinstance(message, ResultMessage):
                    if message.subtype == "success":
                        result = {"nct_id": nct_id, "status": "success", "data": message.result}
                    else:
                        result = {"nct_id": nct_id, "status": "error", "data": message.result}

            return result

    tasks = [process_trial(nct_id) for nct_id in nct_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    processed = []
    for r in results:
        if isinstance(r, Exception):
            processed.append({"nct_id": "unknown", "status": "exception", "data": str(r)})
        else:
            processed.append(r)

    tracker.write_summary()
    return processed


def main() -> None:
    """CLI entry point.

    Usage:
        virtual-biotech "query"           Run a single query
        virtual-biotech --trace "query"   Run with full agent tracing
        virtual-biotech                   Interactive session
        virtual-biotech --trace           Interactive session with tracing
    """
    global _trace  # noqa: PLW0603

    args = [a for a in sys.argv[1:] if a != "--trace"]
    if "--trace" in sys.argv:
        _trace = True
        _log(">>", _MAGENTA, "Tracing enabled — agent outputs will be displayed")

    if args:
        user_query = " ".join(args)
        result = asyncio.run(run_virtual_biotech(user_query))
        print(result)
    else:
        asyncio.run(run_interactive_session())


if __name__ == "__main__":
    main()
