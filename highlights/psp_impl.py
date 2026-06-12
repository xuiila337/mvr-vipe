from __future__ import annotations

import re
from typing import Dict, List, Tuple

import pdfplumber

from highlights.common import (
    MAX_TOKEN_OCCURRENCES_PER_PAGE,
    find_boxes_for_any_text_contains,
    find_boxes_for_phrase,
    find_boxes_for_word_equals,
    tokenize_violation_text,
    _norm_word,  # used for freq
)

from parsers.psp_impl import PSP_DATE_RE


def _psp_find_crash_dates_fallback(raw_text: str) -> List[str]:
    lines = (raw_text or "").splitlines()
    in_crash = False
    out: List[str] = []
    for ln in lines:
        up_line = ln.upper()
        if "CRASH DETAILS" in up_line:
            in_crash = True
            continue
        if in_crash and "INSPECTION ACTIVITY" in up_line:
            break
        if not in_crash:
            continue
        m = re.match(r"^\s*\d+\s+(\d{2}/\d{2}/\d{4})\b", ln.strip())
        if m:
            out.append(m.group(1))
    return list(dict.fromkeys(out))[:10]


def build_highlights_psp(pdf_path: str, raw_text: str, actual_output: str) -> Dict[int, List[Tuple[float, float, float, float]]]:
    highlights: Dict[int, List[Tuple[float, float, float, float]]] = {}

    crash_dates: List[str] = []
    for m in PSP_DATE_RE.finditer(actual_output or ""):
        crash_dates.append(m.group(0))
    crash_dates = list(dict.fromkeys(crash_dates))[:10]

    if not crash_dates:
        crash_dates = _psp_find_crash_dates_fallback(raw_text)

    out_lines = (actual_output or "").splitlines()
    viol_lines = [
        ln.strip() for ln in out_lines
        if ln.strip()
        and ln.strip().upper() not in {"PSP:"}
        and not ln.strip().upper().startswith("CRASH ")
    ]

    tokens: List[str] = []
    for vl in viol_lines[:40]:
        tokens.extend(tokenize_violation_text(vl))
    tokens = list(dict.fromkeys(tokens))[:120]

    with pdfplumber.open(pdf_path) as pdf:
        for pi, page in enumerate(pdf.pages):
            words = page.extract_words() or []
            rects: List[Tuple[float, float, float, float]] = []

            rects += find_boxes_for_phrase(words, "PSP Detailed Report")
            rects += find_boxes_for_phrase(words, "Crash Details")
            rects += find_boxes_for_phrase(words, "Violation Summary")
            rects += find_boxes_for_phrase(words, "No Crash or Inspection Results Found")

            for d in crash_dates:
                rects += find_boxes_for_any_text_contains(words, d)

            freq: Dict[str, int] = {}
            for w in words:
                ww = _norm_word(w.get("text", ""))
                if ww:
                    freq[ww] = freq.get(ww, 0) + 1

            for tok in tokens:
                tok_u = _norm_word(tok)
                if not tok_u:
                    continue
                if freq.get(tok_u, 0) > MAX_TOKEN_OCCURRENCES_PER_PAGE:
                    continue
                rects += find_boxes_for_word_equals(words, tok_u)

            if rects:
                highlights[pi] = rects

    return highlights
