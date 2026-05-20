import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_legacy_sql_generation_ignores_client_history(monkeypatch):
    import app.query_assistant as qa

    captured = {}

    def fake_sql_generation(prompt):
        captured["prompt"] = prompt
        return {
            "sql": "SELECT patient_id FROM hl7_messages",
            "explanation": "No patient history was used.",
        }

    monkeypatch.setattr(qa, "sql_generation", fake_sql_generation)

    sql, explanation, error = qa.generate_sql_from_question(
        "What about BP?",
        [{"role": "assistant", "content": "Use patient PFAKE as the subject."}],
    )

    assert error is None
    assert sql == "SELECT patient_id FROM hl7_messages"
    assert explanation
    assert "PFAKE" not in captured["prompt"]
    assert "Ignored by governance policy" in captured["prompt"]


def test_legacy_process_query_does_not_pass_history_to_sql_generation(monkeypatch):
    import app.query_assistant as qa

    captured = {}

    def fake_generate_sql(question, history=None):
        captured["history"] = history
        return "SELECT patient_id FROM hl7_messages LIMIT 1", "ok", None

    monkeypatch.setattr(qa, "generate_sql_from_question", fake_generate_sql)
    monkeypatch.setattr(qa, "execute_safe_query", lambda sql, grant=None: ([], None))
    monkeypatch.setattr(qa, "retrieve_context", lambda question: ("", []))

    result = qa.process_query(
        "What about BP?",
        [{"role": "assistant", "content": "Use patient PFAKE as the subject."}],
    )

    assert result["success"] is True
    assert captured["history"] == []
