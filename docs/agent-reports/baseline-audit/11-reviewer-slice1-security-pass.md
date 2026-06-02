# Agent Report: security-reviewer -- Slice 1 Final Pass

## Assignment

Final security review of Slice 1 (hl7_note_extraction Warden boundary) before merge.
Read app/warden.py, app/agent.py, and tests/test_hl7_note_extraction_warden.py.
Check PHI leakage, Warden scope lifecycle, register_identifiers() correctness, test gaps.

## Files Inspected

- app/warden.py
- app/agent.py
- app/security_validation.py
- app/token_guard.py
- tests/test_hl7_note_extraction_warden.py
- app/hl7_parser.py (read-only reference)

## Files Changed

None (read-only review)

---

## Critical Findings

**C1 -- No Post-Deanonymize PHI Validation on LLM Output**
Location: app/agent.py OUT-GATE block
deanonymize() is called correctly on the LLM output. But there is no check that the
resulting string/dict is free of raw patient identifiers. If the LLM somehow echoes
back a real name (not a token), it passes through undetected.
Action: After deanonymize(), check that known PHI values from the patient dict are
not present in the output string. Raise or log to governance if found.

**C2 -- register_identifiers() Does Not Cover Provider Names**
Location: app/warden.py register_identifiers()
Provider names from OBR segments (ordering provider, performing provider) are not
registered. build_token_map() covers providers already in the DB visits table. A
first-time provider referenced in a clinical note will leak to the LLM prompt.
Action: Either extend register_identifiers() to accept an optional providers list,
OR document and acknowledge this gap explicitly in a PR risk note with a ticket.

**C3 -- Missing Test: LLM Output Deanonymization**
Location: tests/test_hl7_note_extraction_warden.py
No test verifies that PHI tokens in LLM output are correctly restored. A test
should mock hl7_note_extraction() to return a response containing a PHI token,
then assert the token is restored (or redacted if not authorized) in llm_raw.

---

## Warning Findings

**W1 -- Grant TTL Is 5 Minutes for a Synchronous Call**
Location: app/agent.py, iso_after(minutes=5)
hl7_note_extraction() should complete in seconds. A 5-minute TTL is excessive.
If a token is leaked (e.g., debug log), the window for exploitation is unnecessary.
Recommended: iso_after(minutes=1) or iso_after(seconds=30).

**W2 -- No Governance Event Logged for Warden Scope Entry/Exit**
Location: app/agent.py, Warden scope block
No governance event is emitted when the Warden scope is entered or exited.
PHI tokenization count and scope lifecycle are not in the audit log.
Acceptable deferral if a governance-hardening slice is planned separately.

**W3 -- Post-Anonymize Completeness Not Checked**
Location: app/agent.py after warden_ctx.anonymize(prompt)
No assertion that safe_prompt does not contain real patient identifiers.
If register_identifiers() misses a field, the gap is silent.
Recommended: assert none of patient name/id/dob appear in safe_prompt before calling LLM.

**W4 -- register_identifiers() Partial Dict Is Silently Incomplete**
Location: app/warden.py register_identifiers()
If patient dict has only first_name and no last_name, name tokenization is skipped
silently. No warning logged.
Acceptable: behavior is safe (no crash, no false mapping). Document clearly.

---

## Informational

**I1 -- Token Map Lifecycle Is Correct**
context manager clears token map on exit even on exception. PASS.

**I2 -- Comment in OUT-GATE Is Accurate**
"Do NOT call anonymize_json() here" comment is correct and prevents a common mistake. PASS.

**I3 -- register_identifiers() Duplicate Check Is Correct**
get_token() check before add_mapping() prevents double-registration. PASS.

---

## Tests To Add

1. test_llm_output_deanonymized -- mock LLM to return dict containing a PHI token; verify token is restored to real value in llm_raw output (CRITICAL gap)
2. test_register_identifiers_partial_dict -- pass patient with only first_name; verify no error; verify ID not registered since both name parts required
3. test_anonymize_completeness -- after anonymize(), assert patient first_name, last_name, id, dob not in safe_prompt
4. test_warden_scope_cleared_on_exception -- raise inside with block; verify token map is empty after

---

## Sign-Off Condition

NOT MERGEABLE in current form.

Required before merge:
- C1: Add post-deanonymize PHI check on LLM output
- C3: Add test for LLM output deanonymization
- C2: Either fix provider name gap OR add documented risk acknowledgment in PR

Acceptable deferrals (document in PR):
- W1 TTL reduction (low urgency, clean-up item)
- W2 governance event logging (defer to governance-hardening slice)
- W3 post-anonymize completeness check (can follow C1 fix)
