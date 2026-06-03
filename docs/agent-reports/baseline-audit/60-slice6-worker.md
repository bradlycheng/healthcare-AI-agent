# Slice 6 Worker Report — DB & Timeline Hardening

**Date:** 2026-06-03
**Session type:** Narrow-worker — Slice 6 execution
**Files modified:** `app/patient_timeline.py`, `app/db.py`
**Artifacts written:** `tests/test_slice6_db_hardening.py`, `docs/agent-reports/baseline-audit/60-slice6-worker.md`

---

## Changes Made

### app/patient_timeline.py — centralized DB connection

**Lines changed: 10–14 (imports), 24, 62**

- Removed `import sqlite3` (no longer needed).
- Added `from .db import get_connection` import.
- Replaced `sqlite3.connect(db_path); conn.row_factory = sqlite3.Row` in `get_unique_patients()` (was line 24) with `get_connection(db_path)`.
- Replaced `sqlite3.connect(db_path); conn.row_factory = sqlite3.Row` in `get_patient_timeline()` (was line 62) with `get_connection(db_path)`.

Both callers now benefit from WAL mode and the 5000 ms busy timeout configured inside `get_connection()`.

---

### app/db.py — three changes

#### 1. Logger added (line 6, 14)
- Added `import logging` and `logger = logging.getLogger(__name__)` at module level, required for the field-length warnings.

#### 2. deletion_audit table in schema (lines 135–144)
Added to `init_db()`:
```sql
CREATE TABLE IF NOT EXISTS deletion_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER,
    patient_id TEXT,
    deleted_at TEXT
);
```

#### 3. Patient field length enforcement (lines 328–341, inside insert_message_and_observations)
After extracting `pid`, `first`, `last`, `dob` from the patient dict, each field is checked and silently truncated:
- `first_name` / `last_name`: max 100 chars
- `patient_id`: max 50 chars
- `dob`: max 10 chars

`logger.warning()` is emitted (with original length, no patient data content) whenever any truncation occurs.

#### 4. Storage limit wrapped in BEGIN IMMEDIATE (lines 347–359, inside insert_message_and_observations)
Replaced the bare `cur.execute("SELECT COUNT(*) ...")` + conditional raise with:
```python
cur.execute("BEGIN IMMEDIATE")
count = cur.execute("SELECT COUNT(*) FROM hl7_messages").fetchone()[0]
if count >= 1300:
    conn.rollback()
    raise ValueError("Demo database storage limit reached ...")
```
The `BEGIN IMMEDIATE` lock prevents two concurrent threads from both passing the count check before either has committed an insert.

#### 5. Deletion audit in prune_messages() (lines 190–201)
Before the `DELETE FROM observations` / `DELETE FROM hl7_messages` block, a SELECT fetches `id` and `patient_id` for each candidate message, then inserts one row per message into `deletion_audit` with `deleted_at` timestamp.

#### 6. Deletion audit in delete_all_messages() (lines 228–236)
Same pattern: before clearing observations and messages, all existing `(id, patient_id)` pairs are recorded in `deletion_audit`.

---

## Test Results

```
tests/test_slice6_db_hardening.py — 17/17 PASSED
Full regression — 163/164 passed (1 pre-existing async failure in test_context_memory, unrelated to Slice 6)
```

Test classes written:
- `TestPatientTimelineUsesCentralizedConnection` (4 tests) — AST walk confirming no `sqlite3.connect()` calls, import check, functional round-trip tests for both public functions.
- `TestStorageLimitConcurrentInsertBlocked` (3 tests) — raises at exactly 1300, source contains `BEGIN IMMEDIATE`, threading race test confirms at most one winner.
- `TestPatientFieldLengthEnforced` (6 tests) — truncation at each limit boundary, warning logged on truncation, no warning when within limits.
- `TestDeletionAuditLoggedBeforeCascade` (4 tests) — table exists after `init_db()`, correct columns, `prune_messages()` writes audit row, `delete_all_messages()` writes audit rows for all deleted messages.

---

## Sign-off Conditions

| Condition | Status |
|---|---|
| `patient_timeline.py` uses `get_connection()` exclusively — no `sqlite3.connect()` calls remain | PASS |
| Storage limit insert wrapped in `BEGIN IMMEDIATE` transaction | PASS |
| Patient fields truncated to max lengths with `logger.warning()` on truncation | PASS |
| `deletion_audit` row written before each cascading DELETE | PASS |
| `deletion_audit` table created in `init_db()` schema | PASS |

**Verdict: READY FOR REVIEW**
