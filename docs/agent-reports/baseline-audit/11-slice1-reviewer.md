# Slice 1 Reviewer Report — SQL Injection Prevention

**Date:** 2026-06-02
**Reviewer:** security-reviewer (read-only)
**Files reviewed:** `app/db.py`, `app/query_assistant.py`, `tests/test_slice1_sql_hardening.py`
**Verdict:** MERGEABLE

---

## Checklist Results

### 1. Security objective met — PASS
- `prune_messages()` (`app/db.py` lines 153-188): f-string SQL replaced with parameterized `IN (?, ?, ?)` placeholders. IDs are bound as a tuple via `cur.execute(sql, tuple(ids_to_delete))`. No f-string SQL remains anywhere in the function.
- `validate_sql()` (`app/query_assistant.py` lines 249-286): single `sql.upper().strip()` normalization at line 258 drives all keyword checks. Word-boundary regex `\b{keyword}\b` for single-word keywords; substring match for the space-containing `CROSS JOIN`.
- `QUERY_ROW_CAP = 1000` (line 246) enforced via `cursor.fetchmany(QUERY_ROW_CAP)` (line 317). `fetchall()` is no longer used.
- `FORBIDDEN_KEYWORDS` (lines 238-243) includes every keyword the hardening plan required: PRAGMA, ATTACH, DETACH, VACUUM, ANALYZE, EXPLAIN, UNION, CROSS JOIN — plus the pre-existing DDL/DML set.
- RO connection failure now logs a `logger.warning(...)` and returns an error tuple instead of falling through to a read-write connection (lines 304-312).

### 2. Test quality — PASS
- 45 tests, all pass (`pytest tests/test_slice1_sql_hardening.py -v` → 45 passed in 1.64s).
- Real end-to-end assertions: parameterized DELETE verified by inserting old + new rows in a temp DB and confirming counts; row cap verified by inserting 1100 rows and asserting `len(results) == 1000`; f-string absence verified by `inspect.getsource(prune_messages)` + regex.
- Case sensitivity covered with lower/upper/mixed parametrize cases per keyword.
- Test names map to specific behaviors.

### 3. Scope discipline — PASS
- `git status` shows only `app/db.py` and `app/query_assistant.py` modified, plus new `tests/test_slice1_sql_hardening.py`. No other `app/` file touched.

### 4. Deferred items — Acceptable
- Worker report lists none. The intentional non-blocking of `pragma_compile_options()` as a function-name prefix is documented in the worker report and justified — the standalone `PRAGMA` statement (the attack vector) IS blocked.

---

## Non-blocking observations

1. In `test_pragma_as_embedded_word_blocked`, the first `validate_sql("select pragma_compile_options()")` call has no assertion on its return value. Cosmetic only.
2. Some `EXPLAIN`-prefixed test cases are rejected by the earlier "Only SELECT queries are allowed" gate rather than the `EXPLAIN` keyword check. Result (rejection) still satisfies assertions. Not a security issue.
3. `EXEC` precedes `EXECUTE` in the forbidden list, but word-boundary regex correctly avoids matching `EXEC` inside `EXECUTE`.

---

## Verdict

**MERGEABLE.** All four critical sign-off conditions are satisfied. No blocking findings.
