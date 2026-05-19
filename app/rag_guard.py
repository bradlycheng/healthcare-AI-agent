from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


TRUST_LEVELS: Dict[str, int] = {
    "UNKNOWN": 0,
    "USER_UPLOADED_UNTRUSTED": 1,
    "DEMO_SEEDED_DOC": 2,
    "TRUSTED_LOCAL_DOC": 3,
}

REQUIRED_METADATA_KEYS = {"trust_level", "source_hash", "chunk_type"}
ALLOWED_CHUNK_TYPES = {"guideline", "reference", "policy", "clinical_note_legacy", "unknown"}
TEXT_LIMIT = 6000

ROLE_SPOOF_PATTERNS = (
    re.compile(r"(?im)^\s*(system|developer|assistant|tool|user)\s*[:=]"),
    re.compile(r"(?i)<\|/?(?:system|developer|assistant|tool|user)\|>"),
    re.compile(r"(?i)\bignore\s+(?:all\s+)?(?:previous|prior)\s+instructions\b"),
    re.compile(r"(?i)\b(?:grant|role|permission|policy)\s*[:=]\s*(?:admin|system|developer|allow|trusted)\b"),
)

ENCODED_BLOB_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{120,}={0,2}(?![A-Za-z0-9+/=])"),
    re.compile(r"\b(?:[A-Fa-f0-9]{2}){80,}\b"),
    re.compile(r"(?:%[0-9A-Fa-f]{2}){40,}"),
)

METADATA_AUTHORITY_KEYS = {
    "allowed_tools",
    "authority",
    "grant",
    "instructions",
    "output_authorized",
    "permissions",
    "role",
    "system_prompt",
    "trusted",
}


@dataclass(frozen=True)
class RagChunkInput:
    text: str
    metadata: Mapping[str, Any]
    chunk_id: Optional[str] = None
    distance: Optional[float] = None


@dataclass(frozen=True)
class TrustedRagChunk:
    text: str
    metadata: Dict[str, Any]
    chunk_id: Optional[str] = None
    distance: Optional[float] = None
    evidence_only: bool = True
    warnings: Tuple[str, ...] = ()


@dataclass(frozen=True)
class RagGuardResult:
    accepted: List[TrustedRagChunk] = field(default_factory=list)
    rejected: List[Dict[str, Any]] = field(default_factory=list)


def filter_rag_chunks(
    chunks: Iterable[RagChunkInput | Mapping[str, Any]],
    *,
    minimum_trust: str = "USER_UPLOADED_UNTRUSTED",
) -> RagGuardResult:
    accepted: List[TrustedRagChunk] = []
    rejected: List[Dict[str, Any]] = []
    minimum_rank = TRUST_LEVELS.get(minimum_trust, TRUST_LEVELS["USER_UPLOADED_UNTRUSTED"])

    for index, chunk in enumerate(chunks):
        normalized = coerce_rag_chunk(chunk)
        if normalized is None:
            rejected.append(_rejection(index, None, "malformed_chunk"))
            continue

        ok, reason, safe_chunk = validate_rag_chunk(normalized, minimum_rank=minimum_rank)
        if ok and safe_chunk is not None:
            accepted.append(safe_chunk)
        else:
            rejected.append(_rejection(index, normalized.chunk_id, reason))

    return RagGuardResult(accepted=accepted, rejected=rejected)


def coerce_rag_chunk(chunk: RagChunkInput | Mapping[str, Any]) -> Optional[RagChunkInput]:
    if isinstance(chunk, RagChunkInput):
        return chunk
    if not isinstance(chunk, Mapping):
        return None

    text = chunk.get("text", chunk.get("document", chunk.get("content")))
    metadata = chunk.get("metadata", {})
    if not isinstance(text, str) or not isinstance(metadata, Mapping):
        return None

    chunk_id = chunk.get("chunk_id", chunk.get("id"))
    distance = chunk.get("distance")
    return RagChunkInput(
        text=text,
        metadata=metadata,
        chunk_id=chunk_id if isinstance(chunk_id, str) else None,
        distance=distance if isinstance(distance, (int, float)) and not isinstance(distance, bool) else None,
    )


def validate_rag_chunk(
    chunk: RagChunkInput,
    *,
    minimum_rank: int = TRUST_LEVELS["USER_UPLOADED_UNTRUSTED"],
) -> Tuple[bool, str, Optional[TrustedRagChunk]]:
    text = chunk.text
    metadata = dict(chunk.metadata)

    if len(text) > TEXT_LIMIT:
        return False, "chunk_text_too_large", None
    if _has_hidden_unicode(text) or any(_has_hidden_unicode(str(value)) for value in metadata.values()):
        return False, "hidden_unicode_detected", None
    if _has_role_spoofing(text) or _metadata_claims_authority(metadata):
        return False, "role_spoofing_detected", None
    if _has_encoded_blob(text):
        return False, "encoded_blob_detected", None

    missing = sorted(REQUIRED_METADATA_KEYS - set(metadata.keys()))
    if missing:
        return False, f"missing_metadata:{missing[0]}", None

    trust_level = str(metadata.get("trust_level", "UNKNOWN")).upper()
    if trust_level not in TRUST_LEVELS:
        return False, "unknown_trust_level", None
    if TRUST_LEVELS[trust_level] < minimum_rank:
        return False, "insufficient_trust", None

    source_hash = metadata.get("source_hash")
    if not isinstance(source_hash, str) or not re.fullmatch(r"[a-fA-F0-9]{32,64}", source_hash):
        return False, "invalid_source_hash", None

    chunk_type = str(metadata.get("chunk_type", "unknown")).lower()
    if chunk_type not in ALLOWED_CHUNK_TYPES:
        return False, "invalid_chunk_type", None

    safe_metadata = {
        "trust_level": trust_level,
        "source_hash": source_hash.lower(),
        "chunk_type": chunk_type,
        "evidence_only": True,
    }
    for optional_key in ("title", "source"):
        optional_value = metadata.get(optional_key)
        if isinstance(optional_value, str):
            safe_metadata[optional_key] = optional_value[:240]
    warnings = _metadata_warnings(metadata)
    if warnings:
        safe_metadata["policy_warnings"] = list(warnings)

    return True, "accepted", TrustedRagChunk(
        text=text,
        metadata=safe_metadata,
        chunk_id=chunk.chunk_id,
        distance=chunk.distance,
        evidence_only=True,
        warnings=warnings,
    )


def chunks_from_chroma_results(results: Mapping[str, Any]) -> List[RagChunkInput]:
    documents = _first_query_result(results.get("documents"))
    metadatas = _first_query_result(results.get("metadatas"))
    ids = _first_query_result(results.get("ids"))
    distances = _first_query_result(results.get("distances"))

    chunks: List[RagChunkInput] = []
    for index, document in enumerate(documents):
        metadata = metadatas[index] if index < len(metadatas) and isinstance(metadatas[index], Mapping) else {}
        chunk_id = ids[index] if index < len(ids) and isinstance(ids[index], str) else None
        distance = distances[index] if index < len(distances) and isinstance(distances[index], (int, float)) else None
        if isinstance(document, str):
            chunks.append(RagChunkInput(text=document, metadata=metadata, chunk_id=chunk_id, distance=distance))
    return chunks


def _first_query_result(value: Any) -> Sequence[Any]:
    if isinstance(value, list) and value and isinstance(value[0], list):
        return value[0]
    if isinstance(value, list):
        return value
    return []


def _has_hidden_unicode(text: str) -> bool:
    for char in text:
        category = unicodedata.category(char)
        if category in {"Cf", "Cc"} and char not in "\n\r\t":
            return True
    return False


def _has_role_spoofing(text: str) -> bool:
    return any(pattern.search(text) for pattern in ROLE_SPOOF_PATTERNS)


def _metadata_claims_authority(metadata: Mapping[str, Any]) -> bool:
    return any(key.lower() in METADATA_AUTHORITY_KEYS for key in metadata.keys())


def _has_encoded_blob(text: str) -> bool:
    for pattern in ENCODED_BLOB_PATTERNS:
        for match in pattern.findall(text):
            token = match if isinstance(match, str) else match[0]
            if _looks_like_decodable_blob(token):
                return True
    return False


def _looks_like_decodable_blob(token: str) -> bool:
    if "%" in token:
        return True
    if re.fullmatch(r"(?:[A-Fa-f0-9]{2}){80,}", token):
        return True
    try:
        base64.b64decode(token, validate=True)
        return True
    except (binascii.Error, ValueError):
        return False


def _metadata_warnings(metadata: Mapping[str, Any]) -> Tuple[str, ...]:
    warnings = metadata.get("policy_warnings")
    if not isinstance(warnings, list):
        return ()
    safe = [warning for warning in warnings if isinstance(warning, str) and len(warning) <= 80]
    return tuple(safe[:10])


def _rejection(index: int, chunk_id: Optional[str], reason: str) -> Dict[str, Any]:
    return {"index": index, "chunk_id": chunk_id, "reason": reason}
