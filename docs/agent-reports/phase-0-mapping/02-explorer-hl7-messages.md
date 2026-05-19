# Agent Report: Explorer B - HL7 And Messages

## Assignment

Map `/oru/parse`, `/messages`, FHIR generation, observation persistence, parse/persist behavior, and client-trusted fields. No files edited.

## Files Inspected

- `app/api.py`
- `app/agent.py`
- `app/hl7_parser.py`
- `app/fhir_builder.py`
- `app/db.py`
- `app/hl7_msh.py`
- `app/security.py`
- `web/script.js`
- Selected API/HL7/FHIR tests referenced by the explorer

## Current Flow

- `POST /oru/parse` accepts `hl7_text`, `use_llm`, and `persist`.
- `/oru/parse` sanitizes HL7 with strict ASCII, loosely checks for `MSH`, parses MSH, generates ACK, rejects non-ORU when MSH parsing succeeds, then calls `run_oru_pipeline`.
- `run_oru_pipeline` parses HL7, builds a basic summary, builds FHIR with local `_build_fhir_bundle`, optionally calls LLM for NTE/text observations, checks alerts, and persists only when `persist=True`.
- `parse_oru` parses PID/OBX and attaches NTE notes to the last observation; NTE before OBX becomes a placeholder `NOTE` observation.
- The live FHIR builder is `app/agent.py` local `_build_fhir_bundle`; richer `app/fhir_builder.py` appears unused.
- Persistence writes `hl7_messages` and `observations` through `insert_message_and_observations`.
- Browser flow calls `/oru/parse` with `persist:false`, lets the user edit/manual-add observations, then posts `patient`, `clinical_summary`, `structured_observations`, `fhir_bundle`, and `raw_hl7` to `POST /messages`.
- `POST /messages` persists the client-supplied structures directly.

## Risks / Bypasses

- `POST /messages` is a major trust-boundary bypass: it accepts client-supplied patient JSON, observations, summary, FHIR, and raw HL7 as authority.
- No parse session, digest, nonce, signed preview, or server-owned draft binds `/oru/parse persist:false` output to later `/messages` persistence.
- Client can fabricate parsed clinical JSON and save it.
- Frontend allows edited/manual observations, but server does not distinguish verified HL7 data from user-entered additions.
- Client-supplied FHIR can diverge from saved observations.
- LLM-enriched observations may be normalized after FHIR construction, causing FHIR/observation mismatch.
- Client controls observation `source`.
- NTE note text is not persisted as its own note field; without LLM extraction, note content is only in raw HL7/transient response.
- `parse_msh` can find MSH anywhere, while endpoint text says the message must start with MSH.
- `/messages` does not enforce ORU message type.
- Parse/persist errors may return raw exception text.
- Frontend uses `innerHTML` for HL7-derived values, creating rendering/injection risk.

## Recommended Implementation Notes

- Make persistence server-authoritative.
- Prefer `/oru/parse persist:true` or make `/messages` reparse raw HL7 and ignore client clinical JSON as authority.
- Introduce parse sessions with `parse_id`, session ownership, raw HL7 hash, status, expiry, and server parse result.
- Confirm-save should submit parse ID plus allowed edits, not trusted clinical payload.
- Server assigns provenance (`HL7`, `AI_EXTRACTED`, `MANUAL`).
- Rebuild FHIR after all normalization, filtering, alert enrichment, and accepted edits.
- Merge or choose one FHIR builder.
- Preserve NTE notes explicitly if they need query/display behavior.
- Require first segment to be MSH and enforce ORU validation everywhere persistence can happen.
- Return generic public parse/persist errors.

## Tests To Add

- `/messages` rejects fabricated clinical JSON that does not match server parse.
- `/messages` rejects non-ORU raw HL7.
- Parse preview cannot be saved without valid parse session.
- Wrong-session, expired, already-used, or tampered parse IDs fail.
- Server-rebuilt FHIR matches persisted observations.
- LLM-extracted/normalized observations are reflected in FHIR.
- NTE-only and NTE-attached messages preserve note content according to policy.
- Leading junk before MSH is rejected.
- Client-supplied `source`, `alert_level`, and `alert_message` cannot spoof authority.
- Frontend escapes HL7-derived display/value/unit strings.

## Open Questions

- Should reviewed manual observations be first-class persisted data, or stored separately as user annotations?
- Is `/messages` public API, legacy endpoint, or frontend helper only?
- Should AI-extracted findings persist automatically or require confirmation?
- Are NTE notes expected to be queryable?
- Should FHIR be stored canonically or generated on demand?
