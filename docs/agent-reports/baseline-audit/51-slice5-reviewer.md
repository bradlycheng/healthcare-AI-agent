# Slice 5 Reviewer Report — API Rate Limiting & CORS Hardening

**Date:** 2026-06-02
**Reviewer role:** security-reviewer (read-only)
**Worker report reviewed:** `50-slice5-worker.md`
**Verdict:** MERGEABLE

---

## Checklist Results

| Requirement | Evidence | Status |
|---|---|---|
| CORS never uses `"*"` | `api.py:30-35` reads `ALLOWED_ORIGINS` env, defaults to localhost list; `"*"` cannot appear | PASS |
| Rate limiter validates XFF against `TRUSTED_PROXIES` | `api.py:66-79` `_get_rate_limit_key()` only honors XFF when client IP in `TRUSTED_PROXIES`; defaults empty | PASS |
| Admin 503 when password unset | `api.py:42-47` no default; startup warning; `api.py:786-790` raises 503 before any comparison | PASS |
| Admin brute-force delay ≥ 3.0s | `api.py:794` `time.sleep(3.0)` confirmed by AST test and wall-clock test | PASS |

## Test Quality — PASS

15 tests. Highlights: XFF spoofing surface covered with 5 parametrized variants; wall-clock measurement on wrong-password delay; `TestClient`-driven 503 path; AST inspection confirms sleep constant ≥ 3.0. All real assertions.

## Scope Discipline — PASS

Only `app/api.py` touched for this slice.

## Deferred / Non-blocking

- Exponential backoff not added (plan secondary objective) — constant 3.0s delay meets explicit sign-off condition.
- Startup uses `logger.warning` + runtime 503 rather than hard fail — safer for demo mode, documented in worker report.
- `_get_rate_limit_key()` returns `"unknown"` if `request.client` is None (all unknowns share one bucket). Future cleanup.

## Verdict

**MERGEABLE.** No blocking findings.
