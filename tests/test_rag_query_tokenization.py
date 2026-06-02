"""
Slice 3 -- RAG Query Tokenization Tests

Verifies that the Warden IN-GATE correctly tokenizes the user question before
it is passed to retrieve_context() / embed_text() / Bedrock Titan, ensuring
raw patient PHI is never sent to the embedding service.

Tests:
    1. test_rag_query_no_phi_to_bedrock
       Patient name in question must not reach retrieve_context() in any RAG call
       path: direct-answer, search_guidelines tool, query_database tool.
       Simulates the normal flow where the LLM returns the PHI token in its plan
       (because it only saw safe_question, never the real name).

    2. test_rag_context_deanonymized_before_return
       context_text returned by retrieve_context that contains PHI tokens must be
       deanonymized before it is included in the tool result / synthesis prompt.

    3. test_rag_retrieval_called_with_safe_query
       retrieve_context() must receive the tokenized query (not the raw patient
       name) when called from the agent dispatch loop, both for search_guidelines
       and query_database, as well as the direct-answer path.

Mocking strategy:
    - app.query_assistant.retrieve_context is patched to capture the exact string
      the agent passes to it (avoids needing a real vector store / Bedrock).
    - app.healthcare_agent.agent_planning is patched to return a plan whose query
      field already contains the PHI token (simulating the LLM output after the
      question was anonymized with safe_question before planning).
    - app.warden.WardenAnalyzer.build_token_map is patched to seed a known
      real_name <-> phi_token mapping so that:
        * warden_ctx.anonymize() replaces the real name with the token
        * warden_ctx.deanonymize() restores the token to the real name

Usage:
    python -m pytest tests/test_rag_query_tokenization.py -v
"""

import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

PATIENT_FIRST = "Reginald"
PATIENT_LAST = "Foxworth"
PATIENT_FULL = f"{PATIENT_FIRST} {PATIENT_LAST}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_phi_token():
    from app.warden import _new_phi_token
    return _new_phi_token("PAT")


def _seeding_build_token_map(real_name: str, phi_token: str):
    """Return a patched WardenAnalyzer.build_token_map that seeds a known mapping.

    The mapping is registered with output_authorized=True and the request_id
    is copied from the live grant so that deanonymize() can restore it.
    """
    from app.warden import PHITokenMap
    from app.security_validation import TokenRecord

    def _build(self_inner, grant=None):
        request_id = grant.request_id if grant else "req_test"
        tm = PHITokenMap(request_id=request_id)
        tm.add_mapping(real_name, phi_token, field_type="patient_name",
                       output_authorized=True)
        # Patch token record request_id to match the live grant so deanonymize works
        for token, record in list(tm._token_records.items()):
            tm._token_records[token] = TokenRecord(
                request_id=request_id,
                token=record.token,
                field_type=record.field_type,
                source=record.source,
                output_authorized=record.output_authorized,
            )
        return tm

    return _build


def _plan_with_token(tool_name: str, phi_token: str, base_query: str = "glucose guidelines"):
    """Return a plan dict where the query field contains the PHI token.

    This simulates the LLM planning output after the user question was
    anonymized with safe_question before _plan() was called.
    """
    return {
        "thought": f"Use {tool_name} to answer",
        "tool_calls": [
            {"tool": tool_name, "input": {"query": f"{base_query} for {phi_token}"}}
        ]
    }


def _plan_direct_with_token(answer: str = "Normal fasting glucose is 70-100 mg/dL."):
    return {"direct_answer": answer, "thought": "Direct knowledge answer"}


def _sql_guard_pass_result():
    """Return a SqlGuardResult that always passes SQL validation."""
    from app.sql_guard import SqlGuardResult
    return SqlGuardResult(allowed=True, sql="SELECT 1", reason="ok")


# ---------------------------------------------------------------------------
# Test 1: No raw PHI reaches retrieve_context() in any call path
# ---------------------------------------------------------------------------

class TestRagQueryNoPhiToBedrock:
    """Patient name in the user question must not reach retrieve_context() and
    therefore must not reach embed_text() / Bedrock Titan."""

    def test_direct_answer_path_no_phi_to_bedrock(self):
        """Direct-answer path: safe_question (tokenized) is passed to retrieve_context
        instead of the raw user question containing the patient name.

        Flow: user asks "What is Reginald Foxworth's glucose range?"
              -> Warden anonymizes to "What is <<PHI_PAT_...>>'s glucose range?"
              -> _plan receives safe_question
              -> plan.direct_answer triggers retrieve_context(safe_question)
              -> retrieve_context must NOT see "Reginald" or "Foxworth"
        """
        phi_token = _make_phi_token()
        retrieve_calls = []

        def capture_retrieve(question: str):
            retrieve_calls.append(question)
            return "", []

        plan = _plan_direct_with_token()

        from app.warden import WardenAnalyzer

        with patch("app.healthcare_agent.agent_planning", return_value=plan), \
             patch("app.query_assistant.retrieve_context", side_effect=capture_retrieve), \
             patch.object(WardenAnalyzer, "build_token_map",
                          _seeding_build_token_map(PATIENT_FULL, phi_token)):

            from app.healthcare_agent import HealthcareAgent
            agent = HealthcareAgent()
            agent.run(f"What is {PATIENT_FULL}'s glucose range?")

        assert len(retrieve_calls) >= 1, (
            "retrieve_context() was never called in the direct-answer path"
        )
        for query in retrieve_calls:
            assert PATIENT_FIRST not in query, (
                f"Patient first name '{PATIENT_FIRST}' sent to retrieve_context "
                f"in direct-answer path. Query was: {query!r}"
            )
            assert PATIENT_LAST not in query, (
                f"Patient last name '{PATIENT_LAST}' sent to retrieve_context "
                f"in direct-answer path. Query was: {query!r}"
            )

    def test_search_guidelines_tool_no_phi_to_bedrock(self):
        """search_guidelines tool: _safe_rag_query (the tokenized query from the plan,
        before deanonymization) is passed to retrieve_context instead of the
        deanonymized query.

        The plan is constructed with phi_token in the query field to simulate
        the LLM output after it saw safe_question.  The Warden deanonymizes
        tool_input to real_tool_input (real name for guideline matching context)
        but _safe_rag_query captures the pre-deanonymized token for RAG.
        """
        phi_token = _make_phi_token()
        retrieve_calls = []

        def capture_retrieve(question: str):
            retrieve_calls.append(question)
            return "", []

        plan = _plan_with_token("search_guidelines", phi_token)

        from app.warden import WardenAnalyzer

        with patch("app.healthcare_agent.agent_planning", return_value=plan), \
             patch("app.healthcare_agent.agent_synthesis",
                   return_value="ANSWER: test\nHIGHLIGHTS:\n- test"), \
             patch("app.query_assistant.retrieve_context", side_effect=capture_retrieve), \
             patch.object(WardenAnalyzer, "build_token_map",
                          _seeding_build_token_map(PATIENT_FULL, phi_token)):

            from app.healthcare_agent import HealthcareAgent
            agent = HealthcareAgent()
            agent.run(f"What are the glucose guidelines for {PATIENT_FULL}?")

        assert len(retrieve_calls) >= 1, (
            "retrieve_context() was never called in the search_guidelines tool path"
        )
        for query in retrieve_calls:
            assert PATIENT_FIRST not in query, (
                f"Patient first name '{PATIENT_FIRST}' sent to retrieve_context "
                f"in search_guidelines tool. Query was: {query!r}"
            )
            assert PATIENT_LAST not in query, (
                f"Patient last name '{PATIENT_LAST}' sent to retrieve_context "
                f"in search_guidelines tool. Query was: {query!r}"
            )

    def test_query_database_tool_no_phi_to_bedrock(self):
        """query_database tool: _safe_rag_query (tokenized) is passed to
        retrieve_context for source attribution, not the deanonymized DB query."""
        phi_token = _make_phi_token()
        retrieve_calls = []

        def capture_retrieve(question: str):
            retrieve_calls.append(question)
            return "", []

        plan = _plan_with_token("query_database", phi_token, base_query="glucose results")

        from app.warden import WardenAnalyzer

        with patch("app.healthcare_agent.agent_planning", return_value=plan), \
             patch("app.healthcare_agent.agent_synthesis",
                   return_value="ANSWER: test\nHIGHLIGHTS:\n- test"), \
             patch("app.query_assistant.generate_sql_from_question",
                   return_value=("SELECT 1", "test", None)), \
             patch("app.sql_guard.validate_sql_select", return_value=_sql_guard_pass_result()), \
             patch("app.query_assistant.execute_safe_query", return_value=([], None)), \
             patch("app.query_assistant.retrieve_context", side_effect=capture_retrieve), \
             patch.object(WardenAnalyzer, "build_token_map",
                          _seeding_build_token_map(PATIENT_FULL, phi_token)):

            from app.healthcare_agent import HealthcareAgent
            agent = HealthcareAgent()
            agent.run(f"Show {PATIENT_FULL}'s glucose results")

        for query in retrieve_calls:
            assert PATIENT_FIRST not in query, (
                f"Patient first name '{PATIENT_FIRST}' sent to retrieve_context "
                f"in query_database RAG call. Query was: {query!r}"
            )
            assert PATIENT_LAST not in query, (
                f"Patient last name '{PATIENT_LAST}' sent to retrieve_context "
                f"in query_database RAG call. Query was: {query!r}"
            )


# ---------------------------------------------------------------------------
# Test 2: RAG context with PHI tokens is deanonymized before reaching synthesis
# ---------------------------------------------------------------------------

class TestRagContextDeanonymizedBeforeReturn:
    """context_text containing PHI tokens must be deanonymized before it reaches
    agent_synthesis (and therefore the final answer)."""

    def test_search_guidelines_context_deanonymized(self):
        """If retrieve_context returns context_text containing a PHI token,
        that token must be deanonymized in the tool result before reaching the
        dispatch loop's anonymize_json step (which re-tokenizes for synthesis).

        The architecture is:
          retrieve_context() returns context with token
          -> _tool_search_guidelines deanonymizes it (OUT-GATE in tool)
          -> dispatch loop re-tokenizes with anonymize_json before synthesis
          -> agent_synthesis sees tokenized context (correct; LLM only sees tokens)
          -> OUT-GATE: warden_ctx.deanonymize(answer) restores tokens in final answer

        This test verifies: the _tool_search_guidelines return dict has the
        deanonymized context (not the raw token), and the final answer does not
        contain the raw token after the OUT-GATE.
        """
        phi_token = _make_phi_token()
        real_name = PATIENT_FULL
        context_with_token = (
            f"Guideline note for {phi_token}: "
            f"fasting glucose target is below 100 mg/dL."
        )

        plan = {
            "thought": "Search guidelines",
            "tool_calls": [
                {"tool": "search_guidelines", "input": {"query": f"glucose for {phi_token}"}}
            ]
        }

        def fake_retrieve(question: str):
            return context_with_token, []

        from app.warden import WardenAnalyzer

        # Capture the raw tool result dict before the dispatch loop re-tokenizes it
        tool_results_before_retokenize = []
        from app.healthcare_agent import HealthcareAgent as _HA

        orig_run_standard = _HA._run_standard

        def patched_run_standard(self_inner, question, history=None, grant=None):
            orig_tool = self_inner._tool_search_guidelines

            def capturing_tool(input_data):
                result = orig_tool(input_data)
                tool_results_before_retokenize.append(result)
                return result

            self_inner._tool_search_guidelines = capturing_tool
            self_inner._tools["search_guidelines"] = capturing_tool
            return orig_run_standard(self_inner, question, history, grant)

        with patch("app.healthcare_agent.agent_planning", return_value=plan), \
             patch("app.healthcare_agent.agent_synthesis",
                   return_value="ANSWER: Fasting glucose below 100.\nHIGHLIGHTS:\n- test"), \
             patch("app.query_assistant.retrieve_context", side_effect=fake_retrieve), \
             patch.object(WardenAnalyzer, "build_token_map",
                          _seeding_build_token_map(real_name, phi_token)), \
             patch.object(_HA, "_run_standard", patched_run_standard):

            agent = _HA()
            resp = agent.run("What are the glucose guidelines?")

        # 1. Tool result should have deanonymized context (real name or TOKEN_REDACTION,
        #    but NOT the raw <<PHI_...>> token).
        assert len(tool_results_before_retokenize) >= 1, (
            "_tool_search_guidelines was never called"
        )
        for tool_result in tool_results_before_retokenize:
            context_in_result = tool_result.get("context", "")
            assert phi_token not in context_in_result, (
                f"Raw PHI token found in _tool_search_guidelines result dict: "
                f"{context_in_result!r}. The OUT-GATE deanonymize call in the tool "
                f"did not replace the token."
            )

        # 2. Final answer must not contain the raw token (OUT-GATE on the answer).
        assert phi_token not in resp.answer, (
            f"Raw PHI token appeared in the final answer."
        )

    def test_query_database_context_deanonymized(self):
        """query_database tool: context_text returned by retrieve_context is
        deanonymized in the tool function before inclusion in the result dict.

        This test directly instantiates _tool_query_database with a controlled
        input_data dict (including _warden_ctx and _safe_rag_query) to verify
        the deanonymization path without running the full agent dispatch loop.
        """
        from app.warden import _new_phi_token, PHITokenMap, Warden, WardenAnalyzer
        from app.security_validation import TokenRecord
        from app.grant_builder import build_query_grant
        from app.healthcare_agent import HealthcareAgent

        phi_token = _make_phi_token()
        real_name = PATIENT_FULL
        context_with_token = (
            f"Reference guideline for {phi_token}: target glucose < 100 mg/dL."
        )

        def fake_retrieve(question: str):
            return context_with_token, []

        # Build a real grant and Warden context for the unit test
        grant = build_query_grant(
            session_id="test_session",
            intent="clinical_query",
            scope="demo",
            requested_tools=["query_database"],
            max_rows=50,
        )

        def seeding_build(self_inner, grant_=None):
            request_id = (grant_ or grant).request_id
            tm = PHITokenMap(request_id=request_id)
            tm.add_mapping(real_name, phi_token, field_type="patient_name",
                           output_authorized=True)
            for token, record in list(tm._token_records.items()):
                tm._token_records[token] = TokenRecord(
                    request_id=request_id,
                    token=record.token,
                    field_type=record.field_type,
                    source=record.source,
                    output_authorized=record.output_authorized,
                )
            return tm

        with patch.object(WardenAnalyzer, "build_token_map", seeding_build):
            warden = Warden()
            with warden.request_scope(grant=grant) as warden_ctx:
                # Build input_data the same way the dispatch loop does
                input_data = {
                    "query": f"glucose for {phi_token}",       # deanonymized (real name would be here)
                    "_safe_rag_query": f"glucose for {phi_token}",  # tokenized (stays tokenized)
                    "_warden_ctx": warden_ctx,
                }

                agent = HealthcareAgent()

                with patch("app.query_assistant.retrieve_context",
                           side_effect=fake_retrieve), \
                     patch("app.query_assistant.generate_sql_from_question",
                           return_value=("SELECT 1", "test", None)), \
                     patch("app.sql_guard.validate_sql_select",
                           return_value=_sql_guard_pass_result()), \
                     patch("app.query_assistant.execute_safe_query",
                           return_value=([], None)):

                    result = agent._tool_query_database(input_data, [], grant)

        context_in_result = result.get("context", "")
        assert phi_token not in context_in_result, (
            f"Raw PHI token found in _tool_query_database result dict: "
            f"{context_in_result!r}. The warden_ctx.deanonymize() call in the "
            f"tool function did not replace the token."
        )


# ---------------------------------------------------------------------------
# Test 3: retrieve_context() is called with the safe (tokenized) query string
# ---------------------------------------------------------------------------

class TestRagRetrievalCalledWithSafeQuery:
    """retrieve_context() must receive the tokenized query (the PHI token,
    not the real patient name) when called from the agent dispatch loop."""

    def test_search_guidelines_retrieve_context_called_with_token(self):
        """_safe_rag_query mechanism threads the pre-deanonymization query into
        _tool_search_guidelines so retrieve_context sees the token."""
        phi_token = _make_phi_token()
        real_name = PATIENT_FULL

        retrieve_calls = []

        def capture_retrieve(question: str):
            retrieve_calls.append(question)
            return "", []

        # Plan query contains the PHI token (LLM output after seeing safe_question)
        plan = {
            "thought": "Search guidelines",
            "tool_calls": [
                {
                    "tool": "search_guidelines",
                    "input": {"query": f"glucose guidelines for {phi_token}"}
                }
            ]
        }

        from app.warden import WardenAnalyzer

        with patch("app.healthcare_agent.agent_planning", return_value=plan), \
             patch("app.healthcare_agent.agent_synthesis",
                   return_value="ANSWER: test\nHIGHLIGHTS:\n- test"), \
             patch("app.query_assistant.retrieve_context", side_effect=capture_retrieve), \
             patch.object(WardenAnalyzer, "build_token_map",
                          _seeding_build_token_map(real_name, phi_token)):

            from app.healthcare_agent import HealthcareAgent
            agent = HealthcareAgent()
            agent.run(f"What are the glucose guidelines for {real_name}?")

        assert len(retrieve_calls) >= 1, (
            "retrieve_context() was never called -- check search_guidelines tool path"
        )
        for query in retrieve_calls:
            assert PATIENT_FIRST not in query, (
                f"Patient first name '{PATIENT_FIRST}' found in retrieve_context query: "
                f"{query!r}. The _safe_rag_query threading was not applied."
            )
            assert PATIENT_LAST not in query, (
                f"Patient last name '{PATIENT_LAST}' found in retrieve_context query: "
                f"{query!r}. The _safe_rag_query threading was not applied."
            )
            # The token should appear in the safe query (it was in plan input, not deanonymized)
            assert phi_token in query, (
                f"Expected PHI token '{phi_token}' in retrieve_context query but got: "
                f"{query!r}. The _safe_rag_query was not threaded from plan input."
            )

    def test_query_database_retrieve_context_called_with_token(self):
        """query_database tool: _safe_rag_query threading preserves the tokenized
        query for retrieve_context even though the rest of the DB query path uses
        the deanonymized real name (in real_tool_input["query"])."""
        phi_token = _make_phi_token()
        real_name = PATIENT_FULL

        retrieve_calls = []

        def capture_retrieve(question: str):
            retrieve_calls.append(question)
            return "", []

        plan = {
            "thought": "Query database",
            "tool_calls": [
                {
                    "tool": "query_database",
                    "input": {"query": f"glucose results for {phi_token}"}
                }
            ]
        }

        from app.warden import WardenAnalyzer

        with patch("app.healthcare_agent.agent_planning", return_value=plan), \
             patch("app.healthcare_agent.agent_synthesis",
                   return_value="ANSWER: test\nHIGHLIGHTS:\n- test"), \
             patch("app.query_assistant.generate_sql_from_question",
                   return_value=("SELECT 1", "test", None)), \
             patch("app.sql_guard.validate_sql_select", return_value=_sql_guard_pass_result()), \
             patch("app.query_assistant.execute_safe_query", return_value=([], None)), \
             patch("app.query_assistant.retrieve_context", side_effect=capture_retrieve), \
             patch.object(WardenAnalyzer, "build_token_map",
                          _seeding_build_token_map(real_name, phi_token)):

            from app.healthcare_agent import HealthcareAgent
            agent = HealthcareAgent()
            agent.run(f"Show {real_name}'s glucose results")

        for query in retrieve_calls:
            assert PATIENT_FIRST not in query, (
                f"Patient first name '{PATIENT_FIRST}' in retrieve_context query: "
                f"{query!r}. _safe_rag_query threading for query_database is broken."
            )
            assert PATIENT_LAST not in query, (
                f"Patient last name '{PATIENT_LAST}' in retrieve_context query: "
                f"{query!r}. _safe_rag_query threading for query_database is broken."
            )
            assert phi_token in query, (
                f"Expected PHI token in retrieve_context query but got: {query!r}. "
                f"Tokenization was not preserved for query_database RAG query."
            )

    def test_direct_answer_path_retrieve_context_called_with_safe_question(self):
        """Direct-answer path: safe_question (the tokenized top-level user question)
        is passed to retrieve_context, not the raw question string."""
        phi_token = _make_phi_token()
        real_name = PATIENT_FULL

        retrieve_calls = []

        def capture_retrieve(question: str):
            retrieve_calls.append(question)
            return "", []

        plan = _plan_direct_with_token()

        from app.warden import WardenAnalyzer

        with patch("app.healthcare_agent.agent_planning", return_value=plan), \
             patch("app.query_assistant.retrieve_context", side_effect=capture_retrieve), \
             patch.object(WardenAnalyzer, "build_token_map",
                          _seeding_build_token_map(real_name, phi_token)):

            from app.healthcare_agent import HealthcareAgent
            agent = HealthcareAgent()
            agent.run(f"What is the normal glucose range for {real_name}?")

        assert len(retrieve_calls) >= 1, (
            "retrieve_context() was never called in the direct-answer path"
        )
        for query in retrieve_calls:
            assert PATIENT_FIRST not in query, (
                f"Patient first name '{PATIENT_FIRST}' in retrieve_context "
                f"direct-answer path: {query!r}"
            )
            assert PATIENT_LAST not in query, (
                f"Patient last name '{PATIENT_LAST}' in retrieve_context "
                f"direct-answer path: {query!r}"
            )
            # safe_question contains the PHI token (real name was replaced by Warden)
            assert phi_token in query, (
                f"Expected PHI token in retrieve_context query but got: {query!r}. "
                f"safe_question was not used in the direct-answer path."
            )


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import traceback

    test_classes = [
        ("Test 1: No raw PHI to Bedrock (3 paths)", TestRagQueryNoPhiToBedrock),
        ("Test 2: RAG context deanonymized before return", TestRagContextDeanonymizedBeforeReturn),
        ("Test 3: retrieve_context called with safe query", TestRagRetrievalCalledWithSafeQuery),
    ]

    total = 0
    passed = 0
    failed = 0

    print("=" * 70)
    print("  Slice 3 -- RAG Query Tokenization Tests")
    print("=" * 70)
    print()

    for section_name, cls in test_classes:
        print(f"--- {section_name} ---")
        instance = cls()
        methods = sorted(m for m in dir(instance) if m.startswith("test_"))
        for method_name in methods:
            total += 1
            test_fn = getattr(instance, method_name)
            try:
                test_fn()
                passed += 1
                print(f"  [PASS] {method_name}")
            except AssertionError as e:
                failed += 1
                print(f"  [FAIL] {method_name}: {e}")
            except Exception as e:
                failed += 1
                print(f"  [ERROR] {method_name}:\n{traceback.format_exc()}")
        print()

    print("=" * 70)
    print(f"  Results: {passed}/{total} passed, {failed} failed")
    print("=" * 70)
