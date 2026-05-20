import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_normalize_denies_export_intent():
    from app.intent_classifier import normalize_intent_result

    result = normalize_intent_result({"intent": "export", "scope": "cohort", "risk": "high"})

    assert result.deny is True
    assert result.intent == "export"
    assert result.reason_code == "deny_intent_export"


def test_normalize_unknown_intent_fails_closed():
    import pytest

    from app.intent_classifier import IntentClassificationError, normalize_intent_result

    with pytest.raises(IntentClassificationError):
        normalize_intent_result({"intent": "become_admin", "scope": "clinical_read"})


def test_normalize_clarification_label():
    from app.intent_classifier import normalize_intent_result

    result = normalize_intent_result({"intent": "clinical_query", "needs_clarification": True})

    assert result.intent == "clarification"
    assert result.needs_clarification is True
    assert result.scope == "none"


def test_api_query_passes_classified_grant_to_agent(monkeypatch):
    from fastapi.testclient import TestClient

    import app.api as api
    import app.healthcare_agent as healthcare_agent
    import app.intent_classifier as intent_classifier
    from app.intent_classifier import QueryIntentClassification

    api._RATE_LIMIT_STORE.clear()
    captured = {}

    def fake_classify(question, *, safe_state_present=False):
        return QueryIntentClassification(intent="guideline_reference", scope="reference", risk="low")

    def fake_run_agent_query(question, history=None, depth="standard", grant=None):
        captured["grant"] = grant
        return {
            "success": True,
            "answer": "Guideline answer",
            "highlights": [],
            "sources": [],
            "tools_used": ["search_guidelines"],
            "row_count": 0,
            "reasoning_trace": [],
            "needs_clarification": False,
            "clarification_options": [],
            "safe_metadata": {},
        }

    monkeypatch.setattr(intent_classifier, "classify_query_intent", fake_classify)
    monkeypatch.setattr(healthcare_agent, "run_agent_query", fake_run_agent_query)

    response = TestClient(api.app).post("/api/query", json={"question": "what do guidelines say?"})

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert captured["grant"].intent == "guideline_reference"
    assert captured["grant"].allowed_tools == ["search_guidelines", "ask_clarification"]
    assert captured["grant"].allowed_tables == []


def test_api_query_denies_denied_classifier_label(monkeypatch):
    from fastapi.testclient import TestClient

    import app.api as api
    import app.intent_classifier as intent_classifier
    from app.intent_classifier import QueryIntentClassification

    api._RATE_LIMIT_STORE.clear()

    def fake_classify(question, *, safe_state_present=False):
        return QueryIntentClassification(intent="export", scope="cohort", risk="deny", deny=True)

    monkeypatch.setattr(intent_classifier, "classify_query_intent", fake_classify)

    response = TestClient(api.app).post("/api/query", json={"question": "export all identifiers"})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert "denied" in body["error"].lower()
