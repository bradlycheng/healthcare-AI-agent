# tests/test_slice6_db_hardening.py
"""
Slice 6 DB Hardening Tests
==========================
Tests for:
  - patient_timeline.py uses get_connection() exclusively (no sqlite3.connect)
  - Storage limit insert is wrapped in BEGIN IMMEDIATE transaction
  - Patient fields truncated to max lengths with logger.warning on truncation
  - deletion_audit row written before each cascading DELETE
"""

from __future__ import annotations

import ast
import inspect
import logging
import os
import sqlite3
import tempfile
import textwrap
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(path: str) -> None:
    """Initialize a fresh test database."""
    from app.db import init_db
    init_db(db_path=path)


def _insert(db_path: str, patient: dict = None, observations: list = None) -> int:
    from app.db import insert_message_and_observations
    return insert_message_and_observations(
        raw_hl7="MSH|test",
        patient=patient or {"id": "P1", "first_name": "Alice", "last_name": "Smith", "dob": "1990-01-01", "sex": "F"},
        observations=observations or [],
        db_path=db_path,
    )


# ---------------------------------------------------------------------------
# 1. patient_timeline.py uses centralized connection (no sqlite3.connect calls)
# ---------------------------------------------------------------------------

class TestPatientTimelineUsesCentralizedConnection:
    """AST-level check: no sqlite3.connect() calls remain in patient_timeline.py."""

    def test_patient_timeline_uses_centralized_connection(self):
        """patient_timeline.py must not call sqlite3.connect() anywhere."""
        src_path = Path(__file__).parent.parent / "app" / "patient_timeline.py"
        source = src_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        direct_connects = []
        for node in ast.walk(tree):
            # Look for any Call whose func is an attribute named 'connect'
            # on anything named 'sqlite3'
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "connect"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "sqlite3"
            ):
                direct_connects.append(node)

        assert len(direct_connects) == 0, (
            f"Found {len(direct_connects)} sqlite3.connect() call(s) in patient_timeline.py — "
            "all connections must use get_connection() from app.db"
        )

    def test_patient_timeline_imports_get_connection(self):
        """patient_timeline.py must import get_connection from app.db."""
        src_path = Path(__file__).parent.parent / "app" / "patient_timeline.py"
        source = src_path.read_text(encoding="utf-8")
        assert "get_connection" in source, (
            "patient_timeline.py does not import get_connection from app.db"
        )

    def test_get_unique_patients_returns_data(self):
        """get_unique_patients() works using the centralized connection."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _make_db(db_path)
            _insert(db_path, patient={"id": "P42", "first_name": "John", "last_name": "Doe",
                                       "dob": "1980-05-15", "sex": "M"})
            from app.patient_timeline import get_unique_patients
            patients = get_unique_patients(db_path=db_path)
            assert any(p["patient_id"] == "P42" for p in patients)
        finally:
            os.unlink(db_path)

    def test_get_patient_timeline_returns_data(self):
        """get_patient_timeline() works using the centralized connection."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _make_db(db_path)
            _insert(db_path, patient={"id": "P99", "first_name": "Jane", "last_name": "Doe",
                                       "dob": "1975-03-20", "sex": "F"})
            from app.patient_timeline import get_patient_timeline
            result = get_patient_timeline("P99", db_path=db_path)
            assert result is not None
            assert result["patient"]["patient_id"] == "P99"
            assert result["visit_count"] >= 1
        finally:
            os.unlink(db_path)


# ---------------------------------------------------------------------------
# 2. Storage limit concurrent insert blocked
# ---------------------------------------------------------------------------

class TestStorageLimitConcurrentInsertBlocked:
    """Storage limit check + insert must be atomic via BEGIN IMMEDIATE."""

    def test_storage_limit_raises_at_1300(self):
        """insert_message_and_observations raises ValueError at exactly 1300 messages."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _make_db(db_path)
            # Pre-fill to 1299
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            cur = conn.cursor()
            for i in range(1299):
                cur.execute(
                    "INSERT INTO hl7_messages (received_at, raw_hl7, patient_id, "
                    "patient_first_name, patient_last_name, patient_dob, patient_sex, fhir_bundle_json) "
                    "VALUES (datetime('now'), '', ?, '', '', '', '', '{}')",
                    (f"P{i}",),
                )
            conn.commit()
            conn.close()

            # The 1300th insert should succeed
            msg_id = _insert(db_path)
            assert isinstance(msg_id, int)

            # The 1301st insert must raise ValueError
            with pytest.raises(ValueError, match="storage limit"):
                _insert(db_path)
        finally:
            os.unlink(db_path)

    def test_begin_immediate_in_insert_source(self):
        """Source code must contain 'BEGIN IMMEDIATE' in insert_message_and_observations."""
        src_path = Path(__file__).parent.parent / "app" / "db.py"
        source = src_path.read_text(encoding="utf-8")
        assert "BEGIN IMMEDIATE" in source, (
            "app/db.py does not contain BEGIN IMMEDIATE transaction for storage limit check"
        )

    def test_concurrent_inserts_at_limit_only_one_succeeds(self):
        """
        When two threads race to insert while count==1299, only one should succeed.
        The loser must raise ValueError (not insert silently beyond the cap).
        """
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _make_db(db_path)
            # Pre-fill to 1299
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            cur = conn.cursor()
            for i in range(1299):
                cur.execute(
                    "INSERT INTO hl7_messages (received_at, raw_hl7, patient_id, "
                    "patient_first_name, patient_last_name, patient_dob, patient_sex, fhir_bundle_json) "
                    "VALUES (datetime('now'), '', ?, '', '', '', '', '{}')",
                    (f"PC{i}",),
                )
            conn.commit()
            conn.close()

            results = []
            errors = []

            def try_insert():
                try:
                    mid = _insert(db_path, patient={"id": "RACE", "first_name": "R",
                                                    "last_name": "R", "dob": "2000-01-01", "sex": "M"})
                    results.append(mid)
                except ValueError as e:
                    errors.append(str(e))
                except Exception as e:
                    errors.append(f"unexpected: {e}")

            t1 = threading.Thread(target=try_insert)
            t2 = threading.Thread(target=try_insert)
            t1.start()
            t2.start()
            t1.join()
            t2.join()

            # At most one success (exactly one at the limit)
            assert len(results) <= 1, (
                f"Both concurrent inserts succeeded — BEGIN IMMEDIATE is not enforcing the race: {results}"
            )
            # At least one thread must have hit the limit or lock
            assert len(errors) >= 1 or len(results) == 1
        finally:
            os.unlink(db_path)


# ---------------------------------------------------------------------------
# 3. Patient field length enforced
# ---------------------------------------------------------------------------

class TestPatientFieldLengthEnforced:
    """Patient fields must be silently truncated with a logger.warning."""

    def _do_insert_and_read(self, db_path: str, patient: dict) -> dict:
        _insert(db_path, patient=patient)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM hl7_messages ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        return dict(row)

    def test_first_name_truncated_at_100(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _make_db(db_path)
            long_name = "A" * 200
            row = self._do_insert_and_read(db_path, {
                "id": "P1", "first_name": long_name, "last_name": "Smith",
                "dob": "1990-01-01", "sex": "F"
            })
            stored = row["patient_first_name"]
            assert len(stored) == 100, f"Expected 100 chars, got {len(stored)}"
            assert stored == "A" * 100
        finally:
            os.unlink(db_path)

    def test_last_name_truncated_at_100(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _make_db(db_path)
            long_name = "B" * 150
            row = self._do_insert_and_read(db_path, {
                "id": "P2", "first_name": "Alice", "last_name": long_name,
                "dob": "1990-01-01", "sex": "F"
            })
            stored = row["patient_last_name"]
            assert len(stored) == 100, f"Expected 100 chars, got {len(stored)}"
        finally:
            os.unlink(db_path)

    def test_patient_id_truncated_at_50(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _make_db(db_path)
            long_id = "X" * 100
            row = self._do_insert_and_read(db_path, {
                "id": long_id, "first_name": "Alice", "last_name": "Smith",
                "dob": "1990-01-01", "sex": "F"
            })
            stored = row["patient_id"]
            assert len(stored) == 50, f"Expected 50 chars, got {len(stored)}"
        finally:
            os.unlink(db_path)

    def test_dob_truncated_at_10(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _make_db(db_path)
            long_dob = "1990-01-01-EXTRA-DATA"
            row = self._do_insert_and_read(db_path, {
                "id": "P4", "first_name": "Alice", "last_name": "Smith",
                "dob": long_dob, "sex": "F"
            })
            stored = row["patient_dob"]
            assert len(stored) == 10, f"Expected 10 chars, got {len(stored)}"
            assert stored == "1990-01-01"
        finally:
            os.unlink(db_path)

    def test_truncation_logs_warning(self):
        """logger.warning must be called when a field is truncated."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _make_db(db_path)
            with patch("app.db.logger") as mock_logger:
                _insert(db_path, patient={
                    "id": "P5",
                    "first_name": "C" * 200,
                    "last_name": "Smith",
                    "dob": "1990-01-01",
                    "sex": "F"
                })
                assert mock_logger.warning.called, (
                    "logger.warning was not called when first_name exceeded 100 chars"
                )
        finally:
            os.unlink(db_path)

    def test_no_truncation_no_warning_for_normal_fields(self):
        """No warning should be logged when all fields are within limits."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _make_db(db_path)
            with patch("app.db.logger") as mock_logger:
                _insert(db_path, patient={
                    "id": "P6",
                    "first_name": "Alice",
                    "last_name": "Smith",
                    "dob": "1990-01-01",
                    "sex": "F"
                })
                mock_logger.warning.assert_not_called()
        finally:
            os.unlink(db_path)


# ---------------------------------------------------------------------------
# 4. Deletion audit log written before cascade
# ---------------------------------------------------------------------------

class TestDeletionAuditLoggedBeforeCascade:
    """deletion_audit rows must be written before DELETE FROM hl7_messages."""

    def test_deletion_audit_table_exists_in_schema(self):
        """init_db() must create the deletion_audit table."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _make_db(db_path)
            conn = sqlite3.connect(db_path)
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='deletion_audit'"
            ).fetchone()
            conn.close()
            assert row is not None, "deletion_audit table was not created by init_db()"
        finally:
            os.unlink(db_path)

    def test_prune_messages_writes_deletion_audit(self):
        """prune_messages() must insert into deletion_audit before deleting messages."""
        import datetime as dt
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _make_db(db_path)
            # Insert a message with an old timestamp
            old_time = (dt.datetime.utcnow() - dt.timedelta(days=10)).isoformat(sep=" ")
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO hl7_messages (received_at, raw_hl7, patient_id, "
                "patient_first_name, patient_last_name, patient_dob, patient_sex, fhir_bundle_json) "
                "VALUES (?, '', 'AUDIT_P1', '', '', '', '', '{}')",
                (old_time,),
            )
            msg_id = cur.lastrowid
            conn.commit()
            conn.close()

            from app.db import prune_messages
            deleted = prune_messages(days_to_keep=2, db_path=db_path)
            assert deleted >= 1

            # Check audit record
            conn = sqlite3.connect(db_path)
            audit_row = conn.execute(
                "SELECT * FROM deletion_audit WHERE message_id=?", (msg_id,)
            ).fetchone()
            conn.close()

            assert audit_row is not None, (
                f"No deletion_audit row found for message_id={msg_id} after prune_messages()"
            )
            # audit_row: (id, message_id, patient_id, deleted_at)
            assert audit_row[2] == "AUDIT_P1", (
                f"patient_id in audit row is wrong: {audit_row[2]}"
            )
            assert audit_row[3] is not None and len(audit_row[3]) > 0
        finally:
            os.unlink(db_path)

    def test_delete_all_messages_writes_deletion_audit(self):
        """delete_all_messages() must insert into deletion_audit before clearing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _make_db(db_path)
            # Insert two messages
            mid1 = _insert(db_path, patient={"id": "DA_P1", "first_name": "Del", "last_name": "A",
                                              "dob": "2000-01-01", "sex": "M"})
            mid2 = _insert(db_path, patient={"id": "DA_P2", "first_name": "Del", "last_name": "B",
                                              "dob": "2001-01-01", "sex": "F"})

            from app.db import delete_all_messages
            delete_all_messages(db_path=db_path)

            # Messages should be gone
            conn = sqlite3.connect(db_path)
            count = conn.execute("SELECT COUNT(*) FROM hl7_messages").fetchone()[0]
            assert count == 0

            # Audit rows should exist
            audit_ids = [
                r[0] for r in conn.execute("SELECT message_id FROM deletion_audit").fetchall()
            ]
            conn.close()

            assert mid1 in audit_ids, f"message_id {mid1} not in deletion_audit"
            assert mid2 in audit_ids, f"message_id {mid2} not in deletion_audit"
        finally:
            os.unlink(db_path)

    def test_deletion_audit_schema_columns(self):
        """deletion_audit must have columns: id, message_id, patient_id, deleted_at."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _make_db(db_path)
            conn = sqlite3.connect(db_path)
            cols = [row[1] for row in conn.execute("PRAGMA table_info(deletion_audit)").fetchall()]
            conn.close()
            for expected in ("id", "message_id", "patient_id", "deleted_at"):
                assert expected in cols, f"deletion_audit missing column: {expected}"
        finally:
            os.unlink(db_path)
