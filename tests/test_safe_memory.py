import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_successful_turn_commits_typed_metadata_only(tmp_path):
    from app.db import get_conversation_state
    from app.safe_memory import commit_successful_turn

    db_path = str(tmp_path / "agent.db")
    committed = commit_successful_turn(
        conversation_id="conv_test",
        session_id="sess_test",
        agent_result={
            "success": True,
            "answer": "Jane Doe has high glucose",
            "tools_used": ["query_database"],
            "safe_metadata": {"patient_ids": ["P123"], "result_ids": ["message:7"]},
        },
    )

    assert committed is True
    row = get_conversation_state("conv_test", "sess_test", db_path="agent.db")
    assert row is not None
    state_text = row["state_json"]
    state = json.loads(state_text)
    assert state["patient_ids"] == ["P123"]
    assert state["result_ids"] == ["message:7"]
    assert state["scope"] == "cohort"
    assert "Jane Doe" not in state_text
    assert "answer" not in state_text


def test_failed_turn_does_not_commit():
    from app.safe_memory import commit_successful_turn, load_state

    committed = commit_successful_turn(
        conversation_id="conv_failed_test",
        session_id="sess_failed_test",
        agent_result={
            "success": False,
            "error": "denied",
            "tools_used": ["query_database"],
            "safe_metadata": {"patient_ids": ["P999"]},
        },
    )

    assert committed is False
    assert load_state("conv_failed_test", "sess_failed_test") is None


def test_clarification_turn_does_not_commit():
    from app.safe_memory import commit_successful_turn, load_state

    committed = commit_successful_turn(
        conversation_id="conv_clarify_test",
        session_id="sess_clarify_test",
        agent_result={
            "success": True,
            "needs_clarification": True,
            "tools_used": ["ask_clarification"],
            "safe_metadata": {"patient_ids": ["P999"]},
        },
    )

    assert committed is False
    assert load_state("conv_clarify_test", "sess_clarify_test") is None


def test_extract_safe_metadata_from_tool_results():
    from dataclasses import dataclass

    from app.safe_memory import extract_safe_metadata_from_tool_results

    @dataclass
    class FakeToolResult:
        result: dict

    metadata = extract_safe_metadata_from_tool_results(
        [
            FakeToolResult(
                {
                    "patient": {"patient_id": "P123", "first_name": "Jane"},
                    "visits": [{"message_id": 9}],
                }
            )
        ]
    )

    assert metadata["patient_ids"] == ["P123"]
    assert metadata["result_ids"] == ["message:9"]
    assert "Jane" not in str(metadata)
