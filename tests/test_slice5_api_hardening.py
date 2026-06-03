# tests/test_slice5_api_hardening.py
"""
Slice 5 — API hardening tests.

Covers:
  - CORS wildcard not used (allow_origins is never ["*"])
  - CORS reads from ALLOWED_ORIGINS env var
  - Rate limiter ignores X-Forwarded-For when client is not a trusted proxy
  - Rate limiter uses X-Forwarded-For when client IS a trusted proxy
  - Admin endpoint returns HTTP 503 when ADMIN_PASSWORD env var is not set
  - Admin brute-force delay is >= 3 seconds
"""

from __future__ import annotations

import importlib
import os
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure project root on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reload_api_with_env(**env_overrides):
    """Re-import app.api with specific environment variables set."""
    # Patch os.getenv so module-level code picks up overrides.
    original_env = {}
    for key, val in env_overrides.items():
        original_env[key] = os.environ.get(key)
        if val is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = val

    # Remove cached module so it reinitialises
    mods_to_remove = [k for k in sys.modules if k.startswith("app.api")]
    for m in mods_to_remove:
        del sys.modules[m]

    try:
        import app.api as api_mod
        return api_mod
    finally:
        # Restore env
        for key, original_val in original_env.items():
            if original_val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_val
        # Remove re-imported module so later tests get a fresh load too
        for k in list(sys.modules.keys()):
            if k.startswith("app.api"):
                del sys.modules[k]


def _make_mock_request(client_host: str, xff: str | None = None) -> MagicMock:
    """Build a minimal mock FastAPI Request with the given client IP."""
    req = MagicMock()
    req.client = MagicMock()
    req.client.host = client_host
    headers: dict[str, str] = {}
    if xff is not None:
        headers["X-Forwarded-For"] = xff
    req.headers = headers
    return req


# ---------------------------------------------------------------------------
# 1. CORS — wildcard must never appear
# ---------------------------------------------------------------------------

class TestCorsWildcard:
    def test_cors_wildcard_not_used(self):
        """allow_origins must never be ['*'] regardless of env."""
        # Default env (no ALLOWED_ORIGINS set)
        api = _reload_api_with_env(ALLOWED_ORIGINS=None, ADMIN_PASSWORD="testpw")
        assert api.ALLOWED_ORIGINS != ["*"], (
            "ALLOWED_ORIGINS must not default to ['*']"
        )
        assert "*" not in api.ALLOWED_ORIGINS, (
            "The wildcard '*' must not appear in ALLOWED_ORIGINS"
        )

    def test_cors_wildcard_not_used_explicit_star(self):
        """Even if ALLOWED_ORIGINS env var is set to '*', the wildcard should be used
        as a literal origin string (not the CORS wildcard bypass) — but the real
        requirement is that the *default* is never '*'.  This test verifies the
        module correctly passes the env value through when it IS set."""
        api = _reload_api_with_env(
            ALLOWED_ORIGINS="http://example.com,http://other.com",
            ADMIN_PASSWORD="testpw",
        )
        assert api.ALLOWED_ORIGINS == ["http://example.com", "http://other.com"]
        assert "*" not in api.ALLOWED_ORIGINS


# ---------------------------------------------------------------------------
# 2. CORS — reads from env var
# ---------------------------------------------------------------------------

class TestCorsEnvVar:
    def test_cors_reads_from_env_var(self):
        """ALLOWED_ORIGINS env var (comma-separated) must populate allow_origins."""
        api = _reload_api_with_env(
            ALLOWED_ORIGINS="https://app.example.com, https://admin.example.com",
            ADMIN_PASSWORD="testpw",
        )
        assert "https://app.example.com" in api.ALLOWED_ORIGINS
        assert "https://admin.example.com" in api.ALLOWED_ORIGINS
        assert len(api.ALLOWED_ORIGINS) == 2

    def test_cors_default_when_env_var_not_set(self):
        """When ALLOWED_ORIGINS is not set, defaults to localhost list."""
        api = _reload_api_with_env(ALLOWED_ORIGINS=None, ADMIN_PASSWORD="testpw")
        assert "http://localhost:8000" in api.ALLOWED_ORIGINS
        assert "http://localhost:8080" in api.ALLOWED_ORIGINS

    def test_cors_default_when_env_var_empty(self):
        """When ALLOWED_ORIGINS is empty string, defaults to localhost list."""
        api = _reload_api_with_env(ALLOWED_ORIGINS="", ADMIN_PASSWORD="testpw")
        assert "http://localhost:8000" in api.ALLOWED_ORIGINS
        assert "http://localhost:8080" in api.ALLOWED_ORIGINS


# ---------------------------------------------------------------------------
# 3 & 4. Rate limiter — X-Forwarded-For trust logic
# ---------------------------------------------------------------------------

class TestRateLimitXForwardedFor:
    def _get_helper(self):
        """Return the _get_rate_limit_key function from app.api."""
        # Import the current module (avoid reload side-effects; just import fresh)
        mods_to_remove = [k for k in sys.modules if k == "app.api"]
        for m in mods_to_remove:
            del sys.modules[m]
        os.environ.setdefault("ADMIN_PASSWORD", "testpw")
        import app.api as api_mod
        return api_mod

    def test_rate_limit_ignores_xforwarded_for_without_trusted_proxy(self):
        """X-Forwarded-For must be ignored when client is NOT in TRUSTED_PROXIES."""
        api = _reload_api_with_env(
            TRUSTED_PROXIES="",
            ADMIN_PASSWORD="testpw",
        )
        # TRUSTED_PROXIES is empty — should always use client.host
        req = _make_mock_request(
            client_host="1.2.3.4",
            xff="10.0.0.1, 10.0.0.2",
        )
        key = api._get_rate_limit_key(req)
        assert key == "1.2.3.4", (
            f"Expected client.host '1.2.3.4' but got '{key}'; "
            "X-Forwarded-For must not be trusted without a trusted proxy"
        )

    def test_rate_limit_ignores_xforwarded_for_untrusted_client(self):
        """X-Forwarded-For must be ignored when client host is not in TRUSTED_PROXIES."""
        api = _reload_api_with_env(
            TRUSTED_PROXIES="192.168.1.1",
            ADMIN_PASSWORD="testpw",
        )
        # Client is 9.9.9.9 which is NOT the trusted proxy
        req = _make_mock_request(
            client_host="9.9.9.9",
            xff="10.0.0.1",
        )
        key = api._get_rate_limit_key(req)
        assert key == "9.9.9.9", (
            f"Expected client.host '9.9.9.9' but got '{key}'; "
            "untrusted client should not have XFF header honoured"
        )

    def test_rate_limit_uses_xforwarded_for_with_trusted_proxy(self):
        """X-Forwarded-For must be used when client IS in TRUSTED_PROXIES."""
        api = _reload_api_with_env(
            TRUSTED_PROXIES="10.0.0.100",
            ADMIN_PASSWORD="testpw",
        )
        req = _make_mock_request(
            client_host="10.0.0.100",
            xff="203.0.113.5, 10.0.0.200",
        )
        key = api._get_rate_limit_key(req)
        assert key == "203.0.113.5", (
            f"Expected XFF first address '203.0.113.5' but got '{key}'"
        )

    def test_rate_limit_uses_xforwarded_for_strips_whitespace(self):
        """First IP from X-Forwarded-For should be stripped of whitespace."""
        api = _reload_api_with_env(
            TRUSTED_PROXIES="10.0.0.100",
            ADMIN_PASSWORD="testpw",
        )
        req = _make_mock_request(
            client_host="10.0.0.100",
            xff="  203.0.113.99  , 10.0.0.200",
        )
        key = api._get_rate_limit_key(req)
        assert key == "203.0.113.99", (
            f"Expected stripped IP '203.0.113.99' but got '{key}'"
        )

    def test_rate_limit_no_xff_header_trusted_proxy(self):
        """When trusted proxy sends no X-Forwarded-For, fall back to client.host."""
        api = _reload_api_with_env(
            TRUSTED_PROXIES="10.0.0.100",
            ADMIN_PASSWORD="testpw",
        )
        req = _make_mock_request(
            client_host="10.0.0.100",
            xff=None,  # no header
        )
        key = api._get_rate_limit_key(req)
        assert key == "10.0.0.100", (
            f"Expected client.host '10.0.0.100' but got '{key}' when no XFF present"
        )


# ---------------------------------------------------------------------------
# 5. Admin password not set → HTTP 503
# ---------------------------------------------------------------------------

class TestAdminPasswordNotSet:
    def test_admin_password_not_set_returns_503(self):
        """If ADMIN_PASSWORD env var is not set, /admin/reset returns 503."""
        from fastapi.testclient import TestClient

        api = _reload_api_with_env(ADMIN_PASSWORD=None, ADMIN_PASSWORD_UNSET=None)

        # Patch ADMIN_PASSWORD to None to simulate missing env var
        original = api.ADMIN_PASSWORD
        api.ADMIN_PASSWORD = None
        try:
            client = TestClient(api.app, raise_server_exceptions=False)
            response = client.post("/admin/reset", json={"password": "anything"})
            assert response.status_code == 503, (
                f"Expected 503 when ADMIN_PASSWORD not set, got {response.status_code}"
            )
            assert "unavailable" in response.json().get("detail", "").lower() or \
                   "not configured" in response.json().get("detail", "").lower(), (
                f"Expected informative 503 detail, got: {response.json()}"
            )
        finally:
            api.ADMIN_PASSWORD = original

    def test_admin_password_not_set_module_level(self):
        """Module-level ADMIN_PASSWORD is None when env var absent."""
        api = _reload_api_with_env(ADMIN_PASSWORD=None)
        assert api.ADMIN_PASSWORD is None or api.ADMIN_PASSWORD == "", (
            "ADMIN_PASSWORD should be None/empty when env var is not set"
        )

    def test_admin_password_set_module_level(self):
        """Module-level ADMIN_PASSWORD reflects env var when set."""
        api = _reload_api_with_env(ADMIN_PASSWORD="supersecret123")
        assert api.ADMIN_PASSWORD == "supersecret123"


# ---------------------------------------------------------------------------
# 6. Admin brute-force delay >= 3 seconds
# ---------------------------------------------------------------------------

class TestAdminBruteForceDelay:
    def test_admin_brute_force_delay_is_3_seconds(self):
        """Wrong password must trigger a sleep of >= 3.0 seconds."""
        import inspect
        import ast

        # Read the source of the admin endpoint and verify the sleep value
        api_path = os.path.join(
            os.path.dirname(__file__), "..", "app", "api.py"
        )
        with open(api_path, "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source)

        sleep_values: list[float] = []
        for node in ast.walk(tree):
            # Look for time.sleep(...) or asyncio.sleep(...) calls
            if isinstance(node, ast.Call):
                func = node.func
                is_sleep = (
                    (isinstance(func, ast.Attribute) and func.attr == "sleep")
                    or (isinstance(func, ast.Name) and func.id == "sleep")
                )
                if is_sleep and node.args:
                    arg = node.args[0]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, (int, float)):
                        sleep_values.append(float(arg.value))

        assert sleep_values, "No sleep() calls found in api.py"
        max_sleep = max(sleep_values)
        assert max_sleep >= 3.0, (
            f"Expected anti-brute-force sleep >= 3.0 seconds, found max={max_sleep}"
        )

    def test_admin_brute_force_delay_actually_sleeps(self):
        """Wrong password call takes at least 3 seconds of wall time."""
        from fastapi.testclient import TestClient

        # Need ADMIN_PASSWORD set so we reach the sleep code
        api = _reload_api_with_env(ADMIN_PASSWORD="correct-password-xyz")
        # Override module ADMIN_PASSWORD to a known value
        api.ADMIN_PASSWORD = "correct-password-xyz"

        client = TestClient(api.app, raise_server_exceptions=False)

        t0 = time.monotonic()
        response = client.post("/admin/reset", json={"password": "wrong-password"})
        elapsed = time.monotonic() - t0

        assert response.status_code == 401, (
            f"Expected 401 for wrong password, got {response.status_code}"
        )
        assert elapsed >= 3.0, (
            f"Expected anti-brute-force delay >= 3.0 s, actual elapsed={elapsed:.2f} s"
        )
