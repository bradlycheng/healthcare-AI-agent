# app/hl7_parser.py

from typing import Any, Dict, List, Optional, Tuple

from hl7apy.parser import parse_message
from hl7apy.core import Message


def _normalize_hl7_text(hl7_text: str) -> str:
    """
    Normalize HL7 text so that:
    - All line endings become '\r'
    - Empty lines are stripped

    This avoids hl7apy mis-reading MSH-12 (version) when the file uses
    inconsistent newlines.
    """
    normalized = hl7_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln for ln in normalized.split("\n") if ln.strip() != ""]

    if not lines:
        return ""

    return "\r".join(lines) + "\r"


def _safe_value(component: Any) -> str:
    """
    Safely get a human-readable string from an hl7apy component.

    - Unwraps .value chains (FN -> ST, etc.)
    - Falls back to .to_er7() if available
    - Falls back to str(...) as last resort
    """
    if component is None:
        return ""

    obj = component

    for _ in range(3):
        try:
            v = getattr(obj, "value", None)
        except Exception:
            v = None
        if v is None or v is obj:
            break
        obj = v

    if isinstance(obj, (str, int, float)):
        return str(obj)

    try:
        return obj.to_er7()
    except Exception:
        pass

    try:
        return str(obj)
    except Exception:
        return ""


def _format_units_ce(ce_u: Any) -> str:
    """
    OBX-6 is a CE (in v2.5.1). Units like `10^3/uL` become:
      CE.1 = 10
      CE.2 = 3/uL

    Your old code returned CE.1 only ("10").
    Fix: prefer full ER7 string first, then fall back to components.
    """
    if ce_u is None:
        return ""

    # Best: keep the original ER7 (preserves carets)
    try:
        er7 = ce_u.to_er7()
        if er7:
            return er7.strip()
    except Exception:
        pass

    # Fallback: stitch CE.1 and CE.2 if both exist
    u1 = _safe_value(getattr(ce_u, "ce_1", ce_u)).strip()
    u2 = _safe_value(getattr(ce_u, "ce_2", "")).strip()
    if u1 and u2:
        return f"{u1}^{u2}"
    return u1 or u2


def _parse_patient(msg: Message) -> Dict[str, Any]:
    patient: Dict[str, Any] = {
        "id": "patient-1",
        "first_name": "",
        "last_name": "",
        "dob": "",
        "sex": "",
    }

    pid = None
    for child in msg.children:
        if child.name == "PID":
            pid = child
            break

    if pid is None:
        return patient

    try:
        pid_3 = pid.pid_3
        if pid_3 and len(pid_3) > 0:
            cx = pid_3[0]
            patient["id"] = _safe_value(cx)
    except Exception:
        pass

    try:
        xpn_list = pid.pid_5
        if xpn_list and len(xpn_list) > 0:
            xpn = xpn_list[0]

            try:
                family_name = getattr(xpn, "family_name", None)
                patient["last_name"] = _safe_value(family_name)
            except Exception:
                pass

            try:
                given_name = getattr(xpn, "given_name", None)
                patient["first_name"] = _safe_value(given_name)
            except Exception:
                pass
    except Exception:
        pass

    try:
        ts = pid.pid_7
        patient["dob"] = _safe_value(ts)
    except Exception:
        pass

    try:
        patient["sex"] = _safe_value(pid.pid_8)
    except Exception:
        pass

    return patient


def _parse_reference_range(ref_str: str) -> Tuple[Optional[str], Optional[str]]:
    s = (ref_str or "").strip()
    if not s:
        return None, None

    if "-" in s:
        lo, hi = s.split("-", 1)
        lo = lo.strip() or None
        hi = hi.strip() or None
        return lo, hi

    return None, s


def _parse_value(value_raw: str) -> Any:
    s = (value_raw or "").strip()
    if not s:
        return ""

    try:
        if "." in s:
            return float(s)
        return int(s)
    except ValueError:
        return s


def _parse_observations(msg: Message) -> List[Dict[str, Any]]:
    observations: List[Dict[str, Any]] = []

    for child in msg.children:
        if child.name != "OBX":
            continue
        obx = child

        code = ""
        display = ""
        try:
            ce = obx.obx_3
            try:
                code = _safe_value(getattr(ce, "ce_1", ce))
            except Exception:
                pass
            try:
                display = _safe_value(getattr(ce, "ce_2", ce))
            except Exception:
                pass
        except Exception:
            pass

        if not display:
            display = code

        value_raw = ""
        try:
            if obx.obx_5 and len(obx.obx_5) > 0:
                comp = obx.obx_5[0]
                value_raw = _safe_value(comp)
        except Exception:
            pass

        value_parsed = _parse_value(value_raw)

        # ✅ FIXED OBX-6: preserve units like `10^3/uL` (don’t truncate to "10")
        unit = ""
        try:
            ce_u = obx.obx_6
            unit = _format_units_ce(ce_u)
        except Exception:
            pass

        ref_low: Optional[str] = None
        ref_high: Optional[str] = None
        try:
            ref_str = _safe_value(obx.obx_7)
            ref_low, ref_high = _parse_reference_range(ref_str)
        except Exception:
            pass

        flag = ""
        try:
            flag = _safe_value(obx.obx_8).strip()
        except Exception:
            pass

        status = ""
        try:
            status = _safe_value(obx.obx_11).strip()
        except Exception:
            pass

        obs_dt = ""
        try:
            ts = obx.obx_14
            obs_dt = _safe_value(ts)
        except Exception:
            pass

        observations.append(
            {
                "code": code,
                "display": display,
                "value": value_parsed,
                "unit": unit,
                "reference_low": ref_low,
                "reference_high": ref_high,
                "flag": flag,
                "observation_datetime": obs_dt,
                "status": status,
            }
        )

    return observations


def parse_oru(hl7_text: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    normalized = _normalize_hl7_text(hl7_text)
    msg = parse_message(normalized, find_groups=False)

    patient = _parse_patient(msg)
    structured_observations = _parse_observations(msg)

    return patient, structured_observations
