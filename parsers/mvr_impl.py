from __future__ import annotations

import re
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple


# ==========================================================
#                   MVR PARSER (ORIGINAL LOGIC)
# ==========================================================

DOC_MVR = "MVR"

DATE_RE = re.compile(r"\b(0[1-9]|1[0-2])/(0[1-9]|[12]\d|3[01])/\d{4}\b")

TWO_DATES_START = re.compile(
    r"^\s*(?P<d1>" + DATE_RE.pattern + r")\s+(?P<d2>" + DATE_RE.pattern + r")\b"
)
ONE_DATE_START = re.compile(r"^\s*(?P<d1>" + DATE_RE.pattern + r")\b")

ANY_DESC_LINE = re.compile(r"^\s*(?P<label>.*?Description)\s*=\s*(?P<rhs>.*)$", re.IGNORECASE)
RESTRICTIONS_LINE = re.compile(r"^\s*Restrictions\s*:\s*(?P<rhs>.*)\s*$", re.IGNORECASE)

MANUAL_WARNING_TEXT = (
    "Driver is not allowed to operate a truck with manual transmission until this restriction is removed"
)

TRIGGER_CHECKS = [
    "NO MANUAL TRANSMISSION CMV",
    "AUTO TRANSMISSION CMV",
    "PROHIBITS DRIVING A COMMERCIAL MOTOR VEHICLE EQUIPPED WITH A MANUAL TRANSMISSION",
    "AUTOMATIC TRANSMISSION ONLY",
]

AIR_BRAKE_TRIGGER = "NO AIR BRAKE EQUIPPED CMV"
AIR_BRAKE_WARNING_TEXT = "❌Driver can’t operate a semi truck with this restriction"

EXCEPTED_INTERSTATE_WARNING = (
    "If he wants to drive over the road, his self certification must be changed to Non-Excepted Interstate"
)

TAIL_INVALID_SEARCH_WINDOW = 520
TAIL_REQUIRE_CLASS_A = True
ALERT_PREFIX = "‼️"
TAIL_INVALID_STATUS_LOOKAHEAD = 40

MEDICAL_EXPIRED_TEXT = "❌Medical card expired"
MEDICAL_EXPIRES_SOON_PREFIX = "❌Medical card expires"
MEDICAL_EXPIRES_SOON_DAYS = 30

NO_CDL_TEXT = "❌No CDL information on the MVR"

SELF_CERT_HEADER = "🚨Self Certificate"
SELF_CERT_VALUE_INTRASTATE = "NON-EXCEPTED INTRASTATE"
SELF_CERT_INTRASTATE_EXPLAIN_PREFIX = (
    "‼️Intrastate means that the driver can operate only in the state of his CDL issuance - "
)
SELF_CERT_INTRASTATE_EXPLAIN_SUFFIX = (
    ".  If he wants to drive over the road his self-certification must be changed to Non-Excepted Interstate"
)


def clean_lines(text: str) -> List[str]:
    return [ln.rstrip() for ln in (text or "").splitlines() if ln.strip()]


def value_after_equals_or_next(lines: List[str], idx: int) -> str:
    ln = lines[idx]
    parts = ln.split("=", 1)
    val = parts[1].strip() if len(parts) == 2 else ""

    if val:
        return val

    if idx + 1 < len(lines):
        nxt = lines[idx + 1].strip()
        if nxt and "=" not in nxt and "Date" not in nxt:
            return nxt

    return ""


def parse_mmddyyyy(s: str) -> Optional[date]:
    try:
        return datetime.strptime(s, "%m/%d/%Y").date()
    except ValueError:
        return None


def sort_dates(dateset: Set[str]) -> List[str]:
    return sorted(dateset, key=lambda s: datetime.strptime(s, "%m/%d/%Y"))


def normalize_for_trigger(s: str) -> str:
    x = (s or "").upper()
    x = x.replace("-", " ")
    # Normalize common abbreviations so trigger checks stay stable
    x = re.sub(r"\bTRANS\.?\b", "TRANSMISSION", x)
    x = re.sub(r"\s+", " ", x).strip()
    return x


def build_line_map(page_texts: List[str]) -> Dict[str, Any]:
    page_lines: List[List[str]] = []
    global_lines: List[str] = []
    line_to_page: List[Tuple[int, int]] = []

    for pi, txt in enumerate(page_texts):
        lines = [ln.rstrip() for ln in (txt or "").splitlines() if ln.strip()]
        page_lines.append(lines)
        for li, ln in enumerate(lines):
            line_to_page.append((pi, li))
            global_lines.append(ln)

    return {
        "global_lines": global_lines,
        "line_to_page": line_to_page,
        "page_lines": page_lines,
    }


def line_ref(mapobj: Dict[str, Any], global_idx: Optional[int]) -> Optional[Dict[str, Any]]:
    if global_idx is None:
        return None
    glines = mapobj["global_lines"]
    l2p = mapobj["line_to_page"]
    if global_idx < 0 or global_idx >= len(glines):
        return None
    pi, li = l2p[global_idx]
    return {
        "global_idx": global_idx,
        "page": pi + 1,
        "line_in_page": li + 1,
        "text": glines[global_idx],
    }


def find_license_table_header(lines: List[str]) -> Optional[int]:
    for i, ln in enumerate(lines):
        if (
            re.search(r"\bClass\b", ln, flags=re.IGNORECASE)
            and re.search(r"\bType\b", ln, flags=re.IGNORECASE)
            and re.search(r"\bIssue\b", ln, flags=re.IGNORECASE)
            and re.search(r"\bExpiration\b", ln, flags=re.IGNORECASE)
            and re.search(r"\bStatus\b", ln, flags=re.IGNORECASE)
        ):
            return i
    return None


def find_top_license_end(lines: List[str], header_idx: int) -> int:
    for k in range(header_idx + 1, min(len(lines), header_idx + 250)):
        if re.search(r"\bMedical\s+certificate\b", lines[k], flags=re.IGNORECASE):
            return k
    return min(len(lines), header_idx + 100)


def get_top_license_slice(lines: List[str]) -> List[str]:
    header_idx = find_license_table_header(lines)
    if header_idx is None:
        return []
    end_idx = find_top_license_end(lines, header_idx)
    return lines[header_idx:end_idx]


def _extract_inline_status_value(line: str, label: str) -> Optional[str]:
    if not line:
        return None

    pat = re.compile(
        r"\b" + re.escape(label) + r"\b\s*:\s*([A-Za-z]+(?:\s+[A-Za-z]+){0,2})",
        re.IGNORECASE
    )
    m = pat.search(line)
    if not m:
        return None
    return m.group(1).strip()


def parse_header_status_with_debug(lines: List[str]) -> Dict[str, Any]:
    dbg: Dict[str, Any] = {
        "cdl_status_found": False,
        "cdl_status_value": None,
        "cdl_status_line_global_idx": None,
        "license_status_found": False,
        "license_status_value": None,
        "license_status_line_global_idx": None,
        "cdl_is_valid": False,
        "license_is_valid": False,
        "search_window": 700,
        "match_mode": "inline_search",
    }

    for i, ln in enumerate(lines[:dbg["search_window"]]):
        if not dbg["cdl_status_found"]:
            v = _extract_inline_status_value(ln, "CDL Status")
            if v:
                dbg["cdl_status_found"] = True
                dbg["cdl_status_value"] = v.upper()
                dbg["cdl_status_line_global_idx"] = i
                if v.strip().upper().startswith("VALID"):
                    dbg["cdl_is_valid"] = True

        if not dbg["license_status_found"]:
            v2 = _extract_inline_status_value(ln, "License Status")
            if v2:
                dbg["license_status_found"] = True
                dbg["license_status_value"] = v2.upper()
                dbg["license_status_line_global_idx"] = i
                if v2.strip().upper().startswith("VALID"):
                    dbg["license_is_valid"] = True

        if dbg["cdl_status_found"] and dbg["license_status_found"]:
            break

    return dbg


def parse_state_abbrev_with_debug(lines: List[str]) -> Tuple[Optional[str], Dict[str, Any]]:
    dbg: Dict[str, Any] = {"found": False}
    state_re_inline = re.compile(r"^\s*State\s*:\s*([A-Z]{2})\s*$", re.IGNORECASE)
    state_re_prefix = re.compile(r"^\s*State\s*:\s*$", re.IGNORECASE)

    for i, ln in enumerate(lines[:2500]):
        m = state_re_inline.match(ln)
        if m:
            st = m.group(1).upper()
            dbg["found"] = True
            dbg["state"] = st
            dbg["state_line_global_idx"] = i
            dbg["state_source"] = "inline"
            return st, dbg

        if state_re_prefix.match(ln):
            for j in range(i + 1, min(len(lines), i + 6)):
                nxt = lines[j].strip()
                if not nxt:
                    continue
                if re.fullmatch(r"[A-Za-z]{2}", nxt):
                    st = nxt.upper()
                    dbg["found"] = True
                    dbg["state"] = st
                    dbg["state_line_global_idx"] = j
                    dbg["state_source"] = "next_line"
                    dbg["state_label_line_global_idx"] = i
                    return st, dbg
            dbg["found"] = True
            dbg["state"] = None
            dbg["state_source"] = "label_only"
            dbg["state_label_line_global_idx"] = i
            return None, dbg

    return None, dbg


def top_license_has_class_a(lines: List[str]) -> Tuple[bool, Optional[int]]:
    header_idx = find_license_table_header(lines)
    if header_idx is None:
        return False, None

    top = get_top_license_slice(lines)
    if not top:
        return False, None

    cls_a_re = re.compile(r"\bCLS\s*A\b", re.IGNORECASE)
    class_a_re = re.compile(r"\bCLASS\s*A\b", re.IGNORECASE)

    for off, ln in enumerate(top[1:60], start=1):
        gi = header_idx + off

        if class_a_re.search(ln):
            return True, gi
        if re.match(r"^\s*A\b", ln, flags=re.IGNORECASE) and DATE_RE.search(ln):
            return True, gi

        if cls_a_re.search(ln) and DATE_RE.search(ln):
            return True, gi
        if re.search(r"^\s*CLS\s*A\s*[:\-]", ln, flags=re.IGNORECASE) and DATE_RE.search(ln):
            return True, gi

    return False, None


def parse_top_license_row_issue_date(lines: List[str]) -> Tuple[Optional[str], Optional[int]]:
    header_idx = find_license_table_header(lines)
    if header_idx is None:
        return None, None

    for j in range(header_idx + 1, min(len(lines), header_idx + 40)):
        row = lines[j].strip()

        if re.search(r"\bMedical\b", row, flags=re.IGNORECASE):
            break

        if re.search(r"\bRestrictions?\b", row, flags=re.IGNORECASE):
            continue
        if re.search(r"\bOriginal\s+Issue\b", row, flags=re.IGNORECASE):
            continue

        m2 = re.search(r"(" + DATE_RE.pattern + r")\s+(" + DATE_RE.pattern + r")", row)
        if m2:
            return m2.group(1), j

        if DATE_RE.search(row):
            continue

    return None, None


def _tail_slice(lines: List[str]) -> Tuple[List[str], int]:
    if len(lines) <= TAIL_INVALID_SEARCH_WINDOW:
        return lines[:], 0
    start = len(lines) - TAIL_INVALID_SEARCH_WINDOW
    return lines[-TAIL_INVALID_SEARCH_WINDOW:], start


def parse_tail_invalid_status_block(lines: List[str]) -> Tuple[List[str], Dict[str, Any]]:
    tail, tail_start = _tail_slice(lines)
    dbg: Dict[str, Any] = {"tail_start_global_idx": tail_start, "found": False}

    tail_join = " ".join(tail).upper()
    dbg["tail_has_class_a"] = ("CLASS A" in tail_join)

    if TAIL_REQUIRE_CLASS_A and "CLASS A" not in tail_join:
        return [], dbg

    cdl_re = re.compile(
        r"^\s*(?:" + DATE_RE.pattern + r"\s+)?CDL\s+Status(?:\s+Change\s+To)?\s+Invalid\b",
        re.IGNORECASE
    )
    lic_re = re.compile(
        r"^\s*(?:" + DATE_RE.pattern + r"\s+)?License\s+Status(?:\s+Change\s+To)?\s+Invalid\b",
        re.IGNORECASE
    )

    cdl_idx_local = None
    lic_idx_local = None

    for idx, ln in enumerate(tail):
        if cdl_idx_local is None and cdl_re.search(ln):
            cdl_idx_local = idx
        if lic_idx_local is None and lic_re.search(ln):
            lic_idx_local = idx

    if cdl_idx_local is not None:
        chosen_label = "CDL Status Invalid"
        chosen_idx_local = cdl_idx_local
    elif lic_idx_local is not None:
        chosen_label = "License Status Invalid"
        chosen_idx_local = lic_idx_local
    else:
        return [], dbg

    chosen_idx_global = tail_start + chosen_idx_local
    dbg["found"] = True
    dbg["chosen_label"] = chosen_label
    dbg["invalid_line_global_idx"] = chosen_idx_global

    status_value: Optional[str] = None
    status_re = re.compile(r"^\s*Status\s*:\s*(.+?)\s*$", re.IGNORECASE)
    new_status_re = re.compile(r"^\s*New\s+Status\s+Value\s*:\s*(.+?)\s*$", re.IGNORECASE)

    status_line_global: Optional[int] = None

    for j in range(chosen_idx_local + 1, min(len(tail), chosen_idx_local + 1 + TAIL_INVALID_STATUS_LOOKAHEAD)):
        m_status = status_re.match(tail[j])
        if m_status:
            raw = m_status.group(1).strip()
            if raw:
                status_value = raw.upper()
                status_line_global = tail_start + j
                break

        m_new = new_status_re.match(tail[j])
        if m_new:
            raw = m_new.group(1).strip()
            if raw:
                status_value = raw.upper()
                status_line_global = tail_start + j
                break

    dbg["status_line_global_idx"] = status_line_global
    dbg["status_value"] = status_value

    if status_value:
        return [f"{ALERT_PREFIX}{chosen_label}", f"Status: {status_value}"], dbg

    return [f"{ALERT_PREFIX}{chosen_label}"], dbg


def parse_original_issue_date_in_top_block(lines: List[str]) -> Tuple[Optional[str], Optional[int]]:
    top = get_top_license_slice(lines)
    if not top:
        return None, None

    header_idx = find_license_table_header(lines)
    if header_idx is None:
        return None, None

    top2 = [ln for ln in top if not re.search(r"\bCDL\s+Original\s+Issue\s+Date\b", ln, flags=re.IGNORECASE)]

    for off, ln in enumerate(top2):
        gi = header_idx + off
        m = re.search(
            r"\bOriginal\s+Issue\s+Date\b[:\s]*(" + DATE_RE.pattern + r")",
            ln,
            flags=re.IGNORECASE
        )
        if m:
            return m.group(1), gi

    for off, ln in enumerate(top2):
        gi = header_idx + off
        if re.search(r"\bOriginal\s+Issue\b", ln, flags=re.IGNORECASE):
            m = re.search(r"\bOriginal\s+Issue\b.*?(" + DATE_RE.pattern + r")", ln, flags=re.IGNORECASE)
            if m:
                return m.group(1), gi

    return None, None


def parse_license_row_issue_and_type_flag(lines: List[str]) -> Tuple[Optional[str], bool, Optional[int]]:
    header_idx = find_license_table_header(lines)
    if header_idx is None:
        return None, False, None

    for j in range(header_idx + 1, min(len(lines), header_idx + 30)):
        row = lines[j].strip()

        if re.search(r"\bMedical\b", row, flags=re.IGNORECASE):
            break

        if re.search(r"\bRestrictions?\b", row, flags=re.IGNORECASE):
            continue
        if re.search(r"\bOriginal\s+Issue\b", row, flags=re.IGNORECASE):
            continue

        type_present = bool(re.search(r"\bCommercial\b", row, flags=re.IGNORECASE))
        first_date_match = DATE_RE.search(row)
        if first_date_match:
            prefix = row[:first_date_match.start()]
            tokens = re.findall(r"[A-Za-z]{2,}", prefix)
            if tokens:
                type_present = True

        m2 = re.search(r"(" + DATE_RE.pattern + r")\s+(" + DATE_RE.pattern + r")", row)
        if m2:
            return m2.group(1), type_present, j

        if DATE_RE.search(row):
            return None, type_present, j

    return None, False, None


def parse_cdl_issued_with_debug(text: str) -> Tuple[Optional[str], Dict[str, Any]]:
    lines = clean_lines(text)

    issue_date, type_present, issue_line_idx = parse_license_row_issue_and_type_flag(lines)
    orig, orig_line_idx = parse_original_issue_date_in_top_block(lines)

    chosen: Optional[str]
    chosen_source: str

    if type_present:
        chosen = orig or issue_date
        chosen_source = "original_issue_date" if orig else ("issue_date" if issue_date else "missing")
    else:
        chosen = issue_date or orig
        chosen_source = "issue_date" if issue_date else ("original_issue_date" if orig else "missing")

    dbg = {
        "type_present": type_present,
        "issue_date": issue_date,
        "issue_line_global_idx": issue_line_idx,
        "original_issue_date": orig,
        "original_line_global_idx": orig_line_idx,
        "chosen": chosen,
        "chosen_source": chosen_source,
    }
    return chosen, dbg


def _parse_medical_expires_from_medical_table(lines: List[str]) -> Tuple[Optional[date], Optional[str], Dict[str, Any]]:
    dbg: Dict[str, Any] = {"found": False}

    med_start = None
    for i, ln in enumerate(lines):
        if re.search(r"\bMedical\s+certificate\b", ln, flags=re.IGNORECASE):
            med_start = i
            break
    if med_start is None:
        return None, None, dbg

    dbg["found"] = True
    dbg["medical_start_global_idx"] = med_start

    # Find the end of the medical block — stop at Miscellaneous/Viol/Sus/END etc.
    med_block_end = min(len(lines), med_start + 120)
    for j in range(med_start + 1, min(len(lines), med_start + 120)):
        ln_j = lines[j]
        if re.search(r"\bMiscellaneous\b", ln_j, flags=re.IGNORECASE):
            med_block_end = j
            break
        if re.search(r"\bViol/Sus\b", ln_j, flags=re.IGNORECASE):
            med_block_end = j
            break
        if re.search(r"\*\*\*\*\s*END OF DRIVING RECORD", ln_j, flags=re.IGNORECASE):
            med_block_end = j
            break

    win_end = med_block_end
    dbg["medical_block_end_global_idx"] = med_block_end

    header_idx = None
    for j in range(med_start, win_end):
        cur = lines[j]
        if (
            re.search(r"\bIssued\b", cur, flags=re.IGNORECASE)
            and re.search(r"\bExpires\b", cur, flags=re.IGNORECASE)
            and re.search(r"\bStatus\b", cur, flags=re.IGNORECASE)
        ):
            header_idx = j
            break

    dbg["medical_table_header_global_idx"] = header_idx
    if header_idx is None:
        return None, None, dbg

    # Only search within the medical block, not into violations
    search_end = min(win_end, header_idx + 10)
    for k in range(header_idx + 1, search_end):
        row = lines[k].strip()
        if not row:
            continue

        # Stop if we hit a section that is clearly not medical data
        if re.search(r"\bViol(?:ation)?\b", row, flags=re.IGNORECASE) and not re.search(r"\bMedical\b", row, flags=re.IGNORECASE):
            break
        if re.search(r"\bMiscellaneous\b", row, flags=re.IGNORECASE):
            break

        matches = [m.group(0) for m in DATE_RE.finditer(row)]
        if len(matches) >= 2:
            exp_str = matches[1]
            exp_dt = parse_mmddyyyy(exp_str)
            dbg["expires_row_global_idx"] = k
            dbg["expires_str"] = exp_str
            dbg["expires_dt"] = exp_dt.isoformat() if exp_dt else None
            if exp_dt:
                return exp_dt, exp_str, dbg

    return None, None, dbg


def parse_medical_card_message(lines: List[str]) -> Tuple[Optional[str], Dict[str, Any]]:
    today = datetime.now().date()

    exp_dt, exp_str, dbg = _parse_medical_expires_from_medical_table(lines)
    dbg["today"] = today.isoformat()
    dbg["days_left"] = None

    if not exp_dt or not exp_str:
        return None, dbg

    dbg["days_left"] = (exp_dt - today).days

    if exp_dt < today:
        dbg["decision"] = "expired"
        return MEDICAL_EXPIRED_TEXT, dbg

    if exp_dt <= today + timedelta(days=MEDICAL_EXPIRES_SOON_DAYS):
        dbg["decision"] = "expires_soon"
        return f"{MEDICAL_EXPIRES_SOON_PREFIX} {exp_str}", dbg

    dbg["decision"] = "ok"
    return None, dbg


def find_medical_block_range(lines: List[str]) -> Tuple[Optional[int], Optional[int]]:
    start = None
    for i, ln in enumerate(lines):
        if re.search(r"\bMedical\s+certificate\b", ln, flags=re.IGNORECASE):
            start = i
            break
    if start is None:
        return None, None

    end = min(len(lines), start + 220)
    for j in range(start + 1, min(len(lines), start + 260)):
        if re.search(r"\bMiscellaneous\b", lines[j], flags=re.IGNORECASE):
            end = j
            break
        if re.search(r"\bViol/Sus\b", lines[j], flags=re.IGNORECASE):
            end = j
            break
        if re.search(r"\*\*\*\*\s*END OF DRIVING RECORD", lines[j], flags=re.IGNORECASE):
            end = j
            break

    return start, end


def parse_self_certificate_block_with_debug(lines: List[str]) -> Tuple[List[str], Dict[str, Any]]:
    dbg: Dict[str, Any] = {
        "triggered": False,
        "type": None,
        "state": None,
        "state_line_global_idx": None,
        "intrastate_evidence_global_idx": None,
        "excepted_interstate_detected": False,
        "non_excepted_present_anywhere": False,
    }

    st, st_dbg = parse_state_abbrev_with_debug(lines)
    dbg["state"] = st
    dbg["state_line_global_idx"] = st_dbg.get("state_line_global_idx") or st_dbg.get("state_label_line_global_idx")
    dbg["state_source"] = st_dbg.get("state_source")
    dbg["state_found"] = st_dbg.get("found")

    m_start, m_end = find_medical_block_range(lines)
    dbg["medical_block_start_idx"] = m_start
    dbg["medical_block_end_idx"] = m_end

    if m_start is not None and m_end is not None:
        for i in range(m_start, m_end):
            if re.search(r"\bNON-EXCEPTED\b", lines[i], flags=re.IGNORECASE):
                for j in range(i, min(m_end, i + 6)):
                    if re.search(r"\bINTRASTATE\b", lines[j], flags=re.IGNORECASE):
                        dbg["triggered"] = True
                        dbg["type"] = "non_excepted_intrastate"
                        dbg["intrastate_evidence_global_idx"] = i
                        state_out = st or "??"
                        msg3 = SELF_CERT_INTRASTATE_EXPLAIN_PREFIX + state_out + SELF_CERT_INTRASTATE_EXPLAIN_SUFFIX
                        return [SELF_CERT_HEADER, SELF_CERT_VALUE_INTRASTATE, msg3], dbg

    big = " ".join(lines).upper()
    dbg["non_excepted_present_anywhere"] = ("NON-EXCEPTED" in big)
    dbg["excepted_interstate_detected"] = ("EXCEPTED INTERSTATE" in big)

    if "NON-EXCEPTED" in big:
        return [], dbg

    if "EXCEPTED INTERSTATE" in big:
        dbg["triggered"] = True
        dbg["type"] = "excepted_interstate"
        return ["EXCEPTED INTERSTATE", EXCEPTED_INTERSTATE_WARNING], dbg

    return [], dbg


def _looks_like_license_table_row(line: str) -> bool:
    if not line:
        return False

    dates = [m.group(0) for m in DATE_RE.finditer(line)]
    if len(dates) < 2:
        return False

    up_line = line.upper()
    status_hit = any(tok in up_line for tok in [
        "VALID", "IN FORCE", "ACTIVE", "EXPIRED", "SUSPENDED", "CANCELLED", "CANCELED", "REVOKED", "INVALID"
    ])
    if not status_hit:
        return False

    marker_hit = any(tok in up_line for tok in ["CLASS", "CLS", "COMMERCIAL", "NON-COMMERCIAL", "NON COMMERCIAL", "CDL", "DL"])
    if not marker_hit:
        return False

    return True


def _looks_like_new_section(line: str) -> bool:
    if re.search(r"\bEndorsements?\b", line, flags=re.IGNORECASE):
        return True
    if _looks_like_license_table_row(line):
        return True
    if re.search(r"\bMedical\b", line, flags=re.IGNORECASE):
        return True
    if re.search(r"\bViol/Sus\b|\bConv/Reins\b", line, flags=re.IGNORECASE):
        return True
    if re.search(r"\bMiscellaneous\b", line, flags=re.IGNORECASE):
        return True
    if re.search(r"\bPrevious\s+License\b", line, flags=re.IGNORECASE):
        return True
    if re.match(r"^\s*[A-Za-z][A-Za-z\s/]{1,25}:\s*$", line):
        return True
    return False


def normalize_restrictions_output(s: str) -> str:
    """Normalize restrictions text for output (not for matching).

    Some states abbreviate 'TRANSMISSION' as 'Trans'. We always output
    'TRANSMISSION' to keep reports consistent.
    """
    if not s:
        return s
    return re.sub(r"\bTrans\.?\b", "TRANSMISSION", s, flags=re.IGNORECASE)


def parse_restrictions_block_top_only(lines: List[str]) -> Tuple[Optional[str], Dict[str, Any]]:
    dbg: Dict[str, Any] = {"found": False}

    top = get_top_license_slice(lines)
    if not top:
        return None, dbg

    header_idx = find_license_table_header(lines)
    if header_idx is None:
        return None, dbg

    for i, ln in enumerate(top):
        m = RESTRICTIONS_LINE.match(ln)
        if not m:
            continue

        start_global = header_idx + i
        dbg["found"] = True
        dbg["restrictions_start_global_idx"] = start_global

        rhs = (m.group("rhs") or "").strip()
        parts: List[str] = []
        used_idxs: List[int] = [start_global]

        if rhs:
            parts.append(rhs)

        for j in range(i + 1, min(len(top), i + 12)):
            nxt = top[j].strip()
            if not nxt:
                continue
            if _looks_like_new_section(nxt):
                dbg["stopped_on_line_global_idx"] = header_idx + j
                dbg["stop_reason"] = "new_section_or_license_row"
                break
            if RESTRICTIONS_LINE.match(nxt):
                dbg["stopped_on_line_global_idx"] = header_idx + j
                dbg["stop_reason"] = "next_restrictions_line"
                break
            parts.append(nxt)
            used_idxs.append(header_idx + j)

        dbg["restrictions_used_global_idxs"] = used_idxs

        if parts:
            out = "Restrictions: " + " ".join(parts).strip()
            out2 = normalize_restrictions_output(out)
            dbg["output_normalized_transmission"] = (out2 != out)
            return out2, dbg
        return "Restrictions:", dbg

    return None, dbg


def restrictions_need_manual_warning(restrictions_line: str) -> bool:
    normalized = normalize_for_trigger(restrictions_line)
    for phrase in TRIGGER_CHECKS:
        if phrase in normalized:
            return True
    if "NO MANUAL TRANSMISSION" in normalized:
        return True
    if ("MANUAL" in normalized) and ("TRANSMISSION" in normalized) and ("PROHIBITS DRIVING" in normalized):
        return True
    if "AUTOMATIC TRANSMISSION ONLY" in normalized:
        return True
    if "AUTO TRANSMISSION CMV" in normalized:
        return True
    return False


def restrictions_need_air_brake_warning(restrictions_line: str) -> bool:
    normalized = normalize_for_trigger(restrictions_line)
    return normalize_for_trigger(AIR_BRAKE_TRIGGER) in normalized


def _looks_like_new_kv_line(s: str) -> bool:
    if not s:
        return True
    if DATE_RE.match(s.strip()):
        return True
    if "=" in s:
        return True
    if re.match(r"^\s*[A-Za-z][A-Za-z0-9\s/\-]{1,35}:\s+\S+", s):
        return True
    if re.search(r"\bViol/Sus\b|\bConv/Reins\b|\bMiscellaneous\b|\bEndorsements?\b", s, flags=re.IGNORECASE):
        return True
    if re.search(r"\*\*\*\*\s*END OF DRIVING RECORD", s, flags=re.IGNORECASE):
        return True
    return False


def _parse_description_multiline(lines: List[str], desc_idx: int, max_cont_lines: int = 3) -> Tuple[str, List[int]]:
    base = value_after_equals_or_next(lines, desc_idx).strip()
    used = [desc_idx]
    out = base

    cont_used: List[int] = []
    for j in range(desc_idx + 1, min(len(lines), desc_idx + 1 + max_cont_lines)):
        nxt = lines[j].strip()
        if not nxt:
            continue
        if _looks_like_new_kv_line(nxt):
            break
        if out:
            out = out.rstrip() + " " + nxt
        else:
            out = nxt
        cont_used.append(j)

    if cont_used:
        used.extend(cont_used)

    out = re.sub(r"\s+", " ", out).strip()
    return out, used


def parse_groups_and_future_suspensions(text: str) -> Tuple[Dict[str, Set[str]], List[Tuple[str, str]], Dict[str, Any]]:
    lines = clean_lines(text)

    groups: Dict[str, Set[str]] = {}
    order: List[str] = []
    seen: Set[str] = set()

    susp_set: Set[Tuple[str, str]] = set()
    susp_list: List[Tuple[str, str]] = []

    today = datetime.now().date()

    current_viol_date: Optional[str] = None
    current_is_future = False
    current_date_line_idx: Optional[int] = None

    dbg_items: List[Dict[str, Any]] = []

    for i, ln in enumerate(lines):
        m2 = TWO_DATES_START.match(ln)
        if m2:
            current_viol_date = m2.group("d1")
            current_date_line_idx = i
            dt_obj = parse_mmddyyyy(current_viol_date)
            current_is_future = bool(dt_obj and dt_obj > today)
            continue

        m1 = ONE_DATE_START.match(ln)
        if m1:
            current_viol_date = m1.group("d1")
            current_date_line_idx = i
            dt_obj = parse_mmddyyyy(current_viol_date)
            current_is_future = bool(dt_obj and dt_obj > today)
            continue

        mdesc = ANY_DESC_LINE.match(ln)
        if mdesc:
            violation, used_desc_idxs = _parse_description_multiline(lines, i, max_cont_lines=3)

            if not violation or not current_viol_date:
                dbg_items.append({
                    "desc_line_global_idx": i,
                    "desc_used_line_global_idxs": used_desc_idxs,
                    "desc_value": violation,
                    "date_value": current_viol_date,
                    "date_line_global_idx": current_date_line_idx,
                    "skipped_reason": "missing_desc_or_date",
                })
                continue

            if current_is_future:
                key = (current_viol_date, violation)
                if key not in susp_set:
                    susp_set.add(key)
                    susp_list.append(key)

                dbg_items.append({
                    "desc_line_global_idx": i,
                    "desc_used_line_global_idxs": used_desc_idxs,
                    "desc_value": violation,
                    "date_value": current_viol_date,
                    "date_line_global_idx": current_date_line_idx,
                    "classified_as": "future_suspension",
                })
                continue

            groups.setdefault(violation, set()).add(current_viol_date)
            if violation not in seen:
                order.append(violation)
                seen.add(violation)

            dbg_items.append({
                "desc_line_global_idx": i,
                "desc_used_line_global_idxs": used_desc_idxs,
                "desc_value": violation,
                "date_value": current_viol_date,
                "date_line_global_idx": current_date_line_idx,
                "classified_as": "violation",
            })

    ordered_groups = {k: groups[k] for k in order if k in groups}

    susp_list_sorted = sorted(
        susp_list,
        key=lambda pair: (datetime.strptime(pair[0], "%m/%d/%Y"), pair[1].lower())
    )

    dbg = {
        "today": today.isoformat(),
        "items": dbg_items[:500],
        "future_suspensions_count": len(susp_list_sorted),
        "violations_group_count": len(ordered_groups),
    }
    return ordered_groups, susp_list_sorted, dbg


def format_output_with_debug(text: str, page_texts: List[str], pdf_path: str) -> Tuple[str, Dict[str, Any]]:
    mapobj = build_line_map(page_texts)
    lines = mapobj["global_lines"]

    debug_log: Dict[str, Any] = {
        "doc_type": DOC_MVR,
        "pdf_path": pdf_path,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "today": datetime.now().date().isoformat(),
        "blocks": {},
    }

    out: List[str] = []

    header_dbg = parse_header_status_with_debug(lines)
    header_dbg["cdl_status_line_ref"] = line_ref(mapobj, header_dbg.get("cdl_status_line_global_idx"))
    header_dbg["license_status_line_ref"] = line_ref(mapobj, header_dbg.get("license_status_line_global_idx"))
    debug_log["blocks"]["header_status"] = header_dbg

    invalid_block, inv_dbg = parse_tail_invalid_status_block(lines)

    inv_dbg["suppressed_due_to_header_valid"] = False
    inv_dbg["header_cdl_is_valid"] = bool(header_dbg.get("cdl_is_valid"))
    inv_dbg["header_license_is_valid"] = bool(header_dbg.get("license_is_valid"))

    if invalid_block and header_dbg.get("cdl_is_valid"):
        inv_dbg["suppressed_due_to_header_valid"] = True
        inv_dbg["suppression_reason"] = "header_cdl_status_valid"
        invalid_block = []

    inv_dbg["invalid_line_ref"] = line_ref(mapobj, inv_dbg.get("invalid_line_global_idx"))
    inv_dbg["status_line_ref"] = line_ref(mapobj, inv_dbg.get("status_line_global_idx"))
    debug_log["blocks"]["tail_invalid"] = inv_dbg

    if invalid_block:
        out.extend(invalid_block)
        out.append("")

    has_a, class_a_idx = top_license_has_class_a(lines)
    debug_log["blocks"]["class_a_top"] = {
        "has_class_a": has_a,
        "evidence_line_ref": line_ref(mapobj, class_a_idx),
        "license_header_ref": line_ref(mapobj, find_license_table_header(lines)),
        "license_end_ref": line_ref(mapobj, find_top_license_end(lines, find_license_table_header(lines) or 0))
        if find_license_table_header(lines) is not None else None,
    }

    if has_a:
        issued, cdl_dbg = parse_cdl_issued_with_debug(text)
        cdl_dbg["issue_line_ref"] = line_ref(mapobj, cdl_dbg.get("issue_line_global_idx"))
        cdl_dbg["original_line_ref"] = line_ref(mapobj, cdl_dbg.get("original_line_global_idx"))
        debug_log["blocks"]["cdl_issued"] = cdl_dbg

        if issued:
            out.append(f"CDL issued {issued}")
        else:
            out.append("MVR doesn't provide the original CDL issue date")
    else:
        out.append(NO_CDL_TEXT)
        dl_issue, dl_line = parse_top_license_row_issue_date(lines)
        debug_log["blocks"]["dl_issued"] = {
            "dl_issue_date": dl_issue,
            "dl_issue_line_ref": line_ref(mapobj, dl_line),
        }
        if dl_issue:
            out.append(f"DL issued {dl_issue}")
        else:
            # Fallback: try Original Issue Date
            orig_date, orig_line = parse_original_issue_date_in_top_block(lines)
            debug_log["blocks"]["dl_issued"]["original_issue_date"] = orig_date
            debug_log["blocks"]["dl_issued"]["original_issue_line_ref"] = line_ref(mapobj, orig_line)
            if orig_date:
                out.append(f"DL issued {orig_date}")
            else:
                out.append("DL issued date not found")

    med_msg, med_dbg = parse_medical_card_message(lines)
    med_dbg["medical_start_ref"] = line_ref(mapobj, med_dbg.get("medical_start_global_idx"))
    med_dbg["medical_header_ref"] = line_ref(mapobj, med_dbg.get("medical_table_header_global_idx"))
    med_dbg["expires_row_ref"] = line_ref(mapobj, med_dbg.get("expires_row_global_idx"))
    debug_log["blocks"]["medical_card"] = med_dbg

    # Medical message (expired/expiring)
    if med_msg:
        out.append(med_msg)

    self_lines, self_dbg = parse_self_certificate_block_with_debug(lines)
    self_dbg["state_line_ref"] = line_ref(mapobj, self_dbg.get("state_line_global_idx"))
    self_dbg["intrastate_evidence_ref"] = line_ref(mapobj, self_dbg.get("intrastate_evidence_global_idx"))
    self_dbg["medical_block_start_ref"] = line_ref(mapobj, self_dbg.get("medical_block_start_idx"))
    self_dbg["medical_block_end_ref"] = line_ref(mapobj, self_dbg.get("medical_block_end_idx") - 1) if isinstance(self_dbg.get("medical_block_end_idx"), int) else None
    debug_log["blocks"]["self_cert"] = self_dbg

    for ln in self_lines:
        out.append(ln)

    out.append("")

    restr, restr_dbg = parse_restrictions_block_top_only(lines)
    if restr:
        restr_dbg["start_ref"] = line_ref(mapobj, restr_dbg.get("restrictions_start_global_idx"))
        restr_dbg["used_refs"] = [line_ref(mapobj, x) for x in restr_dbg.get("restrictions_used_global_idxs", [])]
        restr_dbg["manual_warning"] = restrictions_need_manual_warning(restr)
        restr_dbg["air_brake_warning"] = restrictions_need_air_brake_warning(restr)
        restr_dbg["stopped_on_ref"] = line_ref(mapobj, restr_dbg.get("stopped_on_line_global_idx"))
    debug_log["blocks"]["restrictions"] = restr_dbg

    if restr:
        out.append(f"{ALERT_PREFIX}{restr}")
        if restrictions_need_manual_warning(restr):
            out.append(MANUAL_WARNING_TEXT)
        if restrictions_need_air_brake_warning(restr):
            out.append(AIR_BRAKE_WARNING_TEXT)
        out.append("")

    # No medical data warning (placed after restrictions, before violations)
    if not med_msg and not med_dbg.get("found"):
        out.append("\u203c\ufe0fNo medical dates on the record")
        out.append("")

    groups, future_susp, viol_dbg = parse_groups_and_future_suspensions(text)
    debug_log["blocks"]["violations"] = viol_dbg

    if not groups and not future_susp:
        out.append("Clean record")
        return "\n".join(out).strip() + "\n", debug_log

    for susp_date, reason in future_susp:
        out.append(f"CDL will be suspended {susp_date} due to {reason}")

    for viol, dateset in groups.items():
        out.append(f"{viol} {', '.join(sort_dates(dateset))}")

    return "\n".join(out).strip() + "\n", debug_log
