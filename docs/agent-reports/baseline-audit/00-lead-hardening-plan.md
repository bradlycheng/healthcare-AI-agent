# Lead Plan: Baseline Hardening -- 3 Slices

Source reports:
- docs/agent-reports/baseline-audit/01-security-explorer-baseline.md
- docs/agent-reports/baseline-audit/02-hl7-storage-explorer-baseline.md

Date: 2026-06-02
Revised: 2026-06-02 (Codex review: Slice 1 token-registration gap, Slice 2 format-validation flaw)

---

## Triage Notes

The audit found 7 CRITICAL findings across both reports. Not all are equal weight for a first worker pass.

Three are large infrastructure changes requiring design decisions before implementation:
- Raw HL7 encryption at rest (requires KMS/secrets infra decision)
- FHIR bundle access control (requires RBAC design)
- MLLP TLS/auth (requires network/ops decision)

Four are narrow code changes with clear scope and no infrastructure dependencies.
Those four are candidates for the first worker tasks.

This plan picks the 3 narrowest, highest-value slices. Each slice is one worker task.

---

## Slice 1 -- HL7 Note Extraction Warden Boundary

**Risk addressed:** security-explorer C3
PHI in HL7 clinical notes (NTE-3, OBX-5 text fields) is sent to the LLM via
`hl7_note_extraction()` with no Warden scope around it. This is the only LLM
call in the codebase that completely bypasses tokenization.

**Why first:**
- Warden API already exists; the pattern is already in healthcare_agent.py
- No schema changes, no API changes, no new infrastructure
- Clinical notes are the highest-risk PHI surface: free-text diagnoses, medications, symptoms
- The gap is unambiguous and the fix is mechanically clear

**Token-registration gap (Codex review):**
`build_token_map()` queries existing DB records. A brand-new HL7 patient being
ingested for the first time will not yet be in the DB when note extraction runs.
Their name, ID, and DOB will not be in the token map and will pass through
to the LLM unmasked.

Fix: before anonymizing the notes_block, register the current parsed patient
identifiers directly into the request token_map using `token_map.add_mapping()`.
This requires adding a `WardenContext.register_identifiers(patient: dict)` helper
so agent.py does not reach directly into `token_map` internals and does not need
to import the private `_new_phi_token()` function from warden.py.

**Files to edit:**
- app/warden.py -- add `WardenContext.register_identifiers(patient: dict)` helper
- app/agent.py -- add Warden scope around hl7_note_extraction(); call register_identifiers()
- tests/test_hl7_note_extraction_warden.py -- new test file

**Files NOT to touch:**
- app/llm_gateway.py
- app/hl7_parser.py
- `run_oru_pipeline()` function signature must not change
- `run_oru_pipeline()` return structure must not change
- Warden public API (anonymize, deanonymize, intercept, deanonymize_sql) must not change

**Implementation guidance (not final patch):**

In app/warden.py, add to WardenContext:

```python
def register_identifiers(self, patient: dict) -> None:
    """Register current-request patient identifiers into the token map.

    Call this for new patients not yet persisted to DB, before anonymizing
    any text that may contain their identifiers.
    """
    first = (patient.get("first_name") or "").strip()
    last = (patient.get("last_name") or "").strip()
    pid = (patient.get("id") or patient.get("patient_id") or "").strip()
    dob = (patient.get("dob") or "").strip()

    if first and last:
        full_name = f"{first} {last}"
        self.token_map.add_mapping(
            full_name, _new_phi_token("PAT"), field_type="patient_name"
        )
    if pid:
        self.token_map.add_mapping(
            pid, _new_phi_token("PID"), field_type="patient_id"
        )
    if dob:
        self.token_map.add_mapping(
            dob, _new_phi_token("DOB"), field_type="patient_dob"
        )
```

In app/agent.py, wrap the hl7_note_extraction call:

```python
# Create a minimal grant scoped to hl7 ingestion -- no tool access, no DB rows
ingestion_grant = IntentGrant(
    intent="hl7_note_extraction",
    risk="medium",
    session_id="hl7_ingestion",
    request_id=new_request_id(),
    scope="hl7_ingestion",
    allowed_tools=[],
    output_fields=["new_observations"],
    max_rows=0,
    expires_at=iso_after(minutes=5),
)
warden = Warden()
with warden.request_scope(grant=ingestion_grant) as warden_ctx:
    warden_ctx.register_identifiers(patient)   # register new patient before DB write
    safe_prompt = warden_ctx.anonymize(prompt)
    llm_raw = hl7_note_extraction(safe_prompt)
    # OUT-GATE: do NOT call anonymize_json() on llm_raw.
    # The LLM output must be deanonymized, not re-tokenized.
    # If llm_raw may contain PHI tokens in string fields, deanonymize them:
    if isinstance(llm_raw, dict):
        llm_raw_str = json.dumps(llm_raw)
        llm_raw = json.loads(warden_ctx.deanonymize(llm_raw_str))
```

Note to worker: review the actual output structure of hl7_note_extraction() and
apply deanonymize to string fields that may contain patient tokens.

**Tests to add (tests/test_hl7_note_extraction_warden.py):**
- `test_patient_name_not_in_note_extraction_prompt`: inject patient first/last name
  in NTE-3; verify name is NOT in the string passed to hl7_note_extraction()
- `test_new_patient_not_in_db_identifiers_tokenized`: patient not in DB; their name
  in OBX-5 note must still be tokenized before LLM call (validates register_identifiers)
- `test_note_extraction_skipped_when_no_text_fields`: if _needs_ai_analysis() is False,
  Warden scope is never entered; existing pipeline behavior unchanged

**Sign-off condition:**
Patient name present in NTE-3 or OBX-5 must not appear in the string passed to
hl7_note_extraction(). This must hold for both existing DB patients and new patients
not yet persisted. Existing run_oru_pipeline() behavior must be unchanged.

---

## Slice 2 -- Alert Unit Compatibility Validation

**Risk addressed:** hl7-storage-explorer C1
OBX-3 codes are trusted from client input and matched against alert rules.
`check_alert()` looks up the code in CLINICAL_RULES and compares the numeric value
against a threshold. Because the code dict lookup succeeds on any valid-format LOINC
that happens to be in the rules, format validation alone does not close this gap.

**Why the original Slice 2 was wrong (Codex review):**
The original plan claimed LOINC regex format validation would block alert injection.
It would not. An attacker can send code="49563-0" (Troponin I), which is a valid-format
LOINC AND is in CLINICAL_RULES. Format validation passes. Value="0.5" passes float()
conversion. Alert fires. Format validation stopped nothing.

**Correct framing:**
The attack requires the attacker to also send a value that passes the threshold
comparison. Adding unit compatibility validation closes this: if the alert rule
expects Troponin in ng/mL or ug/L, but the OBX says mg/dL, the combination is
suspicious and the alert should not fire.

This does not prevent all possible injection (a sophisticated attacker could fake
a correct unit too), but it substantially raises the bar. Full defense requires
a LOINC registry integration, which is out of scope here.

**Governance logging -- design constraint (Codex review):**
check_alert() has no request/session context. Importing emit_governance_event()
directly inside alerts.py would require fake IDs or broad plumbing changes --
both out of scope for Slice 2. Keep check_alert() pure: accepts code/value/unit,
returns alert dict or None, no side effects. If governance logging for unit mismatch
is needed, it belongs in agent.py (run_oru_pipeline has request context) or deferred
to a governance-hardening slice. Worker must document whichever path is taken.

**Files to edit:**
- app/alerts.py -- add expected_units to CLINICAL_RULES; update check_alert() to accept unit
- app/agent.py -- update check_alert() call site to pass ob.get("unit", "") (one line only)
- tests/test_alert_unit_validation.py -- new test file

**Files NOT to touch:**
- app/hl7_parser.py (parsing unchanged)
- app/db.py (observations still stored regardless of alert outcome)

**Signature and return structure:**
- check_alert() signature MAY change backward-compatibly: `check_alert(code, value, unit="")`
  The unit parameter must default to "" so all existing callers continue to work without changes
  beyond the one call site in agent.py
- check_alert() return structure must not change ({message, level, code} or None)
- Observations with mismatched units must still be stored; only alert triggering is gated

**Implementation guidance (not final patch):**

Extend CLINICAL_RULES entries with expected_units:

```python
CLINICAL_RULES = {
    '49563-0': {  # Troponin I -- conservative set; ng/dL is NOT standard, do not include
        'limit': 0.04,
        'op': '>',
        'msg': 'CRITICAL: Elevated Troponin - Possible Myocardial Infarction',
        'level': 'CRITICAL',
        'expected_units': ['ng/mL', 'ng/L', 'ug/L', 'pg/mL'],
    },
    '2345-7': {   # Glucose
        'limit': 140,
        'op': '>',
        'msg': 'High Glucose - Hyperglycemia',
        'level': 'WARNING',
        'expected_units': ['mg/dL', 'mmol/L'],
    },
    ...
}
```

Update check_alert() signature to accept optional unit parameter:

```python
def check_alert(code: str, value: Any, unit: str = "") -> Optional[Dict[str, str]]:
```

Before triggering the alert, if expected_units is defined, check that unit is in the list
(case-insensitive). If unit is empty, allow the alert (backward-compatible behavior --
no governance side effect inside this function; document deferral in worker report).
If unit is present but incompatible, suppress the alert and return None.
check_alert() must have no side effects -- no logging, no DB calls, no imports of
governance/audit modules. Keep it pure.

The call site in agent.py already has the unit field available:
`check_alert(ob.get("code"), ob.get("value"))` -- add `ob.get("unit", "")`.

Worker: confirm the check_alert() call site in agent.py and update it to pass the unit.
This means agent.py IS in scope for the call-site update, but only that one line.

**Tests to add (tests/test_alert_unit_validation.py):**
- `test_alert_fires_valid_code_value_unit`: Troponin code + value > threshold + correct unit (ng/mL) -> alert fires
- `test_alert_suppressed_incompatible_unit`: Troponin code + value > threshold + "mg/dL" -> no alert, returns None
- `test_alert_fires_missing_unit_backward_compat`: Troponin code + value > threshold + no unit -> alert fires (backward-compatible behavior; no governance side effect tested here)
- `test_alert_not_triggered_wrong_value_type`: Troponin code + value = "POSITIVE" (string) -> no alert (regression test for existing float() catch)
- `test_existing_rules_unaffected`: Glucose and Potassium rules still fire with valid units

**Sign-off condition:**
Troponin LOINC code with value above threshold but incompatible unit must not trigger alert.
Mismatch must appear in governance_events.
All existing alert behavior on valid code/value/unit combinations must be unchanged.

---

## Slice 3 -- RAG Query Tokenization

**Risk addressed:** security-explorer C1
`retrieve_context(question)` is called with the raw (un-tokenized) user question,
which is then embedded via Bedrock Titan. If the question contains a patient name,
that name is sent to Bedrock in cleartext. This bypasses the Warden IN-GATE.

**Why third:**
- More moving parts than slices 1 and 2
- Requires threading the tokenized question through query_assistant.py
- Warden context is already active at the call site; the fix is passing the right string
- Doing slices 1 and 2 first establishes the team's Warden pattern before this slice

**Files to edit:**
- app/healthcare_agent.py -- pass safe_question (tokenized) to retrieve_context()
- app/query_assistant.py -- accept pre-tokenized query in retrieve_context(); document expectation
- tests/test_rag_query_tokenization.py -- new test file

**Files NOT to touch:**
- app/vector_store.py (ChromaDB interface unchanged)
- app/embeddings.py (embed_text unchanged)
- app/warden.py (no Warden changes needed for this slice)
- RAG chunk retrieval logic must not change
- Source attribution (sources list) must continue to work

**Implementation guidance (not final patch):**
In healthcare_agent.py _tool_search_guidelines() and _tool_query_database():
- safe_question is already tokenized at line 352 of the main run() method
- Pass safe_question to retrieve_context() instead of the raw question variable
- After retrieval, deanonymize context_text before adding to tool result
In query_assistant.py:
- Add docstring: "query parameter must be pre-tokenized when called from agent context"
- No signature change needed

**Tests to add (tests/test_rag_query_tokenization.py):**
- `test_rag_query_no_phi_to_bedrock`: question containing patient name; string passed to
  embed_text() must not contain that name
- `test_rag_context_deanonymized_before_return`: source text returned to user must have
  real values, not tokens
- `test_rag_retrieval_quality_regression`: tokenized query still retrieves correct guideline chunks

**Sign-off condition:**
Patient name in a clinical query must not appear in the string passed to embed_text().
Source attribution must continue to return correct file references.

---

## What Is Explicitly Out of Scope for These 3 Slices

- Raw HL7 encryption at rest (db.py) -- requires KMS/secrets decision
- FHIR bundle access control (api.py) -- requires RBAC design
- MLLP TLS and sender auth (mllp_server.py) -- requires network/ops decision
- Token map heuristic for unregistered names (warden.py) -- handled by register_identifiers() in Slice 1 for HL7; query-side names are a separate gap
- Parse session cleanup job (db.py) -- requires scheduler decision
- Message control ID idempotency (db.py) -- requires duplicate handling policy decision

---

## Worker Instructions (Copy-Paste)

**For Slice 1:**
```
Use the narrow-worker subagent to implement Slice 1 from
docs/agent-reports/baseline-audit/00-lead-hardening-plan.md.

File ownership:
- app/warden.py (add WardenContext.register_identifiers() helper only)
- app/agent.py (wrap hl7_note_extraction in Warden scope; call register_identifiers)
- tests/test_hl7_note_extraction_warden.py (new file)

Do not change any Warden public API methods.
Do not change run_oru_pipeline() signature or return structure.
Do not touch app/llm_gateway.py or app/hl7_parser.py.
Add the three tests listed in the plan.
Return a worker report and prompt-ledger entry when done.
```

**For Slice 2:**
```
Use the narrow-worker subagent to implement Slice 2 from
docs/agent-reports/baseline-audit/00-lead-hardening-plan.md.

File ownership:
- app/alerts.py (add expected_units to CLINICAL_RULES; update check_alert to accept unit)
- app/agent.py (update check_alert() call site to pass ob.get("unit", "") -- one line only)
- tests/test_alert_unit_validation.py (new file)
- docs/agent-reports/baseline-audit/20-worker-slice2-alert-unit-validation.md (new report)
- docs/agent-reports/prompt-ledger.md (ledger entry)

Scope:
- In app/alerts.py, add expected_units to all four CLINICAL_RULES entries.
- Use conservative, clinically accurate unit sets. For Troponin: ng/mL, ng/L, ug/L, pg/mL.
  Do NOT include ng/dL -- it is not a standard Troponin unit.
- Change check_alert() signature backward-compatibly: check_alert(code, value, unit="").
- Normalize unit comparison case-insensitively (.strip().lower()).
- Suppress alert (return None) when unit is present and not in expected_units.
- When unit is empty, preserve existing behavior (allow alert). No governance side effect.
- check_alert() must remain pure: no side effects, no logging, no imports of governance
  or audit modules. It has no request/session context.
- In app/agent.py, only update the one check_alert() call site to pass ob.get("unit", "").
  Do not change anything else in agent.py.
- Do not change check_alert() return structure ({message, level, code} or None).
- Observations with mismatched units must still be stored; only alert triggering is gated.
- Do not touch hl7_parser.py, db.py, warden.py, llm_gateway.py, or API contracts.
- If governance logging for unit mismatch is desirable, document it as deferred in the
  worker report with a note that check_alert() lacks request context.

Tests (tests/test_alert_unit_validation.py):
- test_alert_fires_valid_code_value_unit: Troponin + value > threshold + ng/mL -> alert fires
- test_alert_suppressed_incompatible_unit: Troponin + value > threshold + mg/dL -> returns None
- test_alert_fires_missing_unit_backward_compat: Troponin + value > threshold + no unit -> fires
- test_alert_not_triggered_wrong_value_type: Troponin + value "POSITIVE" -> None (regression)
- test_existing_rules_unaffected: Glucose and Potassium rules fire on valid units

Run the new test file and all existing alert/HL7 tests.
Return a worker report (20-worker-slice2-alert-unit-validation.md) and prompt-ledger entry.
```

**For Slice 3:**
```
Use the narrow-worker subagent to implement Slice 3 from
docs/agent-reports/baseline-audit/00-lead-hardening-plan.md.

File ownership:
- app/healthcare_agent.py (pass tokenized question to retrieve_context)
- app/query_assistant.py (add docstring; confirm call site)
- tests/test_rag_query_tokenization.py (new file)

Do not change app/vector_store.py, app/embeddings.py, or app/warden.py.
RAG chunk retrieval logic and source attribution must not change.
Add the three tests listed in the plan.
Return a worker report and prompt-ledger entry when done.
```
