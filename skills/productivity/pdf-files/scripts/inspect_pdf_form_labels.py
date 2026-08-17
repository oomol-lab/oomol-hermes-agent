#!/usr/bin/env python3
"""Inspect visible AcroForm labels and their proximity to field widgets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import fitz
from pypdf import PdfReader


def load_labels(raw: str) -> dict[str, list[str]]:
    path = Path(raw)
    data = json.loads(path.read_text(encoding="utf-8") if path.is_file() else raw)
    if not isinstance(data, dict):
        raise SystemExit("labels must be a JSON object mapping field names to labels")
    labels: dict[str, list[str]] = {}
    for key, value in data.items():
        if not isinstance(key, str):
            continue
        if isinstance(value, str):
            labels[key] = [value]
        elif isinstance(value, list):
            items = [item for item in value if isinstance(item, str) and item]
            if items:
                labels[key] = items
    return labels


def rect_iou(first: list[float], second: list[float]) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    if right <= left or bottom <= top:
        return 0.0
    intersection = (right - left) * (bottom - top)
    first_area = max((first[2] - first[0]) * (first[3] - first[1]), 0.0)
    second_area = max((second[2] - second[0]) * (second[3] - second[1]), 0.0)
    union = first_area + second_area - intersection
    return intersection / union if union > 0 else 0.0


def rect_intersection_area(first: list[float], second: list[float]) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    if right <= left or bottom <= top:
        return 0.0
    return (right - left) * (bottom - top)


def widget_rects(reader: PdfReader) -> dict[str, dict[str, Any]]:
    widgets: dict[str, dict[str, Any]] = {}
    for page_index, page in enumerate(reader.pages):
        page_height = float(page.mediabox.top) - float(page.mediabox.bottom)
        for annot_ref in page.get("/Annots") or []:
            annot = annot_ref.get_object()
            if annot.get("/Subtype") != "/Widget":
                continue
            name = str(annot.get("/T") or annot.get("/TU") or "")
            rect = [float(value) for value in annot.get("/Rect", [])]
            if name and len(rect) == 4:
                left, bottom, right, top = rect
                widgets[name] = {
                    "page": page_index + 1,
                    "fitz_rect": [left, page_height - top, right, page_height - bottom],
                }
    return widgets


def inspect_labels(
    pdf_path: Path,
    labels: dict[str, list[str]],
    *,
    max_row_delta: float,
    min_label_gap: float,
    max_label_gap: float,
    min_above_gap: float,
    max_above_gap: float,
    max_above_x_delta: float,
) -> dict[str, Any]:
    reader = PdfReader(str(pdf_path))
    doc = fitz.open(pdf_path)
    widgets = widget_rects(reader)
    checks: list[dict[str, Any]] = []
    matched_labels: list[dict[str, Any]] = []
    problems: list[str] = []

    for field_name, label_texts in labels.items():
        widget = widgets.get(field_name)
        if not widget:
            problems.append(f"field {field_name}: widget missing")
            checks.append({"field": field_name, "labels": label_texts, "problem": "widget missing"})
            continue

        page = doc[widget["page"] - 1]
        widget_rect = widget["fitz_rect"]
        widget_left = widget_rect[0]
        widget_center_y = (widget_rect[1] + widget_rect[3]) / 2
        occurrences = []
        candidates = []
        for label_text in label_texts:
            for rect in page.search_for(label_text):
                bbox = [round(float(rect.x0), 2), round(float(rect.y0), 2), round(float(rect.x1), 2), round(float(rect.y1), 2)]
                occurrences.append({"label": label_text, "bbox": bbox})
                label_center_y = (bbox[1] + bbox[3]) / 2
                gap = widget_left - bbox[2]
                row_delta = abs(label_center_y - widget_center_y)
                if row_delta <= max_row_delta and min_label_gap <= gap <= max_label_gap:
                    candidates.append({
                        "label": label_text,
                        "bbox": bbox,
                        "gap": round(gap, 2),
                        "row_delta": round(row_delta, 2),
                        "placement": "left",
                    })
                above_gap = widget_rect[1] - bbox[3]
                x_delta = abs(bbox[0] - widget_rect[0])
                if min_above_gap <= above_gap <= max_above_gap and x_delta <= max_above_x_delta:
                    candidates.append({
                        "label": label_text,
                        "bbox": bbox,
                        "gap": round(above_gap, 2),
                        "row_delta": round(row_delta, 2),
                        "placement": "above",
                    })

        if not candidates:
            problems.append(f"field {field_name}: label is missing near its widget")
            checks.append({
                "field": field_name,
                "labels": label_texts,
                "widget": [round(value, 2) for value in widget_rect],
                "occurrences": occurrences,
                "problem": "no adjacent label",
            })
            continue

        best = sorted(
            candidates,
            key=lambda item: (0 if item["placement"] == "left" else 1, item["row_delta"], abs(item["gap"])),
        )[0]
        matched = {
            "field": field_name,
            "label": best["label"],
            "page": widget["page"],
            "bbox": best["bbox"],
            "widget": [round(value, 2) for value in widget_rect],
            "gap": best["gap"],
            "row_delta": best["row_delta"],
            "placement": best["placement"],
        }
        checks.append(matched)
        matched_labels.append(matched)

    for index, first in enumerate(matched_labels):
        for second in matched_labels[index + 1:]:
            if first["page"] != second["page"]:
                continue
            if (
                rect_intersection_area(first["bbox"], second["bbox"]) > 1.0
                or rect_iou(first["bbox"], second["bbox"]) >= 0.10
            ):
                problems.append(f"labels for fields {first['field']} and {second['field']} overlap")

    return {"ok": not problems, "checks": checks, "problems": problems}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--labels", required=True, help="JSON object or path mapping field names to labels.")
    parser.add_argument("--max-row-delta", type=float, default=10.0)
    parser.add_argument("--min-label-gap", type=float, default=2.0)
    parser.add_argument("--max-label-gap", type=float, default=160.0)
    parser.add_argument("--min-above-gap", type=float, default=3.0)
    parser.add_argument("--max-above-gap", type=float, default=24.0)
    parser.add_argument("--max-above-x-delta", type=float, default=12.0)
    args = parser.parse_args()

    result = inspect_labels(
        args.pdf,
        load_labels(args.labels),
        max_row_delta=args.max_row_delta,
        min_label_gap=args.min_label_gap,
        max_label_gap=args.max_label_gap,
        min_above_gap=args.min_above_gap,
        max_above_gap=args.max_above_gap,
        max_above_x_delta=args.max_above_x_delta,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
