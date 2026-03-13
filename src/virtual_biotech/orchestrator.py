"""Main entry point for the Virtual Biotech multi-agent system."""

import asyncio
import sys
import time

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage, query
from claude_agent_sdk.types import (
    AssistantMessage,
    TaskNotificationMessage,
    TaskProgressMessage,
    TaskStartedMessage,
    TextBlock,
    ToolUseBlock,
)

from virtual_biotech.agents.cso import CSO_SUB_AGENTS, CSO_SYSTEM_PROMPT
from virtual_biotech.config import ANTHROPIC_BASE_URL, LITELLM_PROXY_API_KEY, MAX_CONCURRENT_TRIAL_AGENTS, SCIENTIST_MODEL, STAFF_MODEL

# Environment variables forwarded to all Claude SDK subprocesses
_SDK_ENV = {
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


def _log(icon: str, color: str, text: str) -> None:
    """Print a timestamped, colored status line to stderr."""
    ts = time.strftime("%H:%M:%S")
    print(f"{_DIM}{ts}{_RESET} {color}{icon}{_RESET} {text}", file=sys.stderr, flush=True)


def _log_message(message: object) -> None:
    """Log progress for any SDK message type."""
    match message:
        case TaskStartedMessage():
            _log("▶", _CYAN, f"Task started: {message.description}")
        case TaskProgressMessage():
            tool_info = f" (last tool: {message.last_tool_name})" if message.last_tool_name else ""
            _log("⋯", _DIM, f"Working: {message.description}{tool_info}")
        case TaskNotificationMessage():
            icon, color = ("✓", _GREEN) if message.status == "completed" else ("✗", _RED)
            _log(icon, color, f"Task {message.status}: {message.summary}")
        case AssistantMessage():
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    _log("⚙", _YELLOW, f"Tool call: {block.name}")
                elif isinstance(block, TextBlock) and block.text.strip():
                    # Show first 120 chars of assistant text as a status hint
                    preview = block.text.strip().replace("\n", " ")[:120]
                    _log("💬", _DIM, preview)
        case ResultMessage():
            duration_s = message.duration_ms / 1000
            cost = f" (${message.total_cost_usd:.2f})" if message.total_cost_usd else ""
            _log("■", _BOLD, f"Done in {duration_s:.1f}s, {message.num_turns} turns{cost}")


async def run_virtual_biotech(user_query: str) -> str:
    """Main entry point. Sends user query to CSO for orchestration.

    The CSO handles the full workflow:
    1. Clarification interview with user
    2. Chief of Staff briefing (parallel)
    3. Task decomposition and agent routing
    4. Scientific review
    5. Iterative refinement if needed
    6. Final synthesis and report generation

    Args:
        user_query: The scientific question or task from the user.

    Returns:
        The CSO's final synthesized response.
    """
    options = ClaudeAgentOptions(
        system_prompt=CSO_SYSTEM_PROMPT,
        model=SCIENTIST_MODEL,
        allowed_tools=["Agent"],
        agents=CSO_SUB_AGENTS,
        max_turns=50,
        env=_SDK_ENV,
    )

    result_text = ""
    async for message in query(prompt=user_query, options=options):
        _log_message(message)
        if isinstance(message, ResultMessage):
            if message.subtype == "success":
                result_text = message.result
            else:
                result_text = f"Error: {message.subtype} - {message.result}"

    return result_text


async def run_interactive_session() -> None:
    """Run an interactive multi-turn session with the CSO."""
    options = ClaudeAgentOptions(
        system_prompt=CSO_SYSTEM_PROMPT,
        model=SCIENTIST_MODEL,
        allowed_tools=["Agent"],
        agents=CSO_SUB_AGENTS,
        max_turns=50,
        env=_SDK_ENV,
    )

    async with ClaudeSDKClient(options=options) as client:
        print("Virtual Biotech CSO ready. Type your query (or 'quit' to exit):")
        while True:
            user_input = input("\n> ")
            if user_input.strip().lower() in ("quit", "exit", "q"):
                break

            await client.query(user_input)
            async for msg in client.receive_response():
                _log_message(msg)
                if isinstance(msg, ResultMessage):
                    print(f"\nCSO: {msg.result}")


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

    async def process_trial(nct_id: str) -> dict:
        async with semaphore:
            options = ClaudeAgentOptions(
                system_prompt=clinical_trialist_agent.prompt,
                model=SCIENTIST_MODEL,
                allowed_tools=["Bash", "WebSearch", "WebFetch"],
                mcp_servers={
                    "clinical_trials": MCP_SERVERS["clinical_trials"],
                    "drugs": MCP_SERVERS["drugs"],
                },
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
                _log_message(message)
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

    return processed


def main() -> None:
    """CLI entry point."""
    if len(sys.argv) > 1:
        user_query = " ".join(sys.argv[1:])
        result = asyncio.run(run_virtual_biotech(user_query))
        print(result)
    else:
        asyncio.run(run_interactive_session())


if __name__ == "__main__":
    main()
