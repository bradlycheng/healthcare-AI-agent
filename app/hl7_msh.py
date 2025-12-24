# app/hl7_msh.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MSH:
    field_sep: str
    encoding_chars: str
    sending_app: str
    sending_facility: str
    receiving_app: str
    receiving_facility: str
    message_datetime: str
    message_type: str
    message_control_id: str
    processing_id: str
    version: str


def parse_msh(hl7_text: str) -> Optional[MSH]:
    """
    Minimal MSH parser for ER7 HL7.
    Expects MSH as first segment. Returns None if missing/bad.
    """
    if not hl7_text:
        return None

    # Normalize to \r segments for safety
    text = hl7_text.replace("\r\n", "\n").replace("\r", "\n")
    segs = [s for s in text.split("\n") if s.strip()]
    if not segs:
        return None

    msh_line = None
    for s in segs:
        if s.startswith("MSH"):
            msh_line = s
            break
    if not msh_line or len(msh_line) < 4:
        return None

    field_sep = msh_line[3]  # MSH|... -> "|"
    parts = msh_line.split(field_sep)

    # MSH segment indexes are 1-based in HL7 docs; in split() they become 0-based:
    # parts[0]="MSH", parts[1]=MSH-2, parts[2]=MSH-3, ...
    def g(i: int) -> str:
        return parts[i] if i < len(parts) else ""

    return MSH(
        field_sep=field_sep,
        encoding_chars=g(1),
        sending_app=g(2),
        sending_facility=g(3),
        receiving_app=g(4),
        receiving_facility=g(5),
        message_datetime=g(6),
        message_type=g(8),
        message_control_id=g(9),
        processing_id=g(10),
        version=g(11),
    )


def build_ack(original: MSH, ack_code: str = "AA", text: str = "") -> str:
    """
    Build a basic HL7 ACK.
    Swaps sender/receiver, echoes version + control id.
    """
    fs = original.field_sep or "|"
    enc = original.encoding_chars or "^~\\&"

    # MSH-7 can be blank; you can set your own timestamp if you want.
    msh = [
        "MSH",
        fs.join(["", enc]),
    ]

    # Easier: build using fields then join with fs
    msh_fields = [
        "MSH",
        enc,                           # MSH-2
        original.receiving_app,        # MSH-3 (swap)
        original.receiving_facility,   # MSH-4
        original.sending_app,          # MSH-5
        original.sending_facility,     # MSH-6
        "",                            # MSH-7 (datetime)
        "",                            # MSH-8
        "ACK",                         # MSH-9
        original.message_control_id,   # MSH-10
        original.processing_id or "P", # MSH-11
        original.version or "2.5.1",   # MSH-12
    ]

    msa_fields = ["MSA", ack_code, original.message_control_id]
    if text:
        msa_fields.append(text)

    return fs.join(msh_fields) + "\r" + fs.join(msa_fields) + "\r"
