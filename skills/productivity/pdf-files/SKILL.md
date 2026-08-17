---
name: pdf-files
description: Create, inspect, fill, verify, and sign PDF files.
---

# PDF Files

Use this skill when the user asks to create, inspect, fill, verify, or digitally
sign PDF files.

This includes Chinese requests such as `生成 PDF`, `创建 PDF 表单`, `填写 PDF`,
`生成静态已填写 PDF`, `PDF 数字签名`, or `给 PDF 签名`.

## Route Boundaries

- For converting Office files such as `.docx`, `.xlsx`, or `.pptx` to PDF, use
  the bundled `office-files` skill and LibreOffice `soffice --headless`.
- For using a PDF as source material for a basic PowerPoint deck, extract the
  source content first and then use the bundled `office-files` skill.
- For scanned or image-only PDFs where text extraction fails, use the bundled
  `ocr-and-documents` skill before attempting structured PDF editing.
- Do not install PDF libraries at runtime. The image already provides the
  supported PDF stack.

## Default Tool Choices

Use the image-provided Python environment:

```sh
/opt/hermes/.venv/bin/python
```

The image already installs:

- `reportlab` for creating PDF pages and AcroForm fields.
- `pypdf` for reading, filling, and inspecting PDF forms.
- `PyMuPDF` (`fitz`) for rendering pages and checking visible text.
- Poppler `pdftoppm` / `pdfinfo` for independent render and metadata checks.
- `qpdf` for PDF structure checks.
- `pyHanko` / `pyhanko-cli` for digital signatures.
- `tzdata` for pyHanko behavior in slim images.

Reusable helper scripts are bundled under this skill. Prefer them over writing
one-off scripts for common form inspection, static filling, delivery
verification, and test signing. See `references/pdf-form-tools.md`.

## Working Defaults

- Start labeled AcroForms from a JSON spec plus
  `scripts/create_labeled_acroform.py`. Let the helper own two-column geometry,
  multiline note spacing, CJK labels, and safe margins.
- Do not spend time hand-tuning coordinates for common business forms. If a
  form needs unusual geometry, first explain why the helper does not fit, then
  write custom layout code.
- Treat field labels as part of the deliverable, not decoration. A form can have
  valid widgets and still be unusable if labels overlap, sit beside the wrong
  field, or touch multiline boxes.
- For every report table, calculate its available width from the page size minus
  both horizontal margins before calling `Table`. Require
  `sum(col_widths) <= available_width`; ReportLab does not shrink an oversized
  table automatically. If the columns do not fit, shorten or wrap cell content,
  reduce column widths/font size, split the table, or use a landscape page.
- After a failed verification, inspect the named failing check before making
  another attempt. Record whether the trigger was widget bounds, label
  placement, missing visible text, duplicate filled text, font rendering, or PDF
  structure.

## Creation Path

For business PDFs, create the file programmatically with `reportlab`. For CJK
content, register an embedded TrueType-outline TTF/TTC font before drawing Chinese
text. The bundled helpers discover the image's embedded CJK font (or accept an
explicit `--font-path`) and reject unembedded CID fonts such as `STSong-Light`:

```python
import os
import sys

bundled_root = os.environ.get(
    "HERMES_BUNDLED_SKILLS", "/opt/oomol-hermes-agent/curated-skills"
)
sys.path.insert(0, f"{bundled_root}/productivity/pdf-files/scripts")
from pdf_fonts import register_embedded_cjk_font  # noqa: E402
from reportlab.pdfgen import canvas as canvas_module

font_name = register_embedded_cjk_font()
pdf = canvas_module.Canvas(output_path)
pdf.setFont(font_name, 11)
```

Every text object must use a CJK-capable font. Setting the canvas font is not
enough for Platypus paragraphs, tables, headers, or footers:

```python
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import TableStyle

body_style = ParagraphStyle("BodyCJK", fontName=font_name, fontSize=10, leading=14)
table.setStyle(TableStyle([
    ("FONTNAME", (0, 0), (-1, -1), font_name),
]))
```

Write generated files under the user's requested output path, not under
`/opt/hermes`.

## AcroForm Path

For fillable PDF forms:

- When creating a normal labeled business form from scratch, prefer
  `scripts/create_labeled_acroform.py` with a JSON spec before writing custom
  coordinate code. The helper handles CJK labels, one- or two-column text
  fields, multiline note fields, and safe label/field spacing.
- Use stable, semantic field names such as `supplier_contact`,
  `first_shipment_date`, or `purchase_owner`.
- After creating a blank form, run
  `scripts/inspect_pdf_widgets.py` to verify widget bounds, margins, size, and
  overlap before delivering it.
- Also verify that each visible field label is adjacent to its corresponding
  widget. In two-column layouts, draw the right-column label near the
  right-column field rather than reusing the left-column label coordinate.
- Keep known business facts as normal visible page text.
- Use AcroForm text fields only for values the user expects to fill later.
- Keep widget rectangles inside the page, large enough for the expected value,
  and non-overlapping.
- Leave practical safe margins for form widgets: at least 36 pt from the left
  and right page edges, at least 72 pt from the bottom edge, and avoid placing
  editable fields in the footer area.
- For final delivery, prefer a static filled PDF generated from the same data or
  a visible text overlay on top of the form. Do not rely on `pypdf
  flatten=True` as the default delivery guarantee, especially for CJK content.
- Blank interactive widgets use ReportLab's standard form font; use
  `scripts/fill_acroform_static.py` for CJK values before delivery, which
  writes an embedded-font overlay and removes filled widgets.
- When using a visible overlay, do not leave the filled AcroForm text widget
  appearances visible underneath it. Remove or hide the filled text widget
  annotations and prune those fields from `/AcroForm`, or regenerate a true
  static filled PDF. Keep only fields that are still needed later, such as a
  signature field.

Typical field update approach:

```python
from pypdf import PdfReader, PdfWriter

reader = PdfReader(input_path)
writer = PdfWriter()
writer.append(reader)
writer.update_page_form_field_values(
    writer.pages[0],
    {"supplier_contact": "value"},
    auto_regenerate=True,
)
with open(output_path, "wb") as output:
    writer.write(output)
```

If the user asks for broadly visible final content:

- For PDFs created by this skill, regenerate the final static PDF from the
  source business data and filled values.
- For an existing form, prefer `scripts/fill_acroform_static.py`. If you must
  implement the workflow manually, follow this deterministic static-fill path:
  1. Inspect field names and `/Rect` coordinates with `pypdf`.
  2. Create a same-size `reportlab` overlay page and draw every filled value at
     the matching field rectangle using a CJK-capable font.
  3. Merge the overlay onto the original page.
  4. Remove or hide the filled text widget annotations and prune those text
     fields from `/AcroForm`. Keep only fields that are still needed later, such
     as a signature field.
  5. Verify the final PDF with `fitz` visible text extraction, `fitz` rendering,
     `qpdf --check`, and Poppler rendering when available.
- Verify that important filled values do not appear twice at nearly identical
  coordinates. Duplicate field appearance plus overlay text is a delivery
  defect even when text extraction and structure checks pass.
- Prefer `scripts/verify_pdf_delivery.py` for final render, structure, visible
  text, and duplicate-nearby-text checks.
- If a first attempt fails verification, inspect and record the exact failing
  check before writing a new script. Do not repeatedly rewrite fill scripts
  without naming the reason, such as widget outside page bounds, missing visible
  text, duplicate overlay text, missing CJK font, or PDF structure error.

## Signature Path

Use `pyHanko` for PDF signatures. When the user explicitly allows a test
signature, generate a short-lived test certificate at runtime and discard it
after use.

For test signatures, prefer `scripts/sign_pdf_test_cert.py` instead of writing a
new certificate/signing script.

Sign only after the filled PDF has passed visual/static verification. The
signing step should preserve the already verified content and add the requested
signature field; it should not refill the form or add another visible text
overlay.

Do not ask for, invent, or store production certificate material. Real private
keys, PINs, HSM/PKCS#11 configuration, timestamp service credentials, and
company certificates must come from runtime secrets, external services, or the
user.

## Verification

After creating or modifying a PDF:

- Confirm the output file exists and is non-empty.
- Read it back with `pypdf.PdfReader`.
- For created business PDFs, extract text with both `pypdf` and `fitz` when
  possible, and check key IDs, dates, and representative Chinese business text.
- Run `scripts/verify_pdf_delivery.py` with representative `--contains`
  markers. It checks every extracted text span for actual rendered ink and a
  minimum foreground/background contrast, and rejects unembedded CID fonts.
- For an image-backed OCR PDF only, pass `--allow-invisible-ocr-text` to permit
  its standard rendering-mode-3 searchable text layer. Do not use this option
  for generated business PDFs or to bypass a failed visible-text check.
- Render at least the first page with `fitz` and check that the pixmap is not
  blank.
- For PDFs containing tables, render every table page and visually inspect that
  table borders, headers, and cell text remain inside the page margins. A
  successful text extraction or `qpdf --check` does not establish this.
- Run `qpdf --check` when available.
- Run `pdftoppm` when available if visual delivery matters; it must render every
  page without font or syntax errors. PyMuPDF and Poppler are deliberately
  independent renderer checks.
- For blank forms, inspect `reader.get_fields()` and verify expected field names.
- For blank forms, inspect widget rectangles and ensure fields do not overlap or
  fall outside page bounds.
- For blank forms, render the page or inspect text coordinates and ensure field
  labels do not overlap each other, do not cover body text, and sit on the same
  row as the field they describe.
- For signed PDFs, inspect `reader.get_fields()` and confirm at least one field
  has `/FT` equal to `/Sig`.

## Boundaries

- The default PDF contract covers basic PDFs, AcroForm fields, static filled PDF
  delivery, render/structure checks, and local certificate signing.
- XFA forms, complex PDF repair, long-term validation, OCSP/CRL, timestamp
  services, enterprise CA policy, and HSM integration are outside the default
  strong guarantee.
- Do not store user PDFs, certificates, keys, or generated artifacts under
  `/opt/hermes`.
