# Follow-Up Report: Deterministic Intent Grants

## Summary

Added a centralized grant builder so query and SQL grants are created deterministically instead of being assembled inline.

## Implementation Summary

- Added `app/grant_builder.py`.
- Centralized tool, table, column, output field, max-row, and deny-intent mapping.
- Replaced broad inline agent grant construction with `build_query_grant`.
- Replaced SQL helper default grant construction with `build_query_grant`.
- SQL tool validation now uses a grant narrowed to `query_database`.

## Validation

```text
pytest tests/test_grant_builder.py
5 passed
```

## Residual Work

- Feed LLM intent-classifier labels into this grant builder at `/api/query`.
- Add reference/scope-jump detection before grant construction.
- Expand grant builder coverage for admin/RBAC once user accounts exist.
