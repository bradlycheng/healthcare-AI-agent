# app/mllp_server.py
from __future__ import annotations

import socket
import threading
from typing import Tuple

from .agent import run_oru_pipeline
from .hl7_msh import parse_msh, build_ack
from .security_validation import emit_governance_event, new_request_id

VT = b"\x0b"  # <SB>
FS = b"\x1c"  # <EB>
CR = b"\x0d"  # <CR>
MLLP_SESSION_ID = "mllp_server"


def _recv_mllp_message(conn: socket.socket) -> str:
    """
    Read one MLLP-framed message.
    Returns HL7 text (no MLLP wrapper).
    """
    buf = b""
    while True:
        chunk = conn.recv(4096)
        if not chunk:
            raise ConnectionError("client disconnected")
        buf += chunk

        end = buf.find(FS + CR)
        if end != -1:
            frame = buf[:end]
            # Strip leading VT if present
            if frame.startswith(VT):
                frame = frame[1:]
            return frame.decode("utf-8", errors="replace")


def _send_mllp(conn: socket.socket, hl7_text: str) -> None:
    payload = VT + hl7_text.encode("utf-8") + FS + CR
    conn.sendall(payload)


def process_mllp_hl7(hl7: str) -> None:
    """Process MLLP HL7 through the same deterministic ingress guard."""
    from .hl7_guard import validate_hl7_message

    request_id = new_request_id()
    guard_result = validate_hl7_message(hl7)
    if not guard_result.ok:
        emit_governance_event(
            request_id=request_id,
            session_id=MLLP_SESSION_ID,
            component="mllp.ingest",
            action="DENY",
            reason_code="hl7_guard_denied",
            payload={
                "errors": [issue.code for issue in guard_result.errors],
                "metadata": guard_result.metadata,
            },
        )
        raise ValueError("Invalid HL7 message.")

    run_oru_pipeline(hl7)
    emit_governance_event(
        request_id=request_id,
        session_id=MLLP_SESSION_ID,
        component="mllp.ingest",
        action="ALLOW",
        reason_code="mllp_hl7_persisted",
        payload={"segment_count": guard_result.metadata.get("segment_count", 0)},
    )


def _handle_client(conn: socket.socket, addr: Tuple[str, int]) -> None:
    try:
        while True:
            hl7 = _recv_mllp_message(conn)

            msh = parse_msh(hl7)
            if not msh or not msh.message_control_id:
                # Can't build a correct ACK; return AE
                ack = "MSH|^~\\&|||||||ACK||P|2.5.1\rMSA|AE|\r"
                _send_mllp(conn, ack)
                continue

            try:
                # Ingest + store
                process_mllp_hl7(hl7)
                ack = build_ack(msh, ack_code="AA")
            except Exception as e:
                ack = build_ack(msh, ack_code="AE", text=str(e)[:200])

            _send_mllp(conn, ack)

    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def serve(host: str = "0.0.0.0", port: int = 2575) -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, port))
    s.listen(20)
    print(f"MLLP listening on {host}:{port}")

    while True:
        conn, addr = s.accept()
        t = threading.Thread(target=_handle_client, args=(conn, addr), daemon=True)
        t.start()


if __name__ == "__main__":
    serve()
