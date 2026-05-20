# Security Kernel Test Layout

The current test suite still uses mostly flat files, but future build slices
should group tests by boundary so coverage is easier to audit.

Recommended layout:

```text
tests/
  compile/        syntax, imports, direct low-level dependency checks
  governance/     Warden, SQLGuard, Hl7Guard, TokenGuard, grants, memory
  endpoints/      /api/query, /oru/parse, /messages, patient reads, admin
  ingestion/      MLLP and non-HTTP ingestion paths
  audit/          governance_events PHI-free assertions
  ui/             browser/rendered escaping checks
```

Until the files are reorganized, keep new coverage-closure tests focused on
the execution boundary they prove and name test functions by the security
property they assert.
