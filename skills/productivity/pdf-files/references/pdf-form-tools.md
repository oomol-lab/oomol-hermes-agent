# PDF Form Helper Tools

Use these bundled helper scripts before writing one-off PDF form code. They are
synced under `${HERMES_HOME}/skills/productivity/pdf-files` and run with the
image-provided `/opt/hermes/.venv/bin/python`.

## Create Labeled Blank Forms

Use `scripts/create_labeled_acroform.py` when creating a normal business
AcroForm from scratch. It takes a compact JSON spec, draws CJK visible labels
and body content, and places short text fields in one- or two-column rows with
safe label/field spacing. Use it before writing custom coordinate code.

```sh
/opt/hermes/.venv/bin/python \
  "${HERMES_HOME}/skills/productivity/pdf-files/scripts/create_labeled_acroform.py" \
  /opt/data/test-outputs/form-spec.json
```

Example field rows:

```json
[
  [
    {"name": "supplier_contact", "label": "供应商联系人"},
    {"name": "first_shipment_date", "label": "预计首批发货日期"}
  ],
  [
    {"name": "supplier_owner", "label": "整改负责人"},
    {"name": "confirmation_date", "label": "确认日期"}
  ],
  [{"name": "purchase_owner", "label": "采购负责人"}],
  [{"name": "supplier_note", "label": "供应商备注", "kind": "multiline", "height": 56}]
]
```

This helper is the default path for supplier confirmation forms, approval forms,
intake forms, and other ordinary labeled business PDFs. It keeps the generated
implementation small: the agent should produce business content plus a JSON
layout spec, not a large one-off coordinate script.

## Inspect Blank Form Widgets

Use `scripts/inspect_pdf_widgets.py` after creating an AcroForm. It checks page
bounds, safe margins, minimum field size, and widget overlap.

```sh
/opt/hermes/.venv/bin/python \
  "${HERMES_HOME}/skills/productivity/pdf-files/scripts/inspect_pdf_widgets.py" \
  /opt/data/test-outputs/form.pdf
```

Default safety rules:

- left edge >= 36 pt
- right edge <= page width - 36 pt
- bottom edge >= 72 pt
- top edge <= page height - 36 pt
- no widget overlap above 5 percent of the smaller widget area

Widget inspection is not enough for delivery. Also render or inspect text
coordinates and verify that each visible field label is placed beside the
field it describes. In a two-column form, the right-column label must be drawn
near the right-column field, not at the left-column label coordinate. Treat
overlapping labels, labels that cover body text, or labels that are not on the
same row as their widgets as form layout defects.

Use `scripts/inspect_pdf_form_labels.py` for this label/widget proximity check:

```sh
/opt/hermes/.venv/bin/python \
  "${HERMES_HOME}/skills/productivity/pdf-files/scripts/inspect_pdf_form_labels.py" \
  /opt/data/test-outputs/form.pdf \
  --labels '{"supplier_contact":"供应商联系人","supplier_note":"供应商备注"}'
```

Recommended blank-form closeout:

1. Generate the form from a JSON spec.
2. Run widget inspection for bounds and overlap.
3. Run label inspection for label/widget proximity and label overlap.
4. Render one page with Poppler or PyMuPDF and visually inspect dense form
   areas, especially the last rows and multiline fields.
5. If a check fails, fix the specific failed condition before changing other
   layout code.

## Static Filled PDF

Use `scripts/fill_acroform_static.py` when the user needs filled values to be
visible in ordinary PDF readers. It reads AcroForm widget rectangles, draws a
CJK text overlay, merges the overlay, removes filled text widgets, and prunes
filled fields from `/AcroForm`.

```sh
/opt/hermes/.venv/bin/python \
  "${HERMES_HOME}/skills/productivity/pdf-files/scripts/fill_acroform_static.py" \
  /opt/data/test-outputs/form.pdf \
  /opt/data/test-outputs/filled.pdf \
  --values '{"supplier_contact":"刘志强","confirmation_date":"2026-07-02"}'
```

Use a JSON file for larger values to avoid shell escaping mistakes:

```sh
/opt/hermes/.venv/bin/python \
  "${HERMES_HOME}/skills/productivity/pdf-files/scripts/fill_acroform_static.py" \
  input.pdf output.pdf --values values.json
```

## Delivery Verification

Use `scripts/verify_pdf_delivery.py` for final PDFs. It checks PyMuPDF visible
text, per-span rendered ink and contrast, embedded CJK fonts, rendered
nonblank pages, duplicate nearby text, `qpdf --check`, and every-page Poppler
rendering when available.

```sh
/opt/hermes/.venv/bin/python \
  "${HERMES_HOME}/skills/productivity/pdf-files/scripts/verify_pdf_delivery.py" \
  /opt/data/test-outputs/filled.pdf \
  --contains 2026-07-02 \
  --contains 刘志强 \
  --no-duplicate-nearby 2026-07-02 \
  --no-duplicate-nearby 刘志强
```

Do not treat `pypdf` text extraction as the only source of truth for final
visual delivery. The verifier rejects text spans whose rendered pixels have no
measurable contrast with their local background, including white-on-white and
black-on-black text. Prefer PyMuPDF visible text and rendered output checks.

## Test Signature

Use `scripts/sign_pdf_test_cert.py` only when the user explicitly allows a test
signature. It creates a short-lived self-signed certificate in memory and signs
with pyHanko.

```sh
/opt/hermes/.venv/bin/python \
  "${HERMES_HOME}/skills/productivity/pdf-files/scripts/sign_pdf_test_cert.py" \
  /opt/data/test-outputs/filled.pdf \
  /opt/data/test-outputs/signed.pdf \
  --field-name TestSignature
```

Never use this helper for production signatures. Real private keys, PINs,
certificates, timestamp services, and HSM settings must be provided by the user
or runtime secrets.
