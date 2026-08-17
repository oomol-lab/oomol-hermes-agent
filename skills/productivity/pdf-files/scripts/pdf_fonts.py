"""Embedded CJK font discovery shared by the PDF helper scripts."""

from __future__ import annotations

from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


FONT_NAME = "HermesCJK"


def _font_candidates() -> list[Path]:
    candidates = []
    candidates.extend(
        Path(path)
        for path in (
            "/usr/share/fonts/truetype/wqy-zenhei/wqy-zenhei.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
            "/usr/share/fonts/truetype/arphic/ukai.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttf",
            "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
            "/System/Library/Fonts/STHeiti Medium.ttc",
        )
    )
    return candidates


def _has_cjk_coverage(font: TTFont) -> bool:
    mapping = getattr(getattr(font, "face", None), "charToGlyph", None)
    if not isinstance(mapping, dict):
        return False
    return all(mapping.get(ord(character), 0) for character in ("中", "你", "的"))


def register_embedded_cjk_font(
    font_path: str | Path | None = None, *, required_text: str = ""
) -> str:
    """Register a real embedded CJK font and return its ReportLab name.

    CID fonts such as ``STSong-Light`` are intentionally not accepted: they
    can extract as text while rendering as blank glyphs in some readers.
    """

    candidates = (
        [Path(font_path).expanduser()]
        if font_path
        else [candidate for candidate in _font_candidates() if candidate.is_file()]
    )
    if not candidates:
        raise SystemExit(
            "no embeddable CJK TrueType/OpenType font found; install WQY Zen Hei or Noto Sans CJK "
            "or pass --font-path with a TrueType-outline .ttf/.ttc file"
        )
    errors = []
    for path in candidates:
        if path.suffix.lower() not in {".ttf", ".ttc"}:
            errors.append(f"{path}: unsupported suffix")
            continue
        try:
            font = TTFont(FONT_NAME, str(path), subfontIndex=0)
            if not _has_cjk_coverage(font):
                errors.append(f"{path}: no required CJK glyph coverage")
                continue
            mapping = font.face.charToGlyph
            unsupported = sorted({
                character
                for character in required_text
                if not character.isspace() and not mapping.get(ord(character), 0)
            })
            if unsupported:
                preview = " ".join(
                    f"U+{ord(character):04X}" for character in unsupported[:12]
                )
                errors.append(f"{path}: unsupported document characters {preview}")
                continue
            pdfmetrics.registerFont(font)
            return FONT_NAME
        except (
            Exception
        ) as exc:  # ReportLab exposes several font-parser exception types.
            errors.append(f"{path}: {exc}")
    detail = "; ".join(errors[-3:])
    raise SystemExit(
        "could not embed any discovered CJK font; install a TrueType font "
        f"(WQY Zen Hei) or pass --font-path: {detail}"
    )
