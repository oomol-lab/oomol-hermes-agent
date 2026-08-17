#!/usr/bin/env python3
"""Create a labeled CJK AcroForm PDF from a compact JSON specification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from reportlab.lib.colors import HexColor, black
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from pdf_fonts import FONT_NAME, register_embedded_cjk_font


PAGE_WIDTH, PAGE_HEIGHT = A4
LEFT_MARGIN = 36.0
RIGHT_MARGIN = 36.0
TOP_MARGIN = 36.0
BOTTOM_MARGIN = 72.0


def load_spec(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("spec root must be a JSON object")
    return data


def as_text(value: Any) -> str:
    return "" if value is None else str(value)


def all_text(value: Any) -> str:
    if isinstance(value, dict):
        return "".join(
            all_text(item)
            for key, item in value.items()
            if key
            not in {"output", "name", "kind", "column_widths", "row_height", "height"}
        )
    if isinstance(value, list):
        return "".join(all_text(item) for item in value)
    return as_text(value)


def wrap_text(text: str, max_chars: int) -> list[str]:
    text = text.strip()
    if not text:
        return [""]
    lines: list[str] = []
    for raw_line in text.splitlines():
        remaining = raw_line.strip()
        while len(remaining) > max_chars:
            lines.append(remaining[:max_chars])
            remaining = remaining[max_chars:]
        lines.append(remaining)
    return lines or [""]


def draw_wrapped(
    pdf: canvas.Canvas,
    x: float,
    top_y: float,
    text: str,
    *,
    font_size: float,
    leading: float,
    max_chars: int,
) -> float:
    pdf.setFont(FONT_NAME, font_size)
    y = top_y
    for line in wrap_text(text, max_chars):
        pdf.drawString(x, y, line)
        y -= leading
    return y


def ensure_room(top_y: float, needed: float, label: str) -> None:
    if top_y - needed < BOTTOM_MARGIN:
        raise SystemExit(
            f"content does not fit on one A4 page before {label}; "
            "shorten body content or split the document into multiple pages"
        )


def draw_info_items(pdf: canvas.Canvas, y: float, items: list[Any]) -> float:
    pdf.setFont(FONT_NAME, 9)
    for item in items:
        if isinstance(item, dict):
            label = as_text(item.get("label"))
            value = as_text(item.get("value"))
            text = f"{label}：{value}" if label else value
        else:
            text = as_text(item)
        ensure_room(y, 13, "info items")
        y = draw_wrapped(
            pdf, LEFT_MARGIN + 8, y, text, font_size=9, leading=13, max_chars=54
        )
    return y


def draw_table(pdf: canvas.Canvas, y: float, table: dict[str, Any]) -> float:
    headers = [as_text(item) for item in table.get("headers", [])]
    rows = table.get("rows", [])
    if not headers or not isinstance(rows, list):
        return y

    available_width = PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN
    configured_widths = table.get("column_widths")
    if (
        isinstance(configured_widths, list)
        and len(configured_widths) == len(headers)
        and all(
            isinstance(item, (int, float)) and item > 0 for item in configured_widths
        )
    ):
        widths = [float(item) for item in configured_widths]
    else:
        widths = [available_width / len(headers)] * len(headers)
    scale = available_width / sum(widths)
    widths = [item * scale for item in widths]

    row_height = float(table.get("row_height", 24))
    header_height = 16.0
    ensure_room(y, header_height + row_height * len(rows) + 12, "table")

    x = LEFT_MARGIN
    pdf.setFillColor(HexColor("#e9eef5"))
    pdf.rect(x, y - header_height + 3, available_width, header_height, stroke=0, fill=1)
    pdf.setFillColor(black)
    pdf.setFont(FONT_NAME, 8.5)
    cx = x
    for header, width in zip(headers, widths, strict=True):
        pdf.drawString(cx + 3, y - 9, header)
        cx += width
    y -= header_height

    pdf.setStrokeColor(HexColor("#cccccc"))
    for row in rows:
        cells = row if isinstance(row, list) else []
        pdf.line(x, y + 3, x + available_width, y + 3)
        cx = x
        for index, width in enumerate(widths):
            cell = as_text(cells[index]) if index < len(cells) else ""
            max_chars = max(int(width / 7), 8)
            lines = wrap_text(cell, max_chars)[:2]
            pdf.setFont(FONT_NAME, 8)
            line_y = y - 8
            for line in lines:
                pdf.drawString(cx + 3, line_y, line)
                line_y -= 10
            cx += width
        y -= row_height
    pdf.line(x, y + 3, x + available_width, y + 3)
    return y - 14


def draw_sections(pdf: canvas.Canvas, y: float, sections: list[Any]) -> float:
    for section in sections:
        if not isinstance(section, dict):
            continue
        title = as_text(section.get("title"))
        bullets = section.get("bullets", [])
        if title:
            ensure_room(y, 18, title)
            pdf.setFont(FONT_NAME, 11)
            pdf.drawString(LEFT_MARGIN, y, title)
            y -= 18
        if isinstance(bullets, list):
            pdf.setFont(FONT_NAME, 8.5)
            for bullet in bullets:
                ensure_room(y, 12, title or "section")
                y = draw_wrapped(
                    pdf,
                    LEFT_MARGIN + 16,
                    y,
                    f"- {as_text(bullet)}",
                    font_size=8.5,
                    leading=12,
                    max_chars=62,
                )
        y -= 8
    return y


def draw_field_row(
    pdf: canvas.Canvas,
    y: float,
    row: list[dict[str, Any]],
    *,
    acroform: Any,
) -> float:
    row = [item for item in row if isinstance(item, dict)]
    if not row:
        return y

    available_width = PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN
    if len(row) == 1 and as_text(row[0].get("kind", "text")) == "multiline":
        item = row[0]
        label = as_text(item.get("label"))
        name = as_text(item.get("name"))
        height = float(item.get("height", 56))
        ensure_room(y, 14 + height + 10, label or name)
        pdf.setFont(FONT_NAME, 9)
        pdf.drawString(LEFT_MARGIN, y, label)
        field_top = y - 14
        acroform.textfield(
            name=name,
            tooltip=label or name,
            value="",
            fontSize=9,
            fontName="Helvetica",
            borderColor=HexColor("#999999"),
            borderWidth=1,
            borderStyle="solid",
            fillColor=HexColor("#fafafa"),
            textColor=black,
            forceBorder=True,
            x=LEFT_MARGIN,
            y=field_top - height,
            width=available_width,
            height=height,
        )
        return field_top - height - 16

    columns = min(len(row), 2)
    column_gap = 28.0
    column_width = (available_width - column_gap * (columns - 1)) / columns
    label_width = 104.0 if columns == 2 else 126.0
    field_height = 20.0
    ensure_room(y, field_height + 18, "form fields")

    for index, item in enumerate(row[:2]):
        label = as_text(item.get("label"))
        name = as_text(item.get("name"))
        x = LEFT_MARGIN + index * (column_width + column_gap)
        field_x = x + label_width
        field_width = column_width - label_width
        if field_width < 80:
            raise SystemExit(
                f"field {name or label} is too narrow; reduce columns or label width"
            )
        pdf.setFont(FONT_NAME, 9)
        pdf.drawString(x, y - 13, label)
        acroform.textfield(
            name=name,
            tooltip=label or name,
            value="",
            fontSize=9,
            fontName="Helvetica",
            borderColor=HexColor("#999999"),
            borderWidth=1,
            borderStyle="solid",
            fillColor=HexColor("#fafafa"),
            textColor=black,
            forceBorder=True,
            x=field_x,
            y=y - field_height,
            width=field_width,
            height=field_height,
        )
    return y - field_height - 18


def draw_fields(pdf: canvas.Canvas, y: float, field_rows: list[Any]) -> float:
    pdf.setFont(FONT_NAME, 11)
    pdf.drawString(LEFT_MARGIN, y, "供应商确认填写区")
    y -= 24
    for row in field_rows:
        if isinstance(row, dict):
            normalized = [row]
        elif isinstance(row, list):
            normalized = row
        else:
            continue
        y = draw_field_row(pdf, y, normalized, acroform=pdf.acroForm)
    return y


def create_pdf(spec: dict[str, Any], *, font_path: Path | None = None) -> None:
    raw_output = as_text(spec.get("output")).strip()
    if not raw_output:
        raise SystemExit("spec.output is required")
    output = Path(raw_output)
    output.parent.mkdir(parents=True, exist_ok=True)

    font_name = register_embedded_cjk_font(
        font_path,
        required_text=all_text(spec) + "供应商确认填写区：-",
    )
    pdf = canvas.Canvas(str(output), pagesize=A4)
    pdf.setTitle(as_text(spec.get("title")) or "PDF Form")

    y = PAGE_HEIGHT - TOP_MARGIN
    title = as_text(spec.get("title"))
    if title:
        pdf.setFont(font_name, 16)
        pdf.drawString(LEFT_MARGIN, y, title)
        y -= 24
        pdf.setStrokeColor(HexColor("#2f5fa8"))
        pdf.setLineWidth(1.5)
        pdf.line(LEFT_MARGIN, y, PAGE_WIDTH - RIGHT_MARGIN, y)
        y -= 18

    info_items = spec.get("info_items")
    if isinstance(info_items, list):
        y = draw_info_items(pdf, y, info_items)
        y -= 12

    table = spec.get("table")
    if isinstance(table, dict):
        table_title = as_text(table.get("title"))
        if table_title:
            pdf.setFont(FONT_NAME, 11)
            pdf.drawString(LEFT_MARGIN, y, table_title)
            y -= 16
        y = draw_table(pdf, y, table)

    sections = spec.get("sections")
    if isinstance(sections, list):
        y = draw_sections(pdf, y, sections)

    field_rows = spec.get("field_rows")
    if isinstance(field_rows, list):
        y = draw_fields(pdf, y, field_rows)

    if y < BOTTOM_MARGIN:
        raise SystemExit(
            f"content ended below safe bottom margin: y={y:.1f}, margin={BOTTOM_MARGIN}"
        )

    footer = as_text(spec.get("footer"))
    if footer:
        pdf.setFont(FONT_NAME, 7.5)
        pdf.setFillColor(HexColor("#888888"))
        pdf.drawString(LEFT_MARGIN, 36, footer)
        pdf.setFillColor(black)

    pdf.save()
    print(f"wrote labeled AcroForm PDF: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path, help="JSON form specification.")
    parser.add_argument(
        "--font-path",
        type=Path,
        help="Embedded CJK TrueType-outline TTF/TTC font path.",
    )
    args = parser.parse_args()
    create_pdf(load_spec(args.spec), font_path=args.font_path)


if __name__ == "__main__":
    main()
