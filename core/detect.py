from __future__ import annotations

from .types import DocType


def detect_doc_type(raw_text: str) -> DocType:
    up = (raw_text or "").upper()

    # PSP strong signals
    if "PSP DETAILED REPORT" in up:
        return "PSP"
    if "FEDERAL MOTOR CARRIER SAFETY ADMINISTRATION" in up:
        return "PSP"
    if "VIOLATION SUMMARY" in up and "CRASH DETAILS" in up:
        return "PSP"

    # MVR strong signals
    if "MEDICAL CERTIFICATE" in up:
        return "MVR"
    if "**** END OF DRIVING RECORD" in up:
        return "MVR"
    if "VIOL/SUS" in up:
        return "MVR"
    if "CDL STATUS" in up and "LICENSE STATUS" in up:
        return "MVR"

    # fallback
    if "RESTRICTIONS" in up and "ENDORSEMENTS" in up:
        return "MVR"

    return "UNKNOWN"
