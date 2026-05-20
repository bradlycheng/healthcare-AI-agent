from __future__ import annotations

from dataclasses import replace
from typing import Iterable, List, Optional

from .security_validation import IntentGrant, iso_after, new_request_id
from .sql_guard import DEFAULT_ALLOWED_COLUMNS


QUERY_DATABASE = "query_database"
SEARCH_GUIDELINES = "search_guidelines"
GET_PATIENT_CONTEXT = "get_patient_context"
CLINICAL_CALCULATOR = "clinical_calculator"
ASK_CLARIFICATION = "ask_clarification"

REFERENCE_OUTPUT_FIELDS = ["answer", "highlights", "sources"]
PHI_OUTPUT_FIELDS = ["patient_name", "patient_id", "patient_dob", "provider_name"]
CLINICAL_OUTPUT_FIELDS = ["clinical_answer", "row_count", "sources"]

DENY_INTENTS = {
    "admin",
    "delete",
    "export",
    "hidden_instruction_execution",
    "identifier_transformation",
    "policy_override",
    "reset",
    "system_prompt_request",
}


def build_query_grant(
    *,
    session_id: str,
    intent: str = "clinical_query",
    scope: str = "clinical_read",
    requested_tools: Optional[Iterable[str]] = None,
    subject: Optional[str] = None,
    max_rows: int = 50,
    request_id: Optional[str] = None,
) -> IntentGrant:
    normalized_intent = (intent or "clinical_query").strip().lower()
    if normalized_intent in DENY_INTENTS:
        return _deny_grant(session_id=session_id, request_id=request_id, intent=normalized_intent, scope=scope)

    tools = _allowed_tools_for_intent(normalized_intent, requested_tools)
    return IntentGrant(
        intent=normalized_intent,
        risk=_risk_for_intent(normalized_intent),
        session_id=session_id,
        request_id=request_id or new_request_id(),
        scope=scope,
        subject=subject,
        allowed_tools=tools,
        allowed_tables=sorted(DEFAULT_ALLOWED_COLUMNS.keys()) if QUERY_DATABASE in tools else [],
        allowed_columns={
            table: sorted(columns)
            for table, columns in DEFAULT_ALLOWED_COLUMNS.items()
        } if QUERY_DATABASE in tools else {},
        output_fields=_output_fields_for_tools(tools),
        max_rows=max(1, min(int(max_rows or 50), 200)),
        expires_at=iso_after(minutes=5),
    )


def narrow_to_tool(grant: IntentGrant, tool_name: str) -> IntentGrant:
    if tool_name not in grant.allowed_tools:
        return replace(
            grant,
            allowed_tools=[],
            allowed_tables=[],
            allowed_columns={},
            output_fields=[],
            max_rows=0,
        )
    return replace(
        grant,
        allowed_tools=[tool_name],
        allowed_tables=grant.allowed_tables if tool_name == QUERY_DATABASE else [],
        allowed_columns=grant.allowed_columns if tool_name == QUERY_DATABASE else {},
        output_fields=_output_fields_for_tools([tool_name]),
    )


def _allowed_tools_for_intent(intent: str, requested_tools: Optional[Iterable[str]]) -> List[str]:
    requested = [tool for tool in (requested_tools or []) if tool]
    if intent in {"guideline_reference", "clinical_reference"}:
        base = [SEARCH_GUIDELINES, ASK_CLARIFICATION]
    elif intent in {"calculation", "clinical_calculation"}:
        base = [CLINICAL_CALCULATOR, ASK_CLARIFICATION]
    elif intent in {"patient_context", "single_patient"}:
        base = [GET_PATIENT_CONTEXT, SEARCH_GUIDELINES, ASK_CLARIFICATION]
    elif intent == "clarification":
        base = [ASK_CLARIFICATION]
    else:
        base = [QUERY_DATABASE, SEARCH_GUIDELINES, GET_PATIENT_CONTEXT, CLINICAL_CALCULATOR, ASK_CLARIFICATION]
    if not requested:
        return base
    return [tool for tool in base if tool in requested]


def _output_fields_for_tools(tools: Iterable[str]) -> List[str]:
    output_fields = set(REFERENCE_OUTPUT_FIELDS)
    tool_set = set(tools)
    if QUERY_DATABASE in tool_set or GET_PATIENT_CONTEXT in tool_set:
        output_fields.update(PHI_OUTPUT_FIELDS)
        output_fields.update(CLINICAL_OUTPUT_FIELDS)
    if CLINICAL_CALCULATOR in tool_set:
        output_fields.update(["calculation", "result", "unit", "interpretation"])
    return sorted(output_fields)


def _risk_for_intent(intent: str) -> str:
    if intent in {"patient_context", "single_patient"}:
        return "high"
    if intent in {"guideline_reference", "clinical_reference", "calculation", "clinical_calculation"}:
        return "low"
    return "medium"


def _deny_grant(*, session_id: str, request_id: Optional[str], intent: str, scope: str) -> IntentGrant:
    return IntentGrant(
        intent=intent,
        risk="deny",
        session_id=session_id,
        request_id=request_id or new_request_id(),
        scope=scope,
        allowed_tools=[],
        allowed_tables=[],
        allowed_columns={},
        output_fields=[],
        max_rows=0,
        expires_at=iso_after(minutes=5),
    )
