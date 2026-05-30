"""Translate trafilatura's TEI-XML output into our content/code blocks.

trafilatura returns extracted content as TEI XML (``<head>``/``<p>``/``<list>``/
``<table>``/``<code>``/``<quote>`` with inline ``<hi>``/``<code>``/``<lb>``). These
helpers walk that tree and emit the same :class:`ContentBlock`/:class:`CodeBlock` dicts
the native parser produces, so the rest of the pipeline is oblivious to which extractor
ran. Ambiguous ``<quote>`` elements are classified as code or prose via
:func:`extraction.text_utils.looks_like_code`.
"""
from __future__ import annotations

from domain.records import CodeBlock, ContentBlock
from extraction.text_utils import looks_like_code


def walk_xml(elem, content_blocks: list[ContentBlock], code_blocks: list[CodeBlock]) -> None:
    """Recursively convert a trafilatura XML element into appended blocks."""
    for child in elem:
        tag = child.tag.lower()
        if tag in {"doc", "main", "body"}:
            walk_xml(child, content_blocks, code_blocks)
        elif tag == "head":
            level = heading_level_from_rend(child.get("rend", ""))
            text = flatten_inline(child).strip()
            if text:
                content_blocks.append({
                    "type": "heading", "level": level, "text": text,
                    "items": None, "rows": None, "code_block_index": None,
                })
        elif tag == "p":
            text = flatten_inline(child).strip()
            if text:
                content_blocks.append({
                    "type": "paragraph", "level": None, "text": text,
                    "items": None, "rows": None, "code_block_index": None,
                })
        elif tag == "list":
            items = [flatten_inline(item).strip() for item in child.findall("item")]
            items = [it for it in items if it]
            if items:
                content_blocks.append({
                    "type": "list", "level": None, "text": "",
                    "items": items, "rows": None, "code_block_index": None,
                })
        elif tag == "table":
            rows: list[list[str]] = []
            for row_elem in child.findall("row"):
                row = [flatten_inline(cell).strip() for cell in row_elem.findall("cell")]
                if any(row):
                    rows.append(row)
            if rows:
                content_blocks.append({
                    "type": "table", "level": None, "text": "",
                    "items": None, "rows": rows, "code_block_index": None,
                })
        elif tag == "code":
            text = flatten_inline(child)
            if text.strip():
                append_code_block(text, code_blocks, content_blocks)
        elif tag == "quote":
            text = flatten_inline(child)
            if not text.strip():
                continue
            if looks_like_code(text):
                append_code_block(text, code_blocks, content_blocks)
            else:
                content_blocks.append({
                    "type": "paragraph", "level": None, "text": text.strip(),
                    "items": None, "rows": None, "code_block_index": None,
                })


def flatten_inline(elem) -> str:
    """Flatten an element's inline children to Markdown-ish text.

    ``<code>`` → backticks, ``<hi rend="#b/#i">`` → bold/italic, ``<lb>`` → newline.
    Element ``text`` and child ``tail`` are preserved so nothing is dropped.
    """
    parts: list[str] = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        tag = child.tag.lower()
        inner = flatten_inline(child)
        if tag == "code":
            parts.append(f"`{inner}`" if inner else "")
        elif tag == "hi":
            rend = (child.get("rend") or "").lower()
            if "#b" in rend:
                parts.append(f"**{inner}**")
            elif "#i" in rend:
                parts.append(f"*{inner}*")
            else:
                parts.append(inner)
        elif tag == "lb":
            parts.append("\n")
        else:
            parts.append(inner)
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def heading_level_from_rend(rend: str) -> int:
    """Map a TEI ``rend="hN"`` attribute to a 1–6 heading level (default 2)."""
    rend = (rend or "").strip().lower()
    if rend.startswith("h") and rend[1:].isdigit():
        return max(1, min(6, int(rend[1:])))
    return 2


def append_code_block(text: str, code_blocks: list[CodeBlock], content_blocks: list[ContentBlock]) -> None:
    """Append a code block and a matching out-of-line code-marker content block."""
    code_block_index = len(code_blocks)
    code_blocks.append({"language": None, "text": text})
    content_blocks.append({
        "type": "code", "level": None, "text": "",
        "items": None, "rows": None, "code_block_index": code_block_index,
    })


__all__ = ["walk_xml", "flatten_inline", "heading_level_from_rend", "append_code_block"]
