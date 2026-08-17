#!/usr/bin/env python3
"""Inspect AcroForm widget rectangles and report layout problems."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pypdf import PdfReader


def inspect_widgets(
    pdf_path: Path,
    *,
    min_left: float,
    min_right: float,
    min_bottom: float,
    min_top: float,
    min_width: float,
    min_height: float,
) -> dict[str, Any]:
    reader = PdfReader(str(pdf_path))
    widgets: list[dict[str, Any]] = []
    problems: list[str] = []

    for page_index, page in enumerate(reader.pages):
        page_width = float(page.mediabox.width)
        page_height = float(page.mediabox.height)
        page_widgets: list[dict[str, Any]] = []
        for annot_ref in page.get("/Annots") or []:
            annot = annot_ref.get_object()
            if annot.get("/Subtype") != "/Widget":
                continue
            rect_values = annot.get("/Rect") or []
            if len(rect_values) != 4:
                problems.append(f"page {page_index + 1}: widget has invalid /Rect")
                continue
            left, bottom, right, top = [float(value) for value in rect_values]
            width = right - left
            height = top - bottom
            name = str(annot.get("/T") or annot.get("/TU") or "")
            item = {
                "name": name,
                "page": page_index + 1,
                "rect": [left, bottom, right, top],
                "width": width,
                "height": height,
            }
            widgets.append(item)
            page_widgets.append(item)

            label = name or "<unnamed>"
            if left < 0 or bottom < 0 or right > page_width or top > page_height:
                problems.append(f"page {page_index + 1}: widget {label} outside page bounds")
            if left < min_left:
                problems.append(f"page {page_index + 1}: widget {label} too close to left edge")
            if right > page_width - min_right:
                problems.append(f"page {page_index + 1}: widget {label} too close to right edge")
            if bottom < min_bottom:
                problems.append(f"page {page_index + 1}: widget {label} too close to bottom edge")
            if top > page_height - min_top:
                problems.append(f"page {page_index + 1}: widget {label} too close to top edge")
            if width < min_width or height < min_height:
                problems.append(f"page {page_index + 1}: widget {label} too small")

        for i, first in enumerate(page_widgets):
            for second in page_widgets[i + 1:]:
                left = max(first["rect"][0], second["rect"][0])
                bottom = max(first["rect"][1], second["rect"][1])
                right = min(first["rect"][2], second["rect"][2])
                top = min(first["rect"][3], second["rect"][3])
                if right <= left or top <= bottom:
                    continue
                overlap = (right - left) * (top - bottom)
                smaller = min(first["width"] * first["height"], second["width"] * second["height"])
                if smaller > 0 and overlap / smaller > 0.05:
                    first_name = first["name"] or "<unnamed>"
                    second_name = second["name"] or "<unnamed>"
                    problems.append(
                        f"page {page_index + 1}: widgets {first_name} and {second_name} overlap"
                    )

    return {"ok": not problems, "widget_count": len(widgets), "widgets": widgets, "problems": problems}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--min-left", type=float, default=36.0)
    parser.add_argument("--min-right", type=float, default=36.0)
    parser.add_argument("--min-bottom", type=float, default=72.0)
    parser.add_argument("--min-top", type=float, default=36.0)
    parser.add_argument("--min-width", type=float, default=24.0)
    parser.add_argument("--min-height", type=float, default=10.0)
    args = parser.parse_args()

    result = inspect_widgets(
        args.pdf,
        min_left=args.min_left,
        min_right=args.min_right,
        min_bottom=args.min_bottom,
        min_top=args.min_top,
        min_width=args.min_width,
        min_height=args.min_height,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
