#!/usr/bin/env python3
"""Create a static filled PDF from an AcroForm using a visible text overlay."""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, NameObject
from reportlab.pdfgen import canvas

from pdf_fonts import register_embedded_cjk_font


def load_values(raw: str) -> dict[str, str]:
    path = Path(raw)
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = json.loads(raw)
    if not isinstance(data, dict):
        raise SystemExit("values must be a JSON object")
    result: dict[str, str] = {}
    for key, value in data.items():
        if not isinstance(key, str):
            raise SystemExit("field names must be strings")
        result[key] = "" if value is None else str(value)
    return result


def field_widgets(reader: PdfReader) -> dict[str, list[dict[str, Any]]]:
    widgets: dict[str, list[dict[str, Any]]] = {}
    for page_index, page in enumerate(reader.pages):
        for annot_ref in page.get("/Annots") or []:
            annot = annot_ref.get_object()
            if annot.get("/Subtype") != "/Widget":
                continue
            name = annot.get("/T")
            if not name:
                continue
            rect = annot.get("/Rect") or []
            if len(rect) != 4:
                continue
            widgets.setdefault(str(name), []).append({
                "page_index": page_index,
                "annot_ref": annot_ref,
                "rect": [float(value) for value in rect],
            })
    return widgets


def draw_value(
    pdf_canvas: canvas.Canvas,
    value: str,
    rect: list[float],
    *,
    font_name: str,
    font_size: float,
) -> None:
    left, bottom, right, top = rect
    max_width = max(right - left - 6, 1)
    line_height = font_size * 1.25
    chars_per_line = max(int(max_width / (font_size * 0.9)), 1)
    lines = []
    remaining = value.strip()
    while remaining:
        lines.append(remaining[:chars_per_line])
        remaining = remaining[chars_per_line:]
    if not lines:
        return

    pdf_canvas.setFont(font_name, font_size)
    y = top - font_size - 3
    for line in lines:
        if y < bottom + 2:
            break
        pdf_canvas.drawString(left + 3, y, line)
        y -= line_height


def make_overlay(
    page_width: float,
    page_height: float,
    field_items: list[tuple[str, str, list[float]]],
    *,
    font_name: str,
    font_size: float,
) -> PdfReader:
    buffer = io.BytesIO()
    pdf_canvas = canvas.Canvas(buffer, pagesize=(page_width, page_height))
    pdf_canvas.setFillColorRGB(0, 0, 0)
    for _field_name, value, rect in field_items:
        draw_value(pdf_canvas, value, rect, font_name=font_name, font_size=font_size)
    pdf_canvas.save()
    buffer.seek(0)
    return PdfReader(buffer)


def remove_filled_widgets(page: Any, filled_names: set[str]) -> None:
    kept = ArrayObject()
    for annot_ref in page.get("/Annots") or []:
        annot = annot_ref.get_object()
        name = annot.get("/T")
        if annot.get("/Subtype") == "/Widget" and name and str(name) in filled_names:
            continue
        kept.append(annot_ref)
    if kept:
        page[NameObject("/Annots")] = kept
    elif "/Annots" in page:
        del page["/Annots"]


def prune_acroform(writer: PdfWriter, filled_names: set[str]) -> None:
    root = writer._root_object
    acroform = root.get("/AcroForm")
    if not acroform:
        return
    acroform_obj = acroform.get_object()
    kept = ArrayObject()
    for field_ref in acroform_obj.get("/Fields") or []:
        field = field_ref.get_object()
        name = field.get("/T")
        if name and str(name) in filled_names:
            continue
        kept.append(field_ref)
    if kept:
        acroform_obj[NameObject("/Fields")] = kept
    elif "/AcroForm" in root:
        del root["/AcroForm"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_pdf", type=Path)
    parser.add_argument("output_pdf", type=Path)
    parser.add_argument(
        "--values",
        required=True,
        help="JSON object or path to a JSON object of field values.",
    )
    parser.add_argument(
        "--font-path", help="Embedded CJK TrueType-outline TTF/TTC font path."
    )
    parser.add_argument("--font-size", type=float, default=9.0)
    args = parser.parse_args()

    values = load_values(args.values)
    font_name = register_embedded_cjk_font(
        args.font_path, required_text="".join(values.values())
    )
    reader = PdfReader(str(args.input_pdf))
    widgets = field_widgets(reader)
    missing = [name for name in values if name not in widgets]
    if missing:
        raise SystemExit(f"missing fields in input PDF: {missing}")

    writer = PdfWriter()
    writer.append(reader)
    for page_index, page in enumerate(writer.pages):
        page_width = float(page.mediabox.width)
        page_height = float(page.mediabox.height)
        page_fields = []
        for field_name, value in values.items():
            for widget in widgets[field_name]:
                if widget["page_index"] == page_index:
                    page_fields.append((field_name, value, widget["rect"]))
        if not page_fields:
            continue
        overlay = make_overlay(
            page_width,
            page_height,
            page_fields,
            font_name=font_name,
            font_size=args.font_size,
        )
        page.merge_page(overlay.pages[0])
        remove_filled_widgets(page, set(values))

    prune_acroform(writer, set(values))
    args.output_pdf.parent.mkdir(parents=True, exist_ok=True)
    with args.output_pdf.open("wb") as output:
        writer.write(output)
    print(f"wrote static filled PDF: {args.output_pdf}")


if __name__ == "__main__":
    main()
