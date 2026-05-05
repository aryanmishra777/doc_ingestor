from __future__ import annotations

import sys
import urllib.request
from typing import Literal
from urllib.parse import urlparse

try:
    from .models import CodeBlock, ContentBlock, DocPageRecord, make_error_record
except ImportError:
    from models import CodeBlock, ContentBlock, DocPageRecord, make_error_record

DensityLevel = Literal["light", "medium", "dense"]

_SCANNED_CHARS_PER_PAGE = 50
_LIGHT_CHARS_PER_PAGE = 800
_MEDIUM_CHARS_PER_PAGE = 200
_HEADING_SIZE_RATIO = 1.2
_MONO_FONT_HINTS = ("courier", "consolas", "monaco", "mono", "code", "inconsolata", "jetbrains")


def extract_pdf(url: str, depth: int = 0, order_index: int = 0) -> list[DocPageRecord]:
    try:
        import fitz  # noqa: F401 — presence check only
    except ImportError as exc:
        print(f"PDF skip (pymupdf not installed): {url}", file=sys.stderr)
        return [_error_record(url, depth, order_index, "pymupdf not installed; run `pip install pymupdf`", exc)]

    try:
        pdf_bytes = _download(url)
    except Exception as exc:
        print(f"PDF skip (download failed): {url}", file=sys.stderr)
        return [_error_record(url, depth, order_index, "pdf: download failed", exc)]

    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        print(f"PDF skip (could not open): {url}", file=sys.stderr)
        return [_error_record(url, depth, order_index, "pdf: could not open", exc)]

    try:
        if _is_scanned(doc):
            print(f"PDF skip (scanned, no extractable text): {url}", file=sys.stderr)
            return []

        density = _analyze_density(doc)
        base_title = _pdf_title(doc, url)
        outbound_links = _extract_links(doc)

        if density == "light":
            return _extract_light(doc, url, depth, order_index, base_title, outbound_links)
        elif density == "medium":
            return _extract_medium(doc, url, depth, order_index, base_title, outbound_links)
        else:
            return _extract_dense(doc, url, depth, order_index, base_title, outbound_links)
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def _download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "doc-ingestor/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


# ---------------------------------------------------------------------------
# Density analysis
# ---------------------------------------------------------------------------

def _is_scanned(doc) -> bool:
    n = len(doc)
    if n == 0:
        return True
    total_chars = sum(len(page.get_text()) for page in doc)
    return (total_chars / n) < _SCANNED_CHARS_PER_PAGE


def _analyze_density(doc) -> DensityLevel:
    n = len(doc)
    if n == 0:
        return "light"

    total_chars = 0
    total_images = 0
    table_count = 0

    for page in doc:
        total_chars += len(page.get_text())
        total_images += len(page.get_images())
        try:
            table_count += len(page.find_tables().tables)
        except Exception:
            pass

    chars_per_page = total_chars / n
    images_per_page = total_images / n
    tables_per_page = table_count / n

    if chars_per_page >= _LIGHT_CHARS_PER_PAGE and images_per_page < 1.0:
        return "light"
    if chars_per_page >= _MEDIUM_CHARS_PER_PAGE or tables_per_page >= 0.3:
        return "medium"
    return "dense"


# ---------------------------------------------------------------------------
# Extraction strategies
# ---------------------------------------------------------------------------

def _extract_light(doc, url, depth, order_index, title, links) -> list[DocPageRecord]:
    all_content: list[ContentBlock] = []
    all_code: list[CodeBlock] = []

    for page in doc:
        blocks, codes = _page_to_blocks(page, code_offset=len(all_code))
        all_content.extend(blocks)
        all_code.extend(codes)

    return [_make_record(url, None, depth, order_index, title, all_content, all_code, links)]


def _extract_medium(doc, url, depth, order_index, base_title, links) -> list[DocPageRecord]:
    sections: list[tuple[str, list[ContentBlock], list[CodeBlock]]] = []
    cur_title = base_title
    cur_content: list[ContentBlock] = []
    cur_code: list[CodeBlock] = []

    for page in doc:
        blocks, codes = _page_to_blocks(page, code_offset=len(cur_code))
        for block in blocks:
            if block["type"] == "heading" and block["level"] <= 2 and cur_content:
                sections.append((cur_title, cur_content, cur_code))
                cur_title = block["text"]
                cur_content = []
                cur_code = []
            else:
                cur_content.append(block)
        cur_code.extend(codes)

    if cur_content:
        sections.append((cur_title, cur_content, cur_code))

    if not sections:
        return _extract_light(doc, url, depth, order_index, base_title, links)

    records = []
    for i, (sec_title, content, code) in enumerate(sections):
        breadcrumbs = [base_title] if sec_title != base_title else []
        records.append(_make_record(
            f"{url}#section-{i + 1}", None, depth, order_index + i,
            sec_title, content, code,
            links if i == 0 else [], breadcrumbs,
        ))
    return records


def _extract_dense(doc, url, depth, order_index, base_title, links) -> list[DocPageRecord]:
    records = []
    for page_num, page in enumerate(doc):
        blocks, codes = _page_to_blocks(page)
        if not blocks and not codes:
            continue
        page_title = next(
            (b["text"] for b in blocks if b["type"] == "heading"),
            f"{base_title} — Page {page_num + 1}",
        )
        records.append(_make_record(
            f"{url}#page={page_num + 1}", None, depth, order_index + page_num,
            page_title, blocks, codes,
            links if page_num == 0 else [], [base_title],
        ))

    return records or _extract_light(doc, url, depth, order_index, base_title, links)


# ---------------------------------------------------------------------------
# Per-page block extraction
# ---------------------------------------------------------------------------

def _page_to_blocks(
    page,
    code_offset: int = 0,
) -> tuple[list[ContentBlock], list[CodeBlock]]:
    import fitz

    content: list[ContentBlock] = []
    code: list[CodeBlock] = []

    page_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
    median_size = _median_body_size(page_dict)

    # Extract tables first; record their bounding boxes so we don't
    # double-count the same text when processing text blocks.
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
            _append_code_block(content, code, text, code_offset)
            continue

        if max_size > median_size * _HEADING_SIZE_RATIO:
            _append_heading_block(content, text, max_size / median_size)
            continue

        _append_paragraph_block(content, text)

    return content, code


def _median_body_size(page_dict) -> float:
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
    table_bboxes: list[tuple[float, float, float, float]] = []
    try:
        for tab in page.find_tables().tables:
            raw_rows = tab.extract() or []
            rows = [[cell if cell is not None else "" for cell in row] for row in raw_rows]
            if rows and any(map(any, rows)):
                content.append({
                    "type": "table",
                    "level": None,
                    "text": "",
                    "items": None,
                    "rows": rows,
                    "code_block_index": None,
                })
                bb = tab.bbox
                table_bboxes.append((float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3])))
    except Exception:
        pass
    return table_bboxes


def _block_text_info(blk) -> tuple[str, float, bool]:
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
            if any(h in span.get("font", "").lower() for h in _MONO_FONT_HINTS):
                is_mono = True
        if line_parts:
            parts.append(" ".join(line_parts))
    return " ".join(parts).strip(), max_size, is_mono


def _append_code_block(
    content: list[ContentBlock],
    code: list[CodeBlock],
    text: str,
    code_offset: int,
) -> None:
    idx = len(code) + code_offset
    code.append({"language": None, "text": text})
    content.append({
        "type": "code",
        "level": None,
        "text": "",
        "items": None,
        "rows": None,
        "code_block_index": idx,
    })


def _append_heading_block(content: list[ContentBlock], text: str, ratio: float) -> None:
    if ratio > 2.0:
        level = 1
    elif ratio > 1.6:
        level = 2
    elif ratio > 1.3:
        level = 3
    else:
        level = 4
    content.append({
        "type": "heading",
        "level": level,
        "text": text,
        "items": None,
        "rows": None,
        "code_block_index": None,
    })


def _append_paragraph_block(content: list[ContentBlock], text: str) -> None:
    content.append({
        "type": "paragraph",
        "level": None,
        "text": text,
        "items": None,
        "rows": None,
        "code_block_index": None,
    })


def _overlaps(
    bbox: tuple,
    table_bboxes: list[tuple[float, float, float, float]],
) -> bool:
    ax0, ay0, ax1, ay1 = (float(v) for v in bbox)
    for bx0, by0, bx1, by1 in table_bboxes:
        if not (ax1 < bx0 or bx1 < ax0 or ay1 < by0 or by1 < ay0):
            return True
    return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pdf_title(doc, url: str) -> str:
    meta = doc.metadata or {}
    title = (meta.get("title") or "").strip()
    if title:
        return title
    name = urlparse(url).path.rsplit("/", 1)[-1]
    return name.removesuffix(".pdf").replace("-", " ").replace("_", " ").title() or url


def _extract_links(doc) -> list[str]:
    links: list[str] = []
    for page in doc:
        for link in page.get_links():
            uri = link.get("uri", "")
            if uri and uri.startswith(("http://", "https://")):
                links.append(uri)
    return sorted(set(links))


def _make_record(
    url: str,
    canonical_url: str | None,
    depth: int,
    order_index: int,
    title: str,
    content_blocks: list[ContentBlock],
    code_blocks: list[CodeBlock],
    links: list[str],
    breadcrumbs: list[str] | None = None,
) -> DocPageRecord:
    return {
        "url": url,
        "canonical_url": canonical_url,
        "depth": depth,
        "order_index": order_index,
        "title": title,
        "content_blocks": content_blocks,
        "code_blocks": code_blocks,
        "links": links,
        "metadata": {
            "breadcrumbs": breadcrumbs or [],
            "source_domain": urlparse(url).netloc or None,
        },
        "errors": [],
    }


_error_record = make_error_record
