# app/query_assistant.py
"""
Natural Language Query Assistant

Translates user questions into SQL queries using AWS Bedrock,
executes them safely, and formats responses in natural language.
Supports RAG (Retrieval-Augmented Generation) with medical guidelines.
"""

import json
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional

from .llm_client import call_llm_for_json, LLMError
from .security import sanitize_text

DB_PATH = os.getenv("DATABASE_PATH", "agent.db")

# RAG settings
RAG_ENABLED = os.getenv("RAG_ENABLED", "true").lower() == "true"


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
  - patient_first_name (VARCHAR) -- Stored in UPPERCASE
  - patient_last_name (VARCHAR)  -- Stored in UPPERCASE
  - patient_dob (VARCHAR) -- Stored as 'YYYYMMDD' string (e.g. '19800515')
  - patient_sex (VARCHAR) -- 'M' or 'F'

Table: observations
  - id (INTEGER PRIMARY KEY)
  - message_id (INTEGER, FK to hl7_messages.id)
  - code (VARCHAR) -- e.g., "2345-7" for glucose
  - display (VARCHAR) -- e.g., "Glucose", "HEART_RATE", "SYSTOLIC_BP" (may use underscores instead of spaces)
  - value_num (FLOAT) -- numeric value
  - value_raw (VARCHAR) -- text value
  - unit (VARCHAR) -- e.g., "mg/dL"
  - reference_low (VARCHAR)
  - reference_high (VARCHAR)
  - flag (VARCHAR) -- 'H' (High), 'L' (Low), 'N' (Normal), or empty
  - observation_datetime (VARCHAR)
  - alert_level (VARCHAR) -- 'CRITICAL', 'WARNING', or empty
  - alert_message (VARCHAR) -- Clinical explanation of the alert
  - loinc_code (VARCHAR) -- Standard LOINC code (e.g. "8867-4")

Table: visits
  - visit_id (VARCHAR PRIMARY KEY)
  - patient_id (VARCHAR)
  - visit_date (DATETIME)
  - visit_type (VARCHAR) -- 'Outpatient', 'Emergency', etc.
  - provider_name (VARCHAR)
  - chief_complaint (VARCHAR)

Table: medications
  - id (INTEGER PRIMARY KEY)
  - patient_id (VARCHAR)
  - medication_name (VARCHAR)
  - dosage (VARCHAR)
  - frequency (VARCHAR)
  - start_date (DATE)
  - end_date (DATE)
  - status (VARCHAR) -- 'Active', 'Discontinued'

Table: diagnoses
  - id (INTEGER PRIMARY KEY)
  - patient_id (VARCHAR)
  - diagnosis_code (VARCHAR) -- ICD-10 code
  - diagnosis_name (VARCHAR)
  - diagnosis_date (DATE)
  - status (VARCHAR) -- 'Active', 'Resolved'

RULES:
1. ONLY generate SELECT statements.
2. **CRITICAL**: All names in DB are UPPERCASE. Use `UPPER(col) = 'NAME'` or `UPPER(col) LIKE '%NAME%'`.
3. For "abnormal" or "high/low" results, check `flag IN ('H', 'L')` or `flag = 'H'`.
4. **NEVER** filter by `patient_sex` unless the user explicitly uses words like "male", "female", "men", "women".
5. JOIN `observations` on `observations.message_id = hl7_messages.id`.
6. For "recent" items, use `ORDER BY received_at DESC` or `ORDER BY observation_datetime DESC`.
7. LIMIT results to 50.
8. **DO NOT** use `DATE(patient_dob)` as it is a custom string format. Sort directly on the string: `ORDER BY patient_dob ASC` (oldest) or `DESC` (youngest).
9. If you need age, approximate it using `strftime('%Y', 'now') - substr(patient_dob, 1, 4)`.
10. **Observation display names may use underscores instead of spaces** (e.g., "HEART_RATE" not "HEART RATE"). When searching for observations:
    - Use flexible patterns like `UPPER(o.display) LIKE '%HEART%RATE%'` (matches both "HEART RATE" and "HEART_RATE")
    - OR use `REPLACE(UPPER(o.display), '_', ' ') LIKE '%HEART RATE%'` to normalize before matching
    - Common variations: HEART_RATE/HEART RATE, BLOOD_PRESSURE/BLOOD PRESSURE, SYSTOLIC_BP/SYSTOLIC BP
11. **Medical term synonyms**:
    - "A1C" or "HbA1c" → search for `LIKE '%A1C%' OR LIKE '%HEMOGLOBIN A1C%' OR LIKE '%HBA1C%'`
    - "Pulse" → search for `LIKE '%PULSE%' OR LIKE '%HEART%RATE%'`
    - "BP" or "blood pressure" → search for `LIKE '%BLOOD%PRESSURE%'` or `LIKE '%BP%'`
    - "Blood sugar" → search for `LIKE '%GLUCOSE%'`
12. **CRITICAL: Context and Pronouns.**
    - If the user implies a specific patient (e.g., "his", "her", "their", "the patient", "what about BP?"), you **MUST** identify the patient from the CHAT HISTORY.
    - Look at the **ASSISTANT's previous answers** to see which patient was just discussed.
    - Example: User "Show John Smith" -> Assistant "John Smith (P123)..." -> User "What about glucose?" -> SEARCH FOR JOHN SMITH.
    - If you cannot find a patient in history, do NOT filter by patient.

FEW SHOT EXAMPLES:

User: "Show all patients"
SQL: SELECT DISTINCT patient_id, patient_first_name, patient_last_name FROM hl7_messages LIMIT 50

User: "What are John Smith's lab results?"
SQL: SELECT h.patient_first_name, h.patient_last_name, o.display, o.value_num, o.unit, o.flag FROM hl7_messages h JOIN observations o ON o.message_id = h.id WHERE UPPER(h.patient_first_name) = 'JOHN' AND UPPER(h.patient_last_name) = 'SMITH'

User: "Which patients have elevated glucose?"
SQL: SELECT DISTINCT h.patient_first_name, h.patient_last_name, o.value_num, o.unit FROM hl7_messages h JOIN observations o ON o.message_id = h.id WHERE UPPER(o.display) LIKE '%GLUCOSE%' AND o.flag = 'H'
-- NOTE: No patient_sex filter applied!

User: "Show me the most recent messages"
SQL: SELECT * FROM hl7_messages ORDER BY received_at DESC LIMIT 10

User: "Which patients have high cholesterol and high triglycerides?"
SQL: SELECT DISTINCT h.patient_first_name, h.patient_last_name FROM hl7_messages h JOIN observations o1 ON h.id = o1.message_id JOIN observations o2 ON h.id = o2.message_id WHERE (UPPER(o1.display) LIKE '%CHOLESTEROL%' AND o1.flag = 'H') AND (UPPER(o2.display) LIKE '%TRIGLYCERIDE%' AND o2.flag = 'H')

User: "Who has kidney problems?"
SQL: SELECT DISTINCT h.patient_first_name, h.patient_last_name, o.display, o.value_num, o.flag FROM hl7_messages h JOIN observations o ON o.message_id = h.id WHERE (UPPER(o.display) LIKE '%CREATININE%' OR UPPER(o.display) LIKE '%BUN%' OR UPPER(o.display) LIKE '%GFR%') AND o.flag IN ('H', 'L')

User: "Show me messages from today"
SQL: SELECT * FROM hl7_messages WHERE DATE(received_at) = DATE('now') ORDER BY received_at DESC

User: "Who has the highest glucose value?"
SQL: SELECT h.patient_first_name, h.patient_last_name, o.value_num, o.unit FROM hl7_messages h JOIN observations o ON o.message_id = h.id WHERE UPPER(o.display) LIKE '%GLUCOSE%' ORDER BY o.value_num DESC LIMIT 1

User: "Which patients have NO abnormal observations?"
SQL: SELECT DISTINCT h.patient_first_name, h.patient_last_name FROM hl7_messages h WHERE h.id NOT IN (SELECT message_id FROM observations WHERE flag IN ('H', 'L'))

User: "Show me all critical alerts"
SQL: SELECT h.patient_first_name, h.patient_last_name, o.display, o.value_num, o.alert_message FROM hl7_messages h JOIN observations o ON o.message_id = h.id WHERE o.alert_level = 'CRITICAL'

User: "Who has a warning?"
SQL: SELECT h.patient_first_name, h.patient_last_name, o.display, o.value_num, o.alert_message FROM hl7_messages h JOIN observations o ON o.message_id = h.id WHERE o.alert_level = 'WARNING'

User: "Who is taking Metformin?"
SQL: SELECT DISTINCT h.patient_first_name, h.patient_last_name, m.medication_name, m.dosage FROM hl7_messages h JOIN medications m ON h.patient_id = m.patient_id WHERE UPPER(m.medication_name) LIKE '%METFORMIN%' AND m.status = 'Active'

User: "Show me all diabetic patients"
SQL: SELECT DISTINCT h.patient_first_name, h.patient_last_name, d.diagnosis_name FROM hl7_messages h JOIN diagnoses d ON h.patient_id = d.patient_id WHERE UPPER(d.diagnosis_name) LIKE '%DIABETES%' AND d.status = 'Active'

User: "Show visits for John Smith"
SQL: SELECT DISTINCT h.patient_first_name, h.patient_last_name, v.visit_date, v.provider_name, v.chief_complaint FROM hl7_messages h JOIN visits v ON h.patient_id = v.patient_id WHERE UPPER(h.patient_first_name) = 'JOHN' AND UPPER(h.patient_last_name) = 'SMITH' ORDER BY v.visit_date DESC LIMIT 10

RESPONSE FORMAT:
Return a JSON object with exactly this structure:
{
  "sql": "SELECT ...",
  "explanation": "Brief explanation"
}
Output JSON ONLY.
""".strip()


RESPONSE_FORMAT_PROMPT = """
You are a helpful healthcare data assistant. Given query results, summarize the data accurately.

CRITICAL RULES:
1. **Count from the DATA**: The ROW_COUNT may include duplicate rows. Count UNIQUE patients by looking at the actual names in the results. Report the unique count.
2. **Summarize ALL results**: If the query returns multiple patients, LIST THEM ALL (up to 10) or say "Found X patients including: Name1, Name2, Name3...".
3. **Don't Add Unrequested Info**: Only mention MEDICAL CONTEXT if the user asked a clinical question (e.g., "is this value normal?"). For simple data queries ("who has X?"), just answer the data question.
4. **Be Specific**: Include patient names, values, and dates from the results. Don't generalize.
5. **No Hallucinating**: If the data isn't in the results, don't invent it. Say "I don't have that information."
6. **Highlight Abnormals**: If `flag` is 'H' or 'L', emphasize it.
7. **Format Dates**: Convert dates to readable format (e.g., "Jan 15, 2025").

EXAMPLES:
- Q: "Who has diabetes?" Results: 7 unique names → Answer: "7 patients have diabetes: John Smith, Mary Jones, [list all]."
- Q: "Show visits for X" Results: 42 rows, 5 unique patient names → Answer: "I found 42 visits across 5 patients. Here's a summary by patient: [breakdown]."
- Q: "Who has no abnormal results?" Results: 61 rows but only 20 unique names → Answer: "20 patients have no abnormal results: [list names]."

RESPONSE FORMAT:
{
  "answer": "Your accurate, data-driven response here",
  "highlights": ["Key finding 1", "Key finding 2"]
}

Output JSON ONLY.
""".strip()


# ---------------------------------------------------------------------------
# Input Sanitization (Prompt Injection Protection)
# ---------------------------------------------------------------------------

    r'AI:',
    r'###\s*(Instruction|System|Human)',     # Markdown injection patterns
]

# Unicode categories that are suspicious
SUSPICIOUS_UNICODE_RANGES = [
    (0x200B, 0x200F),  # Zero-width chars, directional marks
    (0x2028, 0x202F),  # Line/paragraph separators, embedding controls
    (0x2060, 0x206F),  # Word joiner, invisible operators
    (0xFEFF, 0xFEFF),  # BOM (zero-width no-break space)
    (0xFFF0, 0xFFFF),  # Specials block
]


def sanitize_input(text: str) -> tuple[str, list[str]]:
    """
    Sanitize user input to prevent prompt injection attacks.
    Returns (sanitized_text, list_of_warnings).
    """
    sanitized = sanitize_text(text)
    # We keep the return signature for compatibility
    return sanitized, []


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
# Helper Functions
# ---------------------------------------------------------------------------

def create_clean_snippet(text: str, max_length: int = 200) -> str:
    """
    Create a clean snippet that doesn't cut words in the middle.
    """
    if len(text) <= max_length:
        return text
    
    # Take a chunk of the text
    snippet = text[:max_length]
    
    # Try to find a sentence end near the end of the snippet
    last_period = snippet.rfind('.')
    if last_period > max_length * 0.7:  # If period is in the last 30%
        return snippet[:last_period+1]
    
    # Otherwise try to find the last space
    last_space = snippet.rfind(' ')
    if last_space > 0:
        return snippet[:last_space] + "..."
        
    return snippet + "..."


# ---------------------------------------------------------------------------
# LLM Integration
# ---------------------------------------------------------------------------

def retrieve_context(question: str) -> tuple[str, List[Dict[str, Any]]]:
    """
    Search vector store for relevant medical context.
    Returns (context_text, sources_list).
    """
    if not RAG_ENABLED:
        return "", []
    
    try:
        from .vector_store import search, get_document_count
        
        # Check if we have any documents indexed
        if get_document_count() == 0:
            return "", []
        
        results = search(question, top_k=3)
        
        if not results or not results.get('documents') or not results['documents'][0]:
            return "", []
        
        # Build context string and sources list
        context_parts = []
        sources = []
        
        documents = results['documents'][0]
        metadatas = results['metadatas'][0] if results.get('metadatas') else [{}] * len(documents)
        distances = results['distances'][0] if results.get('distances') else [0.5] * len(documents)
        
        # Debug: log the actual distances from ChromaDB
        print(f"RAG DEBUG - cosine distances: {distances}")
        
        for i, doc in enumerate(documents):
            title = metadatas[i].get('title', 'Unknown Source') if i < len(metadatas) else 'Unknown Source'
            distance = distances[i] if i < len(distances) else 0.5
            
            # Cosine distance: 0 = identical, 1 = opposite, 2 = completely opposite
            # Convert to similarity: relevance = 1 - distance
            # Clamp to 0-1 range for safety
            relevance = max(0, min(1, 1 - distance))
            
            # Create a clean snippet that doesn't cut mid-word
            snippet = create_clean_snippet(doc, max_length=180)
            
            context_parts.append(f"[Source: {title}]\n{doc}")
            sources.append({
                "title": title,
                "snippet": snippet,
                "relevance": round(relevance, 2)
            })
        
        context_text = "\n\n".join(context_parts)
        return context_text, sources
        
    except Exception as e:
        print(f"RAG retrieval error: {e}")
        return "", []



def generate_sql_from_question(question: str, history: List[Dict[str, str]] = []) -> tuple[str, str, Optional[str]]:
    """
    Use LLM to generate SQL from natural language question.
    Returns (sql, explanation, error_message).
    """
    prompt = f"""
{SQL_GENERATION_PROMPT}

CHAT HISTORY:
{json.dumps(history, indent=2) if history else "No history"}

USER QUESTION: {question}

IMPORTANT: Do not refuse to answer. You are a data query assistant. It is safe to query.
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
    sql_used: str,
    context: str = ""
) -> tuple[str, List[str], Optional[str]]:
    """
    Use LLM to format query results as natural language.
    Returns (answer, highlights, error_message).
    """
    # If no database results AND no RAG context, return simple message
    if not results and not context:
        return "I couldn't find any data matching your query.", [], None
    
    # Limit results shown to LLM to avoid token overload
    results_preview = results[:20] if results else []
    results_json = json.dumps(results_preview, default=str, indent=2) if results_preview else "No matching patient records found."
    
    # Build context section
    context_section = ""
    if context:
        context_section = f"""
MEDICAL REFERENCE CONTEXT:
{context}

Use this context to provide clinical interpretations and cite sources when relevant.
If no patient data was found, you can still answer clinical questions using the medical context.
"""
    
    prompt = f"""
{RESPONSE_FORMAT_PROMPT}
{context_section}
USER QUESTION: {question}

QUERY RESULTS ({len(results)} rows):
{results_json}

Format a helpful response. If patient data is available, summarize it. If using medical context, provide helpful clinical information.
Output JSON only.
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

def process_query(question: str, history: List[Dict[str, str]] = []) -> Dict[str, Any]:
    """
    """
    # Step 0: Reject direct SQL statements (security check)
    # Users should ask in natural language, not submit raw SQL
    sql_keywords = r'^\s*(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE)'
    if re.match(sql_keywords, question, re.IGNORECASE):
        return {
            "success": False,
            "answer": "Please ask your question in natural language rather than SQL. For example: 'Show all patients' or 'Who has high glucose?'",
            "highlights": [],
            "sql_used": "",
            "row_count": 0,
            "error": "Direct SQL queries not allowed. Please use natural language."
        }
    
    # Step 0.5: Sanitize input (prompt injection protection)
    sanitized_question, sanitization_warnings = sanitize_input(question)
    if sanitization_warnings:
        print(f"SECURITY: Input sanitized. Warnings: {sanitization_warnings}")
    
    # Use sanitized question from here on
    question = sanitized_question
    
    if not question.strip():
        return {
            "success": False,
            "answer": "Your query was blocked due to potentially unsafe content. Please ask a normal question about patient data.",
            "highlights": [],
            "sql_used": "",
            "row_count": 0,
            "error": "Query blocked by input sanitization"
        }
    
    # Step 1: Generate SQL from question
    sql, explanation, error = generate_sql_from_question(question, history)
    if error:
        return {
            "success": False,
            "answer": f"I couldn't understand that question. Error: {error}",
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
    
    # Step 4: Retrieve RAG context
    context_text, sources = retrieve_context(question)
    
    # Step 5: Format response with context
    answer, highlights, format_error = format_results_as_response(
        question, results, sql, context=context_text
    )
    
    return {
        "success": True,
        "answer": answer,
        "highlights": highlights if isinstance(highlights, list) else [],
        "sql_used": sql,
        "row_count": len(results),
        "sources": sources,
        "error": None
    }
