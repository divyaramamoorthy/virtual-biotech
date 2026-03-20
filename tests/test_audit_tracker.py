"""Tests for AuditTracker message handling and output capture."""

import json
import tempfile

from claude_agent_sdk.types import (
    AssistantMessage,
    TaskNotificationMessage,
    TaskStartedMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from virtual_biotech.orchestrator import AuditTracker


def _make_task_started(task_id: str, description: str, tool_use_id: str | None = None) -> TaskStartedMessage:
    return TaskStartedMessage(
        subtype="task_started",
        data={},
        task_id=task_id,
        description=description,
        uuid="fake-uuid",
        session_id="fake-session",
        tool_use_id=tool_use_id,
    )


def _make_task_notification(
    task_id: str,
    summary: str,
    output_file: str = "",
    tool_use_id: str | None = None,
) -> TaskNotificationMessage:
    return TaskNotificationMessage(
        subtype="task_notification",
        data={},
        task_id=task_id,
        status="completed",
        output_file=output_file,
        summary=summary,
        uuid="fake-uuid",
        session_id="fake-session",
        tool_use_id=tool_use_id,
    )


def _make_user_message_with_result(tool_use_id: str, text: str) -> UserMessage:
    """Simulate the UserMessage the SDK emits after a sub-agent completes.

    Contains a ToolResultBlock in content and tool_use_result with the agent's text.
    """
    return UserMessage(
        content=[ToolResultBlock(tool_use_id=tool_use_id, content=[{"type": "text", "text": text}])],
        uuid="fake-uuid",
        tool_use_result={
            "status": "completed",
            "content": [{"type": "text", "text": text}],
        },
    )


class TestAuditTrackerCapture:
    """Test that AuditTracker correctly captures sub-agent output."""

    def test_user_message_after_notification_updates_report(self):
        """The SDK delivers sub-agent output as a UserMessage with tool_use_result
        AFTER TaskNotificationMessage. The tracker should retroactively update the report.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AuditTracker(audit_dir=tmpdir)
            tool_use_id = "toolu_abc123"
            task_id = "task_xyz789"

            # 1. CSO sends Agent tool call
            tracker.handle_message(AssistantMessage(
                content=[ToolUseBlock(id=tool_use_id, name="Agent", input={"prompt": "test"})],
                model="test",
            ))

            # 2. Task starts
            tracker.handle_message(_make_task_started(task_id, "Test analysis", tool_use_id=tool_use_id))

            # 3. Task completes — output_file is empty, no output yet
            tracker.handle_message(
                _make_task_notification(task_id, "Test analysis", tool_use_id=tool_use_id)
            )

            # At this point, the report exists but has no output
            assert len(tracker._completed) == 1
            assert tracker._completed[0].output is None

            # 4. UserMessage arrives with the sub-agent's actual output
            tracker.handle_message(
                _make_user_message_with_result(tool_use_id, "This is the analysis result.")
            )

            # Now the report should be updated
            assert tracker._completed[0].output == "This is the analysis result."

            # Verify the file on disk was updated
            report_files = list(tracker.run_dir.glob("task_xyz*"))
            assert len(report_files) == 1
            content = report_files[0].read_text()
            assert "This is the analysis result." in content
            assert "_No output captured._" not in content

    def test_notification_without_tool_use_id(self):
        """When TaskNotificationMessage has no tool_use_id, report still written."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AuditTracker(audit_dir=tmpdir)

            tracker.handle_message(_make_task_started("task_1", "No correlation"))
            tracker.handle_message(_make_task_notification("task_1", "No correlation"))

            assert len(tracker._completed) == 1
            assert tracker._completed[0].output is None

    def test_parallel_agents_both_captured(self):
        """Two agents launched in parallel should both get their output captured."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AuditTracker(audit_dir=tmpdir)
            tu_id_1 = "toolu_agent1"
            tu_id_2 = "toolu_agent2"
            task_id_1 = "task_genetics"
            task_id_2 = "task_pharma"

            # CSO launches two agents
            tracker.handle_message(AssistantMessage(
                content=[ToolUseBlock(id=tu_id_1, name="Agent", input={})],
                model="test",
            ))
            tracker.handle_message(_make_task_started(task_id_1, "Genetics", tool_use_id=tu_id_1))

            tracker.handle_message(AssistantMessage(
                content=[ToolUseBlock(id=tu_id_2, name="Agent", input={})],
                model="test",
            ))
            tracker.handle_message(_make_task_started(task_id_2, "Pharmacology", tool_use_id=tu_id_2))

            # Both complete (no output yet)
            tracker.handle_message(
                _make_task_notification(task_id_1, "Genetics", tool_use_id=tu_id_1)
            )
            tracker.handle_message(
                _make_task_notification(task_id_2, "Pharmacology", tool_use_id=tu_id_2)
            )

            # Both UserMessages arrive with results
            tracker.handle_message(_make_user_message_with_result(tu_id_1, "Genetics output"))
            tracker.handle_message(_make_user_message_with_result(tu_id_2, "Pharma output"))

            assert tracker._completed[0].output == "Genetics output"
            assert tracker._completed[1].output == "Pharma output"

    def test_output_file_takes_precedence(self):
        """If output_file has content, UserMessage doesn't overwrite it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AuditTracker(audit_dir=tmpdir)
            tool_use_id = "toolu_withfile"
            task_id = "task_withfile"

            # Create a fake JSONL output file
            output_path = f"{tmpdir}/agent_output.jsonl"
            with open(output_path, "w") as f:
                msg = {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": "Output from file."}]},
                }
                f.write(json.dumps(msg) + "\n")

            tracker.handle_message(AssistantMessage(
                content=[ToolUseBlock(id=tool_use_id, name="Agent", input={})],
                model="test",
            ))
            tracker.handle_message(_make_task_started(task_id, "File test", tool_use_id=tool_use_id))
            tracker.handle_message(
                _make_task_notification(task_id, "File test", output_file=output_path, tool_use_id=tool_use_id)
            )

            # output_file was readable, so output is set immediately (not pending)
            assert tracker._completed[0].output == "Output from file."
            # Should NOT be in pending since output was already resolved
            assert tool_use_id not in tracker._pending_output

    def test_no_result_gives_no_output(self):
        """When neither output_file nor UserMessage provides content, output is None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AuditTracker(audit_dir=tmpdir)
            tool_use_id = "toolu_empty"
            task_id = "task_empty"

            tracker.handle_message(AssistantMessage(
                content=[ToolUseBlock(id=tool_use_id, name="Agent", input={})],
                model="test",
            ))
            tracker.handle_message(_make_task_started(task_id, "Empty", tool_use_id=tool_use_id))
            tracker.handle_message(
                _make_task_notification(task_id, "Empty", tool_use_id=tool_use_id)
            )

            assert tracker._completed[0].output is None
            # Should be pending, waiting for UserMessage
            assert tool_use_id in tracker._pending_output

    def test_user_message_selects_longest_text(self):
        """When tool_use_result has multiple text blocks, the longest is used."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AuditTracker(audit_dir=tmpdir)
            tool_use_id = "toolu_multi"
            task_id = "task_multi"

            tracker.handle_message(AssistantMessage(
                content=[ToolUseBlock(id=tool_use_id, name="Agent", input={})],
                model="test",
            ))
            tracker.handle_message(_make_task_started(task_id, "Multi", tool_use_id=tool_use_id))
            tracker.handle_message(
                _make_task_notification(task_id, "Multi", tool_use_id=tool_use_id)
            )

            # UserMessage with multiple text blocks (like the real SDK emits)
            tracker.handle_message(UserMessage(
                content=[ToolResultBlock(tool_use_id=tool_use_id, content="short")],
                uuid="fake",
                tool_use_result={
                    "status": "completed",
                    "content": [
                        {"type": "text", "text": "Short summary."},
                        {"type": "text", "text": "This is the full detailed analysis with much more content." * 5},
                        {"type": "text", "text": "agentId: task_multi"},
                    ],
                },
            ))

            assert "full detailed analysis" in tracker._completed[0].output
