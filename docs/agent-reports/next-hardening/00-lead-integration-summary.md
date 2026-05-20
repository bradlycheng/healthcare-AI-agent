# Lead Integration Summary: Next Hardening Slice

Date: 2026-05-20

## Decisions Applied

- Added a deterministic reference resolver before intent classification and agent planning.
- Safe references can narrow to a patient subject, but ambiguous, missing, export, identifier, and scope-jump references fail closed or ask for clarification.
- Conversation memory TTL now uses central `SECURITY_CONFIG`.
- Query execution has a configured request timeout; timeout returns safely and skips memory commit.
- Startup cleanup expires transient security state only: parse sessions, conversation state, result refs, and demo sessions.
- `sql_used` is hidden by default and exposed only by explicit debug config.
- Raw HL7 and FHIR detail output are redacted by default.
- Token restore summary counts are attached to safe metadata and emitted only as aggregate audit payload.
- SQLGuard now treats `observations.value_raw` as a note/text column that requires a `note_read` output grant.
- Note-like observation values are redacted from read endpoints and patient timeline output by default.
- Reviewer P1 findings were addressed: client-supplied history is not passed to the agent as authority, resolved patient IDs are not appended to LLM-visible prompt text, and Warden denies patient-context calls outside the grant subject.
- Request timeout work now uses a bounded shared executor; timed-out work may still finish in the background, but repeated timeouts cannot create an unbounded executor/thread-per-request pattern.
- Safe-memory tests can use isolated DB paths for successful commits instead of writing that case to the shared workspace DB.

## Integration Notes

- Explorer reports are saved as:
  - `01-reference-memory-map.md`
  - `02-endpoint-output-map.md`
- Reference resolution carries the resolved subject as structured grant metadata, not prompt-visible patient-ID text.
- `conversation_result_refs` are still schema-only; full result-ref dereferencing remains a later slice.
- Read endpoints are audited and protected for raw HL7/FHIR/note text, but full per-endpoint read grants/RBAC remain deferred.

## Validation Focus

- Reference resolver unit tests.
- Query endpoint reference, ambiguity, timeout, and SQL debug tests.
- Parse/session replay and wrong-session tests.
- Raw HL7/FHIR and note-text output redaction tests.
- SQLGuard note-column policy tests.
- Compile/import gate and focused governance suite.
