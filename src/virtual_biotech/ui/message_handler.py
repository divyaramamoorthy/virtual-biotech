"""Bridge between Claude Agent SDK message stream and Streamlit session state.

Consumes the SDK's message types and updates shared state dicts that
the Streamlit UI reads to render real-time agent tracking.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from claude_agent_sdk import ResultMessage
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

from virtual_biotech.ui.agent_display import display_name, division_for, division_icon, resolve_agent_key

# Callback signature: (name: str, icon: str, output: str, log: list[str]) -> None
ReportCallback = Callable[[str, str, str, list[str]], None]


@dataclass
class AgentTask:
    """Tracks a single agent task's lifecycle for UI display."""

    task_id: str
    description: str
    agent_key: str = ""
    status: str = "running"  # running | completed | failed | stopped
    summary: str = ""
    output: str = ""
    last_tool: str = ""
    start_time: float = field(default_factory=time.time)
    tools_used: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)  # timestamped log entries for this task

    @property
    def display_name(self) -> str:
        return display_name(self.agent_key, self.description[:50])

    @property
    def division(self) -> str:
        return division_for(self.agent_key)

    @property
    def division_icon(self) -> str:
        return division_icon(self.division)

    @property
    def elapsed(self) -> float:
        return time.time() - self.start_time


class StreamlitMessageHandler:
    """Collects SDK messages into dicts that Streamlit can render.

    This handler is NOT Streamlit-dependent — it updates plain Python dicts
    so it can run inside an async task. The Streamlit UI polls these dicts.
    """

    def __init__(self, on_report: ReportCallback | None = None) -> None:
        self.tasks: dict[str, AgentTask] = {}
        self.pending_output: dict[str, str] = {}  # tool_use_id -> task_id
        self.cso_text_blocks: list[str] = []
        self.status_log: list[str] = []  # timestamped status messages
        self.total_cost: float = 0.0
        self.total_turns: int = 0
        self.duration_s: float = 0.0
        self.final_result: str = ""
        self.done: bool = False
        self._on_report = on_report
        self._emitted_reports: set[str] = set()  # task_ids already emitted

    def handle(self, message: object) -> None:
        """Route an SDK message to the appropriate handler."""
        if isinstance(message, TaskStartedMessage):
            self._on_task_started(message)
        elif isinstance(message, TaskProgressMessage):
            self._on_task_progress(message)
        elif isinstance(message, TaskNotificationMessage):
            self._on_task_notification(message)
        elif isinstance(message, UserMessage) and isinstance(getattr(message, "tool_use_result", None), dict):
            self._on_user_message(message)
        elif isinstance(message, AssistantMessage):
            self._on_assistant_message(message)
        elif isinstance(message, ResultMessage):
            self._on_result(message)

    def _emit_report(self, task: AgentTask) -> None:
        """Fire the on_report callback if a task has substantial output."""
        if not self._on_report:
            return
        if task.task_id in self._emitted_reports:
            return
        if not task.output or len(task.output) <= 100:
            return
        self._emitted_reports.add(task.task_id)
        self._on_report(task.display_name, task.division_icon, task.output, list(task.log))

    def _log(self, text: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self.status_log.append(f"{ts} {text}")

    def _task_log(self, task: AgentTask, entry: str) -> None:
        """Append a timestamped log entry to a specific task."""
        ts = time.strftime("%H:%M:%S")
        elapsed = f" [{task.elapsed:.0f}s]" if task.elapsed > 1 else ""
        task.log.append(f"{ts} {entry}{elapsed}")

    def _on_task_started(self, message: TaskStartedMessage) -> None:
        agent_key = resolve_agent_key(message.description, getattr(message, "task_type", None))
        task = AgentTask(task_id=message.task_id, description=message.description, agent_key=agent_key)
        self.tasks[message.task_id] = task
        self._task_log(task, f"▶ Started: {task.display_name}")
        self._log(f"▶ Started: {task.display_name}")

    def _on_task_progress(self, message: TaskProgressMessage) -> None:
        task = self.tasks.get(message.task_id)
        if task and message.last_tool_name:
            task.last_tool = message.last_tool_name
            if message.last_tool_name not in task.tools_used:
                task.tools_used.append(message.last_tool_name)
            self._task_log(task, f"⚙ Tool call: `{message.last_tool_name}`")
        tool_info = f" — {message.last_tool_name}" if message.last_tool_name else ""
        self._log(f"⋯ Working: {message.description}{tool_info}")

    def _on_task_notification(self, message: TaskNotificationMessage) -> None:
        task = self.tasks.get(message.task_id)
        if task:
            task.status = message.status
            task.summary = message.summary or ""
            if not task.output and task.summary:
                task.output = task.summary
            icon = "✅" if message.status == "completed" else "❌"
            self._task_log(task, f"{icon} {message.status}: {message.summary or ''}")
            self._emit_report(task)

        icon = "✅" if message.status == "completed" else "❌"
        self._log(f"{icon} {message.summary or message.status}")

        # Register for deferred output from UserMessage
        if message.tool_use_id:
            self.pending_output[message.tool_use_id] = message.task_id

    def _on_user_message(self, message: UserMessage) -> None:
        """Handle sub-agent output delivered after TaskNotificationMessage."""
        content_blocks = message.tool_use_result.get("content", [])
        texts = [b["text"] for b in content_blocks if isinstance(b, dict) and b.get("type") == "text" and b.get("text", "").strip()]
        if not texts:
            return

        tool_use_id: str | None = None
        if isinstance(message.content, list):
            for block in message.content:
                if isinstance(block, ToolResultBlock) and block.tool_use_id in self.pending_output:
                    tool_use_id = block.tool_use_id
                    break

        if not tool_use_id:
            return

        task_id = self.pending_output.pop(tool_use_id)
        task = self.tasks.get(task_id)
        if task:
            task.output = max(texts, key=len)
            self._emit_report(task)

    def _on_assistant_message(self, message: AssistantMessage) -> None:
        if message.parent_tool_use_id is not None:
            return
        for block in message.content:
            if isinstance(block, TextBlock) and block.text.strip():
                self.cso_text_blocks.append(block.text)
            elif isinstance(block, ToolUseBlock):
                self._log(f"🔧 Tool: {block.name}")

    def _on_result(self, message: ResultMessage) -> None:
        if message.total_cost_usd:
            self.total_cost += message.total_cost_usd
        self.total_turns += message.num_turns
        self.duration_s = message.duration_ms / 1000
        if message.subtype == "success":
            self.final_result = message.result or ""
        else:
            self.final_result = f"**Error:** {message.subtype} — {message.result}"
        self.done = True

    def get_cso_synthesis(self) -> str:
        """Return the CSO's longest text block, or final result as fallback."""
        if self.cso_text_blocks:
            return max(self.cso_text_blocks, key=len)
        return self.final_result
