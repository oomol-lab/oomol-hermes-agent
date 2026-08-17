#!/usr/bin/env python3
"""Verify rendered/static PDF delivery quality."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import fitz
from pypdf import PdfReader


def _luminance(red: int, green: int, blue: int) -> float:
    def linearize(channel: int) -> float:
        value = channel / 255.0
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * linearize(red) + 0.7152 * linearize(green) + 0.0722 * linearize(blue)
    )


def _contrast_ratio(first: float, second: float) -> float:
    light, dark = max(first, second), min(first, second)
    return (light + 0.05) / (dark + 0.05)


def _pixel_reader(pix: fitz.Pixmap):
    """Return an on-demand RGB pixel reader without materializing the page."""

    channels = min(pix.n, 3)
    samples = pix.samples
    stride = pix.n

    def read(x: int, y: int) -> tuple[int, int, int]:
        offset = (y * pix.width + x) * stride
        if channels == 3:
            return (samples[offset], samples[offset + 1], samples[offset + 2])
        value = samples[offset]
        return (value, value, value)

    return read


def text_visibility(
    pdf_path: Path,
    *,
    scale: float = 2.0,
    min_ink_ratio: float = 0.005,
    min_contrast_ratio: float = 2.0,
    allow_invisible_ocr_text: bool = False,
) -> dict[str, Any]:
    """Check that every extracted text span has visible, contrasting ink.

    The background is estimated from the modal color inside each span, and
    rendered pixels are matched to the PDF text component colors.
    """

    doc = fitz.open(pdf_path)
    pages: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for page_index, page in enumerate(doc):
        page_pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        read_pixel = _pixel_reader(page_pix)
        traces = []
        for trace in page.get_texttrace():
            trace_text = "".join(
                chr(character[0]) for character in trace.get("chars", [])
            )
            traces.append((trace_text, fitz.Rect(trace["bbox"]), trace))
        spans = []
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans.extend(
                    span
                    for span in line.get("spans", [])
                    if str(span.get("text") or "").strip()
                )
        page_failures = []
        for span in spans:
            x0, y0, x1, y1 = (float(value) for value in span["bbox"])
            raw_bbox = fitz.Rect(x0, y0, x1, y1)
            span_text = str(span.get("text") or "")
            matching_traces = []
            for _trace_text, trace_bbox, trace in traces:
                intersection = trace_bbox & raw_bbox
                trace_area = max(trace_bbox.width * trace_bbox.height, 1.0)
                same_font = str(trace.get("font") or "") == str(span.get("font") or "")
                if (
                    same_font
                    and not intersection.is_empty
                    and intersection.width * intersection.height / trace_area >= 0.5
                ):
                    matching_traces.append(trace)
            invisible_mode = matching_traces and all(
                int(trace.get("type", 0)) == 3 for trace in matching_traces
            )
            if invisible_mode:
                if allow_invisible_ocr_text:
                    continue
                page_failures.append({
                    "text": span_text[:120],
                    "bbox": [round(value, 2) for value in (x0, y0, x1, y1)],
                    "ink_ratio": 0.0,
                    "contrast_ratio": 1.0,
                    "reason": "invisible text rendering mode",
                })
                continue
            bbox = (fitz.Rect(x0, y0, x1, y1) * page.rotation_matrix) & page.rect
            if bbox.is_empty or bbox.width <= 0 or bbox.height <= 0:
                continue
            inner_left = max(0, int((bbox.x0 - page.rect.x0) * scale))
            inner_top = max(0, int((bbox.y0 - page.rect.y0) * scale))
            inner_right = min(
                page_pix.width,
                max(inner_left + 1, int((bbox.x1 - page.rect.x0) * scale) + 1),
            )
            inner_bottom = min(
                page_pix.height,
                max(inner_top + 1, int((bbox.y1 - page.rect.y0) * scale) + 1),
            )
            inner = []
            for py in range(inner_top, inner_bottom):
                inner.extend(
                    read_pixel(px, py) for px in range(inner_left, inner_right)
                )
            if not inner:
                continue
            buckets: dict[tuple[int, int, int], int] = {}
            # The modal color inside the span is the best available estimate
            # of the surface beneath its glyph strokes. Using the outer ring
            # would misclassify short labels on a tight colored panel.
            for color in inner:
                bucket = tuple(channel // 16 * 16 for channel in color)
                buckets[bucket] = buckets.get(bucket, 0) + 1
            background = max(buckets, key=buckets.get)
            components = []
            for trace in matching_traces:
                if int(trace.get("type", 0)) == 3:
                    continue
                trace_color = trace.get("color") or (0.0, 0.0, 0.0)
                if len(trace_color) == 1:
                    trace_color = (trace_color[0], trace_color[0], trace_color[0])
                components.append((
                    tuple(round(float(value) * 255) for value in trace_color[:3]),
                    float(trace.get("opacity", 1.0)),
                ))
            if not components:
                raw_color = int(span.get("color") or 0)
                components.append((
                    ((raw_color >> 16) & 255, (raw_color >> 8) & 255, raw_color & 255),
                    float(span.get("alpha", 255)) / 255.0,
                ))

            component_results = []
            for foreground, alpha in components:
                effective_foreground = tuple(
                    round(
                        background[index]
                        + alpha * (foreground[index] - background[index])
                    )
                    for index in range(3)
                )
                vector = tuple(
                    effective_foreground[index] - background[index]
                    for index in range(3)
                )
                length_squared = sum(component * component for component in vector)

                def is_ink(color: tuple[int, int, int]) -> bool:
                    if length_squared == 0:
                        return False
                    progress = (
                        sum(
                            (color[index] - background[index]) * vector[index]
                            for index in range(3)
                        )
                        / length_squared
                    )
                    projected = tuple(
                        background[index] + progress * vector[index]
                        for index in range(3)
                    )
                    deviation = max(
                        abs(color[index] - projected[index]) for index in range(3)
                    )
                    return 0.08 <= progress <= 1.25 and deviation <= 24

                component_results.append((
                    sum(is_ink(color) for color in inner) / len(inner),
                    _contrast_ratio(
                        _luminance(*effective_foreground), _luminance(*background)
                    ),
                ))
            ink_ratio, contrast = max(
                component_results,
                key=lambda item: (
                    item[0] >= min_ink_ratio and item[1] >= min_contrast_ratio,
                    item[0],
                    item[1],
                ),
            )
            if not any(
                ink >= min_ink_ratio and ratio >= min_contrast_ratio
                for ink, ratio in component_results
            ):
                page_failures.append({
                    "text": str(span.get("text") or "")[:120],
                    "bbox": [round(value, 2) for value in (x0, y0, x1, y1)],
                    "ink_ratio": round(ink_ratio, 5),
                    "contrast_ratio": round(contrast, 3),
                })
        pages.append({
            "page": page_index + 1,
            "text_span_count": len(spans),
            "failures": page_failures,
        })
        failures.extend(
            {"page": page_index + 1, **failure} for failure in page_failures
        )
    return {"pages": pages, "failures": failures, "ok": not failures}


def unembedded_cid_fonts(reader: PdfReader) -> list[str]:
    """Return CID/Type0 fonts that have no embedded font program."""

    def resolve(value: Any) -> Any:
        return value.get_object() if hasattr(value, "get_object") else value

    def page_resources(page: Any) -> Any:
        current = page
        seen: set[int] = set()
        while current is not None:
            marker = id(current)
            if marker in seen:
                break
            seen.add(marker)
            resources = resolve(current.get("/Resources"))
            if resources:
                return resources
            current = resolve(current.get("/Parent"))
        return {}

    missing: set[str] = set()
    visited_resources: set[int] = set()

    def scan_resources(resources: Any) -> None:
        resources = resolve(resources) or {}
        marker = id(resources)
        if marker in visited_resources:
            return
        visited_resources.add(marker)
        fonts = resolve(resources.get("/Font")) or {}
        for _name, font_ref in fonts.items():
            font = resolve(font_ref)
            if str(font.get("/Subtype")) != "/Type0":
                continue
            descendants = resolve(font.get("/DescendantFonts")) or []
            embedded = False
            for descendant_ref in descendants:
                descriptor = resolve(descendant_ref).get("/FontDescriptor")
                if descriptor:
                    descriptor = resolve(descriptor)
                    embedded = embedded or any(
                        key in descriptor
                        for key in ("/FontFile", "/FontFile2", "/FontFile3")
                    )
            if not embedded:
                missing.add(str(font.get("/BaseFont") or _name))
        xobjects = resolve(resources.get("/XObject")) or {}
        for xobject_ref in xobjects.values():
            xobject = resolve(xobject_ref)
            if str(xobject.get("/Subtype")) == "/Form":
                scan_resources(xobject.get("/Resources"))

    for page in reader.pages:
        scan_resources(page_resources(page))

        def scan_appearance(value: Any) -> None:
            appearance = resolve(value)
            if not isinstance(appearance, dict):
                return
            resources = appearance.get("/Resources")
            if resources:
                scan_resources(resources)
            # Normal appearances are streams; button states use a nested
            # dictionary (/Off, /Yes, ...), so recurse through that mapping.
            if "/Subtype" not in appearance:
                for nested in appearance.values():
                    scan_appearance(nested)

        for annotation_ref in page.get("/Annots") or []:
            annotation = resolve(annotation_ref)
            appearance = resolve(annotation.get("/AP")) or {}
            for appearance_ref in appearance.values():
                scan_appearance(appearance_ref)
    root = resolve(reader.trailer.get("/Root")) or {}
    acroform = resolve(root.get("/AcroForm")) or {}
    scan_resources(resolve(acroform.get("/DR")))
    return sorted(missing)


def nonstatic_text_annotations(reader: PdfReader) -> list[dict[str, Any]]:
    """Find displayed text that bypasses the static page-content checks."""

    findings = []
    for page_number, page in enumerate(reader.pages, start=1):
        for annotation_ref in page.get("/Annots") or []:
            annotation = annotation_ref.get_object()
            subtype = str(annotation.get("/Subtype") or "")
            field_type = annotation.get("/FT")
            value = annotation.get("/V")
            parent = annotation.get("/Parent")
            seen_parents: set[int] = set()
            while parent and (field_type is None or value is None):
                parent = parent.get_object()
                marker = id(parent)
                if marker in seen_parents:
                    break
                seen_parents.add(marker)
                if field_type is None:
                    field_type = parent.get("/FT")
                if value is None:
                    value = parent.get("/V")
                parent = parent.get("/Parent")
            field_type = str(field_type or "")
            value = str(value or "").strip()
            contents = str(annotation.get("/Contents") or "").strip()
            if (subtype == "/Widget" and field_type == "/Tx" and value) or (
                subtype == "/FreeText" and contents
            ):
                findings.append({
                    "page": page_number,
                    "subtype": subtype,
                    "text": (value or contents)[:120],
                })
    return findings


def nonwhite_ratio(pdf_path: Path) -> dict[str, Any]:
    doc = fitz.open(pdf_path)
    pages = []
    total = 0.0
    for index, page in enumerate(doc):
        pix = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5), alpha=False)
        pixel_count = max(pix.width * pix.height, 1)
        nonwhite = 0
        for offset in range(0, len(pix.samples), pix.n):
            channels = pix.samples[offset : offset + min(pix.n, 3)]
            if any(channel < 245 for channel in channels):
                nonwhite += 1
        ratio = nonwhite / pixel_count
        total += ratio
        pages.append({
            "page": index + 1,
            "nonwhite_ratio": ratio,
            "width": pix.width,
            "height": pix.height,
        })
    return {
        "page_count": doc.page_count,
        "average_nonwhite_ratio": total / max(doc.page_count, 1),
        "pages": pages,
    }


def duplicate_nearby_text(pdf_path: Path, targets: list[str]) -> dict[str, Any]:
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

    doc = fitz.open(pdf_path)
    duplicates = []
    occurrences_by_target = {}
    for target in targets:
        occurrences = []
        for page_index, page in enumerate(doc):
            for rect in page.search_for(target):
                bbox = [
                    round(float(rect.x0), 2),
                    round(float(rect.y0), 2),
                    round(float(rect.x1), 2),
                    round(float(rect.y1), 2),
                ]
                occurrences.append({"page": page_index + 1, "bbox": bbox})
        occurrences_by_target[target] = occurrences
        for index, first in enumerate(occurrences):
            for second in occurrences[index + 1 :]:
                if first["page"] != second["page"]:
                    continue
                first_bbox = first["bbox"]
                second_bbox = second["bbox"]
                near_same_origin = (
                    abs(first_bbox[0] - second_bbox[0]) <= 4.0
                    and abs(first_bbox[1] - second_bbox[1]) <= 8.0
                )
                if near_same_origin or rect_iou(first_bbox, second_bbox) >= 0.25:
                    duplicates.append({
                        "text": target,
                        "page": first["page"],
                        "first_bbox": first_bbox,
                        "second_bbox": second_bbox,
                    })
    return {"duplicates": duplicates, "occurrences": occurrences_by_target}


def outside_page_text(pdf_path: Path, tolerance: float = 1.0) -> dict[str, Any]:
    """Find visible text whose bounding box falls outside its page MediaBox."""
    doc = fitz.open(pdf_path)
    overflow = []
    for page_index, page in enumerate(doc):
        page_rect = page.rect
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = str(span.get("text") or "").strip()
                    if not text:
                        continue
                    x0, y0, x1, y1 = (float(value) for value in span["bbox"])
                    if (
                        x0 < page_rect.x0 - tolerance
                        or y0 < page_rect.y0 - tolerance
                        or x1 > page_rect.x1 + tolerance
                        or y1 > page_rect.y1 + tolerance
                    ):
                        overflow.append({
                            "page": page_index + 1,
                            "text": text[:120],
                            "bbox": [
                                round(x0, 2),
                                round(y0, 2),
                                round(x1, 2),
                                round(y1, 2),
                            ],
                            "page_bbox": [
                                round(page_rect.x0, 2),
                                round(page_rect.y0, 2),
                                round(page_rect.x1, 2),
                                round(page_rect.y1, 2),
                            ],
                        })
    return {"overflow": overflow}


def run_command(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument(
        "--contains",
        action="append",
        default=[],
        help="Visible text that must be present; repeatable.",
    )
    parser.add_argument(
        "--no-duplicate-nearby",
        action="append",
        default=[],
        help="Text that must not repeat at nearby coordinates; repeatable.",
    )
    parser.add_argument("--min-nonwhite-ratio", type=float, default=0.002)
    parser.add_argument("--min-text-ink-ratio", type=float, default=0.005)
    parser.add_argument("--min-text-contrast-ratio", type=float, default=2.0)
    parser.add_argument(
        "--allow-invisible-ocr-text",
        action="store_true",
        help="Allow rendering-mode-3 text layers in image-backed OCR PDFs.",
    )
    parser.add_argument("--skip-qpdf", action="store_true")
    parser.add_argument("--skip-poppler", action="store_true")
    args = parser.parse_args()

    problems = []
    reader = PdfReader(str(args.pdf))
    fitz_text = "\n".join(page.get_text() or "" for page in fitz.open(args.pdf))
    pypdf_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if not fitz_text.strip():
        problems.append("PDF contains no extractable text; lines/background pixels are not sufficient")
    missing_cid_fonts = unembedded_cid_fonts(reader)
    if missing_cid_fonts:
        problems.append(
            f"unembedded CID fonts are not suitable for delivery: {missing_cid_fonts}"
        )
    annotation_text = nonstatic_text_annotations(reader)
    if annotation_text:
        problems.append(
            "text annotations require static flattening before delivery visibility can be verified: "
            f"{annotation_text}"
        )
    missing = [text for text in args.contains if text not in fitz_text]
    if missing:
        problems.append(f"missing visible text: {missing}")

    visibility = text_visibility(
        args.pdf,
        min_ink_ratio=args.min_text_ink_ratio,
        min_contrast_ratio=args.min_text_contrast_ratio,
        allow_invisible_ocr_text=args.allow_invisible_ocr_text,
    )
    if not visibility["ok"]:
        problems.append(
            f"text spans have no visible contrasting ink: {visibility['failures']}"
        )

    render = nonwhite_ratio(args.pdf)
    if (
        render["page_count"] < 1
        or render["average_nonwhite_ratio"] < args.min_nonwhite_ratio
    ):
        problems.append(
            f"rendered page too blank: {render['average_nonwhite_ratio']:.4f} across {render['page_count']} pages"
        )

    duplicate_result = duplicate_nearby_text(args.pdf, args.no_duplicate_nearby)
    if duplicate_result["duplicates"]:
        problems.append(f"duplicate nearby text: {duplicate_result['duplicates']}")

    page_overflow_result = outside_page_text(args.pdf)
    if page_overflow_result["overflow"]:
        problems.append(
            f"visible text outside page bounds: {page_overflow_result['overflow']}"
        )

    qpdf_result: dict[str, Any] | None = None
    if not args.skip_qpdf and shutil.which("qpdf"):
        qpdf_result = run_command(["qpdf", "--check", str(args.pdf)])
        if not qpdf_result["ok"]:
            problems.append("qpdf --check failed")

    poppler_result: dict[str, Any] | None = None
    if not args.skip_poppler and shutil.which("pdftoppm"):
        with tempfile.TemporaryDirectory() as tmp_dir:
            page_results = []
            markers = (
                "syntax error",
                "no font",
                "missing language pack",
                "non-page object",
                "invalid key",
            )
            full_prefix = str(Path(tmp_dir) / "render-full")
            full_result = run_command(["pdftoppm", "-png", str(args.pdf), full_prefix])
            full_combined = f"{full_result['stdout']}\n{full_result['stderr']}".lower()
            full_failed = not full_result["ok"] or any(
                marker in full_combined for marker in markers
            )
            if full_failed:
                page_problem_count = len(problems)
                for page_number in range(1, len(reader.pages) + 1):
                    prefix = str(Path(tmp_dir) / f"render-{page_number}")
                    page_result = run_command([
                        "pdftoppm",
                        "-png",
                        "-f",
                        str(page_number),
                        "-l",
                        str(page_number),
                        "-singlefile",
                        str(args.pdf),
                        prefix,
                    ])
                    combined = (
                        f"{page_result['stdout']}\n{page_result['stderr']}".lower()
                    )
                    page_result["page"] = page_number
                    page_result["ok"] = page_result["ok"] and not any(
                        marker in combined for marker in markers
                    )
                    page_results.append(page_result)
                    if not page_result["ok"]:
                        problems.append(
                            f"Poppler render failed or reported errors on page {page_number}"
                        )
                if len(problems) == page_problem_count:
                    problems.append(
                        "Poppler full-document render failed or reported structural/font errors"
                    )
            else:
                page_results = [
                    {
                        "page": page_number,
                        "ok": True,
                        "returncode": 0,
                    }
                    for page_number in range(1, len(reader.pages) + 1)
                ]
            poppler_result = {
                "ok": not full_failed and all(item["ok"] for item in page_results),
                "full_document": {
                    **full_result,
                    "ok": not full_failed,
                },
                "pages": page_results,
            }

    result = {
        "ok": not problems,
        "problems": problems,
        "fitz_text_present": bool(fitz_text.strip()),
        "pypdf_text_present": bool(pypdf_text.strip()),
        "unembedded_cid_fonts": missing_cid_fonts,
        "nonstatic_text_annotations": annotation_text,
        "text_visibility": visibility,
        "missing": missing,
        "render": render,
        "duplicate_nearby_text": duplicate_result,
        "outside_page_text": page_overflow_result,
        "qpdf": qpdf_result,
        "poppler": poppler_result,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
