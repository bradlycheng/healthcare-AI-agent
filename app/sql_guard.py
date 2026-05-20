from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Set, Tuple

from .security_validation import IntentGrant


GUARD_NAME = "SQLGuard"

BLOCKED_TABLES: Set[str] = {"contacts"}

DEFAULT_ALLOWED_COLUMNS: Dict[str, Set[str]] = {
    "hl7_messages": {
        "id",
        "received_at",
        "patient_id",
        "patient_first_name",
        "patient_last_name",
        "patient_dob",
        "patient_sex",
    },
    "observations": {
        "id",
        "message_id",
        "code",
        "display",
        "value_num",
        "value_raw",
        "unit",
        "reference_low",
        "reference_high",
        "flag",
        "observation_datetime",
        "status",
        "alert_level",
        "alert_message",
        "loinc_code",
    },
    "visits": {
        "visit_id",
        "patient_id",
        "visit_date",
        "visit_type",
        "provider_name",
        "chief_complaint",
    },
    "medications": {
        "id",
        "patient_id",
        "medication_name",
        "dosage",
        "frequency",
        "start_date",
        "end_date",
        "status",
    },
    "diagnoses": {
        "id",
        "patient_id",
        "diagnosis_code",
        "diagnosis_name",
        "diagnosis_date",
        "status",
    },
}

NOTE_TEXT_COLUMNS: Dict[str, Set[str]] = {
    "observations": {"value_raw"},
}

SAFE_FUNCTIONS: Set[str] = {
    "abs",
    "avg",
    "coalesce",
    "count",
    "date",
    "datetime",
    "ifnull",
    "instr",
    "length",
    "lower",
    "ltrim",
    "max",
    "min",
    "nullif",
    "round",
    "rtrim",
    "strftime",
    "substr",
    "substring",
    "sum",
    "trim",
    "upper",
    "replace",
}

FORBIDDEN_KEYWORDS: Set[str] = {
    "alter",
    "analyze",
    "attach",
    "create",
    "delete",
    "detach",
    "drop",
    "exec",
    "execute",
    "grant",
    "insert",
    "pragma",
    "reindex",
    "replace",
    "revoke",
    "truncate",
    "update",
    "vacuum",
}

DISALLOWED_SELECT_KEYWORDS: Set[str] = {
    "except",
    "intersect",
    "union",
    "with",
}

SQL_KEYWORDS: Set[str] = {
    "and",
    "as",
    "asc",
    "between",
    "by",
    "case",
    "collate",
    "desc",
    "distinct",
    "else",
    "end",
    "escape",
    "from",
    "glob",
    "group",
    "having",
    "in",
    "is",
    "join",
    "left",
    "like",
    "limit",
    "not",
    "null",
    "on",
    "or",
    "order",
    "outer",
    "right",
    "select",
    "then",
    "when",
    "where",
}

TABLE_REF_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)"
    r"(?:\s+(?:AS\s+)?"
    r"(?!ON\b|WHERE\b|JOIN\b|LEFT\b|RIGHT\b|INNER\b|OUTER\b|GROUP\b|ORDER\b|HAVING\b|LIMIT\b)"
    r"([A-Za-z_][A-Za-z0-9_]*))?",
    re.IGNORECASE,
)
QUALIFIED_COLUMN_RE = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*([A-Za-z_][A-Za-z0-9_]*|\*)\b",
    re.IGNORECASE,
)
FUNCTION_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", re.IGNORECASE)
IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
LIMIT_RE = re.compile(r"\bLIMIT\s+(\d+)\b", re.IGNORECASE)


@dataclass(frozen=True)
class SqlGuardResult:
    allowed: bool
    reason: str = ""
    sql: str = ""
    tables: List[str] = field(default_factory=list)
    columns: Dict[str, List[str]] = field(default_factory=dict)
    max_rows: int = 0
    limit_was_injected: bool = False
    limit_was_capped: bool = False


class SqlGuard:
    def __init__(
        self,
        *,
        schema: Optional[Mapping[str, Iterable[str]]] = None,
        blocked_tables: Optional[Iterable[str]] = None,
        safe_functions: Optional[Iterable[str]] = None,
    ) -> None:
        source_schema = schema or DEFAULT_ALLOWED_COLUMNS
        self.schema = {
            table.lower(): {column.lower() for column in columns}
            for table, columns in source_schema.items()
        }
        self.blocked_tables = {table.lower() for table in (blocked_tables or BLOCKED_TABLES)}
        self.safe_functions = {name.lower() for name in (safe_functions or SAFE_FUNCTIONS)}

    def validate(self, sql: str, grant: IntentGrant) -> SqlGuardResult:
        normalized = (sql or "").strip()
        if not normalized:
            return self._deny("empty query")

        preflight = self._preflight(normalized)
        if preflight:
            return self._deny(preflight)

        if grant.max_rows <= 0:
            return self._deny("grant.max_rows must be positive")

        allowed_tables = self._grant_tables(grant)
        if not allowed_tables:
            return self._deny("grant does not allow any readable tables")

        text_without_strings = _strip_string_literals(normalized)
        table_result = self._extract_tables(text_without_strings, allowed_tables)
        if isinstance(table_result, str):
            return self._deny(table_result)
        alias_to_table, tables = table_result

        function_error = self._validate_functions(text_without_strings)
        if function_error:
            return self._deny(function_error)

        allowed_columns = self._grant_columns(grant, tables)
        column_result = self._validate_columns(text_without_strings, alias_to_table, tables, allowed_columns)
        if isinstance(column_result, str):
            return self._deny(column_result)

        rewritten_sql, injected, capped, limit_error = _enforce_limit(normalized, grant.max_rows)
        if limit_error:
            return self._deny(limit_error)

        return SqlGuardResult(
            allowed=True,
            sql=rewritten_sql,
            tables=sorted(tables),
            columns={table: sorted(columns) for table, columns in sorted(column_result.items())},
            max_rows=grant.max_rows,
            limit_was_injected=injected,
            limit_was_capped=capped,
        )

    def _preflight(self, sql: str) -> str:
        upper = sql.upper()
        no_strings = _strip_string_literals(sql)
        lowered = no_strings.lower()

        if "--" in sql or "/*" in sql or "*/" in sql or "#" in sql:
            return "SQL comments are not allowed"
        if ";" in sql:
            return "semicolons and multiple statements are not allowed"
        if not re.match(r"^\s*SELECT\b", sql, re.IGNORECASE):
            return "exactly one SELECT statement is required"
        if len(re.findall(r"\bSELECT\b", no_strings, flags=re.IGNORECASE)) != 1:
            return "exactly one SELECT statement is required"

        for keyword in sorted(FORBIDDEN_KEYWORDS | DISALLOWED_SELECT_KEYWORDS):
            if re.search(rf"\b{re.escape(keyword)}\b", lowered, flags=re.IGNORECASE):
                return f"forbidden keyword: {keyword.upper()}"
        if "SELECT" not in upper:
            return "exactly one SELECT statement is required"
        return ""

    def _grant_tables(self, grant: IntentGrant) -> Set[str]:
        grant_tables = {table.lower() for table in grant.allowed_tables}
        return {
            table
            for table in grant_tables
            if table in self.schema or table in self.blocked_tables
        }

    def _grant_columns(self, grant: IntentGrant, tables: Set[str]) -> Dict[str, Set[str]]:
        policy: Dict[str, Set[str]] = {}
        grant_columns = {
            table.lower(): {column.lower() for column in columns}
            for table, columns in grant.allowed_columns.items()
        }
        for table in tables:
            static_columns = self.schema[table]
            if table in grant_columns and grant_columns[table]:
                policy[table] = static_columns & grant_columns[table]
            else:
                policy[table] = set(static_columns)
            if "note_read" not in set(grant.output_fields or []):
                policy[table] -= NOTE_TEXT_COLUMNS.get(table, set())
        return policy

    def _extract_tables(
        self,
        sql: str,
        allowed_tables: Set[str],
    ) -> Tuple[Dict[str, str], Set[str]] | str:
        alias_to_table: Dict[str, str] = {}
        tables: Set[str] = set()

        for match in TABLE_REF_RE.finditer(sql):
            table = match.group(1).lower()
            alias = (match.group(2) or "").lower()
            if table in self.blocked_tables:
                return f"blocked table: {table}"
            if table not in self.schema:
                return f"unknown table: {table}"
            if table not in allowed_tables:
                return f"table not allowed by grant: {table}"
            tables.add(table)
            alias_to_table[table] = table
            if alias and alias not in SQL_KEYWORDS:
                alias_to_table[alias] = table

        if not tables:
            return "query must read from an allowlisted table"
        return alias_to_table, tables

    def _validate_functions(self, sql: str) -> str:
        for match in FUNCTION_RE.finditer(sql):
            name = match.group(1).lower()
            if name in SQL_KEYWORDS:
                continue
            if name not in self.safe_functions:
                return f"function not allowed: {name}"
        return ""

    def _validate_columns(
        self,
        sql: str,
        alias_to_table: Dict[str, str],
        tables: Set[str],
        allowed_columns: Dict[str, Set[str]],
    ) -> Dict[str, Set[str]] | str:
        used: Dict[str, Set[str]] = {table: set() for table in tables}
        scratch = re.sub(r"\bCOUNT\s*\(\s*\*\s*\)", "COUNT_STAR()", sql, flags=re.IGNORECASE)
        if "*" in scratch:
            return "wildcard columns are not allowed"

        consumed_spans: List[Tuple[int, int]] = []
        for match in QUALIFIED_COLUMN_RE.finditer(sql):
            alias = match.group(1).lower()
            column = match.group(2).lower()
            if alias not in alias_to_table:
                return f"unknown table alias: {alias}"
            if column == "*":
                return "wildcard columns are not allowed"
            table = alias_to_table[alias]
            if column not in allowed_columns.get(table, set()):
                return f"column not allowed by grant: {table}.{column}"
            used[table].add(column)
            consumed_spans.append(match.span())

        ignored_identifiers = set(SQL_KEYWORDS) | set(alias_to_table) | set(tables) | self.safe_functions
        ignored_identifiers.update(_select_aliases(sql))

        for match in IDENTIFIER_RE.finditer(sql):
            token = match.group(0).lower()
            if token in ignored_identifiers:
                continue
            if any(start <= match.start() and match.end() <= end for start, end in consumed_spans):
                continue
            if _is_function_name(sql, match):
                continue

            matching_tables = [table for table in tables if token in allowed_columns.get(table, set())]
            if not matching_tables:
                schema_matches = [table for table in tables if token in self.schema.get(table, set())]
                if schema_matches:
                    return f"column not allowed by grant: {schema_matches[0]}.{token}"
                return f"unknown or non-allowlisted column: {token}"
            if len(matching_tables) > 1:
                return f"ambiguous unqualified column: {token}"
            used[matching_tables[0]].add(token)

        return used

    def _deny(self, reason: str) -> SqlGuardResult:
        return SqlGuardResult(allowed=False, reason=reason)


def validate_sql_select(sql: str, grant: IntentGrant) -> SqlGuardResult:
    return SqlGuard().validate(sql, grant)


def require_safe_sql(sql: str, grant: IntentGrant) -> str:
    result = validate_sql_select(sql, grant)
    if not result.allowed:
        raise ValueError(result.reason)
    return result.sql


def _strip_string_literals(sql: str) -> str:
    chars: List[str] = []
    index = 0
    in_single = False
    in_double = False
    while index < len(sql):
        char = sql[index]
        if in_single:
            if char == "'" and index + 1 < len(sql) and sql[index + 1] == "'":
                chars.extend("  ")
                index += 2
                continue
            if char == "'":
                in_single = False
            chars.append(" ")
        elif in_double:
            if char == '"' and index + 1 < len(sql) and sql[index + 1] == '"':
                chars.extend("  ")
                index += 2
                continue
            if char == '"':
                in_double = False
            chars.append(" ")
        else:
            if char == "'":
                in_single = True
                chars.append(" ")
            elif char == '"':
                in_double = True
                chars.append(" ")
            else:
                chars.append(char)
        index += 1
    return "".join(chars)


def _select_aliases(sql: str) -> Set[str]:
    aliases = set()
    for alias in re.findall(r"\bAS\s+([A-Za-z_][A-Za-z0-9_]*)\b", sql, flags=re.IGNORECASE):
        aliases.add(alias.lower())
    return aliases


def _is_function_name(sql: str, match: re.Match[str]) -> bool:
    index = match.end()
    while index < len(sql) and sql[index].isspace():
        index += 1
    return index < len(sql) and sql[index] == "("


def _enforce_limit(sql: str, max_rows: int) -> Tuple[str, bool, bool, str]:
    if re.search(r"\bLIMIT\s+\d+\s*,", sql, flags=re.IGNORECASE):
        return "", False, False, "comma-form LIMIT is not allowed"

    limit_matches = list(LIMIT_RE.finditer(sql))
    bare_limit_count = len(re.findall(r"\bLIMIT\b", sql, flags=re.IGNORECASE))
    if bare_limit_count != len(limit_matches):
        return "", False, False, "LIMIT must be a numeric literal"
    if len(limit_matches) > 1:
        return "", False, False, "multiple LIMIT clauses are not allowed"

    if not limit_matches:
        return f"{sql} LIMIT {max_rows}", True, False, ""

    match = limit_matches[0]
    current_limit = int(match.group(1))
    if current_limit <= max_rows:
        return sql, False, False, ""

    rewritten = f"{sql[:match.start(1)]}{max_rows}{sql[match.end(1):]}"
    return rewritten, False, True, ""
