from __future__ import annotations

from typing import Any, Dict, List

from .llm_client import LLMError, call_llm as _call_llm, call_llm_for_json as _call_llm_for_json


def call_llm_json(task_name: str, prompt: str) -> Dict[str, Any]:
    """Only approved low-level JSON LLM gateway."""
    return _call_llm_for_json(prompt)


def call_llm_text(task_name: str, prompt: str) -> str:
    """Only approved low-level text LLM gateway."""
    return _call_llm(prompt)


def intent_classification(prompt: str) -> Dict[str, Any]:
    return call_llm_json("intent_classification", prompt)


def agent_planning(prompt: str) -> Dict[str, Any]:
    return call_llm_json("agent_planning", prompt)


def agent_synthesis(prompt: str) -> str:
    return call_llm_text("agent_synthesis", prompt)


def sql_generation(prompt: str) -> Dict[str, Any]:
    return call_llm_json("sql_generation", prompt)


def hl7_note_extraction(prompt: str) -> Dict[str, Any]:
    return call_llm_json("hl7_note_extraction", prompt)


def deep_reflection(prompt: str) -> Dict[str, Any]:
    return call_llm_json("deep_reflection", prompt)


def patient_summary(prompt: str) -> str:
    return call_llm_text("patient_summary", prompt)


def embed_text_gateway(text: str) -> List[float]:
    from .embeddings import embed_text

    return embed_text(text)
