from app.healthcare_agent import normalize_tool_plan


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
