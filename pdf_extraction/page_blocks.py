"""Convert a single PDF page into content/code blocks.

PyMuPDF ("fitz") yields a page as nested dict blocks → lines → spans, each span carrying
text, font and size. The strategy: extract tables first (recording their bounding boxes),
then walk text blocks, skipping any that overlap a table (to avoid double-counting), and
classify each remaining block by font (monospace → code), size (large → heading) or
default (paragraph). The page's median span size anchors the heading threshold.
"""
from __future__ import annotations

from domain.records import CodeBlock, ContentBlock
from pdf_extraction.block_builders import (
    append_code_block,
    append_heading_block,
    append_paragraph_block,
)
from pdf_extraction.constants import HEADING_SIZE_RATIO, MONO_FONT_HINTS


def page_to_blocks(page, code_offset: int = 0) -> tuple[list[ContentBlock], list[CodeBlock]]:
    """Extract ordered content and code blocks from one page."""
    import fitz

    content: list[ContentBlock] = []
    code: list[CodeBlock] = []

    page_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
    median_size = _median_body_size(page_dict)
    table_bboxes = _extract_tables(page, content)

    for blk in page_dict["blocks"]:
        if blk.get("type") != 0:
            continue
        if table_bboxes and _overlaps(blk["bbox"], table_bboxes):
            continue

        text, max_size, is_mono = _block_text_info(blk)
        if not text:
            continue
        if is_mono:
            append_code_block(content, code, text, code_offset)
        elif max_size > median_size * HEADING_SIZE_RATIO:
            append_heading_block(content, text, max_size / median_size)
        else:
            append_paragraph_block(content, text)

    return content, code


def _median_body_size(page_dict) -> float:
    """Median non-blank span size on the page (defaults to 12.0 when empty)."""
    sizes: list[float] = []
    for blk in page_dict["blocks"]:
        if blk.get("type") != 0:
            continue
        for line in blk["lines"]:
            for span in line["spans"]:
                if span["text"].strip():
                    sizes.append(span["size"])
    return sorted(sizes)[len(sizes) // 2] if sizes else 12.0


def _extract_tables(page, content: list[ContentBlock]) -> list[tuple[float, float, float, float]]:
    """Append detected tables as table blocks; return their bounding boxes."""
    table_bboxes: list[tuple[float, float, float, float]] = []
    try:
        for tab in page.find_tables().tables:
            raw_rows = tab.extract() or []
            rows = [[cell if cell is not None else "" for cell in row] for row in raw_rows]
            if rows and any(map(any, rows)):
                content.append({
                    "type": "table", "level": None, "text": "",
                    "items": None, "rows": rows, "code_block_index": None,
                })
                bb = tab.bbox
                table_bboxes.append((float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3])))
    except Exception:
        pass
    return table_bboxes


def _block_text_info(blk) -> tuple[str, float, bool]:
    """Return a block's joined text, its largest span size, and whether it's monospace."""
    parts: list[str] = []
    max_size = 0.0
    is_mono = False
    for line in blk["lines"]:
        line_parts: list[str] = []
        for span in line["spans"]:
            t = span["text"].strip()
            if not t:
                continue
            line_parts.append(t)
            max_size = max(max_size, span["size"])
            if any(h in span.get("font", "").lower() for h in MONO_FONT_HINTS):
                is_mono = True
        if line_parts:
            parts.append(" ".join(line_parts))
    return " ".join(parts).strip(), max_size, is_mono


def _overlaps(bbox: tuple, table_bboxes: list[tuple[float, float, float, float]]) -> bool:
    """Whether ``bbox`` intersects any already-extracted table box."""
    ax0, ay0, ax1, ay1 = (float(v) for v in bbox)
    for bx0, by0, bx1, by1 in table_bboxes:
        if not (ax1 < bx0 or bx1 < ax0 or ay1 < by0 or by1 < ay0):
            return True
    return False


__all__ = ["page_to_blocks"]
