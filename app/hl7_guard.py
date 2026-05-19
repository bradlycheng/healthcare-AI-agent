from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Sequence


MAX_HL7_MESSAGE_CHARS = 64_000
MAX_SEGMENTS = 1_000
MAX_SEGMENT_CHARS = 8_000
MAX_FIELDS_PER_SEGMENT = 80
MAX_FIELD_CHARS = 4_000
MAX_NOTE_CHARS = 2_000

TEXT_LIKE_OBX_TYPES = {"ED", "FT", "ST", "TX"}

SQL_LIKE_PATTERNS = (
    re.compile(r"\b(drop|alter|truncate)\s+(table|database|schema|index|view)\b", re.IGNORECASE),
    re.compile(r"\b(insert\s+into|update\s+\w+\s+set|delete\s+from)\b", re.IGNORECASE),
    re.compile(r"\bunion\s+(all\s+)?select\b", re.IGNORECASE),
    re.compile(r"\bselect\s+(.{0,80}\s+)?from\s+\w+", re.IGNORECASE),
    re.compile(r"(--|/\*|\*/|;\s*(drop|alter|truncate|insert|update|delete|select)\b)", re.IGNORECASE),
    re.compile(r"\bxp_cmdshell\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class Hl7GuardConfig:
    max_message_chars: int = MAX_HL7_MESSAGE_CHARS
    max_segments: int = MAX_SEGMENTS
    max_segment_chars: int = MAX_SEGMENT_CHARS
    max_fields_per_segment: int = MAX_FIELDS_PER_SEGMENT
    max_field_chars: int = MAX_FIELD_CHARS
    max_note_chars: int = MAX_NOTE_CHARS


@dataclass(frozen=True)
class Hl7GuardIssue:
    code: str
    message: str
    segment_index: int | None = None
    segment_name: str | None = None
    field: str | None = None


@dataclass(frozen=True)
class Hl7GuardResult:
    ok: bool
    errors: List[Hl7GuardIssue] = field(default_factory=list)
    warnings: List[Hl7GuardIssue] = field(default_factory=list)
    metadata: Dict[str, object] = field(default_factory=dict)


def validate_hl7_message(
    hl7_text: str,
    *,
    config: Hl7GuardConfig | None = None,
) -> Hl7GuardResult:
    """
    Validate raw HL7 before parser, storage, or LLM enrichment.

    The result intentionally contains counts and reason codes only. It does not
    echo raw HL7, patient identifiers, notes, or other PHI-bearing values.
    """
    cfg = config or Hl7GuardConfig()
    errors: List[Hl7GuardIssue] = []

    if not isinstance(hl7_text, str):
        return Hl7GuardResult(
            ok=False,
            errors=[Hl7GuardIssue("hl7_not_text", "HL7 payload must be text.")],
            metadata={"segment_count": 0, "pid_count": 0, "obr_count": 0, "obx_count": 0},
        )

    if "\x00" in hl7_text:
        errors.append(Hl7GuardIssue("hl7_null_byte", "HL7 payload contains a null byte."))

    if len(hl7_text) > cfg.max_message_chars:
        errors.append(Hl7GuardIssue("hl7_message_too_large", "HL7 payload exceeds the message size cap."))

    segments = _split_segments(hl7_text)
    if not segments:
        errors.append(Hl7GuardIssue("hl7_empty", "HL7 payload is empty."))
        return _result(errors, segments)

    if len(segments) > cfg.max_segments:
        errors.append(Hl7GuardIssue("hl7_too_many_segments", "HL7 payload exceeds the segment count cap."))

    first_name = _segment_name(segments[0])
    if first_name != "MSH":
        errors.append(Hl7GuardIssue("hl7_first_segment_not_msh", "HL7 payload must start with an MSH segment.", 1, first_name))

    field_sep = "|"
    if first_name == "MSH":
        if len(segments[0]) < 4:
            errors.append(Hl7GuardIssue("hl7_msh_malformed", "MSH segment is malformed.", 1, "MSH"))
        else:
            field_sep = segments[0][3]
            if not field_sep or field_sep.isalnum() or field_sep in "\r\n\x00":
                errors.append(Hl7GuardIssue("hl7_bad_field_separator", "MSH field separator is invalid.", 1, "MSH"))

    counts = {"PID": 0, "OBR": 0, "OBX": 0, "NTE": 0}
    note_field_count = 0

    for index, segment in enumerate(segments, start=1):
        name = _segment_name(segment)
        if name in counts:
            counts[name] += 1

        if len(segment) > cfg.max_segment_chars:
            errors.append(Hl7GuardIssue("hl7_segment_too_large", "HL7 segment exceeds the segment length cap.", index, name))

        fields = segment.split(field_sep)
        if len(fields) > cfg.max_fields_per_segment:
            errors.append(Hl7GuardIssue("hl7_too_many_fields", "HL7 segment exceeds the field count cap.", index, name))

        for field_index, value in enumerate(fields[1:], start=1):
            if len(value) > cfg.max_field_chars:
                errors.append(
                    Hl7GuardIssue(
                        "hl7_field_too_large",
                        "HL7 field exceeds the field length cap.",
                        index,
                        name,
                        f"{name}-{field_index}",
                    )
                )

        if name == "MSH" and index == 1:
            message_type = _field(fields, 8)
            if not _is_oru_message_type(message_type):
                errors.append(Hl7GuardIssue("hl7_not_oru", "MSH-9 must identify an ORU message.", index, name, "MSH-9"))

        if name == "NTE":
            note_field_count += 1
            _validate_note_text(errors, _field(fields, 3), cfg, index, name, "NTE-3")

        if name == "OBX" and _field(fields, 2).strip().upper() in TEXT_LIKE_OBX_TYPES:
            note_field_count += 1
            _validate_note_text(errors, _field(fields, 5), cfg, index, name, "OBX-5")

    if counts["PID"] < 1:
        errors.append(Hl7GuardIssue("hl7_missing_pid", "HL7 payload must include a PID segment."))

    if counts["OBR"] + counts["OBX"] < 1:
        errors.append(Hl7GuardIssue("hl7_missing_result_segment", "HL7 payload must include at least one OBR or OBX segment."))

    metadata = {
        "segment_count": len(segments),
        "pid_count": counts["PID"],
        "obr_count": counts["OBR"],
        "obx_count": counts["OBX"],
        "nte_count": counts["NTE"],
        "note_field_count": note_field_count,
        "message_chars": len(hl7_text),
    }
    return Hl7GuardResult(ok=not errors, errors=errors, metadata=metadata)


def _split_segments(hl7_text: str) -> List[str]:
    normalized = hl7_text.replace("\r\n", "\n").replace("\r", "\n")
    return [segment.strip() for segment in normalized.split("\n") if segment.strip()]


def _segment_name(segment: str) -> str:
    return segment[:3].upper() if len(segment) >= 3 else segment.upper()


def _field(fields: Sequence[str], hl7_index: int) -> str:
    return fields[hl7_index] if hl7_index < len(fields) else ""


def _is_oru_message_type(message_type: str) -> bool:
    parts = [part.strip().upper() for part in message_type.split("^") if part.strip()]
    return bool(parts and parts[0] == "ORU")


def _validate_note_text(
    errors: List[Hl7GuardIssue],
    note_text: str,
    cfg: Hl7GuardConfig,
    segment_index: int,
    segment_name: str,
    field_name: str,
) -> None:
    if len(note_text) > cfg.max_note_chars:
        errors.append(
            Hl7GuardIssue(
                "hl7_note_too_large",
                "HL7 note field exceeds the note length cap.",
                segment_index,
                segment_name,
                field_name,
            )
        )

    if _contains_sql_like_text(note_text):
        errors.append(
            Hl7GuardIssue(
                "hl7_note_sql_like",
                "HL7 note field contains SQL-like control text.",
                segment_index,
                segment_name,
                field_name,
            )
        )


def _contains_sql_like_text(note_text: str) -> bool:
    return any(pattern.search(note_text or "") for pattern in SQL_LIKE_PATTERNS)


def _result(errors: List[Hl7GuardIssue], segments: List[str]) -> Hl7GuardResult:
    return Hl7GuardResult(
        ok=False,
        errors=errors,
        metadata={
            "segment_count": len(segments),
            "pid_count": 0,
            "obr_count": 0,
            "obx_count": 0,
            "nte_count": 0,
            "note_field_count": 0,
        },
    )
