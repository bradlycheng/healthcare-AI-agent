import pytest
from unittest.mock import MagicMock, patch
import sys
import os

# Add app to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.document_loader import extract_title, chunk_text, load_document
from app.query_assistant import create_clean_snippet, format_results_as_response

# ---------------------------------------------------------------------------
# Unit Tests: Document Processing
# ---------------------------------------------------------------------------

def test_title_extraction():
    """Test extracting friendly titles from markdown headers."""
    # Case 1: Standard Header
    text = "# Medical Reference: Blood Glucose Guidelines\nSome content..."
    assert extract_title(text, "file.txt") == "Blood Glucose Guidelines"
    
    # Case 2: Simple Header
    text = "# Hypertension Guide\nSome content..."
    assert extract_title(text, "file.txt") == "Hypertension Guide"
    
    # Case 3: Fallback to filename
    text = "Just some text without a header."
    assert extract_title(text, "guidelines_v2.txt") == "Guidelines V2"

def test_chunking_logic():
    """Test that text chunking respects boundaries."""
    text = "Sentence one. Sentence two. Sentence three."
    # Force small chunks to test splitting
    chunks = chunk_text(text, chunk_size=20, overlap=5)
    
    assert len(chunks) > 0
    # Ideally should try to keep sentences together or overlap correctly
    assert "Sentence one" in chunks[0]

def test_clean_snippet():
    """Test that snippets don't cut words in half."""
    text = "This is a long sentence that should be truncated gracefully."
    
    # Truncate at 20 chars
    # "This is a long sente..." -> "This is a long..."
    snippet = create_clean_snippet(text, max_length=20)
    
    assert not snippet.endswith("sente...")
    assert snippet.endswith("...")
    assert len(snippet) <= 23  # 20 + "..."

# ---------------------------------------------------------------------------
# Integration Tests: RAG Logic (Mocked)
# ---------------------------------------------------------------------------

@patch('app.query_assistant.call_llm_for_json')
def test_rag_context_injection(mock_llm):
    """Verify that RAG context is actually passed to the LLM."""
    
    # Mock LLM response
    mock_llm.return_value = {
        "answer": "RAG answer",
        "highlights": []
    }
    
    question = "Is high glucose bad?"
    results = [] # No DB results
    context = "High glucose is dangerous."
    
    # Call the function
    format_results_as_response(question, results, "SELECT * FROM dummy", context)
    
    # Capture the prompt sent to the LLM
    args, _ = mock_llm.call_args
    prompt_sent = args[0]
    
    # ASSERT: The prompt MUST contain the medical context
    assert "MEDICAL REFERENCE CONTEXT:" in prompt_sent
    assert "High glucose is dangerous" in prompt_sent
    assert "If no patient data was found" in prompt_sent

# ---------------------------------------------------------------------------
# Manual Verification Script (for print debugging)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Running manual tests...")
    test_title_extraction()
    test_clean_snippet()
    print("ALL TESTS PASSED")
