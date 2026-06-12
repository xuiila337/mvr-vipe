from __future__ import annotations

import re
from typing import Dict, List, Tuple


MAX_TOKEN_OCCURRENCES_PER_PAGE = 3
MIN_TOKEN_LEN = 5


def _norm_word(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().upper()


STOP_TOKENS = {
    "MISCELLANEOUS", "HISTORY", "REPORT", "FROM", "STATE", "CDL", "HOLDER",
    "VIOL", "VIOLATION", "CONV", "CERTIFIED", "DATE", "STATUS", "CODE",
    "DESCRIPTION", "TEXT", "INFO", "DRIVER", "LICENSE", "REQUESTED", "DIVISION",
    "NAME", "YES", "NO", "ACTION",
}


def tokenize_violation_text(desc: str) -> List[str]:
    if not desc:
        return []
    tokens = re.findall(r"[A-Za-z0-9']+", desc.upper())
    out: List[str] = []
    for t in tokens:
        if len(t) < MIN_TOKEN_LEN:
            continue
        if t in STOP_TOKENS:
            continue
        out.append(t)
    # dedup, keep order
    return list(dict.fromkeys(out))


def find_boxes_for_phrase(words: List[dict], phrase: str) -> List[Tuple[float, float, float, float]]:
    if not phrase:
        return []
    target = [_norm_word(t) for t in phrase.split()]
    seq = [_norm_word(w.get("text", "")) for w in words]

    rects: List[Tuple[float, float, float, float]] = []
    n = len(target)
    if n == 0:
        return rects

    for i in range(0, len(seq) - n + 1):
        if seq[i:i+n] == target:
            x0 = min(words[j]["x0"] for j in range(i, i+n))
            x1 = max(words[j]["x1"] for j in range(i, i+n))
            top = min(words[j]["top"] for j in range(i, i+n))
            bottom = max(words[j]["bottom"] for j in range(i, i+n))
            rects.append((x0, top, x1, bottom))

    return rects


def find_boxes_for_word_equals(words: List[dict], token: str) -> List[Tuple[float, float, float, float]]:
    t = _norm_word(token)
    if not t:
        return []
    rects: List[Tuple[float, float, float, float]] = []
    for w in words:
        if _norm_word(w.get("text", "")) == t:
            rects.append((w["x0"], w["top"], w["x1"], w["bottom"]))
    return rects


def find_boxes_for_any_text_contains(words: List[dict], needle: str) -> List[Tuple[float, float, float, float]]:
    n = _norm_word(needle)
    if not n:
        return []
    rects: List[Tuple[float, float, float, float]] = []
    for w in words:
        if n in _norm_word(w.get("text", "")):
            rects.append((w["x0"], w["top"], w["x1"], w["bottom"]))
    return rects
