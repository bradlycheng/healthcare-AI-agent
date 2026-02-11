# app/healthcare_agent.py
"""
Healthcare AI Agent with Tool-Use Capabilities

A ReAct-style agent that can reason through healthcare queries using tools:
- query_database: Natural language to SQL queries
- search_guidelines: RAG search for medical context
- get_patient_context: Patient history and trends
- clinical_calculator: BMI, eGFR, etc.
- ask_clarification: Handle ambiguous queries
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Callable

from .llm_client import call_llm_for_json, call_llm, LLMError
from .security import sanitize_text, detect_injection_patterns


# =============================================================================
# Data Classes and Enums
# =============================================================================

class ToolName(str, Enum):
    """Available tools for the agent."""
    QUERY_DATABASE = "query_database"
    SEARCH_GUIDELINES = "search_guidelines"
    GET_PATIENT_CONTEXT = "get_patient_context"
    CLINICAL_CALCULATOR = "clinical_calculator"

    ASK_CLARIFICATION = "ask_clarification"


class ReasoningDepth(str, Enum):
    """Depth of reasoning strategies."""
    FAST = "fast"        # Direct SQL/RAG (Legacy)
    STANDARD = "standard"  # ReAct Loop (Current)
    DEEP = "deep"        # Reflection + Planning + ReAct


@dataclass
class ToolCall:
    """A single tool invocation."""
    tool: str
    input: Dict[str, Any]
    

@dataclass
class ToolResult:
    """Result from a tool execution."""
    tool: str
    success: bool
    result: Dict[str, Any]
    error: Optional[str] = None
    execution_time_ms: int = 0


@dataclass
class AgentStep:
    """One step in the agent's reasoning process."""
    thought: str
    tool_calls: List[ToolCall]
    tool_results: List[ToolResult] = field(default_factory=list)


@dataclass
class AgentResponse:
    """Final response from the agent."""
    answer: str
    success: bool
    highlights: List[str] = field(default_factory=list)
    reasoning_trace: List[AgentStep] = field(default_factory=list)
    tools_used: List[str] = field(default_factory=list)
    sources: List[Dict[str, Any]] = field(default_factory=list)
    sql_used: str = ""
    row_count: int = 0
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    clarification_options: List[str] = field(default_factory=list)
    error: Optional[str] = None


# =============================================================================
# Agent System Prompt
# =============================================================================

AGENT_SYSTEM_PROMPT = """
You are a healthcare data assistant with access to tools. Given a user question,
decide which tool(s) to use to answer it.

AVAILABLE TOOLS:

1. query_database
   - Purpose: Query patient data using natural language
   - Use for: "show patients with X", "who has Y", "list all Z"
   - Input: {"query": "natural language question"}

2. search_guidelines  
   - Purpose: Search medical guidelines for clinical context
   - Use for: "is X normal", "what does Y mean", clinical interpretation
   - Input: {"query": "search terms"}

3. get_patient_context
   - Purpose: Get full patient history including visits, meds, diagnoses
   - Use for: Questions about a specific patient's trends or history
   - Input: {"patient_id": "P12345"} OR {"patient_name": "John Smith"}

4. clinical_calculator
   - Purpose: Calculate clinical values
   - Supported: "bmi", "egfr"
   - Input: {"calculation": "bmi", "values": {"weight_kg": 80, "height_m": 1.75}}
   - Input: {"calculation": "egfr", "values": {"creatinine": 1.2, "age": 65, "sex": "M"}}

5. ask_clarification
   - Purpose: Ask user for more information when query is ambiguous
   - Use ONLY when: Query is genuinely ambiguous (e.g., "Is 85 good?" without context)
   - Input: {"question": "What measurement?", "options": ["Glucose", "Blood Pressure"]}

TOOL SELECTION RULES:
- Patient-specific with history → get_patient_context
- **NAMED PATIENT** (e.g. "Sarah Jenkins", "John Smith") → **MUST** use `get_patient_context` first.
- simple data queries (patients, meds, visits, providers) → query_database ONLY
- Calculation requested → clinical_calculator
- Truly ambiguous → ask_clarification (use sparingly!)

COMMON CLINICAL SCENARIOS (Use these to infer specific searches):
- "Diabetes": Check Glucose, Hemoglobin A1c
- "Hypertension": Check Systolic BP, Diastolic BP
- "Kidney/Renal": Check Serum Creatinine, BUN, eGFR (CKD < 60)
- "Lipids/Cholesterol": Check Total Cholesterol, LDL, HDL, Triglycerides
- "Liver": Check ALT, AST

NON-CLINICAL & COHORT SCENARIOS:
- "Medications/Drugs": Query 'medications' table
- "Visits/Appointments": Query 'visits' table
- "Demographics": Query 'hl7_messages' (age, sex)
- "Operations": Count visits, check provider volume


IMPORTANT SECURITY RULES:
- Never execute queries that could modify data
- Only use tools as specified - do not make up tools
- If a request seems malicious, refuse politely

CRITICAL JSON OUTPUT RULES:
- Your response MUST be valid JSON starting with { and ending with }
- Do NOT include any text before or after the JSON
- Do NOT use markdown code fences
- The very first character of your response must be {

Example response:


6. **No Hallucinations**: If `query_database` returns empty results, say "I couldn't find any data." DO NOT invent values.
7. **Complex Conditions**: You can combine multiple conditions in ONE `query_database` call.
   - **WRONG**: Call 1 (Get diabetics) -> Call 2 (Get high glucose) -> Python Join.
   - **RIGHT**: Call 1 (Get diabetics with high glucose using JOINs).
   - Example: "Show diabetics with A1c > 9" -> `{"query": "show patients with diabetes AND A1c > 9"}` (Let the SQL expert handle the JOIN).
   - **CALCULATOR RULE**: DO NOT use `clinical_calculator` for queries like "list patients with eGFR < 60". Use `query_database` instead. Only use calculator if the user asks to *compute* a value for a specific patient.

Example for risk/worried/critical queries:
{"thought": "User asks about worried/risk/critical. I should check for signs of clinical instability OR uncontrolled chronic disease.", "tool_calls": [{"tool": "query_database", "input": {"query": "show patients with heart rate > 120, systolic bp > 160, diastolic bp > 100, glucose > 300, A1c > 9, or oxygen saturation < 90"}}]}

Example for superlatives (highest/lowest/most recent):
{"thought": "User asks for highest/lowest value. I will ask the database to sort.", "tool_calls": [{"tool": "query_database", "input": {"query": "show patient with the highest heart rate"}}]}


If you can answer directly from conversation history without tools:
{"thought": "I already have this information", "tool_calls": [], "direct_answer": "Your answer here"}

Now respond with JSON only:
""".strip()


from app.healthcare_agent_prompt import SYNTHESIS_PROMPT
# Note: SYNTHESIS_PROMPT is imported from healthcare_agent_prompt.py


# =============================================================================
# Healthcare Agent
# =============================================================================

class HealthcareAgent:
    """
    ReAct-style agent for healthcare data queries.
    
    Uses a single-pass reasoning approach:
    1. Analyze question → decide tools
    2. Execute tools (in parallel when possible)
    3. Synthesize results into answer
    """
    
    MAX_STEPS = 2  # Prevent runaway loops
    
    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._register_tools()
    
    def _register_tools(self):
        """Register all available tools."""
        self._tools = {
            ToolName.QUERY_DATABASE.value: self._tool_query_database,
            ToolName.SEARCH_GUIDELINES.value: self._tool_search_guidelines,
            ToolName.GET_PATIENT_CONTEXT.value: self._tool_get_patient_context,
            ToolName.CLINICAL_CALCULATOR.value: self._tool_clinical_calculator,
            ToolName.ASK_CLARIFICATION.value: self._tool_ask_clarification,
        }
    
    def run(self, question: str, history: List[Dict[str, str]] = None, depth: str = "standard") -> AgentResponse:
        """
        Main agent entry point with Reasoning Router.
        
        Args:
            question: User's natural language question
            history: Previous conversation history
            depth: "fast", "standard", or "deep"
        """
        if history is None:
            history = []
            
        # Router
        if depth == ReasoningDepth.FAST.value:
            return self._run_fast(question, history)
        elif depth == ReasoningDepth.DEEP.value:
            return self._run_deep(question, history)
        else:
            return self._run_standard(question, history)

    def _run_standard(self, question: str, history: List[Dict[str, str]] = None) -> AgentResponse:
        """
        Standard ReAct Loop (Legacy 'run' method).
        """
        if history is None:
            history = []
        
        # Security: Check for injection attempts
        injection_warnings = detect_injection_patterns(question)
        if injection_warnings:
            return AgentResponse(
                answer="Your query was blocked due to potentially unsafe content.",
                success=False,
                error="Query blocked by security filter"
            )
        
        # Sanitize input
        question = sanitize_text(question)
        if not question.strip():
            return AgentResponse(
                answer="Please ask a valid question about patient data.",
                success=False,
                error="Empty query after sanitization"
            )
        
        trace: List[AgentStep] = []
        tools_used: List[str] = []
        all_sources: List[Dict[str, Any]] = []
        sql_used = ""
        row_count = 0
        
        try:
            # Step 1: Planning - decide which tools to use
            plan = self._plan(question, history)
            print(f"DEBUG: Plan result: {plan}")
            
            if plan.get("error"):
                return AgentResponse(
                    answer="I had trouble understanding that question. Please try rephrasing.",
                    success=False,
                    error=plan["error"]
                )
            
            # Check for direct answer (no tools needed)
            if plan.get("direct_answer"):
                return AgentResponse(
                    answer=plan["direct_answer"],
                    success=True,
                    reasoning_trace=[AgentStep(
                        thought=plan.get("thought", "Answered from context"),
                        tool_calls=[],
                        tool_results=[]
                    )]
                )
            
            # Check for clarification needed
            tool_calls = plan.get("tool_calls", [])
            for tc in tool_calls:
                if tc.get("tool") == ToolName.ASK_CLARIFICATION.value:
                    inp = tc.get("input", {})
                    return AgentResponse(
                        answer=inp.get("question", "Could you please clarify your question?"),
                        success=True,
                        needs_clarification=True,
                        clarification_question=inp.get("question"),
                        clarification_options=inp.get("options", []),
                        reasoning_trace=[AgentStep(
                            thought=plan.get("thought", "Need clarification"),
                            tool_calls=[ToolCall(tool=tc["tool"], input=inp)],
                            tool_results=[]
                        )]
                    )
            
            # Step 2: Execute tools
            step = AgentStep(
                thought=plan.get("thought", ""),
                tool_calls=[ToolCall(tool=tc["tool"], input=tc.get("input", {})) 
                           for tc in tool_calls]
            )
            
            for tc in tool_calls:
                tool_name = tc.get("tool", "")
                tool_input = tc.get("input", {})
                
                # Validate tool exists
                if tool_name not in self._tools:
                    step.tool_results.append(ToolResult(
                        tool=tool_name,
                        success=False,
                        result={},
                        error=f"Unknown tool: {tool_name}"
                    ))
                    continue
                
                # Execute tool with timing
                start_time = time.time()
                try:
                    # Pass history for context-aware tools
                    if tool_name == ToolName.QUERY_DATABASE.value:
                        result = self._tools[tool_name](tool_input, history)
                    else:
                        result = self._tools[tool_name](tool_input)
                    
                    execution_time = int((time.time() - start_time) * 1000)
                    
                    step.tool_results.append(ToolResult(
                        tool=tool_name,
                        success=True,
                        result=result,
                        execution_time_ms=execution_time
                    ))
                    
                    tools_used.append(tool_name)
                    
                    # Collect metadata
                    if tool_name == ToolName.QUERY_DATABASE.value:
                        sql_used = result.get("sql", "")
                        row_count = result.get("row_count", 0)
                    if tool_name == ToolName.SEARCH_GUIDELINES.value:
                        all_sources.extend(result.get("sources", []))
                        
                except Exception as e:
                    step.tool_results.append(ToolResult(
                        tool=tool_name,
                        success=False,
                        result={},
                        error=str(e)
                    ))
            
            trace.append(step)
            
            # Step 3: Synthesize answer
            answer, highlights = self._synthesize(question, step.tool_results)
            
            return AgentResponse(
                answer=answer,
                success=True,
                highlights=highlights,
                reasoning_trace=trace,
                tools_used=tools_used,
                sources=all_sources,
                sql_used=sql_used,
                row_count=row_count
            )
            
        except LLMError as e:
            return AgentResponse(
                answer="I encountered an error processing your question. Please try again.",
                success=False,
                error=f"LLM error: {str(e)}"
            )
        except Exception as e:
            return AgentResponse(
                answer="Sorry, something went wrong. Please try again.",
                success=False,
                error=f"Agent error: {str(e)}"
            )
    
    def _plan(self, question: str, history: List[Dict[str, str]]) -> Dict[str, Any]:
        """Use LLM to plan which tools to call."""
        history_str = ""
        if history:
            history_str = "\n\nCONVERSATION HISTORY:\n"
            # Reverse to label them relative to now? No, chronological is better for reading.
            # But we can label the last one explicitly.
            relevant_history = history[-5:]
            for i, msg in enumerate(relevant_history):
                role = msg.get("role", "user")
                content = msg.get("content", "")
                
                label = ""
                if i == len(relevant_history) - 1:
                    label = " [IMMEDIATELY PRECEDING MESSAGE]"
                
                history_str += f"{role.upper()}{label}: {content}\n"
        
        prompt = f"""
{AGENT_SYSTEM_PROMPT}

{history_str}

CURRENT USER QUESTION: {question}

IMPORTANT: 
- You interpret "it", "that", "he", "she" as referring to the SUBJECT of the [IMMEDIATELY PRECEDING MESSAGE].
- Do NOT refer to older messages if a new topic was introduced in the [IMMEDIATELY PRECEDING MESSAGE].

Decide which tools to use. Output valid JSON only. Do not use code blocks.
"""
        
        try:
            result = call_llm_for_json(prompt)
            return result
        except Exception as e:
            return {"error": str(e)}
    
    def _synthesize(self, question: str, tool_results: List[ToolResult]) -> Tuple[str, List[str]]:
        """Synthesize tool results into a natural language answer."""
        # Format tool results for LLM
        results_str = ""
        for tr in tool_results:
            if tr.success:
                results_str += f"\n[{tr.tool}]: {json.dumps(tr.result, default=str)}\n"
            else:
                results_str += f"\n[{tr.tool}]: ERROR - {tr.error}\n"
        
        prompt = SYNTHESIS_PROMPT.format(
            question=question,
            tool_results=results_str
        )
        
        try:
            # Use text generation to avoid JSON parsing issues with Markdown tables
            text_response = call_llm(prompt)
            
            # Parse the text response
            answer = text_response
            highlights = []
            
            # Extract Answer
            answer_match = re.search(r"ANSWER:(.*?)(?=HIGHLIGHTS:|$)", text_response, re.DOTALL | re.IGNORECASE)
            if answer_match:
                answer = answer_match.group(1).strip()
                # Clean up bold wrapping if LLM insists on it
                if answer.startswith("**") and answer.endswith("**"):
                    answer = answer[2:-2].strip()
                elif answer.startswith("```json") and answer.endswith("```"):
                    # Emergency fix if it outputs JSON instead of text
                    try:
                        data = json.loads(answer[7:-3])
                        answer = data.get("answer", answer)
                    except: pass
            
            # Extract Highlights
            highlights_match = re.search(r"HIGHLIGHTS:(.*)", text_response, re.DOTALL | re.IGNORECASE)
            if highlights_match:
                highlights_text = highlights_match.group(1).strip()
                # Split by bullets (hyphen or asterisk)
                highlights = [line.strip().lstrip("-* ").strip() 
                             for line in highlights_text.split("\n") 
                             if line.strip().startswith("-") or line.strip().startswith("*")]
            
            return answer, highlights

        except Exception as e:
            # Fallback: Create a basic answer from tool results
            return self._fallback_synthesis(tool_results), []
    
    def _fallback_synthesis(self, tool_results: List[ToolResult]) -> str:
        """Create a fallback answer when LLM synthesis fails."""
        answers = []
        
        for tr in tool_results:
            if not tr.success:
                continue
                
            result = tr.result
            
            if tr.tool == ToolName.QUERY_DATABASE.value:
                row_count = result.get("row_count", 0)
                results = result.get("results", [])
                if row_count == 0:
                    answers.append("No matching records found.")
                elif row_count <= 5:
                    # Format small result sets nicely
                    items = []
                    for row in results[:5]:
                        if isinstance(row, dict):
                            # Get patient name if available
                            name = row.get("patient_name") or row.get("full_name")
                            if not name:
                                first = row.get("patient_first_name", "")
                                last = row.get("patient_last_name", "")
                                if first or last:
                                    name = f"{first} {last}".strip()
                            
                            if name:
                                items.append(name)
                    if items:
                        answers.append(f"Found {row_count} record(s): {', '.join(items)}")
                    else:
                        answers.append(f"Found {row_count} record(s).")
                else:
                    # For larger sets, still show first 5
                    items = []
                    for row in results[:5]:
                        if isinstance(row, dict):
                            name = row.get("patient_name") or row.get("full_name")
                            if not name:
                                first = row.get("patient_first_name", "")
                                last = row.get("patient_last_name", "")
                                if first or last:
                                    name = f"{first} {last}".strip()
                            if name:
                                items.append(name)
                    
                    if items:
                        answers.append(f"Found {row_count} records, including: {', '.join(items)} and others.")
                    else:
                        answers.append(f"Found {row_count} records.")
                    
            elif tr.tool == ToolName.CLINICAL_CALCULATOR.value:
                calc_result = result.get("result")
                unit = result.get("unit", "")
                interpretation = result.get("interpretation", "")
                if calc_result:
                    answers.append(f"Result: {calc_result} {unit}. {interpretation}")
                    
            elif tr.tool == ToolName.SEARCH_GUIDELINES.value:
                context = result.get("context", "")
                if context:
                    # Truncate if too long
                    if len(context) > 300:
                        context = context[:300] + "..."
                    answers.append(f"Guidelines: {context}")
        
        if not answers:
            return "I found some data but had trouble formatting the results. Please try rephrasing your question."
        
        return " ".join(answers)
    
    # =========================================================================
    # Tool Implementations
    # =========================================================================
    
    def _tool_query_database(self, input_data: Dict[str, Any], 
                              history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """Execute natural language query against patient database."""
        from .query_assistant import (
            generate_sql_from_question,
            validate_sql,
            execute_safe_query,
            retrieve_context
        )
        
        query = input_data.get("query", "")
        if not query:
            return {"error": "No query provided", "results": [], "row_count": 0}
        
        # Sanitize query input
        query = sanitize_text(query)
        
        # Generate SQL
        sql, explanation, error = generate_sql_from_question(query, history or [])
        if error:
            if error.startswith("AMBIGUOUS:"):
                return {
                    "needs_clarification": True,
                    "message": error.replace("AMBIGUOUS:", "").strip(),
                    "results": [],
                    "row_count": 0
                }
            return {"error": error, "results": [], "row_count": 0, "sql": ""}
        
        # Validate SQL
        is_valid, validation_error = validate_sql(sql)
        if not is_valid:
            return {"error": f"Invalid SQL: {validation_error}", "results": [], "row_count": 0}
        
        # Execute query
        results, exec_error = execute_safe_query(sql)
        if exec_error:
            return {"error": exec_error, "results": [], "row_count": 0, "sql": sql}
        
        return {
            "results": results[:50],  # Limit results
            "row_count": len(results),
            "sql": sql,
            "explanation": explanation
        }
    
    def _tool_search_guidelines(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Search medical guidelines using RAG."""
        from .query_assistant import retrieve_context
        
        query = input_data.get("query", "")
        if not query:
            return {"context": "", "sources": []}
        
        context_text, sources = retrieve_context(query)
        
        return {
            "context": context_text,
            "sources": sources
        }
    
    def _tool_get_patient_context(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Get comprehensive patient context."""
        from .patient_timeline import get_patient_timeline
        
        patient_id = input_data.get("patient_id")
        patient_name = input_data.get("patient_name")
        
        # Search strategy:
        # 1. If patient_id looks like a name (no P- prefix), treat as patient_name
        if patient_id and not str(patient_id).startswith('P-') and not patient_name:
            patient_name = patient_id
            patient_id = None

        # 2. If name provided, try to find patient ID
        if patient_name and not patient_id:
            from .db import get_connection
            conn = get_connection()
            try:
                # Try full name exact match
                row = conn.execute(
                    "SELECT DISTINCT patient_id FROM hl7_messages WHERE UPPER(patient_first_name || ' ' || patient_last_name) = ?",
                    (patient_name.upper(),)
                ).fetchone()
                
                if not row:
                    # Try last name match
                    row = conn.execute(
                        "SELECT DISTINCT patient_id FROM hl7_messages WHERE UPPER(patient_last_name) = ?",
                        (patient_name.upper(),)
                    ).fetchone()
                
                if not row:
                    # Handle "First Last" format
                    parts = patient_name.upper().split()
                    if len(parts) >= 2:
                        first_name = parts[0]
                        last_name = parts[-1]
                        row = conn.execute(
                            "SELECT DISTINCT patient_id FROM hl7_messages WHERE UPPER(patient_first_name) = ? AND UPPER(patient_last_name) = ?",
                            (first_name, last_name)
                        ).fetchone()
                
                if row:
                    patient_id = row["patient_id"]
            finally:
                conn.close()
        
        if not patient_id:
            return {"error": "Could not find patient", "patient": None}
        
        try:
            timeline = get_patient_timeline(patient_id)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"error": f"Error retrieving timeline: {str(e)}", "patient": None}

        if not timeline:
            return {"error": "Patient not found", "patient": None}
        
        return {
            "patient": timeline.get("patient"),
            "visits": timeline.get("visits", [])[:10],  # Last 10 visits
            "visit_count": timeline.get("visit_count", 0)
        }
    
    def _tool_clinical_calculator(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Perform clinical calculations."""
        calculation = input_data.get("calculation", "").lower()
        values = input_data.get("values", {})
        
        if calculation == "bmi":
            weight = values.get("weight_kg")
            height = values.get("height_m")
            
            if not weight or not height:
                return {"error": "BMI requires weight_kg and height_m"}
            
            try:
                bmi = float(weight) / (float(height) ** 2)
                
                # Interpretation
                if bmi < 18.5:
                    interpretation = "Underweight"
                elif bmi < 25:
                    interpretation = "Normal weight"
                elif bmi < 30:
                    interpretation = "Overweight"
                else:
                    interpretation = "Obese"
                
                return {
                    "result": round(bmi, 1),
                    "unit": "kg/m²",
                    "formula": "weight / height²",
                    "interpretation": interpretation
                }
            except (ValueError, ZeroDivisionError) as e:
                return {"error": f"Calculation error: {str(e)}"}
        
        elif calculation == "egfr":
            creatinine = values.get("creatinine")
            age = values.get("age")
            sex = values.get("sex", "").upper()
            
            if not creatinine or not age:
                return {"error": "eGFR requires creatinine (mg/dL) and age"}
            
            try:
                # CKD-EPI formula (simplified)
                cr = float(creatinine)
                age = int(age)
                
                # Sex-based constants
                if sex == "F":
                    kappa = 0.7
                    alpha = -0.241
                    multiplier = 1.012
                else:
                    kappa = 0.9
                    alpha = -0.302
                    multiplier = 1.0
                
                min_cr = min(cr / kappa, 1)
                max_cr = max(cr / kappa, 1)
                
                egfr = 142 * (min_cr ** alpha) * (max_cr ** -1.200) * (0.9938 ** age) * multiplier
                
                # Interpretation
                if egfr >= 90:
                    stage = "Normal (G1)"
                elif egfr >= 60:
                    stage = "Mildly decreased (G2)"
                elif egfr >= 45:
                    stage = "Mild-moderate decrease (G3a)"
                elif egfr >= 30:
                    stage = "Moderate-severe decrease (G3b)"
                elif egfr >= 15:
                    stage = "Severely decreased (G4)"
                else:
                    stage = "Kidney failure (G5)"
                
                return {
                    "result": round(egfr, 1),
                    "unit": "mL/min/1.73m²",
                    "formula": "CKD-EPI 2021",
                    "interpretation": stage
                }
            except (ValueError, ZeroDivisionError) as e:
                return {"error": f"Calculation error: {str(e)}"}
        
        else:
            return {"error": f"Unknown calculation: {calculation}. Supported: bmi, egfr"}
    
    def _tool_ask_clarification(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Ask user for clarification."""
        return {
            "needs_clarification": True,
            "question": input_data.get("question", "Could you please clarify?"),
            "options": input_data.get("options", [])
        }

    # =========================================================================
    # Reasoning Modes
    # =========================================================================

    def _run_fast(self, question: str, history: List[Dict[str, str]]) -> AgentResponse:
        """
        Fast Mode: Direct SQL/RAG without ReAct loop.
        Wraps `query_assistant.process_query` logic.
        """
        from .query_assistant import process_query
        
        # We need to adapt the dict response from process_query to AgentResponse
        start_time = time.time()
        result = process_query(question, history)
        duration = int((time.time() - start_time) * 1000)
        
        # Create a "fake" trace step for transparency
        step = AgentStep(
            thought="Fast Mode: Direct execution via Query Assistant",
            tool_calls=[],
            tool_results=[ToolResult(
                tool="query_assistant",
                success=result["success"],
                result={"row_count": result.get("row_count")},
                execution_time_ms=duration
            )]
        )
        
        return AgentResponse(
            answer=result["answer"],
            success=result["success"],
            highlights=result.get("highlights", []),
            reasoning_trace=[step],
            sql_used=result.get("sql_used", ""),
            row_count=result.get("row_count", 0),
            sources=result.get("sources", []),
            error=result.get("error")
        )

    def _run_deep(self, question: str, history: List[Dict[str, str]]) -> AgentResponse:
        """
        Deep Mode: Reflection + Standard ReAct.
        """
        # 1. Reflection / Planning Step
        # JSON template in separate string to avoid f-string escaping issues
        json_template = """
{
  "analysis": "This request requires...",
  "strategy": "First query X, then check guidelines Y...",
  "modifications": "Ensure to check for synonyms of..."
}
"""
        reflection_prompt = f"""
You are a Senior Clinical AI Supervisor.
A user has asked: "{question}"

Analyze the complexity of this request.
1. Identify if this requires multi-step reasoning (e.g., compare two patients, trend analysis).
2. Identify potential pitfalls (e.g., missing units, ambiguous terms).
3. Formulate a high-level plan for the agent.

Output JSON:
""" + json_template + """
Output valid JSON only. Do not use code blocks.
"""
        try:
            reflection = call_llm_for_json(reflection_prompt)
            strategy = reflection.get("strategy", "Proceed with standard analysis.")
            
            # Inject strategy into history or prompt to guide _run_standard?
            # For now, we prepend the strategy to the question to guide the ReAct agent
            enhanced_question = f"[STRATEGY: {strategy}] {question}"
            
            # Run Standard loop with enhanced context
            response = self._run_standard(enhanced_question, history)
            
            # Prepend reflection step to trace
            reflection_step = AgentStep(
                thought=f"Deep Mode Reflection: {reflection.get('analysis')}",
                tool_calls=[],
                tool_results=[ToolResult(
                    tool="reflection", 
                    success=True, 
                    result=reflection, 
                    execution_time_ms=0
                )]
            )
            response.reasoning_trace.insert(0, reflection_step)
            
            return response
            
        except Exception as e:
            # Fallback to standard if reflection fails
            return self._run_standard(question, history)



# =============================================================================
# Convenience Function
# =============================================================================


def run_agent_query(question: str, history: List[Dict[str, str]] = None, depth: str = "standard") -> Dict[str, Any]:
    """
    Run an agent query and return the result as a dict.
    
    This is the main entry point for the API.
    """
    agent = HealthcareAgent()
    response = agent.run(question, history, depth)
    
    return {
        "success": response.success,
        "answer": response.answer,
        "highlights": response.highlights,
        "reasoning_trace": [
            {
                "thought": step.thought,
                "tools": [{"tool": tc.tool, "input": tc.input} for tc in step.tool_calls],
                "results": [
                    {"tool": tr.tool, "success": tr.success, "time_ms": tr.execution_time_ms}
                    for tr in step.tool_results
                ]
            }
            for step in response.reasoning_trace
        ],
        "tools_used": response.tools_used,
        "sources": response.sources,
        "sql_used": response.sql_used,
        "row_count": response.row_count,
        "needs_clarification": response.needs_clarification,
        "clarification_question": response.clarification_question,
        "clarification_options": response.clarification_options,
        "error": response.error
    }
