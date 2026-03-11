"""
MCP Warden Sidecar — Deterministic Governance for Healthcare AI Agents

Architecture: Presidio-pattern (Analyzer → Anonymizer → Deanonymizer)
implemented as a three-gate MCP sidecar proxy.

Gates:
  IN-GATE:     Tokenizes PHI before data reaches the LLM (Bedrock)
  POLICY GATE: Validates tool calls with deterministic ALLOW/DENY/MODIFY
  OUT-GATE:    Detokenizes (rehydrates) tokens in LLM response for the user

Compliance:
  - HIPAA Safe Harbor (6 of 18 identifiers present in schema)
  - NIST AI RMF (AI 100-1) Data Minimization
  - Colorado AI Act (CAIA) Duty of Reasonable Care
  - OWASP Agentic Top 10 2026

Author: Bradly Cheng
"""

import json
import re
import sqlite3
import os
import uuid
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Optional, Any
from contextlib import contextmanager

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WARDEN_CONFIG = {
    "phi_tokenization": True,            # Core HIPAA-6 tokenization
    "clinical_surrogation_level": "PASS", # PASS | CLASS | FULL
    "audit_logging": True,
    "max_query_rows": 50,
    "blocked_tables": ["contacts"],
}

# ---------------------------------------------------------------------------
# Format-Preserving Token Pools
# ---------------------------------------------------------------------------

# NATO phonetic for patient names — LLM sees natural "first last" patterns
_PATIENT_NAMES = [
    "Alpha", "Bravo", "Charlie", "Delta",
    "Echo", "Foxtrot", "Golf", "Hotel",
    "India", "Juliet", "Kilo", "Lima",
    "Mike", "November", "Oscar", "Papa",
    "Quebec", "Romeo", "Sierra", "Tango",
    "Uniform", "Victor", "Whiskey", "Xray",
    "Yankee", "Zulu",
]

# Synthetic provider names — preserves "Dr." prefix
_PROVIDER_NAMES = [
    "Dr. Morgan", "Dr. Ellis", "Dr. Reed", "Dr. Blake", "Dr. Quinn",
    "NP Casey", "NP Jordan", "Dr. Hayes", "Dr. Avery", "Dr. Lane",
]

# Synthetic DOBs — offset preserves approximate age reasoning
_SYNTHETIC_DOBS = [
    "1990-06-15", "1985-03-22", "1978-11-08", "1992-01-30", "1988-07-14",
    "1975-09-03", "1982-12-19", "1995-04-25", "1970-08-11", "1980-02-28",
    "1993-10-07", "1977-05-16", "1991-06-21", "1986-09-12", "1983-01-04",
    "1989-11-30", "1976-03-17", "1994-07-09", "1981-04-02", "1987-08-26",
]


# ---------------------------------------------------------------------------
# Blocked Command Tokens (Contextual Jail)
# ---------------------------------------------------------------------------

BLOCKED_COMMAND_TOKENS = [
    "ignore previous", "ignore above", "disregard", "system prompt",
    "override", "sudo", "admin", "drop table", "delete from",
    "insert into", "update set", "alter table", "truncate",
    "exec(", "eval(", "import os", "__import__", "subprocess",
    "os.system", "os.popen", "base64.decode", "pickle.loads",
    "you are now", "act as", "new instructions", "forget everything",
    "from now on", "pretend to be",
]

# ---------------------------------------------------------------------------
# Tool Input Schemas (Strict Type-Checking)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS = {
    "query_database": {"query": str},
    "search_guidelines": {"query": str},
    "get_patient_context": {"patient_id": (str, type(None)), "patient_name": (str, type(None))},
    "clinical_calculator": {"calculation": str, "params": dict},
    "ask_clarification": {"question": str},
}


# ===========================================================================
# PHITokenMap — Session-Pinned, Ephemeral (RAM-Only)
# ===========================================================================

class PHITokenMap:
    """Ephemeral, session-pinned, RAM-only bidirectional token map.

    SECURITY: This object must NEVER be persisted, logged, or cached.
    It exists only for the duration of a single request.

    Satisfies: NIST AI 100-1 §5.2 (Data Minimization)
    """

    def __init__(self):
        self._real_to_token: Dict[str, str] = {}
        self._token_to_real: Dict[str, str] = {}
        self._counter: Dict[str, int] = {}  # per-category counter

    def add_mapping(self, real_value: str, token_value: str) -> None:
        """Register a bidirectional mapping."""
        self._real_to_token[real_value] = token_value
        self._token_to_real[token_value] = real_value

    def tokenize(self, text: str) -> str:
        """Replace all known real values with their tokens."""
        result = text
        # Sort by length descending to avoid partial matches
        # e.g., "Dr. Alice Chen" before "Alice"
        for real, token in sorted(
            self._real_to_token.items(), key=lambda x: len(x[0]), reverse=True
        ):
            result = result.replace(real, token)
        return result

    def detokenize(self, text: str) -> str:
        """Replace all tokens with their real values."""
        result = text
        for token, real in sorted(
            self._token_to_real.items(), key=lambda x: len(x[0]), reverse=True
        ):
            result = result.replace(token, real)
        return result

    def get_token(self, real_value: str) -> Optional[str]:
        """Get token for a real value, or None if not mapped."""
        return self._real_to_token.get(real_value)

    def get_real(self, token_value: str) -> Optional[str]:
        """Get real value for a token, or None if not mapped."""
        return self._token_to_real.get(token_value)

    @property
    def field_count(self) -> int:
        """Number of mapped fields (for audit logging)."""
        return len(self._real_to_token)

    @property
    def field_types_anonymized(self) -> List[str]:
        """List of field type categories anonymized (for audit logging).
        SECURITY: Returns category names only, never actual values."""
        return list(self._counter.keys())

    def _increment_category(self, category: str) -> None:
        """Track which categories have been anonymized."""
        self._counter[category] = self._counter.get(category, 0) + 1

    def clear(self) -> None:
        """Explicitly zero out all mappings."""
        self._real_to_token.clear()
        self._token_to_real.clear()
        self._counter.clear()

    def __del__(self):
        """Zero out on garbage collection as safety net."""
        self.clear()


# ===========================================================================
# WardenAnalyzer — Detects PHI entities, builds token map from DB
# ===========================================================================

class WardenAnalyzer:
    """Scans the database for known PHI entities and builds a fresh
    PHITokenMap for each request.

    Equivalent to: Microsoft Presidio Analyzer
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            from .db import DB_PATH
            db_path = DB_PATH
        self.db_path = db_path

    def build_token_map(self) -> PHITokenMap:
        """Query DB for known PHI entities, assign format-preserving tokens.

        Returns a fresh PHITokenMap for this request.
        """
        token_map = PHITokenMap()
        patient_idx = 0
        provider_idx = 0
        dob_idx = 0
        pid_counter = 1

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row

            # --- Patient names, DOBs, IDs ---
            patients = conn.execute("""
                SELECT DISTINCT patient_id, patient_first_name,
                       patient_last_name, patient_dob
                FROM hl7_messages
                WHERE patient_first_name IS NOT NULL
                ORDER BY patient_id
            """).fetchall()

            for row in patients:
                pid = row["patient_id"] or ""
                first = row["patient_first_name"] or ""
                last = row["patient_last_name"] or ""
                dob = row["patient_dob"] or ""
                full_name = f"{first} {last}".strip()

                # Assign format-preserving tokens
                if patient_idx < len(_PATIENT_NAMES):
                    name_token = _PATIENT_NAMES[patient_idx]
                else:
                    name_token = f"Patient P{patient_idx + 1:03d}"

                # Map full name "First Last" -> "Patient Alpha"
                if full_name:
                    token_map.add_mapping(full_name, name_token)
                    token_map._increment_category("patient_name")

                # Map patient ID
                if pid:
                    pid_token = f"P{pid_counter:05d}"
                    token_map.add_mapping(pid, pid_token)
                    token_map._increment_category("patient_id")
                    pid_counter += 1

                # Map DOB
                if dob:
                    if dob_idx < len(_SYNTHETIC_DOBS):
                        dob_token = _SYNTHETIC_DOBS[dob_idx]
                    else:
                        dob_token = f"1950-01-{(dob_idx % 28) + 1:02d}"
                    token_map.add_mapping(dob, dob_token)
                    token_map._increment_category("patient_dob")
                    dob_idx += 1

                patient_idx += 1

            # --- Provider names ---
            providers = conn.execute("""
                SELECT DISTINCT provider_name FROM visits
                WHERE provider_name IS NOT NULL
                ORDER BY provider_name
            """).fetchall()

            for row in providers:
                provider = row["provider_name"] or ""
                if provider:
                    if provider_idx < len(_PROVIDER_NAMES):
                        prov_token = _PROVIDER_NAMES[provider_idx]
                    else:
                        prov_token = f"Dr. Temp{provider_idx}"
                    token_map.add_mapping(provider, prov_token)
                    token_map._increment_category("provider_name")
                    provider_idx += 1

            conn.close()

        except Exception as e:
            print(f"[WARDEN] Analyzer error building token map: {e}")

        return token_map


# ===========================================================================
# WardenAnonymizer — IN-GATE (tokenize) + OUT-GATE (detokenize)
# ===========================================================================

class WardenAnonymizer:
    """Applies Format-Preserving Tokenization (IN-GATE) and
    Rehydration (OUT-GATE) using the PHITokenMap.

    Equivalent to: Microsoft Presidio Anonymizer + DeanonymizerEngine
    """

    def anonymize(self, text: str, token_map: PHITokenMap) -> str:
        """IN-GATE: Replace real PHI with format-preserving tokens.

        Call this BEFORE sending data to the LLM.
        """
        if not text or not token_map:
            return text
        return token_map.tokenize(text)

    def anonymize_json(self, data: Any, token_map: PHITokenMap) -> Any:
        """IN-GATE for structured data: recursively tokenize JSON values."""
        if isinstance(data, str):
            return token_map.tokenize(data)
        elif isinstance(data, dict):
            return {k: self.anonymize_json(v, token_map) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.anonymize_json(item, token_map) for item in data]
        else:
            return data

    def deanonymize(self, text: str, token_map: PHITokenMap) -> str:
        """OUT-GATE: Restore real values from tokens.

        Call this AFTER receiving response from the LLM.
        """
        if not text or not token_map:
            return text
        return token_map.detokenize(text)

    def deanonymize_sql(self, sql: str, token_map: PHITokenMap) -> str:
        """DOUBLE-BLIND SQL: Detokenize SQL before DB execution.

        The LLM generates SQL with tokens (WHERE name = 'ALPHA').
        We restore real values before the query hits the database.
        """
        if not sql or not token_map:
            return sql
        return token_map.detokenize(sql)


# ===========================================================================
# WardenPolicy — POLICY GATE (Tool Call Interception)
# ===========================================================================

@dataclass
class WardenDecision:
    """The verdict for an intercepted tool call."""
    action: str          # ALLOW | DENY | MODIFY
    tool_name: str
    reason: str
    evidence: str = ""   # PHI-free description of what was checked
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    phi_fields_anonymized: int = 0
    field_types: List[str] = field(default_factory=list)


class WardenPolicy:
    """Deterministic policy engine for tool call interception.

    Three checks per call:
      1. Strict Type-Checking (schema validation)
      2. Command-Token Validator (contextual jail)
      3. Tool-Specific Policy Rules

    Equivalent to: MCP security sidecar proxy
    """

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or WARDEN_CONFIG
        self.audit_log = WardenAuditLog()

    def intercept(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        token_map: PHITokenMap = None,
    ) -> WardenDecision:
        """Main entry point — every tool call passes through here.

        Returns ALLOW/DENY/MODIFY with reasoning.
        """
        # Check 1: Strict Type-Checking
        decision = self._check_schema(tool_name, tool_input)
        if decision.action == "DENY":
            self.audit_log.log(decision)
            return decision

        # Check 2: Command-Token Validator (Contextual Jail)
        decision = self._check_command_tokens(tool_name, tool_input)
        if decision.action == "DENY":
            self.audit_log.log(decision)
            return decision

        # Check 3: Tool-Specific Policy
        decision = self._check_tool_policy(tool_name, tool_input)

        # Attach PHI tokenization metadata (counts only, never values)
        if token_map:
            decision.phi_fields_anonymized = token_map.field_count
            decision.field_types = token_map.field_types_anonymized

        self.audit_log.log(decision)
        return decision

    def _check_schema(self, tool_name: str, tool_input: Dict[str, Any]) -> WardenDecision:
        """Check 1: Strict Type-Checking — fail-closed on schema mismatch."""
        schema = TOOL_SCHEMAS.get(tool_name)
        if not schema:
            return WardenDecision(
                action="DENY",
                tool_name=tool_name,
                reason="Unknown tool — not in TOOL_SCHEMAS",
                evidence=f"Tool '{tool_name}' not registered",
            )

        for param_name, expected_type in schema.items():
            if param_name in tool_input:
                value = tool_input[param_name]
                if value is not None and not isinstance(value, expected_type):
                    return WardenDecision(
                        action="DENY",
                        tool_name=tool_name,
                        reason=f"Type mismatch: '{param_name}' expected {expected_type.__name__}, got {type(value).__name__}",
                        evidence=f"Schema validation failed for parameter '{param_name}'",
                    )

        return WardenDecision(action="ALLOW", tool_name=tool_name, reason="Schema valid")

    def _check_command_tokens(self, tool_name: str, tool_input: Dict[str, Any]) -> WardenDecision:
        """Check 2: Command-Token Validator — contextual jail for injection."""
        for param_name, value in tool_input.items():
            if not isinstance(value, str):
                continue
            value_lower = value.lower()
            for blocked in BLOCKED_COMMAND_TOKENS:
                if blocked in value_lower:
                    return WardenDecision(
                        action="DENY",
                        tool_name=tool_name,
                        reason=f"Blocked command token detected in parameter '{param_name}'",
                        evidence=f"Contextual jail triggered: blocked token found in '{param_name}'",
                    )

        return WardenDecision(action="ALLOW", tool_name=tool_name, reason="No blocked tokens")

    def _check_tool_policy(self, tool_name: str, tool_input: Dict[str, Any]) -> WardenDecision:
        """Check 3: Tool-specific deterministic rules."""
        if tool_name == "query_database":
            return self._validate_query_database(tool_input)
        elif tool_name == "search_guidelines":
            return self._validate_search_guidelines(tool_input)
        elif tool_name == "get_patient_context":
            return self._validate_get_patient_context(tool_input)
        elif tool_name == "clinical_calculator":
            return self._validate_clinical_calculator(tool_input)
        elif tool_name == "ask_clarification":
            return WardenDecision(action="ALLOW", tool_name=tool_name, reason="Safe by design")
        else:
            return WardenDecision(
                action="DENY", tool_name=tool_name,
                reason=f"Unknown tool: {tool_name}",
            )

    def _validate_query_database(self, tool_input: Dict[str, Any]) -> WardenDecision:
        """Validate query_database tool input.
        
        NOTE: The 'query' field contains a NATURAL LANGUAGE question,
        not SQL. SQL is generated later inside _tool_query_database.
        We check for injection patterns only, not SQL syntax.
        """
        query = tool_input.get("query", "")
        if not query:
            return WardenDecision(
                action="DENY", tool_name="query_database",
                reason="Empty query", evidence="No query provided",
            )

        query_upper = query.strip().upper()

        import re
        # Block write operation keywords in the NL query (injection attempt)
        write_patterns = [
            r'\bINSERT\s+INTO\b', 
            r'\bUPDATE\s+.*?\s+SET\b', 
            r'\bDELETE\s+FROM\b', 
            r'\bDROP\s+(TABLE|DATABASE|VIEW)\b', 
            r'\bALTER\s+TABLE\b', 
            r'\bCREATE\s+(TABLE|DATABASE|VIEW)\b', 
            r'\bTRUNCATE\s+TABLE\b'
        ]
        for pattern in write_patterns:
            if re.search(pattern, query_upper):
                return WardenDecision(
                    action="DENY", tool_name="query_database",
                    reason=f"Write operation blocked by regex",
                    evidence=f"Query matches blocked pattern: {pattern}",
                )

        # Block access to restricted tables
        for table in self.config.get("blocked_tables", []):
            if table.upper() in query_upper:
                return WardenDecision(
                    action="DENY", tool_name="query_database",
                    reason=f"Access to restricted table '{table}' blocked",
                    evidence=f"Query references blocked table",
                )

        return WardenDecision(
            action="ALLOW", tool_name="query_database",
            reason="Query validated — no injection patterns",
            evidence=f"Row limit: {self.config.get('max_query_rows', 50)}",
        )

    def _validate_search_guidelines(self, tool_input: Dict[str, Any]) -> WardenDecision:
        """Enforce query length and content limits."""
        query = tool_input.get("query", "")
        max_len = 500
        if len(query) > max_len:
            return WardenDecision(
                action="MODIFY", tool_name="search_guidelines",
                reason=f"Query truncated to {max_len} chars",
                evidence=f"Original length: {len(query)}",
            )
        return WardenDecision(
            action="ALLOW", tool_name="search_guidelines",
            reason="Query within limits",
        )

    def _validate_get_patient_context(self, tool_input: Dict[str, Any]) -> WardenDecision:
        """Require valid patient ID or name."""
        pid = tool_input.get("patient_id")
        pname = tool_input.get("patient_name")
        if not pid and not pname:
            return WardenDecision(
                action="DENY", tool_name="get_patient_context",
                reason="No patient_id or patient_name provided",
                evidence="At least one patient identifier required",
            )
        return WardenDecision(
            action="ALLOW", tool_name="get_patient_context",
            reason="Valid patient identifier provided",
        )

    def _validate_clinical_calculator(self, tool_input: Dict[str, Any]) -> WardenDecision:
        """Whitelist allowed calculations."""
        calc = tool_input.get("calculation", "").lower()
        allowed = ["bmi", "egfr"]
        if calc not in allowed:
            return WardenDecision(
                action="DENY", tool_name="clinical_calculator",
                reason=f"Calculation '{calc}' not in whitelist {allowed}",
                evidence="Only approved calculations permitted",
            )
        return WardenDecision(
            action="ALLOW", tool_name="clinical_calculator",
            reason=f"Calculation '{calc}' approved",
        )


# ===========================================================================
# ClinicalSurrogator — Architect's Hook (pass-through with prod hooks)
# ===========================================================================

class ClinicalSurrogator:
    """Pluggable clinical data surrogation layer.

    Production upgrade path:
    - Level PASS:  Medications/diagnoses pass through (demo default)
    - Level CLASS: RxNorm drug class mapping (Metformin → Antidiabetic)
    - Level FULL:  SNOMED-CT/ICD-10 chapter rollup + k-anonymity

    For the demo, this preserves LLM reasoning by passing clinical
    terms through untokenized. The hooks document exactly where
    production-grade logic would plug in.
    """

    def __init__(self, level: str = None):
        self.level = level or WARDEN_CONFIG.get("clinical_surrogation_level", "PASS")

    def surrogate_medication(self, medication_name: str) -> str:
        """In production: Map via RxNorm → drug class hierarchy."""
        if self.level == "PASS":
            return medication_name  # Demo: preserve LLM reasoning
        # PRODUCTION HOOK: RxNorm API lookup
        # return rxnorm_class_map.get(medication_name, "Medication [REDACTED]")
        return medication_name

    def surrogate_diagnosis(self, diagnosis_name: str) -> str:
        """In production: Map via ICD-10 chapter rollup."""
        if self.level == "PASS":
            return diagnosis_name  # Demo: preserve LLM reasoning
        # PRODUCTION HOOK: ICD-10 chapter grouping
        # E11.9 → "Endocrine disorder" (Chapter IV rollup)
        return diagnosis_name

    def surrogate_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Apply surrogation to a full patient record dict."""
        result = dict(record)
        if "medication_name" in result:
            result["medication_name"] = self.surrogate_medication(result["medication_name"])
        if "diagnosis_name" in result:
            result["diagnosis_name"] = self.surrogate_diagnosis(result["diagnosis_name"])
        return result


# ===========================================================================
# WardenAuditLog — PHI-free structured logging
# ===========================================================================

class WardenAuditLog:
    """Append-only structured audit log.

    SECURITY RULE: The audit log must NEVER record real values and their
    tokens in the same entry. It records THAT tokenization occurred and
    WHICH field types were anonymized, but never the actual values.

    Satisfies: HIPAA §164.312 (audit controls)
    """

    def __init__(self, log_path: str = None):
        if log_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            log_path = os.path.join(base_dir, "warden_audit.jsonl")
        self.log_path = log_path

    def log(self, decision: WardenDecision) -> None:
        """Append a PHI-free decision record."""
        if not WARDEN_CONFIG.get("audit_logging", True):
            return

        entry = {
            "ts": decision.timestamp,
            "tool": decision.tool_name,
            "decision": decision.action,
            "reason": decision.reason,
            "evidence": decision.evidence,
            "phi_fields_anonymized": decision.phi_fields_anonymized,
            "field_types": decision.field_types,
        }

        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            print(f"[WARDEN] Audit log write error: {e}")

    def get_recent(self, n: int = 20) -> List[Dict]:
        """Read the most recent n audit entries."""
        entries = []
        try:
            if os.path.exists(self.log_path):
                with open(self.log_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                for line in lines[-n:]:
                    entries.append(json.loads(line.strip()))
        except Exception:
            pass
        return entries


# ===========================================================================
# Warden — Main Orchestrator (the sidecar entry point)
# ===========================================================================

class Warden:
    """MCP Warden Sidecar — the single entry point for all security operations.

    Usage in healthcare_agent.py:
        warden = Warden()

        # Per-request: create ephemeral token map
        with warden.request_scope() as ctx:
            # IN-GATE: tokenize before LLM
            safe_prompt = ctx.anonymize(raw_prompt)

            # POLICY GATE: validate tool call
            decision = ctx.intercept("query_database", {"query": sql})

            # DOUBLE-BLIND: detokenize SQL before DB, re-tokenize results
            real_sql = ctx.deanonymize_sql(tokenized_sql)
            safe_results = ctx.anonymize_json(raw_results)

            # OUT-GATE: detokenize LLM response for user
            user_answer = ctx.deanonymize(llm_response)
    """

    def __init__(self, db_path: str = None):
        self.analyzer = WardenAnalyzer(db_path)
        self.anonymizer = WardenAnonymizer()
        self.policy = WardenPolicy()
        self.surrogator = ClinicalSurrogator()

    @contextmanager
    def request_scope(self):
        """Create a request-scoped security context.

        The PHITokenMap is created fresh and destroyed when the
        context exits — session-pinned, ephemeral, RAM-only.
        """
        token_map = self.analyzer.build_token_map()
        ctx = WardenContext(
            token_map=token_map,
            anonymizer=self.anonymizer,
            policy=self.policy,
            surrogator=self.surrogator,
        )
        try:
            yield ctx
        finally:
            # Explicit cleanup — zero out the mapping
            token_map.clear()


# ===========================================================================
# WardenContext — Per-request security context
# ===========================================================================

class WardenContext:
    """Request-scoped security context providing all three gates.

    This is what healthcare_agent.py interacts with — a clean API
    for anonymize/deanonymize/intercept within a single request.
    """

    def __init__(
        self,
        token_map: PHITokenMap,
        anonymizer: WardenAnonymizer,
        policy: WardenPolicy,
        surrogator: ClinicalSurrogator,
    ):
        self.token_map = token_map
        self._anonymizer = anonymizer
        self._policy = policy
        self._surrogator = surrogator

    # --- IN-GATE ---

    def anonymize(self, text: str) -> str:
        """IN-GATE: Tokenize PHI in text before sending to LLM."""
        return self._anonymizer.anonymize(text, self.token_map)

    def anonymize_json(self, data: Any) -> Any:
        """IN-GATE: Tokenize PHI in structured JSON data."""
        return self._anonymizer.anonymize_json(data, self.token_map)

    # --- POLICY GATE ---

    def intercept(self, tool_name: str, tool_input: Dict[str, Any]) -> WardenDecision:
        """POLICY GATE: Validate a tool call. Returns ALLOW/DENY/MODIFY."""
        return self._policy.intercept(tool_name, tool_input, self.token_map)

    # --- DOUBLE-BLIND SQL ---

    def deanonymize_sql(self, sql: str) -> str:
        """DOUBLE-BLIND: Detokenize SQL before DB execution."""
        return self._anonymizer.deanonymize_sql(sql, self.token_map)

    # --- OUT-GATE ---

    def deanonymize(self, text: str) -> str:
        """OUT-GATE: Rehydrate tokens in LLM response for the user."""
        return self._anonymizer.deanonymize(text, self.token_map)

    # --- Clinical Surrogation ---

    def surrogate_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Apply clinical surrogation (pass-through in demo mode)."""
        return self._surrogator.surrogate_record(record)
