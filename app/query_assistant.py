# app/query_assistant.py
"""
Natural Language Query Assistant

Translates user questions into SQL queries using AWS Bedrock,
executes them safely, and formats responses in natural language.
"""

import json
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional

from .llm_client import call_llm_for_json, LLMError

DB_PATH = os.getenv("DATABASE_PATH", "agent.db")


# ---------------------------------------------------------------------------
# System Prompts
# ---------------------------------------------------------------------------

SQL_GENERATION_PROMPT = """
You are a healthcare data assistant. Given a user question about patient data,
generate a SQLite SELECT query to answer it.

DATABASE SCHEMA:
Table: hl7_messages
  - id (INTEGER PRIMARY KEY)
  - received_at (DATETIME) 
  - patient_id (VARCHAR)
  - patient_first_name (VARCHAR)
  - patient_last_name (VARCHAR)
  - patient_dob (VARCHAR)
  - patient_sex (VARCHAR)

Table: observations
  - id (INTEGER PRIMARY KEY)
  - message_id (INTEGER, FK to hl7_messages.id)
  - code (VARCHAR) - e.g., "2345-7" for glucose
  - display (VARCHAR) - e.g., "Glucose"
  - value_num (FLOAT) - numeric value
  - value_raw (VARCHAR) - text value if not numeric
  - unit (VARCHAR) - e.g., "mg/dL"
  - reference_low (VARCHAR)
  - reference_high (VARCHAR)
  - flag (VARCHAR) - 'H' for high, 'L' for low, 'N' for normal, '' for none
  - observation_datetime (VARCHAR)
  - status (VARCHAR)

RULES:
1. ONLY generate SELECT statements - never INSERT, UPDATE, DELETE, DROP, etc.
2. Use LOWER() with LIKE for case-insensitive name searches
3. For abnormal results, use: flag IN ('H', 'L')
4. JOIN observations to hl7_messages using: observations.message_id = hl7_messages.id
5. LIMIT results to 50 maximum
6. Use readable column aliases

RESPONSE FORMAT:
Return a JSON object with exactly this structure:
{
  "sql": "SELECT ... FROM ... WHERE ... LIMIT 50",
  "explanation": "Brief explanation of what this query does"
}

Output JSON ONLY, no markdown fences.
""".strip()


RESPONSE_FORMAT_PROMPT = """
You are a helpful healthcare data assistant. Given query results, provide a
natural, conversational response to the user's question.

RULES:
1. Be concise but informative
2. If results are empty, say so helpfully
3. Format numbers and dates readably
4. Highlight abnormal values (flag = 'H' or 'L')
5. Don't mention SQL or technical details

RESPONSE FORMAT:
Return a JSON object:
{
  "answer": "Your natural language response here",
  "highlights": ["Key point 1", "Key point 2"]
}

Output JSON ONLY.
""".strip()


# ---------------------------------------------------------------------------
# SQL Validation
# ---------------------------------------------------------------------------

FORBIDDEN_KEYWORDS = [
    'INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'CREATE', 
    'TRUNCATE', 'REPLACE', 'GRANT', 'REVOKE', 'EXEC', 'EXECUTE',
    'ATTACH', 'DETACH', 'PRAGMA', 'VACUUM'
]


def validate_sql(sql: str) -> tuple[bool, str]:
    """
    Validate that SQL is safe to execute.
    Returns (is_valid, error_message).
    """
    if not sql or not sql.strip():
        return False, "Empty query"
    
    normalized = sql.upper().strip()
    
    # Must start with SELECT
    if not normalized.startswith('SELECT'):
        return False, "Only SELECT queries are allowed"
    
    # Check for forbidden keywords
    for keyword in FORBIDDEN_KEYWORDS:
        # Use word boundary matching to avoid false positives
        if re.search(rf'\b{keyword}\b', normalized):
            return False, f"Forbidden keyword: {keyword}"
    
    # Check for multiple statements (;)
    # Allow ; only at the very end
    semicolon_count = sql.count(';')
    if semicolon_count > 1:
        return False, "Multiple statements not allowed"
    if semicolon_count == 1 and not sql.strip().endswith(';'):
        return False, "Semicolon only allowed at end of query"
    
    # Check for comments that might hide malicious code
    if '--' in sql or '/*' in sql:
        return False, "SQL comments not allowed"
    
    return True, ""


# ---------------------------------------------------------------------------
# Query Execution
# ---------------------------------------------------------------------------

def execute_safe_query(sql: str) -> tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Execute a validated SQL query in read-only mode.
    Returns (results, error_message).
    """
    is_valid, error = validate_sql(sql)
    if not is_valid:
        return [], error
    
    try:
        # Open connection in read-only mode where possible
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        
        cursor = conn.execute(sql)
        rows = cursor.fetchall()
        
        # Convert to list of dicts
        results = [dict(row) for row in rows]
        
        conn.close()
        return results, None
        
    except sqlite3.Error as e:
        return [], f"Database error: {str(e)}"
    except Exception as e:
        return [], f"Query execution error: {str(e)}"


# ---------------------------------------------------------------------------
# LLM Integration
# ---------------------------------------------------------------------------

def generate_sql_from_question(question: str) -> tuple[str, str, Optional[str]]:
    """
    Use LLM to generate SQL from natural language question.
    Returns (sql, explanation, error_message).
    """
    prompt = f"""
{SQL_GENERATION_PROMPT}

USER QUESTION: {question}

Generate the SQL query now. Output JSON only.
"""
    
    try:
        result = call_llm_for_json(prompt)
        sql = result.get("sql", "").strip()
        explanation = result.get("explanation", "")
        
        if not sql:
            return "", "", "LLM did not generate a SQL query"
        
        return sql, explanation, None
        
    except LLMError as e:
        return "", "", f"LLM error: {str(e)}"
    except Exception as e:
        return "", "", f"Unexpected error: {str(e)}"


def format_results_as_response(
    question: str, 
    results: List[Dict[str, Any]], 
    sql_used: str
) -> tuple[str, List[str], Optional[str]]:
    """
    Use LLM to format query results as natural language.
    Returns (answer, highlights, error_message).
    """
    # For empty results, don't need LLM
    if not results:
        return "I couldn't find any data matching your query.", [], None
    
    # Limit results shown to LLM to avoid token overload
    results_preview = results[:20]
    results_json = json.dumps(results_preview, default=str, indent=2)
    
    prompt = f"""
{RESPONSE_FORMAT_PROMPT}

USER QUESTION: {question}

QUERY RESULTS ({len(results)} rows, showing first {len(results_preview)}):
{results_json}

Format a helpful response. Output JSON only.
"""
    
    try:
        result = call_llm_for_json(prompt)
        answer = result.get("answer", "Here are the results I found.")
        highlights = result.get("highlights", [])
        
        return answer, highlights, None
        
    except LLMError as e:
        # Fallback: return basic response without LLM formatting
        return f"Found {len(results)} results.", [], None
    except Exception as e:
        return f"Found {len(results)} results.", [], None


# ---------------------------------------------------------------------------
# Main Query Function
# ---------------------------------------------------------------------------

def process_query(question: str) -> Dict[str, Any]:
    """
    Main entry point: process a natural language query.
    
    Returns:
        {
            "success": bool,
            "answer": str,
            "highlights": List[str],
            "sql_used": str,
            "row_count": int,
            "error": Optional[str]
        }
    """
    # Step 1: Generate SQL from question
    sql, explanation, error = generate_sql_from_question(question)
    if error:
        return {
            "success": False,
            "answer": "I couldn't understand that question. Try asking something like 'Show all patients' or 'What are John Smith's lab results?'",
            "highlights": [],
            "sql_used": "",
            "row_count": 0,
            "error": error
        }
    
    # Step 2: Validate SQL
    is_valid, validation_error = validate_sql(sql)
    if not is_valid:
        return {
            "success": False,
            "answer": "I generated an unsafe query. Please try rephrasing your question.",
            "highlights": [],
            "sql_used": sql,
            "row_count": 0,
            "error": validation_error
        }
    
    # Step 3: Execute query
    results, exec_error = execute_safe_query(sql)
    if exec_error:
        return {
            "success": False,
            "answer": "There was an error running the query. Please try again.",
            "highlights": [],
            "sql_used": sql,
            "row_count": 0,
            "error": exec_error
        }
    
    # Step 4: Format response
    answer, highlights, format_error = format_results_as_response(question, results, sql)
    
    return {
        "success": True,
        "answer": answer,
        "highlights": highlights if isinstance(highlights, list) else [],
        "sql_used": sql,
        "row_count": len(results),
        "error": None
    }
