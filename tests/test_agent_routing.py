from app import healthcare_agent
from app.healthcare_agent import (
    AgentResponse,
    HealthcareAgent,
    ToolResult,
    normalize_tool_plan,
)


def test_cohort_query_cannot_use_single_patient_context_tool():
    plan = {
        "thought": "Inspect all synthetic patients.",
        "tool_calls": [
            {
                "tool": "get_patient_context",
                "input": {"patient_id": "all_synthetic_patients"},
            }
        ],
    }

    normalized = normalize_tool_plan(
        "Which synthetic patients have critical findings?",
        plan,
    )

    assert normalized["tool_calls"] == [
        {
            "tool": "query_database",
            "input": {
                "query": "Which synthetic patients have critical findings?",
            },
        }
    ]


def test_named_patient_query_keeps_patient_context_tool():
    plan = {
        "thought": "Inspect one patient.",
        "tool_calls": [
            {
                "tool": "get_patient_context",
                "input": {"patient_name": "John Smith"},
            }
        ],
    }

    assert normalize_tool_plan("Show me John Smith's history", plan) == plan


def test_deep_strategy_prefix_is_not_forwarded_to_database_query():
    plan = {
        "thought": "Inspect the cohort.",
        "tool_calls": [
            {
                "tool": "get_patient_context",
                "input": {"patient_id": "all_patients"},
            }
        ],
    }

    normalized = normalize_tool_plan(
        "[STRATEGY: inspect all alerts] Which patients have abnormal findings?",
        plan,
    )

    assert normalized["tool_calls"][0]["input"]["query"] == (
        "Which patients have abnormal findings?"
    )


def test_oldest_patient_is_treated_as_population_query():
    plan = {
        "thought": "Mistakenly inspect one patient.",
        "tool_calls": [
            {
                "tool": "get_patient_context",
                "input": {"patient_id": "P12345"},
            }
        ],
    }

    normalized = normalize_tool_plan("Who is the oldest patient?", plan)

    assert normalized["tool_calls"] == [
        {
            "tool": "query_database",
            "input": {"query": "Who is the oldest patient?"},
        }
    ]


def test_superlative_database_query_preserves_original_question():
    plan = {
        "thought": "Inspect systolic BP values.",
        "tool_calls": [
            {
                "tool": "query_database",
                "input": {"query": "show patients with systolic BP"},
            }
        ],
    }

    normalized = normalize_tool_plan("Who has the minimum systolic BP?", plan)

    assert normalized["tool_calls"] == [
        {
            "tool": "query_database",
            "input": {"query": "Who has the minimum systolic BP?"},
        }
    ]


def test_deep_mode_preserves_original_question_as_standard_input(monkeypatch):
    captured = {}
    agent = HealthcareAgent.__new__(HealthcareAgent)

    monkeypatch.setattr(
        healthcare_agent,
        "call_llm_for_json",
        lambda _prompt: {
            "analysis": "Simple aggregate query.",
            "strategy": "Query patient demographics by date of birth.",
            "modifications": "",
        },
    )

    def fake_run_standard(self, question, history=None, strategy_context=""):
        captured["question"] = question
        captured["history"] = history
        captured["strategy_context"] = strategy_context
        return AgentResponse(answer="ok", success=True)

    monkeypatch.setattr(HealthcareAgent, "_run_standard", fake_run_standard)

    agent._run_deep("Who is the oldest patient?", [])

    assert captured == {
        "question": "Who is the oldest patient?",
        "history": [],
        "strategy_context": "Query patient demographics by date of birth.",
    }


def test_plan_receives_strategy_as_context_not_question(monkeypatch):
    captured = {}
    agent = HealthcareAgent.__new__(HealthcareAgent)

    def fake_call_llm_for_json(prompt):
        captured["prompt"] = prompt
        return {"thought": "Plan", "tool_calls": []}

    monkeypatch.setattr(healthcare_agent, "call_llm_for_json", fake_call_llm_for_json)

    agent._plan(
        "Who has the highest glucose?",
        [],
        "Review units before answering.",
    )

    prompt = captured["prompt"]
    assert "CURRENT USER QUESTION: Who has the highest glucose?" in prompt
    assert "DEEP STRATEGY CONTEXT:" in prompt
    assert "Review units before answering." in prompt
    assert 'query_database("Who has the highest glucose?")' in prompt
    assert "use exactly one" in prompt
    assert "Do not add" in prompt
    assert "clinical_calculator" in prompt
    assert "[STRATEGY:" not in prompt


def test_worried_patient_results_are_grouped_without_llm_drift(monkeypatch):
    agent = HealthcareAgent.__new__(HealthcareAgent)
    tool_results = [
        ToolResult(
            tool="query_database",
            success=True,
            result={
                "row_count": 3,
                "results": [
                    {
                        "patient_first_name": "Harold",
                        "patient_last_name": "Bennett",
                        "display": "SpO2",
                        "value_num": 88,
                        "unit": "%",
                        "flag": "L",
                        "alert_level": "CRITICAL",
                    },
                    {
                        "patient_first_name": "Hannah",
                        "patient_last_name": "Ortiz",
                        "display": "Glucose",
                        "value_num": 55,
                        "unit": "mg/dL",
                        "flag": "L",
                        "alert_level": "WARNING",
                    },
                    {
                        "patient_first_name": "Harold",
                        "patient_last_name": "Bennett",
                        "display": "Heart Rate",
                        "value_num": 135,
                        "unit": "bpm",
                        "flag": "H",
                        "alert_level": "CRITICAL",
                    },
                ],
            },
        )
    ]

    monkeypatch.setattr(
        healthcare_agent,
        "call_llm",
        lambda _prompt: (_ for _ in ()).throw(
            AssertionError("LLM synthesis should not run")
        ),
    )

    answer, highlights = agent._synthesize(
        "Which patients should I be worried about?",
        tool_results,
    )

    assert "Found 2 patients with 3 concerning finding(s)" in answer
    assert answer.count("| **Harold Bennett** |") == 1
    assert "SpO2 88 % (flag L); Heart Rate 135 bpm (flag H)" in answer
    assert "| **Hannah Ortiz** | [WARNING] | Glucose 55 mg/dL (flag L) |" in answer
    assert highlights == []


def test_oldest_patient_answer_is_rendered_without_llm_drift(monkeypatch):
    agent = HealthcareAgent.__new__(HealthcareAgent)
    tool_results = [
        ToolResult(
            tool="query_database",
            success=True,
            result={
                "row_count": 1,
                "results": [
                    {
                        "patient_id": "P-OLDEST",
                        "patient_first_name": "Elizabeth",
                        "patient_last_name": "SearchTest",
                        "patient_dob": "1946-08-01",
                        "age": 79,
                    }
                ],
            },
        )
    ]
    monkeypatch.setattr(
        healthcare_agent,
        "call_llm",
        lambda _prompt: (_ for _ in ()).throw(
            AssertionError("LLM synthesis should not run")
        ),
    )

    answer, highlights = agent._synthesize(
        "Who is the oldest patient?",
        tool_results,
    )

    assert "The oldest patient is **Elizabeth SearchTest**, age **79**." in answer
    assert "| **Elizabeth SearchTest** | -- | Age: **79**; DOB: 1946-08-01 |" in answer
    assert highlights == []


def test_specific_single_measurement_query_still_uses_llm_synthesis(monkeypatch):
    agent = HealthcareAgent.__new__(HealthcareAgent)
    tool_results = [
        ToolResult(
            tool="query_database",
            success=True,
            result={
                "row_count": 1,
                "results": [
                    {
                        "patient_first_name": "Thomas",
                        "patient_last_name": "Grant",
                        "display": "Heart Rate",
                        "value_num": 115,
                        "unit": "bpm",
                    }
                ],
            },
        )
    ]
    monkeypatch.setattr(
        healthcare_agent,
        "call_llm",
        lambda _prompt: (
            "ANSWER:\n| Patient | Status | Findings |\n"
            "| :--- | :--- | :--- |\n"
            "| **Thomas Grant** | [WARNING] | Heart Rate 115 bpm |\n\n"
            "HIGHLIGHTS:\n- Highest heart rate"
        ),
    )

    answer, highlights = agent._synthesize(
        "Who has the highest heart rate?",
        tool_results,
    )

    assert "Thomas Grant" in answer
    assert highlights == ["Highest heart rate"]
