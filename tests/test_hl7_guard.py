import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.hl7_guard import Hl7GuardConfig, validate_hl7_message


VALID_ORU = "\r".join(
    [
        "MSH|^~\\&|LAB|HOSP|APP|FAC|202501010000||ORU^R01|MSG1|P|2.5.1",
        "PID|1||P123||Doe^Jane||19800101|F",
        "OBR|1||ORD1|CBC^Complete blood count",
        "OBX|1|NM|789-8^Erythrocytes||4.5|10^6/uL|4.0-5.2|N|||F",
        "NTE|1|L|Continue metformin and order repeat BMP in two weeks",
    ]
) + "\r"


def error_codes(result):
    return {error.code for error in result.errors}


def test_validate_hl7_message_accepts_valid_oru_and_normal_clinical_note():
    result = validate_hl7_message(VALID_ORU)

    assert result.ok is True
    assert result.errors == []
    assert result.metadata["pid_count"] == 1
    assert result.metadata["obr_count"] == 1
    assert result.metadata["obx_count"] == 1
    assert result.metadata["note_field_count"] == 1


def test_validate_hl7_message_rejects_null_byte():
    result = validate_hl7_message(VALID_ORU.replace("Doe", "Do\x00e"))

    assert result.ok is False
    assert "hl7_null_byte" in error_codes(result)


def test_validate_hl7_message_requires_first_segment_msh():
    result = validate_hl7_message("EVN|junk\r" + VALID_ORU)

    assert result.ok is False
    assert "hl7_first_segment_not_msh" in error_codes(result)


def test_validate_hl7_message_requires_oru_message_type():
    result = validate_hl7_message(VALID_ORU.replace("ORU^R01", "ADT^A01"))

    assert result.ok is False
    assert "hl7_not_oru" in error_codes(result)


def test_validate_hl7_message_requires_pid():
    result = validate_hl7_message(VALID_ORU.replace("PID|1||P123||Doe^Jane||19800101|F\r", ""))

    assert result.ok is False
    assert "hl7_missing_pid" in error_codes(result)


def test_validate_hl7_message_requires_obr_or_obx_segment():
    hl7 = "\r".join(
        [
            "MSH|^~\\&|LAB|HOSP|APP|FAC|202501010000||ORU^R01|MSG1|P|2.5.1",
            "PID|1||P123||Doe^Jane||19800101|F",
            "NTE|1|L|Patient asks about diet",
        ]
    )

    result = validate_hl7_message(hl7)

    assert result.ok is False
    assert "hl7_missing_result_segment" in error_codes(result)


def test_validate_hl7_message_enforces_message_segment_field_and_note_caps():
    cfg = Hl7GuardConfig(
        max_message_chars=120,
        max_segments=3,
        max_segment_chars=50,
        max_fields_per_segment=6,
        max_field_chars=10,
        max_note_chars=12,
    )

    result = validate_hl7_message(VALID_ORU, config=cfg)

    codes = error_codes(result)
    assert "hl7_message_too_large" in codes
    assert "hl7_too_many_segments" in codes
    assert "hl7_segment_too_large" in codes
    assert "hl7_too_many_fields" in codes
    assert "hl7_field_too_large" in codes
    assert "hl7_note_too_large" in codes


def test_validate_hl7_message_denies_sql_like_nte3():
    hl7 = VALID_ORU.replace(
        "Continue metformin and order repeat BMP in two weeks",
        "DROP TABLE hl7_messages",
    )

    result = validate_hl7_message(hl7)

    assert result.ok is False
    assert "hl7_note_sql_like" in error_codes(result)


def test_validate_hl7_message_denies_sql_like_text_obx5():
    hl7 = "\r".join(
        [
            "MSH|^~\\&|LAB|HOSP|APP|FAC|202501010000||ORU^R01|MSG1|P|2.5.1",
            "PID|1||P123||Doe^Jane||19800101|F",
            "OBX|1|TX|NOTE^Clinical note||UNION SELECT password FROM users||||||F",
        ]
    )

    result = validate_hl7_message(hl7)

    assert result.ok is False
    assert "hl7_note_sql_like" in error_codes(result)


def test_validate_hl7_message_does_not_apply_sql_note_policy_to_numeric_obx5():
    hl7 = "\r".join(
        [
            "MSH|^~\\&|LAB|HOSP|APP|FAC|202501010000||ORU^R01|MSG1|P|2.5.1",
            "PID|1||P123||Doe^Jane||19800101|F",
            "OBX|1|NM|1234^Synthetic lab||SELECT 1 FROM dual||||||F",
        ]
    )

    result = validate_hl7_message(hl7)

    assert "hl7_note_sql_like" not in error_codes(result)
