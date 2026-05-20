from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .security_validation import SafeConversationState


REFERENCE_RE = re.compile(
    r"\b(that patient|this patient|first one|second one|third one|his|her|their|them|those|that)\b",
    re.IGNORECASE,
)
ORDINAL_INDEX = {
    "first one": 0,
    "second one": 1,
    "third one": 2,
}
COHORT_JUMP_RE = re.compile(r"\b(all|everyone|everybody|cohort|population|patients)\b", re.IGNORECASE)
EXPORT_JUMP_RE = re.compile(r"\b(export|download|csv|spreadsheet|encode|base64|transform)\b", re.IGNORECASE)
IDENTIFIER_JUMP_RE = re.compile(r"\b(identifier|identifiers|ids|patient ids|dob|birth date)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ReferenceResolution:
    action: str
    question: str
    reason_code: str
    subject: Optional[str] = None
    referenced_patient_count: int = 0

    @property
    def allowed(self) -> bool:
        return self.action in {"unchanged", "resolved"}

    @property
    def needs_clarification(self) -> bool:
        return self.action == "clarify"


def resolve_safe_references(question: str, state: Optional[SafeConversationState]) -> ReferenceResolution:
    """Resolve only typed safe-state references before grants are issued.

    The resolver never trusts raw history or assistant text. It can narrow a
    request to a known patient ID, clarify ambiguous references, or deny obvious
    attempts to turn a prior answer into export/identifier authority.
    """
    text = question or ""
    reference_match = REFERENCE_RE.search(text)
    if not reference_match:
        if state and state.scope == "single_patient" and COHORT_JUMP_RE.search(text):
            return ReferenceResolution("clarify", text, "scope_jump_single_patient_to_cohort")
        return ReferenceResolution("unchanged", text, "no_reference")

    if EXPORT_JUMP_RE.search(text):
        return ReferenceResolution("deny", text, "reference_scope_jump_export")
    if IDENTIFIER_JUMP_RE.search(text) and state and state.scope != "single_patient":
        return ReferenceResolution("deny", text, "reference_scope_jump_identifiers")
    if not state or not state.patient_ids:
        return ReferenceResolution("clarify", text, "reference_without_safe_state")

    patient_ids = list(state.patient_ids)
    subject = _resolve_subject(reference_match.group(0).lower(), patient_ids)
    if subject is None:
        return ReferenceResolution("clarify", text, "ambiguous_reference", referenced_patient_count=len(patient_ids))

    return ReferenceResolution(
        "resolved",
        text,
        "reference_resolved_patient",
        subject=subject,
        referenced_patient_count=len(patient_ids),
    )


def _resolve_subject(reference_text: str, patient_ids: list[str]) -> Optional[str]:
    normalized = reference_text.strip().lower()
    if normalized in ORDINAL_INDEX:
        index = ORDINAL_INDEX[normalized]
        return patient_ids[index] if index < len(patient_ids) else None
    if len(patient_ids) == 1:
        return patient_ids[0]
    return None
