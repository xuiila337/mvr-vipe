from __future__ import annotations

import json
import zipfile
import os
import sys
import platform
from datetime import datetime
import difflib
from typing import Any, Dict, List, Optional, Tuple

from .types import PdfText, ParseResult


APP_VERSION = "beta 1.0"
DEBUG_SCHEMA_VERSION = 2


def _make_diff(expected: str, actual: str) -> str:
    exp_lines = (expected or "").splitlines(keepends=True)
    act_lines = (actual or "").splitlines(keepends=True)
    diff = difflib.unified_diff(
        exp_lines,
        act_lines,
        fromfile="expected.txt",
        tofile="actual.txt",
        lineterm="",
        n=3,
    )
    return "\n".join(diff).strip() + ("\n" if expected.strip() or actual.strip() else "")


def _safe_get(d: Dict[str, Any], *path: str) -> Any:
    cur: Any = d
    for p in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


def _diagnosis_for_mvr(result: ParseResult) -> Dict[str, Any]:
    dbg = result.debug_log or {}
    blocks = dbg.get("blocks") if isinstance(dbg, dict) else None
    blocks = blocks if isinstance(blocks, dict) else {}

    fired: List[Dict[str, Any]] = []
    suppression: List[Dict[str, Any]] = []

    # Tail invalid suppression
    tail = blocks.get("tail_invalid") if isinstance(blocks.get("tail_invalid"), dict) else {}
    if tail.get("found"):
        if tail.get("suppressed_due_to_header_valid"):
            suppression.append({
                "block": "tail_invalid",
                "reason": tail.get("suppression_reason"),
                "invalid_line_ref": tail.get("invalid_line_ref"),
                "status_line_ref": tail.get("status_line_ref"),
            })
        else:
            fired.append({
                "block": "tail_invalid",
                "invalid_line_ref": tail.get("invalid_line_ref"),
                "status_line_ref": tail.get("status_line_ref"),
            })

    # CDL/DL issued
    class_a = blocks.get("class_a_top") if isinstance(blocks.get("class_a_top"), dict) else {}
    if class_a.get("has_class_a"):
        cdl = blocks.get("cdl_issued") if isinstance(blocks.get("cdl_issued"), dict) else {}
        fired.append({
            "block": "cdl_issued",
            "chosen_source": cdl.get("chosen_source"),
            "issue_line_ref": cdl.get("issue_line_ref"),
            "original_line_ref": cdl.get("original_line_ref"),
        })
    else:
        dl = blocks.get("dl_issued") if isinstance(blocks.get("dl_issued"), dict) else {}
        fired.append({
            "block": "dl_issued",
            "dl_issue_line_ref": dl.get("dl_issue_line_ref"),
        })

    # Medical
    med = blocks.get("medical_card") if isinstance(blocks.get("medical_card"), dict) else {}
    if med.get("decision") in {"expired", "expires_soon"}:
        fired.append({
            "block": "medical_card",
            "decision": med.get("decision"),
            "expires_row_ref": med.get("expires_row_ref"),
            "medical_header_ref": med.get("medical_header_ref"),
        })

    # Self cert
    sc = blocks.get("self_cert") if isinstance(blocks.get("self_cert"), dict) else {}
    if sc.get("triggered"):
        fired.append({
            "block": "self_cert",
            "type": sc.get("type"),
            "state_line_ref": sc.get("state_line_ref"),
            "intrastate_evidence_ref": sc.get("intrastate_evidence_ref"),
        })

    # Restrictions
    restr = blocks.get("restrictions") if isinstance(blocks.get("restrictions"), dict) else {}
    if restr.get("found"):
        fired.append({
            "block": "restrictions",
            "start_ref": restr.get("start_ref"),
            "stopped_on_ref": restr.get("stopped_on_ref"),
            "manual_warning": restr.get("manual_warning"),
            "air_brake_warning": restr.get("air_brake_warning"),
        })

    return {
        "doc_type": "MVR",
        "blocks_fired": fired,
        "suppression": suppression,
    }


def _diagnosis_for_psp(result: ParseResult) -> Dict[str, Any]:
    dbg = result.debug_log or {}
    return {
        "doc_type": "PSP",
        "decision": dbg.get("decision"),
        "detected_no_results": dbg.get("detected_no_results"),
        "counts": dbg.get("counts"),
        "crash": {
            "crash_count": _safe_get(dbg, "crash", "crash_count"),
            "dates": _safe_get(dbg, "crash", "dates"),
            "dates_source_lines": _safe_get(dbg, "crash", "dates_source_lines"),
        },
        "violations": {
            "found_violation_summary": _safe_get(dbg, "violations", "found_violation_summary"),
            "items_count": len(_safe_get(dbg, "violations", "items") or []),
        },
        "extras": {
            "handheld_phone_found": _safe_get(dbg, "extras", "handheld_phone_found"),
            "state_citation_results": _safe_get(dbg, "extras", "state_citation_results"),
            "filtered_out_as_duplicates": _safe_get(dbg, "extras", "filtered_out_as_duplicates"),
        },
    }


def _make_diagnosis(result: ParseResult) -> Dict[str, Any]:
    if result.doc_type == "MVR":
        return _diagnosis_for_mvr(result)
    if result.doc_type == "PSP":
        return _diagnosis_for_psp(result)
    return {"doc_type": result.doc_type, "note": "unknown document type; limited diagnosis"}


def _build_output_map(result: ParseResult) -> Dict[str, Any]:
    """
    Map each actual output line to the best-known source evidence.
    This is intentionally best-effort and safe: it should never crash bundle saving.
    """
    actual = (result.actual_text or "").splitlines()
    dbg = result.debug_log or {}

    out_map: List[Dict[str, Any]] = []

    # Helpers for MVR block refs
    blocks = dbg.get("blocks") if isinstance(dbg, dict) else None
    blocks = blocks if isinstance(blocks, dict) else {}

    def add(line: str, source: Any = None, notes: Optional[str] = None) -> None:
        if not line.strip():
            return
        item: Dict[str, Any] = {"text": line}
        if source is not None:
            item["source"] = source
        if notes:
            item["notes"] = notes
        out_map.append(item)

    # Precompute PSP lookup maps if needed
    psp_violation_items = _safe_get(dbg, "violations", "items") or []
    psp_state_citation = _safe_get(dbg, "extras", "state_citation_results") or []
    psp_crash_lines = _safe_get(dbg, "crash", "dates_source_lines") or []

    for ln in actual:
        s = ln.strip()
        if not s:
            continue

        if result.doc_type == "MVR":
            tail = blocks.get("tail_invalid") if isinstance(blocks.get("tail_invalid"), dict) else {}
            restr = blocks.get("restrictions") if isinstance(blocks.get("restrictions"), dict) else {}
            cdl = blocks.get("cdl_issued") if isinstance(blocks.get("cdl_issued"), dict) else {}
            dl = blocks.get("dl_issued") if isinstance(blocks.get("dl_issued"), dict) else {}
            med = blocks.get("medical_card") if isinstance(blocks.get("medical_card"), dict) else {}
            sc = blocks.get("self_cert") if isinstance(blocks.get("self_cert"), dict) else {}

            if s.startswith("‼️CDL Status Invalid") or s.startswith("‼️License Status Invalid") or s.startswith("‼️CDL Status Invalid".replace("‼️","")):
                add(ln, source={"invalid_line_ref": tail.get("invalid_line_ref"), "status_line_ref": tail.get("status_line_ref")})
                continue
            if s.startswith("Status:"):
                add(ln, source={"status_line_ref": tail.get("status_line_ref")})
                continue
            if s.startswith("CDL issued"):
                add(ln, source={"chosen_source": cdl.get("chosen_source"), "issue_line_ref": cdl.get("issue_line_ref"), "original_line_ref": cdl.get("original_line_ref")})
                continue
            if s.startswith("DL issued"):
                add(ln, source={"dl_issue_line_ref": dl.get("dl_issue_line_ref")})
                continue
            if s.startswith("❌Medical card"):
                add(ln, source={"expires_row_ref": med.get("expires_row_ref"), "medical_header_ref": med.get("medical_header_ref")})
                continue
            if s.startswith("🚨Self Certificate") or s.startswith("EXCEPTED INTERSTATE") or s.startswith("‼️Intrastate means"):
                add(ln, source={"intrastate_evidence_ref": sc.get("intrastate_evidence_ref"), "state_line_ref": sc.get("state_line_ref")})
                continue
            if s.startswith("‼️Restrictions:") or s.startswith("‼️Restrictions"):
                add(ln, source={"start_ref": restr.get("start_ref"), "used_refs": restr.get("used_refs"), "stopped_on_ref": restr.get("stopped_on_ref")})
                continue
            if "manual transmission" in s.lower() and "restriction" in s.lower():
                add(ln, source={"start_ref": restr.get("start_ref"), "used_refs": restr.get("used_refs")}, notes="derived from restrictions warning")
                continue
            if "air brake" in s.lower():
                add(ln, source={"start_ref": restr.get("start_ref"), "used_refs": restr.get("used_refs")}, notes="derived from restrictions warning")
                continue

            # Violations / suspensions are best-effort; keep line with no mapping
            add(ln, notes="no structured source mapping for this line (best-effort)")
            continue

        if result.doc_type == "PSP":
            if s.upper().startswith("PSP:"):
                add(ln, notes="header")
                continue
            if s.upper().startswith("CRASH "):
                add(ln, source={"dates_source_lines": psp_crash_lines})
                continue
            # Try match violation item text
            matched = next((it for it in psp_violation_items if isinstance(it, dict) and (it.get("text") or "").strip() == s), None)
            if matched:
                add(ln, source={"start_line": matched.get("start_line"), "source_lines": matched.get("source_lines")})
                continue
            # State citation result lines
            if s.lower().startswith("state citation result:"):
                matched2 = next((it for it in psp_state_citation if isinstance(it, dict) and (it.get("text") or "").strip() == s), None)
                if matched2:
                    add(ln, source={"line": matched2.get("line")})
                    continue
            add(ln, notes="no structured source mapping for this line (best-effort)")
            continue

        add(ln, notes="unknown doc type; no mapping")

    return {"lines": out_map}


def _try_make_screenshots(pdf_path: str, highlights: Dict[int, Any]) -> Tuple[Optional[bytes], Optional[bytes], Optional[str]]:
    """
    Returns (page01_png, page01_hl_png, error_str).
    If dependencies are missing or anything fails, returns (None, None, "reason").
    """
    try:
        import fitz  # type: ignore
        from PIL import Image, ImageDraw  # type: ignore
    except Exception as e:
        return None, None, f"deps_missing: {e}"

    if not pdf_path or not os.path.exists(pdf_path):
        return None, None, "pdf_missing"

    try:
        doc = fitz.open(pdf_path)  # type: ignore
        try:
            if doc.page_count <= 0:
                return None, None, "empty_pdf"
            page = doc.load_page(0)
            zoom = 2.0
            mat = fitz.Matrix(zoom, zoom)  # type: ignore
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

            # Base screenshot
            import io
            buf1 = io.BytesIO()
            img.save(buf1, format="PNG")
            page_png = buf1.getvalue()

            # Highlighted screenshot (best-effort)
            img_hl = img.copy()
            draw = ImageDraw.Draw(img_hl)

            rects = highlights.get(0) or []
            # rect format can be dataclass or tuple; normalize
            for r in rects[:400]:
                try:
                    if isinstance(r, dict):
                        x0, top, x1, bottom = float(r["x0"]), float(r["top"]), float(r["x1"]), float(r["bottom"])
                    else:
                        x0, top, x1, bottom = float(getattr(r, "x0", r[0])), float(getattr(r, "top", r[1])), float(getattr(r, "x1", r[2])), float(getattr(r, "bottom", r[3]))
                    x0 *= zoom
                    x1 *= zoom
                    top *= zoom
                    bottom *= zoom
                    draw.rectangle([x0, top, x1, bottom], outline="red", width=3)
                except Exception:
                    continue

            buf2 = io.BytesIO()
            img_hl.save(buf2, format="PNG")
            page_hl_png = buf2.getvalue()

            return page_png, page_hl_png, None
        finally:
            doc.close()
    except Exception as e:
        return None, None, f"render_failed: {e}"


def save_debug_bundle(zip_path: str, pdf_text: PdfText, result: ParseResult, expected_text: str) -> None:
    """
    Save a reproducible bundle for bug reports:
      - input.pdf
      - raw text (full + per-page)
      - actual/expected text
      - debug_log.json
      - doc_type.txt
      + diff.txt
      + diagnosis.json
      + output_map.json
      + (optional) screenshots/page_01.png + screenshots_hl/page_01.png
    """
    exp = (expected_text or "").strip()
    act = (result.actual_text or "").strip()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        meta = {
            "app_version": APP_VERSION,
            "debug_schema_version": DEBUG_SCHEMA_VERSION,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "doc_type": result.doc_type,
            "pdf_filename": os.path.basename(pdf_text.pdf_path or ""),
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "issues": [
                {
                    "level": it.level,
                    "code": it.code,
                    "message": it.message,
                    "details": it.details,
                }
                for it in (result.issues or [])
            ],
        }
        zf.writestr("meta.json", json.dumps(meta, ensure_ascii=False, indent=2))

        zf.writestr("doc_type.txt", f"{result.doc_type}\n")
        zf.writestr("expected.txt", exp + ("\n" if exp else ""))
        zf.writestr("actual.txt", act + ("\n" if act else ""))
        zf.writestr("debug_log.json", json.dumps(result.debug_log or {}, ensure_ascii=False, indent=2))
        zf.writestr("raw_text_full.txt", pdf_text.raw_text or "")

        for i, ptxt in enumerate(pdf_text.page_texts or [], start=1):
            zf.writestr(f"raw_text_pages/page_{i:02d}.txt", ptxt or "")

        # New: diff + diagnosis + output_map
        try:
            if exp or act:
                zf.writestr("diff.txt", _make_diff(exp, act))
        except Exception:
            pass

        try:
            diagnosis = _make_diagnosis(result)
            zf.writestr("diagnosis.json", json.dumps(diagnosis, ensure_ascii=False, indent=2))
        except Exception:
            pass

        try:
            out_map = _build_output_map(result)
            zf.writestr("output_map.json", json.dumps(out_map, ensure_ascii=False, indent=2))
        except Exception:
            pass

        # Optional screenshots
        try:
            page_png, page_hl_png, err = _try_make_screenshots(pdf_text.pdf_path, result.highlights or {})
            if page_png:
                zf.writestr("screenshots/page_01.png", page_png)
            if page_hl_png:
                zf.writestr("screenshots_hl/page_01.png", page_hl_png)
            if err:
                # Keep a note for later troubleshooting; does not break bundle saving
                zf.writestr("screenshots_note.txt", f"{err}\n")
        except Exception:
            pass

        # Input PDF copy
        try:
            with open(pdf_text.pdf_path, "rb") as f:
                zf.writestr("input.pdf", f.read())
        except OSError:
            pass
