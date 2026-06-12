from __future__ import annotations

import json
import os
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Any, Optional, Dict, List

from core.bundle import save_debug_bundle
from core.pipeline import Engine
from core.types import PdfText, ParseResult, HighlightRect

from ui.theme import (
    ACCENT,
    APP_BG,
    BG_BOTTOM,
    BG_TOP,
    CARD_BG,
    CARD_BORDER,
    MUTED,
    TEXT,
    Card,
    GradientBackground,
    ModernSlider,
    SoftButton,
    ToggleSwitch,
    soft_text,
)
from ui.pdf_viewer import PDF_VIEW_AVAILABLE, get_page_count, render_pdf_page_to_photo


# Optional drag & drop support
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore
    DND_AVAILABLE = True
except Exception:
    DND_AVAILABLE = False
    DND_FILES = None
    TkinterDnD = None


def run_ui(engine: Engine) -> None:
    if DND_AVAILABLE and TkinterDnD is not None:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()

    root.title("MVR / PSP Check — beta 1.0")
    root.geometry("1420x840")
    root.minsize(1100, 650)

    # ------------------------
    # State
    # ------------------------
    state: Dict[str, Any] = {
        "pdf_path": "",
        "pdf_text": None,      # type: Optional[PdfText]
        "result": None,        # type: Optional[ParseResult]
        "page_count": 0,
        "page_index": 0,
        "zoom": 1.5,
        "photo": None,
        "debug_panel_visible": True,
    }

    # ------------------------
    # Background
    # ------------------------
    bg = GradientBackground(root, BG_TOP, BG_BOTTOM)
    bg.pack(fill="both", expand=True)

    app = tk.Frame(bg, bg=APP_BG)
    app_id = bg.create_window(18, 18, anchor="nw", window=app)

    def _resize_app(_evt=None):
        w = bg.winfo_width()
        h = bg.winfo_height()
        bg.coords(app_id, 18, 18)
        bg.itemconfigure(app_id, width=max(10, w - 36), height=max(10, h - 36))

    bg.bind("<Configure>", _resize_app)

    # Layout
    app.grid_rowconfigure(1, weight=1)
    app.grid_columnconfigure(0, weight=1)

    # ------------------------
    # Topbar
    # ------------------------
    top = Card(app, radius=20, pad=14)
    top.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 10))
    top.grid_propagate(False)
    top.configure(height=104)

    tb = top.body
    tb.grid_columnconfigure(0, weight=0)
    tb.grid_columnconfigure(1, weight=1)
    tb.grid_columnconfigure(2, weight=0)

    # Variables (UI)
    show_hl_var = tk.BooleanVar(value=True)
    debug_mode_var = tk.BooleanVar(value=True)  # affects only preview visibility

    zoom_var = tk.DoubleVar(value=float(state["zoom"]))

    # Left: Choose PDF
    def choose_pdf() -> None:
        path = filedialog.askopenfilename(title="Select PDF", filetypes=[("PDF files", "*.pdf")])
        if not path:
            return
        process_pdf(path)

    SoftButton(tb, "Choose PDF", choose_pdf, kind="primary").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=10)

    # Center: Navigation + zoom + hide debug
    mid = tk.Frame(tb, bg=CARD_BG)
    mid.grid(row=0, column=1, sticky="ew")
    mid.grid_columnconfigure(99, weight=1)

    page_lbl = tk.Label(mid, text="Page: 0 / 0", bg=CARD_BG, fg=MUTED, font=("Segoe UI", 10))
    page_lbl.grid(row=0, column=0, sticky="w")

    doc_type_lbl = tk.Label(mid, text="Doc: -", bg=CARD_BG, fg=MUTED, font=("Segoe UI", 10))
    doc_type_lbl.grid(row=0, column=1, sticky="w", padx=(12, 0))

    def prev_page() -> None:
        if not state["pdf_path"]:
            return
        if state["page_index"] > 0:
            state["page_index"] -= 1
            redraw_pdf()

    def next_page() -> None:
        if not state["pdf_path"]:
            return
        if state["page_index"] < state["page_count"] - 1:
            state["page_index"] += 1
            redraw_pdf()

    SoftButton(mid, "◀ Prev", prev_page, width=80, height=32, radius=8).grid(row=0, column=2, padx=(14, 6))
    SoftButton(mid, "Next ▶", next_page, width=80, height=32, radius=8).grid(row=0, column=3, padx=6)

    tk.Label(mid, text="Zoom", bg=CARD_BG, fg=MUTED, font=("Segoe UI", 10)).grid(row=0, column=4, sticky="w", padx=(16, 6))

    zoom_value_lbl = tk.Label(mid, text=f"{zoom_var.get():.2f}x", bg=CARD_BG, fg=TEXT, font=("Segoe UI", 10, "bold"))
    zoom_value_lbl.grid(row=0, column=5, sticky="w", padx=(0, 8))

    _zoom_after_id: Dict[str, Optional[str]] = {"id": None}

    def _apply_zoom(v: float) -> None:
        # debounce in case user drags
        zoom_value_lbl.config(text=f"{v:.2f}x")
        state["zoom"] = float(v)
        redraw_pdf()

    def on_zoom_change(v: float) -> None:
        if _zoom_after_id["id"] is not None:
            root.after_cancel(_zoom_after_id["id"])
            _zoom_after_id["id"] = None

        def _do():
            _zoom_after_id["id"] = None
            _apply_zoom(float(zoom_var.get()))

        _zoom_after_id["id"] = str(root.after(40, _do))

    ModernSlider(mid, zoom_var, from_=0.8, to=2.0, resolution=0.05, width=220, height=26, command=on_zoom_change).grid(row=0, column=6, sticky="w")

    # Debug panel toggle button (does not remove Debug mode switch)
    def toggle_debug_panel() -> None:
        state["debug_panel_visible"] = not bool(state["debug_panel_visible"])
        apply_debug_panel_visibility()

    btn_toggle_debug_panel = SoftButton(mid, "Hide Debug", toggle_debug_panel, width=110, height=32, radius=8)
    btn_toggle_debug_panel.grid(row=0, column=7, padx=(16, 0), sticky="e")

    def check_updates() -> None:
        from core.update_checker import check_for_updates_async
        check_for_updates_async(root, silent=False)

    btn_check_updates = SoftButton(mid, "Check Updates", check_updates, width=120, height=32, radius=8)
    btn_check_updates.grid(row=0, column=8, padx=(12, 0), sticky="e")

    mid.grid_columnconfigure(9, weight=1)

    # Right: toggles (clean alignment, no clipping)
    right = tk.Frame(tb, bg=CARD_BG)
    right.grid(row=0, column=2, sticky="e", padx=(12, 0))
    right.grid_columnconfigure(1, weight=1)

    row1 = tk.Frame(right, bg=CARD_BG)
    row1.grid(row=0, column=0, sticky="e", pady=(2, 6))
    ToggleSwitch(row1, show_hl_var, width=50, height=24).pack(side="left")
    tk.Label(row1, text="Show highlights", bg=CARD_BG, fg=TEXT, font=("Segoe UI", 10)).pack(side="left", padx=10)

    row2 = tk.Frame(right, bg=CARD_BG)
    row2.grid(row=1, column=0, sticky="e")
    ToggleSwitch(row2, debug_mode_var, width=50, height=24).pack(side="left")
    tk.Label(row2, text="Debug mode", bg=CARD_BG, fg=TEXT, font=("Segoe UI", 10)).pack(side="left", padx=10)

    # ------------------------
    # Main 3-column area
    # ------------------------
    main = tk.Frame(app, bg=APP_BG)
    main.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 10))
    main.grid_rowconfigure(0, weight=1)
    main.grid_columnconfigure(0, weight=3)
    main.grid_columnconfigure(1, weight=4)
    main.grid_columnconfigure(2, weight=3)

    # Left card (actual/expected)
    c_left = Card(main, radius=22, pad=14)
    c_left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
    left = c_left.body
    left.grid_rowconfigure(1, weight=1)
    left.grid_rowconfigure(3, weight=1)
    left.grid_columnconfigure(0, weight=1)

    tk.Label(left, text="Actual output (program)", bg=CARD_BG, fg=TEXT, font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w")
    txt_actual = soft_text(left, height=8)
    txt_actual.grid(row=1, column=0, sticky="nsew", pady=(8, 14))

    tk.Label(left, text="Expected output (human checked)", bg=CARD_BG, fg=TEXT, font=("Segoe UI", 12, "bold")).grid(row=2, column=0, sticky="w")
    txt_expected = soft_text(left, height=8)
    txt_expected.grid(row=3, column=0, sticky="nsew", pady=(8, 0))

    # Middle card (PDF viewer)
    c_mid = Card(main, radius=22, pad=14)
    c_mid.grid(row=0, column=1, sticky="nsew", padx=10)
    midb = c_mid.body
    midb.grid_rowconfigure(1, weight=1)
    midb.grid_columnconfigure(0, weight=1)

    tk.Label(midb, text="PDF Viewer", bg=CARD_BG, fg=TEXT, font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w")

    canvas_frame = tk.Frame(midb, bg=CARD_BG)
    canvas_frame.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
    canvas_frame.grid_rowconfigure(0, weight=1)
    canvas_frame.grid_columnconfigure(0, weight=1)

    yscroll = tk.Scrollbar(canvas_frame, orient="vertical")
    yscroll.grid(row=0, column=1, sticky="ns")
    xscroll = tk.Scrollbar(canvas_frame, orient="horizontal")
    xscroll.grid(row=1, column=0, sticky="ew")

    canvas = tk.Canvas(canvas_frame, bg="#111115", highlightthickness=1, highlightbackground=CARD_BORDER,
                       yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
    canvas.grid(row=0, column=0, sticky="nsew")

    yscroll.config(command=canvas.yview)
    xscroll.config(command=canvas.xview)

    # Right card (debug preview)
    c_right = Card(main, radius=22, pad=14)
    c_right.grid(row=0, column=2, sticky="nsew", padx=(10, 0))
    rb = c_right.body
    rb.grid_rowconfigure(1, weight=1)
    rb.grid_columnconfigure(0, weight=1)

    tk.Label(rb, text="Debug log preview", bg=CARD_BG, fg=TEXT, font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w")
    txt_debug = soft_text(rb, height=18, readonly=True)
    txt_debug.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

    def apply_debug_panel_visibility() -> None:
        visible = bool(state["debug_panel_visible"])
        if visible:
            c_right.grid()
            main.grid_columnconfigure(2, weight=3)
            main.grid_columnconfigure(1, weight=4)
            btn_toggle_debug_panel.configure(text="Hide Debug")
        else:
            c_right.grid_remove()
            main.grid_columnconfigure(2, weight=0)
            main.grid_columnconfigure(1, weight=7)
            btn_toggle_debug_panel.configure(text="Show Debug")
        root.update_idletasks()
        redraw_pdf()

    # ------------------------
    # Bottom action bar
    # ------------------------
    bottom = Card(app, radius=20, pad=14)
    bottom.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 14))
    bottom.grid_propagate(False)
    bottom.configure(height=88)

    bb = bottom.body
    bb.grid_columnconfigure(0, weight=1)

    actions = tk.Frame(bb, bg=CARD_BG)
    actions.pack(fill="x", pady=6)

    beta_lbl = tk.Label(actions, text="beta 1.0", bg=CARD_BG, fg=MUTED, font=("Segoe UI", 9))
    beta_lbl.pack(side="right", padx=(10, 0))

    def save_actual_txt() -> None:
        content = txt_actual.get("1.0", "end").strip()
        if not content:
            messagebox.showinfo("Info", "Nothing to save.")
            return
        out_path = filedialog.asksaveasfilename(
            title="Save actual output",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt")]
        )
        if not out_path:
            return
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(content + "\n")
            messagebox.showinfo("Saved", f"Saved:\n{out_path}")
        except OSError as e:
            messagebox.showerror("Error", f"Failed to save:\n{e}")

    def copy_actual_clipboard() -> None:
        content = txt_actual.get("1.0", "end").strip()
        if not content:
            messagebox.showinfo("Info", "Nothing to copy.")
            return
        root.clipboard_clear()
        root.clipboard_append(content)
        messagebox.showinfo("Copied", "Copied to clipboard.")

    def save_bundle_zip() -> None:
        if not state["pdf_path"] or state["pdf_text"] is None or state["result"] is None:
            messagebox.showinfo("Info", "Load a PDF first.")
            return

        # Suggest an informative default name for bug-report bundles
        pdf_base = os.path.splitext(os.path.basename(state["pdf_text"].pdf_path or ""))[0]
        stamp = datetime.now().strftime("%Y-%m-%d__%H%M")
        doc = (state["result"].doc_type if state.get("result") else "UNKNOWN")
        default_name = f"{doc}__{pdf_base}__{stamp}.zip" if pdf_base else f"{doc}__{stamp}.zip"

        zip_path = filedialog.asksaveasfilename(
            title="Save debug bundle (ZIP)",
            defaultextension=".zip",
            filetypes=[("ZIP archive", "*.zip")],
            initialfile=default_name,
        )
        if not zip_path:
            return

        expected = txt_expected.get("1.0", "end").strip()
        try:
            save_debug_bundle(zip_path, state["pdf_text"], state["result"], expected)
            messagebox.showinfo("Saved", f"Debug bundle saved:\n{zip_path}")
        except OSError as e:
            messagebox.showerror("Error", f"Failed to save bundle:\n{e}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save bundle:\n{e}")

    SoftButton(actions, "Save actual .txt", save_actual_txt, width=140, height=38, radius=12).pack(side="left", padx=8)
    SoftButton(actions, "Copy actual", copy_actual_clipboard, width=140, height=38, radius=12).pack(side="left", padx=8)
    SoftButton(actions, "Save debug bundle (ZIP)", save_bundle_zip, kind="primary", width=220, height=38, radius=12).pack(side="right", padx=8)

    # ------------------------
    # PDF rendering + highlights
    # ------------------------
    def _on_mousewheel(event: tk.Event) -> None:
        delta = getattr(event, "delta", 0)
        if event.state & 0x0001:  # Shift
            canvas.xview_scroll(int(-1 * (delta / 120)), "units")
        else:
            canvas.yview_scroll(int(-1 * (delta / 120)), "units")

    canvas.bind("<MouseWheel>", _on_mousewheel)

    def redraw_pdf() -> None:
        canvas.delete("all")

        if state["page_count"] > 0:
            page_lbl.config(text=f"Page: {state['page_index'] + 1} / {state['page_count']}")
        else:
            page_lbl.config(text="Page: 0 / 0")

        if not state["pdf_path"]:
            if not PDF_VIEW_AVAILABLE:
                canvas.create_text(
                    20, 20, anchor="nw",
                    text="Install viewer deps: pip install pillow pymupdf",
                    fill=MUTED,
                    font=("Segoe UI", 12),
                )
            return

        if not PDF_VIEW_AVAILABLE:
            canvas.create_text(
                20, 20, anchor="nw",
                text="PDF viewer disabled (missing pillow/pymupdf).",
                fill=MUTED,
                font=("Segoe UI", 12),
            )
            return

        photo, w_px, h_px = render_pdf_page_to_photo(state["pdf_path"], int(state["page_index"]), float(state["zoom"]))
        if photo is None:
            return

        state["photo"] = photo  # keep reference
        canvas.config(scrollregion=(0, 0, w_px, h_px))
        canvas.create_image(0, 0, anchor="nw", image=state["photo"])

        if show_hl_var.get() and state["result"] is not None:
            rects = state["result"].highlights.get(int(state["page_index"]), [])
            z = float(state["zoom"])
            for r in rects:
                canvas.create_rectangle(r.x0 * z, r.top * z, r.x1 * z, r.bottom * z, outline="red", width=2)

    def set_debug_preview(text: str) -> None:
        txt_debug.configure(state="normal")
        txt_debug.delete("1.0", "end")
        txt_debug.insert("1.0", text)
        txt_debug.configure(state="disabled")

    def update_debug_preview() -> None:
        res: Optional[ParseResult] = state.get("result")
        if not res:
            set_debug_preview("")
            return
        if not debug_mode_var.get():
            set_debug_preview("(Debug mode is OFF)")
            return
        set_debug_preview(json.dumps(res.debug_log or {}, ensure_ascii=False, indent=2))

    def process_pdf(path: str) -> None:
        try:
            pdf_text, result = engine.run(path)

            state["pdf_path"] = path
            state["pdf_text"] = pdf_text
            state["result"] = result

            # doc labels
            doc_type_lbl.config(text=f"Doc: {result.doc_type}")

            # update actual field
            txt_actual.delete("1.0", "end")
            txt_actual.insert("1.0", result.actual_text or "")

            # debug preview (display only)
            update_debug_preview()

            # page count
            pc = get_page_count(path)
            state["page_count"] = int(pc) if pc > 0 else max(0, len(pdf_text.page_texts))
            state["page_index"] = 0

            # render
            redraw_pdf()

            # show any important issues
            if result.issues:
                # only show hard errors (warnings are non-blocking)
                errs = [i for i in result.issues if i.level == "error"]
                if errs:
                    messagebox.showwarning("Parsing issue", "\n".join(e.message for e in errs))

        except Exception as e:
            messagebox.showerror("Error", f"Failed:\n{e}")

    # toggle changes
    debug_mode_var.trace_add("write", lambda *_: update_debug_preview())
    show_hl_var.trace_add("write", lambda *_: redraw_pdf())

    # ------------------------
    # Drag & Drop
    # ------------------------
    if DND_AVAILABLE and DND_FILES is not None:
        import re as _re
        _DND_BRACED_RE = _re.compile(r"{([^}]+)}")

        def _extract_paths_from_dnd_event(data: str) -> List[str]:
            if not data:
                return []
            braced = _DND_BRACED_RE.findall(data)
            if braced:
                return [p.strip() for p in braced if p.strip()]
            parts = data.split()
            return [p.strip() for p in parts if p.strip()]

        def on_drop(event: Any) -> None:
            paths = _extract_paths_from_dnd_event(str(getattr(event, "data", "")))
            if not paths:
                return
            p = paths[0]
            if p.lower().endswith(".pdf"):
                process_pdf(p)
            else:
                messagebox.showwarning("Not a PDF", "Please drop a .pdf file.")

        try:
            root.drop_target_register(DND_FILES)  # type: ignore[arg-type]
            root.dnd_bind("<<Drop>>", on_drop)
        except Exception:
            pass

    # initial debug panel visibility
    apply_debug_panel_visibility()

    # Check for updates asynchronously in silent mode on startup
    try:
        from core.update_checker import check_for_updates_async
        check_for_updates_async(root, silent=True)
    except Exception as e:
        print(f"[UpdateCheck] Startup check failed: {e}")

    root.mainloop()
