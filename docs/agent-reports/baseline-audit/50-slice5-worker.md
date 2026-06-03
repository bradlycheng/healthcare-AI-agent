# Slice 5 Worker Report — API Hardening

**Date:** 2026-06-03  
**Session type:** Narrow-worker — Slice 5 execution  
**Files modified:** `app/api.py`  
**Artifacts written:** `tests/test_slice5_api_hardening.py`, `docs/agent-reports/baseline-audit/50-slice5-worker.md`

---

## Changes Made

### 1. CORS — replaced wildcard with configurable allowlist
**`app/api.py` lines 30–35 (new), 51–57 (middleware)**

- Added module-level block that reads `ALLOWED_ORIGINS` env var (comma-separated).
- If the env var is absent or empty, defaults to `["http://localhost:8000", "http://localhost:8080"]` — never `"*"`.
- `app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, ...)` now references the computed list instead of the hardcoded `["*"]`.

### 2. Rate limiter — X-Forwarded-For validated against trusted proxy list
**`app/api.py` lines 38–39, 66–79**

- Added `TRUSTED_PROXIES` module-level list read from `TRUSTED_PROXIES` env var (comma-separated, default empty).
- Introduced `_get_rate_limit_key(request: Request) -> str` helper:
  - If `X-Forwarded-For` header is present **and** `request.client.host` is in `TRUSTED_PROXIES`, returns the first (leftmost) address from XFF (whitespace-stripped).
  - Otherwise always returns `request.client.host`, ignoring the header entirely.
- All three rate-limit call sites (`/api/query`, `/patients/{id}/summary`, `/oru/parse`) updated to call `_get_rate_limit_key(request)` instead of reading `request.client.host` directly.

### 3. Admin password — no hardcoded default
**`app/api.py` lines 41–47, 785–793**

- `ADMIN_PASSWORD` is now read at module level via `os.getenv("ADMIN_PASSWORD")` with **no default argument** (returns `None` if unset).
- If `ADMIN_PASSWORD` is falsy at startup, `logger.warning(...)` is emitted describing the missing configuration.
- The `/admin/reset` endpoint now checks `if not ADMIN_PASSWORD` first and raises `HTTPException(status_code=503, detail="Admin endpoint unavailable: server not configured")` before any password comparison.
- The old `os.getenv("ADMIN_PASSWORD", "d3m0th1s")` inside the handler body is removed entirely.

### 4. Admin brute-force delay — raised to 3.0 seconds
**`app/api.py` line 794**

- `time.sleep(1.0)` changed to `time.sleep(3.0)` in the wrong-password branch.

---

## Test Results

```
tests/test_slice5_api_hardening.py — 15/15 PASSED
Regression (api or cors or admin or rate) — 19/19 PASSED, 0 failures
```

Test classes written:
- `TestCorsWildcard` — verifies `["*"]` never appears in `ALLOWED_ORIGINS`
- `TestCorsEnvVar` — verifies env var is parsed, defaults applied correctly
- `TestRateLimitXForwardedFor` — 5 cases covering trusted/untrusted proxy, no-XFF fallback, whitespace stripping
- `TestAdminPasswordNotSet` — 503 returned when `ADMIN_PASSWORD` is None; module-level value reflection
- `TestAdminBruteForceDelay` — AST check confirms sleep constant >= 3.0; wall-clock check on TestClient call

---

## Sign-off Conditions

| Condition | Status |
|---|---|
| `allow_origins` reads from `ALLOWED_ORIGINS` env var, defaults to localhost list, never `"*"` | PASS |
| Rate limiter only uses `X-Forwarded-For` when client IP is in `TRUSTED_PROXIES` | PASS |
| Admin endpoint returns HTTP 503 if `ADMIN_PASSWORD` env var is not set | PASS |
| Admin brute-force delay is >= 3.0 seconds | PASS |
| Startup logs a warning if `ADMIN_PASSWORD` is not configured | PASS |

**Verdict: READY FOR REVIEW**
