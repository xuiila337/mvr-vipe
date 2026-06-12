# MVR / PSP Check (Desktop) — beta 1.0

This is a modularized version of the desktop tool:

- Detects PDF type (MVR / PSP)
- Extracts text via `pdfplumber`
- Parses MVR or PSP and produces:
  - Actual output (compact)
  - Debug JSON (for bug bundles)
- Renders PDF pages via `PyMuPDF + Pillow`
- Highlights important fragments using `pdfplumber.extract_words()`
- Allows saving a debug ZIP bundle (pdf + raw text + actual/expected + debug json)

## Install

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
python app.py
```

If you don't need drag&drop, you can uninstall tkinterdnd2.

If you see "PDF viewer disabled", install:

```bash
pip install pillow pymupdf
```
