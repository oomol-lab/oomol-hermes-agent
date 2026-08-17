---
name: office-files
description: Create, edit, convert, and inspect Microsoft Office files.
---

# Office Files

Use the OOMOL Hermes Agent image-provided Office stack. Do not install replacement document
libraries at runtime before trying the supported tools below.

## Default tools

- Use `markitdown` first for model-readable extraction from ordinary `.docx`,
  `.xlsx`, and simple `.pptx` files.
- Use `python-docx` for structured Word `.docx` creation or updates.
- Use `openpyxl` for structured Excel `.xlsx` or `.xlsm` creation or updates.
  Use `defusedxml`-safe parsing paths for untrusted XML-adjacent content.
- Use `python-pptx` for basic PowerPoint `.pptx` creation, inspection, or
  patching. Complex beautification, template filling, animations, and
  high-fidelity presentation generation are outside this skill's guarantee.
- Use `pandoc` for Markdown-to-Word and similar document conversions.
- Use LibreOffice through `soffice --headless` for Office-to-PDF export,
  format conversion, and legacy `.doc`, `.xls`, or `.ppt` handling.
- Use the bundled `pdf-files` skill for native PDF creation, AcroForm filling,
  static PDF delivery, verification, and digital signatures.

## Runtime

Use the image-provided Python environment directly:

```sh
/opt/hermes/.venv/bin/python
```

The OOMOL image installs `markitdown`, `docx`, `openpyxl`, `pptx`, and
`defusedxml` into this interpreter. It also installs LibreOffice, Pandoc, and
CJK fonts during the image build.

Do not install Office packages at runtime. Check only the tool needed for the
current task instead of probing every binary and Python module at once.

## PowerPoint boundary

This skill provides deterministic, basic `.pptx` work through `python-pptx`.
It does not include the old repository's PPT Master workflow. Convert legacy
`.ppt` input to `.pptx` with LibreOffice first, or export it to PDF when
editable structure is not required.

## PDF boundary

Office-to-PDF export stays in this skill: use LibreOffice for `.docx`, `.xlsx`,
`.pptx`, `.doc`, `.xls`, or `.ppt` conversion.

Native PDF work belongs to `pdf-files`: creating PDFs from scratch, creating
or filling AcroForms, flattening content into a static deliverable, inspecting
fields, verifying rendering and structure, or adding a test/real signature.

## LibreOffice runtime profile

LibreOffice must not write state under `/opt/hermes`. Use a unique writable
profile for each concurrent conversion, for example:

```sh
profile_dir="$(mktemp -d /tmp/libreoffice-profile.XXXXXX)"
soffice --headless --nologo --nofirststartwizard --norestore \
  -env:UserInstallation="file://${profile_dir}" \
  --convert-to pdf --outdir /tmp/out /path/to/input.docx
```

Remove the temporary profile after the conversion. Write user documents and
generated files under the requested workspace path, never under `/opt/hermes`.

## Verification

- Read created Office files back with their corresponding Python library.
- Use MarkItDown to confirm representative visible text when extraction is
  part of the request.
- For conversion, confirm LibreOffice exits successfully and the output file
  is non-empty.
- For Office-to-PDF delivery, use the `pdf-files` verification path when visual
  correctness matters.

## Limits

Legacy binary formats are conversion-only best effort. High-fidelity layout,
complex macros, password-protected files, embedded OLE objects, and proprietary
fonts are outside the default strong guarantee.
