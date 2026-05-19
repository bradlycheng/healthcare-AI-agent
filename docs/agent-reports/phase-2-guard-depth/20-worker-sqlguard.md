# Worker Report: SQLGuard

## Assignment

Implement a deterministic SQLite `SELECT` validator for Phase 2 guard depth without integrating it into `app/query_assistant.py`.

## Changed Files

- `app/sql_guard.py`
- `tests/test_sql_guard.py`
- `docs/agent-reports/phase-2-guard-depth/20-worker-sqlguard.md`

## Implementation Summary

- Added `SqlGuard`, `SqlGuardResult`, `validate_sql_select`, and `require_safe_sql` as the lead integration API.
- Enforces exactly one top-level `SELECT` by rejecting comments, semicolons, nested `SELECT`, compound queries, PRAGMA, ATTACH/DETACH, and DDL/DML keywords.
- Blocks `contacts` even if a malformed grant includes it.
- Applies static table/column safety plus grant-scoped table and column narrowing.
- Rejects wildcards, unknown aliases, unsafe functions, non-numeric limits, comma-form limits, and ambiguous unqualified columns.
- Injects `LIMIT grant.max_rows` when absent and caps numeric limits above `grant.max_rows`.

## Validation

- Added focused tests for safe SELECT rewriting, row cap enforcement, comments, semicolons, multiple SELECTs, unsafe keywords, blocked tables, table grants, unsafe functions, column allowlists, static sensitive columns, joins, aliases, wildcards, ambiguous columns, invalid limits, exception helper behavior, and custom schema construction.

## Lead Integration Notes

- Call `validate_sql_select(sql, grant)` after SQL generation and before SQLite execution.
- Execute `result.sql`, not the original SQL, because `SQLGuard` may inject or cap `LIMIT`.
- Treat `result.allowed == False` as fail closed and expose only `result.reason` or a mapped user-safe message.
- The guard intentionally rejects complex SQL patterns such as subqueries and compound SELECTs until a dependency-backed parser or stricter AST layer is approved.

## Residual Risks

- This is a deterministic lexical/policy validator, not a full SQL AST parser.
- Unqualified columns in multi-table queries are allowed only when they resolve to exactly one selected table; otherwise the query must qualify them.
- Subject predicates and aggregate-vs-identifier disclosure rules remain future guard depth unless the lead wires richer grant scope into this API.
