import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.api import (
    ORUParseRequest,
    QueryRequest,
    app,
    prune_expired_messages,
    validate_production_config,
)


ROOT = Path(__file__).resolve().parents[1]


def test_api_routes_do_not_have_duplicate_method_path_pairs():
    seen = set()
    duplicates = []
    for route in app.routes:
        for method in getattr(route, "methods", set()):
            pair = (method, route.path)
            if pair in seen:
                duplicates.append(pair)
            seen.add(pair)
    assert duplicates == []


def test_unused_contact_storage_and_legacy_reset_routes_are_not_public():
    routes = {(method, route.path) for route in app.routes for method in getattr(route, "methods", set())}
    assert ("POST", "/api/contact") not in routes
    assert ("DELETE", "/messages") not in routes
    assert ("POST", "/admin/reset") in routes


def test_retention_is_disabled_by_default(monkeypatch):
    called = False

    def fake_prune_messages(days_to_keep):
        nonlocal called
        called = True

    monkeypatch.delenv("MESSAGE_RETENTION_DAYS", raising=False)
    monkeypatch.setattr("app.db.prune_messages", fake_prune_messages)
    prune_expired_messages()
    assert called is False


def test_public_request_models_enforce_bounds():
    with pytest.raises(ValidationError):
        QueryRequest(question="")
    with pytest.raises(ValidationError):
        QueryRequest(question="x" * 2001)
    with pytest.raises(ValidationError):
        QueryRequest(question="ok", reasoning_depth="unbounded")
    with pytest.raises(ValidationError):
        ORUParseRequest(hl7_text="x" * 100_001)


def test_deployment_files_have_no_insecure_demo_defaults():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    caddy = (ROOT / "Caddyfile").read_text(encoding="utf-8")
    caddy_local = (ROOT / "Caddyfile.local").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "ADMIN_PASSWORD=${ADMIN_PASSWORD:?" in compose
    assert "ENABLE_API_DOCS=${ENABLE_API_DOCS:-false}" in compose
    assert "ALLOWED_HOSTS=${ALLOWED_HOSTS:-healthdataagent.com" in compose
    assert "APP_ENV=production" in compose
    assert '127.0.0.1:8080:8080' in compose
    assert "ADMIN_PASSWORD=d3m0th1s" not in env_example
    assert "AUTH_PASSWORD=healthcare2025" not in env_example
    assert "Access-Control-Allow-Origin *" not in caddy
    assert "Access-Control-Allow-Origin *" not in caddy_local
    assert "HEALTHCHECK" in dockerfile
    assert "http://127.0.0.1:8080/health" in dockerfile


def test_production_rejects_demo_or_short_admin_passwords(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADMIN_PASSWORD", "d3m0th1s")
    with pytest.raises(RuntimeError):
        validate_production_config()

    monkeypatch.setenv("ADMIN_PASSWORD", "short")
    with pytest.raises(RuntimeError):
        validate_production_config()

    monkeypatch.setenv("ADMIN_PASSWORD", "a-long-unique-demo-password")
    validate_production_config()


def test_runtime_database_sidecars_and_audit_log_are_ignored():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "*.db-wal" in gitignore
    assert "*.db-shm" in gitignore
    assert "warden_audit.jsonl" in gitignore


def test_reverse_proxy_client_ips_are_trusted_for_rate_limits():
    entrypoint = (ROOT / "entrypoint.sh").read_text(encoding="utf-8")
    assert "--proxy-headers" in entrypoint
    assert '--forwarded-allow-ips="*"' in entrypoint


def test_entrypoint_reindexes_missing_or_empty_rag_store():
    entrypoint = (ROOT / "entrypoint.sh").read_text(encoding="utf-8")

    assert "get_document_count() > 0" in entrypoint
    assert "python ingest_guidelines.py" in entrypoint
    assert '[ ! -f "/app/vector_data/vectors.sqlite3" ]' not in entrypoint
