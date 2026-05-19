from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Set

from .security_validation import IntentGrant, TokenRecord


TOKEN_REDACTION = "[REDACTED_PHI_TOKEN]"
TOKEN_PATTERN = re.compile(r"<<PHI_[A-Za-z0-9_]+>>")
TRUSTED_TOKEN_SOURCES = {"server", "database", "warden", "tool_result"}
UNTRUSTED_TOKEN_SOURCES = {"user", "rag", "retrieval", "llm"}


FIELD_PREFIXES = {
    "patient_name": "PAT",
    "patient_first_name": "PAT",
    "patient_last_name": "PAT",
    "patient_id": "PID",
    "patient_dob": "DOB",
    "dob": "DOB",
    "provider_name": "PROV",
}


@dataclass(frozen=True)
class RestoreResult:
    text: str
    restored_count: int = 0
    redacted_count: int = 0
    redacted_tokens: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class TokenGuardSnapshot:
    request_id: str
    session_id: str
    token_count: int
    field_types: List[str]


class TokenGuardScope:
    """Request-scoped opaque token registry and restore gate.

    Real values are held only in this object. TokenRecord carries the auditable
    token metadata, while this scope enforces request/session/grant boundaries
    before any token can be restored.
    """

    def __init__(self, *, session_id: str, request_id: str, grant: IntentGrant):
        self.session_id = session_id
        self.request_id = request_id
        self.grant = grant
        self._records: Dict[str, TokenRecord] = {}
        self._real_values: Dict[str, str] = {}

    @property
    def records(self) -> List[TokenRecord]:
        return list(self._records.values())

    def create_token(
        self,
        real_value: str,
        *,
        field_type: str,
        source: str = "server",
        output_authorized: bool = True,
    ) -> TokenRecord:
        if not real_value:
            raise ValueError("real_value is required")
        if not field_type:
            raise ValueError("field_type is required")

        token = self._new_token(field_type)
        record = TokenRecord(
            request_id=self.request_id,
            token=token,
            field_type=field_type,
            source=source,
            output_authorized=output_authorized,
        )
        self._records[token] = record
        self._real_values[token] = real_value
        return record

    def tokenize_text(
        self,
        text: str,
        *,
        real_value: str,
        field_type: str,
        source: str = "server",
        output_authorized: bool = True,
    ) -> str:
        record = self.create_token(
            real_value,
            field_type=field_type,
            source=source,
            output_authorized=output_authorized,
        )
        return text.replace(real_value, record.token)

    def restore_text(self, text: str, *, session_id: Optional[str] = None) -> RestoreResult:
        if not text:
            return RestoreResult(text=text)

        active_session_id = session_id or self.session_id
        restored_count = 0
        redacted_count = 0
        redacted_tokens: List[str] = []

        def replace(match: re.Match[str]) -> str:
            nonlocal restored_count, redacted_count
            token = match.group(0)
            record = self._records.get(token)
            if self._can_restore(record, active_session_id):
                restored_count += 1
                return self._real_values[token]

            redacted_count += 1
            redacted_tokens.append(token)
            return TOKEN_REDACTION

        restored_text = TOKEN_PATTERN.sub(replace, text)
        return RestoreResult(
            text=restored_text,
            restored_count=restored_count,
            redacted_count=redacted_count,
            redacted_tokens=redacted_tokens,
        )

    def import_record(self, record: TokenRecord, real_value: str) -> None:
        """Attach an existing record for boundary tests or future integration.

        The restore gate still validates record.request_id, source, and grant
        authorization before using the supplied real value.
        """
        self._records[record.token] = record
        self._real_values[record.token] = real_value

    def audit_summary(self) -> TokenGuardSnapshot:
        return TokenGuardSnapshot(
            request_id=self.request_id,
            session_id=self.session_id,
            token_count=len(self._records),
            field_types=sorted({record.field_type for record in self._records.values()}),
        )

    def clear(self) -> None:
        self._records.clear()
        self._real_values.clear()

    def _new_token(self, field_type: str) -> str:
        prefix = FIELD_PREFIXES.get(field_type, _field_prefix(field_type))
        while True:
            token = f"<<PHI_{prefix}_{secrets.token_hex(12).upper()}>>"
            if token not in self._records:
                return token

    def _can_restore(self, record: Optional[TokenRecord], session_id: str) -> bool:
        if record is None:
            return False
        if session_id != self.session_id:
            return False
        if self.grant.session_id != self.session_id:
            return False
        if self.grant.request_id != self.request_id:
            return False
        if not _grant_is_live(self.grant):
            return False
        if record.request_id != self.request_id:
            return False
        if record.token not in self._real_values:
            return False
        if not record.output_authorized:
            return False
        if record.source in UNTRUSTED_TOKEN_SOURCES:
            return False
        if record.source not in TRUSTED_TOKEN_SOURCES:
            return False
        return _field_type_allowed(record.field_type, self.grant.output_fields)


class TokenGuard:
    """Factory for request-scoped TokenGuardScope instances."""

    def request_scope(self, grant: IntentGrant) -> TokenGuardScope:
        return TokenGuardScope(
            session_id=grant.session_id,
            request_id=grant.request_id,
            grant=grant,
        )


def restore_text(text: str, *, records: Iterable[TokenRecord], grant: IntentGrant) -> RestoreResult:
    """Fail-closed restore helper for metadata-only callers.

    Without the request-local real-value registry, even valid-looking tokens
    cannot be restored. This prevents guessed or replayed TokenRecord metadata
    from becoming a disclosure primitive.
    """
    scope = TokenGuardScope(session_id=grant.session_id, request_id=grant.request_id, grant=grant)
    for record in records:
        scope._records[record.token] = record
    return scope.restore_text(text)


def _field_type_allowed(field_type: str, output_fields: Iterable[str]) -> bool:
    allowed: Set[str] = set(output_fields or [])
    return "*" in allowed or field_type in allowed


def _grant_is_live(grant: IntentGrant) -> bool:
    try:
        expires_at = datetime.fromisoformat(grant.expires_at)
    except ValueError:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > datetime.now(timezone.utc)


def _field_prefix(field_type: str) -> str:
    compact = "".join(ch for ch in field_type.upper() if ch.isalnum())
    return (compact[:8] or "FIELD")
