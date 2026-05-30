"""The three density-driven segmentation strategies (a Strategy family).

* ``light`` — flatten the whole document into a single record.
* ``medium`` — start a new record at each top-level (``<= h2``) heading, so a structured
  report becomes one record per section, with the document title as a breadcrumb.
* ``dense`` — emit one record per page (figure-heavy/sparse PDFs rarely have reliable
  headings), titling each by its first heading or "… — Page N".

Each falls back to ``light`` if its finer segmentation yields nothing.
"""
from __future__ import annotations

from domain.records import CodeBlock, ContentBlock, DocPageRecord
from pdf_extraction.page_blocks import page_to_blocks
from pdf_extraction.records import make_record


def extract_light(doc, url, depth, order_index, title, links) -> list[DocPageRecord]:
    """Flatten every page into one record."""
    all_content: list[ContentBlock] = []
    all_code: list[CodeBlock] = []
    for page in doc:
        blocks, codes = page_to_blocks(page, code_offset=len(all_code))
        all_content.extend(blocks)
        all_code.extend(codes)
    return [make_record(url, None, depth, order_index, title, all_content, all_code, links)]


def extract_medium(doc, url, depth, order_index, base_title, links) -> list[DocPageRecord]:
    """Split into records at each top-level heading."""
    sections: list[tuple[str, list[ContentBlock], list[CodeBlock]]] = []
    cur_title = base_title
    cur_content: list[ContentBlock] = []
    cur_code: list[CodeBlock] = []

    for page in doc:
        blocks, codes = page_to_blocks(page, code_offset=len(cur_code))
        for block in blocks:
            if block["type"] == "heading" and block["level"] <= 2 and cur_content:
                sections.append((cur_title, cur_content, cur_code))
                cur_title, cur_content, cur_code = block["text"], [], []
            else:
                cur_content.append(block)
        cur_code.extend(codes)

    if cur_content:
        sections.append((cur_title, cur_content, cur_code))
    if not sections:
        return extract_light(doc, url, depth, order_index, base_title, links)

    records = []
    for i, (sec_title, content, code) in enumerate(sections):
        breadcrumbs = [base_title] if sec_title != base_title else []
        records.append(make_record(
            f"{url}#section-{i + 1}", None, depth, order_index + i,
            sec_title, content, code, links if i == 0 else [], breadcrumbs,
        ))
    return records


def extract_dense(doc, url, depth, order_index, base_title, links) -> list[DocPageRecord]:
    """Emit one record per page."""
    records = []
    for page_num, page in enumerate(doc):
        blocks, codes = page_to_blocks(page)
        if not blocks and not codes:
            continue
        page_title = next(
            (b["text"] for b in blocks if b["type"] == "heading"),
            f"{base_title} — Page {page_num + 1}",
        )
        records.append(make_record(
            f"{url}#page={page_num + 1}", None, depth, order_index + page_num,
            page_title, blocks, codes, links if page_num == 0 else [], [base_title],
        ))
    return records or extract_light(doc, url, depth, order_index, base_title, links)


__all__ = ["extract_light", "extract_medium", "extract_dense"]
