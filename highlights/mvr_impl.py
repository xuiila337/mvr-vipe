from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import pdfplumber

from highlights.common import (
    MAX_TOKEN_OCCURRENCES_PER_PAGE,
    find_boxes_for_any_text_contains,
    find_boxes_for_phrase,
    find_boxes_for_word_equals,
    tokenize_violation_text,
    _norm_word,  # used for freq
)

from parsers.mvr_impl import (
    AIR_BRAKE_TRIGGER,
    DATE_RE,
    MEDICAL_EXPIRES_SOON_PREFIX,
    SELF_CERT_VALUE_INTRASTATE,
    clean_lines,
    parse_cdl_issued_with_debug,
    parse_groups_and_future_suspensions,
    parse_header_status_with_debug,
    parse_medical_card_message,
    parse_restrictions_block_top_only,
    parse_self_certificate_block_with_debug,
    parse_tail_invalid_status_block,
    parse_top_license_row_issue_date,
    restrictions_need_air_brake_warning,
    top_license_has_class_a,
)


def build_highlights_mvr(pdf_path: str, raw_text: str) -> Dict[int, List[Tuple[float, float, float, float]]]:
    highlights: Dict[int, List[Tuple[float, float, float, float]]] = {}

    lines = clean_lines(raw_text)

    has_a, _ = top_license_has_class_a(lines)
    issued_date: Optional[str]
    if has_a:
        issued_date, _dbg = parse_cdl_issued_with_debug(raw_text)
    else:
        issued_date, _li = parse_top_license_row_issue_date(lines)

    med_msg, _ = parse_medical_card_message(lines)
    med_exp_str: Optional[str] = None
    if med_msg and med_msg.startswith(MEDICAL_EXPIRES_SOON_PREFIX):
        parts = med_msg.split()
        if parts:
            last = parts[-1]
            if DATE_RE.fullmatch(last):
                med_exp_str = last

    restr, _ = parse_restrictions_block_top_only(lines)

    groups, future_susp, _ = parse_groups_and_future_suspensions(raw_text)
    violation_descriptions = list(groups.keys())
    future_descriptions = [reason for _, reason in future_susp]

    out_dates = [m.group(0) for m in DATE_RE.finditer(raw_text)]
    out_dates = list(dict.fromkeys(out_dates))

    header_dbg = parse_header_status_with_debug(lines)
    invalid_block, _inv_dbg = parse_tail_invalid_status_block(lines)
    if invalid_block and header_dbg.get("cdl_is_valid"):
        invalid_block = []

    want_cdl_invalid = bool(invalid_block and "CDL Status Invalid" in invalid_block[0])
    want_lic_invalid = bool(invalid_block and "License Status Invalid" in invalid_block[0])

    self_lines, _ = parse_self_certificate_block_with_debug(lines)
    want_intrastate = bool(self_lines and len(self_lines) >= 2 and self_lines[1].strip().upper() == SELF_CERT_VALUE_INTRASTATE)

    viol_tokens: List[str] = []
    for desc in violation_descriptions:
        viol_tokens.extend(tokenize_violation_text(desc))
    for desc in future_descriptions:
        viol_tokens.extend(tokenize_violation_text(desc))
    viol_tokens = list(dict.fromkeys(viol_tokens))[:160]

    with pdfplumber.open(pdf_path) as pdf:
        for pi, page in enumerate(pdf.pages):
            words = page.extract_words() or []
            rects: List[Tuple[float, float, float, float]] = []

            freq: Dict[str, int] = {}
            for w in words:
                ww = _norm_word(w.get("text", ""))
                if ww:
                    freq[ww] = freq.get(ww, 0) + 1

            if want_cdl_invalid:
                rects += find_boxes_for_phrase(words, "CDL Status Invalid")
                rects += find_boxes_for_phrase(words, "New Status Value")
            if want_lic_invalid:
                rects += find_boxes_for_phrase(words, "License Status Invalid")
                rects += find_boxes_for_phrase(words, "New Status Value")

            rects += find_boxes_for_phrase(words, "Original Issue Date")
            if issued_date and DATE_RE.fullmatch(issued_date):
                rects += find_boxes_for_any_text_contains(words, issued_date)

            if med_msg:
                rects += find_boxes_for_phrase(words, "Medical certificate")
                rects += find_boxes_for_phrase(words, "Expires")
                if med_exp_str:
                    rects += find_boxes_for_any_text_contains(words, med_exp_str)

            if want_intrastate:
                rects += find_boxes_for_phrase(words, "Self Certificate")
                rects += find_boxes_for_phrase(words, "NON-EXCEPTED")
                rects += find_boxes_for_phrase(words, "INTRASTATE")

            if restr:
                rects += find_boxes_for_phrase(words, "Restrictions")
                if restrictions_need_air_brake_warning(restr):
                    rects += find_boxes_for_phrase(words, AIR_BRAKE_TRIGGER)

            for d in out_dates[:40]:
                if DATE_RE.fullmatch(d):
                    rects += find_boxes_for_any_text_contains(words, d)

            for tok in viol_tokens:
                tok_u = _norm_word(tok)
                if not tok_u:
                    continue
                if freq.get(tok_u, 0) > MAX_TOKEN_OCCURRENCES_PER_PAGE:
                    continue
                rects += find_boxes_for_word_equals(words, tok_u)

            if rects:
                highlights[pi] = rects

    return highlights
