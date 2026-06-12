from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from core.types import DocType

DOC_PSP: DocType = "PSP"

PSP_DATE_RE = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")
PSP_TRAILING_COUNTS_RE = re.compile(r"\s+\d+\s+\d+\s*$")

PSP_HANDHELD_PHONE_RE = re.compile(
    r"\bDRIVER\s*-\s*USING\s+A\s+HAND-HELD\s+MOBILE\s+TELEPHONE\b",
    re.IGNORECASE
)
PSP_STATE_CITATION_RE = re.compile(r"^\s*State\s+Citation\s+Result\s*:\s*(.+)\s*$", re.IGNORECASE)


def _psp_parse_int_after(label: str, text_upper: str) -> Tuple[int, Optional[str]]:
    m = re.search(rf"{re.escape(label)}\s*:\s*(\d+)", text_upper, flags=re.IGNORECASE)
    if not m:
        return 0, None
    return int(m.group(1)), m.group(0)


def _psp_norm_text(s: str) -> str:
    s2 = re.sub(r"\s+", " ", (s or "")).strip()
    s2 = PSP_TRAILING_COUNTS_RE.sub("", s2).strip()
    return s2


def _psp_parse_crash_dates(lines: List[str], crash_count: int) -> Tuple[List[str], Dict[str, Any]]:
    dbg: Dict[str, Any] = {
        "crash_count": crash_count,
        "found_crash_details_header": False,
        "start_line": None,
        "end_on_line": None,
        "dates": [],
        "dates_source_lines": [],
    }

    if crash_count <= 0:
        return [], dbg

    in_crash_details = False
    crash_dates: List[str] = []

    for i, ln in enumerate(lines):
        up_line = ln.upper()

        if "CRASH DETAILS" in up_line:
            in_crash_details = True
            dbg["found_crash_details_header"] = True
            dbg["start_line"] = i + 1
            continue

        if in_crash_details and "INSPECTION ACTIVITY" in up_line:
            dbg["end_on_line"] = i + 1
            break

        if not in_crash_details:
            continue

        # Row starts with index then date: "1  09/21/2024 ..."
        m = re.match(r"^\s*\d+\s+(\d{2}/\d{2}/\d{4})\b", ln.strip())
        if m:
            crash_dates.append(m.group(1))
            dbg["dates_source_lines"].append({"line": i + 1, "text": ln})

    crash_dates = list(dict.fromkeys(crash_dates))
    dbg["dates"] = crash_dates
    return crash_dates, dbg


def _psp_parse_violations_from_summary(lines: List[str]) -> Tuple[List[str], Dict[str, Any]]:
    dbg: Dict[str, Any] = {
        "found_violation_summary": False,
        "start_line": None,
        "stop_on_line": None,
        "items": [],
        "skipped_noise_lines": 0,
        "row_start_rule": "must_start_with_digit_code",
    }

    violations: List[str] = []
    in_block = False

    # MUST start with a code (digit...) so we don't accidentally scrape random footer numbers etc.
    row_start_re = re.compile(r"^\s*\d[0-9A-Z.\-()/]*\s+.+", re.IGNORECASE)
    counts_line_re = re.compile(r"^\s*\d+\s+\d+\s*$")
    leading_code_re = re.compile(r"^\s*\d[0-9A-Z.\-()/]*(?:\s+|\s*-\s*)", re.IGNORECASE)

    def is_noise(upper_line: str) -> bool:
        if not upper_line:
            return True
        if upper_line == "VIOLATIONS":
            return True
        if upper_line in {"VIOLATION #", "DESCRIPTION"}:
            return True
        if "VIOLATION #" in upper_line or "# OF VIOLATIONS" in upper_line:
            return True
        if ("OUT-OF-SERVICE" in upper_line) and ("VIOL" in upper_line):
            return True
        if "THE SUMMARY COUNTS AND RATES" in upper_line:
            return True
        # Footer / boilerplate lines that appear on every page
        if "PROPERLY DISPOSE" in upper_line:
            return True
        if "REPORT EXECUTED" in upper_line:
            return True
        if "MCMIS SNAPSHOT" in upper_line:
            return True
        if "INADVERTENT DISCLOSUREA" in upper_line or "INADVERTENT DISCLOSURE" in upper_line:
            return True
        if "HANDLE AND SECURE" in upper_line:
            return True
        if "NEGATIVELY AFFECT INDIVIDUALS" in upper_line:
            return True
        if "FMCSA-REPORTABLE CRASHES" in upper_line:
            return True
        if "PSP.FMCSA.DOT.GOV" in upper_line:
            return True
        # Page number lines like "1 of 2", "2 of 2"
        if re.fullmatch(r"\d+\s+OF\s+\d+", upper_line):
            return True
        return False

    current_parts: List[str] = []
    current_meta: Dict[str, Any] = {"start_line": None, "source_lines": []}

    def flush() -> None:
        nonlocal current_parts, current_meta
        if not current_parts:
            current_meta = {"start_line": None, "source_lines": []}
            return

        merged = " ".join(p.strip() for p in current_parts if p.strip())
        merged = _psp_norm_text(merged)
        merged = PSP_TRAILING_COUNTS_RE.sub("", merged).strip()

        if merged:
            violations.append(merged)
            dbg["items"].append({
                "text": merged,
                "start_line": current_meta.get("start_line"),
                "source_lines": current_meta.get("source_lines", []),
            })

        current_parts = []
        current_meta = {"start_line": None, "source_lines": []}

    for i, ln in enumerate(lines):
        upper_line = ln.upper().strip()

        if "VIOLATION SUMMARY" in upper_line:
            in_block = True
            dbg["found_violation_summary"] = True
            dbg["start_line"] = i + 1
            continue

        if not in_block:
            continue

        # NOTE: do NOT break on REPORT EXECUTED — it can appear as a
        # page footer in multi-page PDFs, with violations continuing
        # after it.  Instead, REPORT EXECUTED is filtered out as noise
        # by is_noise() above.

        if is_noise(upper_line):
            dbg["skipped_noise_lines"] += 1
            continue

        if counts_line_re.match(ln.strip()):
            flush()
            continue

        if row_start_re.match(ln):
            flush()
            clean = leading_code_re.sub("", ln).strip()
            clean = _psp_norm_text(clean)
            clean = PSP_TRAILING_COUNTS_RE.sub("", clean).strip()
            if clean:
                current_parts.append(clean)
                current_meta["start_line"] = i + 1
                current_meta["source_lines"].append({"line": i + 1, "text": ln})
            continue

        if ln.strip():
            current_parts.append(ln.strip())
            current_meta["source_lines"].append({"line": i + 1, "text": ln})

    flush()

    violations = list(dict.fromkeys(violations))
    return violations, dbg


def _psp_parse_extras(lines: List[str]) -> Tuple[List[str], Dict[str, Any]]:
    dbg: Dict[str, Any] = {
        "handheld_phone_found": False,
        "handheld_phone_line": None,
        "state_citation_results": [],
    }

    extras: List[str] = []
    raw_join = "\n".join(lines)

    if PSP_HANDHELD_PHONE_RE.search(raw_join):
        dbg["handheld_phone_found"] = True
        for i, ln in enumerate(lines):
            if PSP_HANDHELD_PHONE_RE.search(ln):
                dbg["handheld_phone_line"] = i + 1
                break
        extras.append("DRIVER - USING A HAND-HELD MOBILE TELEPHONE")

    for i, ln in enumerate(lines):
        m = PSP_STATE_CITATION_RE.match(ln)
        if m:
            txt = f"State Citation Result: {m.group(1).strip()}"
            extras.append(txt)
            dbg["state_citation_results"].append({"line": i + 1, "text": txt})

    extras = list(dict.fromkeys(extras))
    return extras, dbg


def parse_psp_with_debug(raw_text: str) -> Tuple[str, Dict[str, Any]]:
    text_upper = (raw_text or "").upper()
    lines = (raw_text or "").splitlines()

    dbg: Dict[str, Any] = {
        "doc_type": DOC_PSP,
        "detected_no_results": False,
        "no_results_phrase_found": None,
        "counts": {},
        "crash": {},
        "violations": {},
        "extras": {},
        "decision": None,
        "extras_dedup_applied": False,
    }

    if "NO CRASH OR INSPECTION RESULTS FOUND" in text_upper:
        dbg["detected_no_results"] = True
        dbg["no_results_phrase_found"] = "NO CRASH OR INSPECTION RESULTS FOUND"
        dbg["decision"] = "no_results"
        return "PSP:\nNo crash or inspection results found", dbg

    crash_count, crash_match = _psp_parse_int_after("# OF CRASHES", text_upper)
    driver_insp, insp_match = _psp_parse_int_after("DRIVER INSPECTIONS", text_upper)
    dbg["counts"] = {
        "crashes": crash_count,
        "driver_inspections": driver_insp,
        "crashes_match": crash_match,
        "driver_inspections_match": insp_match,
    }

    crash_dates, crash_dbg = _psp_parse_crash_dates(lines, crash_count)
    violations, viol_dbg = _psp_parse_violations_from_summary(lines)
    extras, extras_dbg = _psp_parse_extras(lines)

    # FIX: extras must not duplicate violations
    viol_norm = {v.strip().upper() for v in violations}
    before_extras = extras[:]
    extras = [e for e in extras if e.strip().upper() not in viol_norm]
    dbg["extras_dedup_applied"] = (before_extras != extras)

    dbg["crash"] = crash_dbg
    dbg["violations"] = viol_dbg
    dbg["extras"] = extras_dbg
    dbg["extras"]["filtered_out_as_duplicates"] = [e for e in before_extras if e not in extras]

    if crash_dates or violations or extras:
        out_lines: List[str] = ["PSP:"]
        if crash_dates:
            out_lines.append("Crash " + ", ".join(crash_dates))
        out_lines.extend(violations)
        out_lines.extend(extras)
        dbg["decision"] = "psp_findings"
        return "\n".join(out_lines), dbg

    dbg["decision"] = "clean_inspections"
    return "PSP:\nClean inspection", dbg
