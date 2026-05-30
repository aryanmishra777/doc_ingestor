"""Collectors that turn list/table token ranges into block data.

Each collector takes a *slice* of tokens (the interior of a ``bullet_list``/``table`` etc.)
and produces the plain Python structures our records use: a list of item strings, or a
list of row/cell strings. Inline content is flattened via
:func:`markdown_extraction.inline.flatten_inline`.
"""
from __future__ import annotations

from markdown_extraction.inline import flatten_inline
from markdown_extraction.util import find_matching_close


def collect_list_items(tokens: list, links: list[str], base_url: str) -> list[str]:
    """Extract one string per ``list_item`` in ``tokens``."""
    items: list[str] = []
    i = 0
    while i < len(tokens):
        if tokens[i].type == "list_item_open":
            end = find_matching_close(tokens, i, "list_item_close")
            text = _flatten_item_content(tokens[i + 1:end], links, base_url)
            if text:
                items.append(text)
            i = end + 1
        else:
            i += 1
    return items


def _flatten_item_content(tokens: list, links: list[str], base_url: str) -> str:
    """Join all inline content within a single list item."""
    parts: list[str] = []
    for tok in tokens:
        if tok.type == "inline":
            text = flatten_inline(tok, links, base_url)
            if text:
                parts.append(text)
    return " ".join(parts).strip()


def collect_table_rows(tokens: list, links: list[str], base_url: str) -> list[list[str]]:
    """Extract non-empty rows (each a list of cell strings) from a table token range."""
    rows: list[list[str]] = []
    i = 0
    while i < len(tokens):
        if tokens[i].type == "tr_open":
            end = find_matching_close(tokens, i, "tr_close")
            row = _collect_table_cells(tokens[i + 1:end], links, base_url)
            if any(row):
                rows.append(row)
            i = end + 1
        else:
            i += 1
    return rows


def _collect_table_cells(tokens: list, links: list[str], base_url: str) -> list[str]:
    """Extract the cell strings from a single table row's token range."""
    cells: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type in {"th_open", "td_open"}:
            close_type = tok.type.replace("_open", "_close")
            end = find_matching_close(tokens, i, close_type)
            inline_tokens = [t for t in tokens[i + 1:end] if t.type == "inline"]
            text = " ".join(flatten_inline(t, links, base_url) for t in inline_tokens).strip()
            cells.append(text)
            i = end + 1
        else:
            i += 1
    return cells


__all__ = ["collect_list_items", "collect_table_rows"]
