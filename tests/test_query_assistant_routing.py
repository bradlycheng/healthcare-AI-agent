from app import query_assistant


def test_critical_cohort_query_uses_stable_sql_without_llm(monkeypatch):
    monkeypatch.setattr(
        query_assistant,
        "call_llm_for_json",
        lambda _prompt: (_ for _ in ()).throw(AssertionError("LLM should not run")),
    )

    sql, explanation, error = query_assistant.generate_sql_from_question(
        "Which synthetic patients have critical findings?"
    )

    assert error is None
    assert "o.alert_level = 'CRITICAL'" in sql
    assert "JOIN observations o ON o.message_id = h.id" in sql
    assert explanation == "Retrieved all critical patient findings."


def test_worried_cohort_query_includes_warning_and_critical_findings():
    sql, _, error = query_assistant.generate_sql_from_question(
        "Which patients should I be worried about?"
    )

    assert error is None
    assert "o.flag IN ('H', 'HH', 'L', 'LL')" in sql
    assert "o.alert_level IN ('CRITICAL', 'WARNING')" in sql
    assert "WHEN o.alert_level = 'CRITICAL' THEN 1" in sql


def test_no_abnormal_query_still_uses_llm(monkeypatch):
    monkeypatch.setattr(
        query_assistant,
        "call_llm_for_json",
        lambda _prompt: {
            "sql": "SELECT patient_id FROM hl7_messages LIMIT 50",
            "explanation": "Patients without abnormal findings.",
        },
    )

    sql, _, error = query_assistant.generate_sql_from_question(
        "Which patients have no abnormal observations?"
    )

    assert error is None
    assert sql == "SELECT patient_id FROM hl7_messages LIMIT 50"


def test_measurement_specific_critical_query_still_uses_llm(monkeypatch):
    monkeypatch.setattr(
        query_assistant,
        "call_llm_for_json",
        lambda _prompt: {
            "sql": "SELECT display FROM observations WHERE display = 'Glucose'",
            "explanation": "Critical glucose findings.",
        },
    )

    sql, _, error = query_assistant.generate_sql_from_question(
        "Show critical glucose results"
    )

    assert error is None
    assert sql == "SELECT display FROM observations WHERE display = 'Glucose'"
