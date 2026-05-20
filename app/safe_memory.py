from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import Any, Dict, Iterable, List, Set

from .security_validation import SECURITY_CONFIG, SafeConversationState, iso_after


CONTROLLED_TOPIC_BY_TOOL = {
    "query_database": "clinical_database_query",
    "search_guidelines": "guideline_reference",
    "get_patient_context": "patient_context",
    "clinical_calculator": "clinical_calculation",
}

RAW_MEMORY_BLOCKLIST = {
    "answer",
    "question",
    "raw_goal",
    "last_topic",
    "permission",
    "permissions",
    "admin",
    "assistant_claim",
    "history",
}


def conversation_id_for_session(session_id: str) -> str:
    return f"conv_{session_id}"


def load_state(conversation_id: str, session_id: str, db_path: str | None = None) -> SafeConversationState | None:
    from .db import get_conversation_state

    if db_path is None:
        row = get_conversation_state(conversation_id, session_id)
    else:
        row = get_conversation_state(conversation_id, session_id, db_path=db_path)
    if row is None:
        return None
    data = json.loads(row["state_json"])
    return SafeConversationState(**data)


def commit_successful_turn(
    *,
    conversation_id: str,
    session_id: str,
    agent_result: Dict[str, Any],
    db_path: str | None = None,
) -> bool:
    """Commit only typed safe metadata after a fully successful turn."""
    if not agent_result.get("success"):
        return False
    if agent_result.get("error") or agent_result.get("needs_clarification"):
        return False

    safe_metadata = agent_result.get("safe_metadata") or {}
    state = SafeConversationState(
        conversation_id=conversation_id,
        session_id=session_id,
        patient_ids=_bounded_sorted_strings(safe_metadata.get("patient_ids", []), limit=25),
        topic_codes=_bounded_sorted_strings(_topic_codes(agent_result), limit=20),
        result_ids=_bounded_sorted_strings(safe_metadata.get("result_ids", []), limit=25),
        scope=_scope_from_tools(agent_result.get("tools_used", [])),
        intent="clinical_query",
        expires_at=iso_after(minutes=SECURITY_CONFIG["ttl"]["conversation_minutes"]),
    )
    payload = asdict(state)
    _assert_no_raw_memory(payload)

    from .db import upsert_conversation_state

    if db_path is None:
        upsert_conversation_state(conversation_id, session_id, payload, state.expires_at)
    else:
        upsert_conversation_state(conversation_id, session_id, payload, state.expires_at, db_path=db_path)
    return True


def extract_safe_metadata_from_tool_results(tool_results: Iterable[Any]) -> Dict[str, List[str]]:
    patient_ids: Set[str] = set()
    result_ids: Set[str] = set()
    for tool_result in tool_results:
        result = getattr(tool_result, "result", None)
        _walk_safe_ids(result, patient_ids, result_ids)
    return {
        "patient_ids": sorted(patient_ids),
        "result_ids": sorted(result_ids),
    }


def _walk_safe_ids(value: Any, patient_ids: Set[str], result_ids: Set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).lower()
            if normalized_key == "patient_id" and isinstance(item, str) and _safe_identifier(item):
                patient_ids.add(item)
            elif normalized_key == "message_id" and isinstance(item, (str, int)):
                result_ids.add(f"message:{item}")
            elif normalized_key == "patient" and isinstance(item, dict):
                patient_id = item.get("patient_id") or item.get("id")
                if isinstance(patient_id, str) and _safe_identifier(patient_id):
                    patient_ids.add(patient_id)
                _walk_safe_ids(item, patient_ids, result_ids)
            else:
                _walk_safe_ids(item, patient_ids, result_ids)
    elif isinstance(value, list):
        for item in value[:100]:
            _walk_safe_ids(item, patient_ids, result_ids)


def _topic_codes(agent_result: Dict[str, Any]) -> List[str]:
    return [
        CONTROLLED_TOPIC_BY_TOOL[tool]
        for tool in agent_result.get("tools_used", [])
        if tool in CONTROLLED_TOPIC_BY_TOOL
    ]


def _scope_from_tools(tools_used: Iterable[str]) -> str:
    tools = set(tools_used or [])
    if "get_patient_context" in tools:
        return "single_patient"
    if "query_database" in tools:
        return "cohort"
    if tools:
        return "reference"
    return "none"


def _bounded_sorted_strings(values: Iterable[Any], *, limit: int) -> List[str]:
    safe = [str(value) for value in values if isinstance(value, (str, int))]
    return sorted(set(safe))[:limit]


def _safe_identifier(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", value))


def _assert_no_raw_memory(payload: Dict[str, Any]) -> None:
    text = json.dumps(payload, sort_keys=True).lower()
    for key in RAW_MEMORY_BLOCKLIST:
        if f'"{key}"' in text:
            raise ValueError(f"unsafe raw memory field: {key}")
