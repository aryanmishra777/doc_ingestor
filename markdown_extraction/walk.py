"""The Markdown token-stream walker.

Consumes the flat markdown-it token list and appends structured blocks. Headings and
paragraphs are emitted from their following ``inline`` token (which is why the index jumps
by 3 — open/inline/close); lists, tables, and blockquotes are sliced out with
:func:`find_matching_close` and delegated to the collectors; fenced/indented code becomes
an out-of-line code block; and raw ``html_block`` content degrades to a paragraph.
"""
from __future__ import annotations

from domain.records import CodeBlock, ContentBlock
from markdown_extraction.blocks import collect_list_items, collect_table_rows
from markdown_extraction.inline import flatten_inline, strip_html
from markdown_extraction.util import find_matching_close


def walk_tokens(
    tokens: list,
    content_blocks: list[ContentBlock],
    code_blocks: list[CodeBlock],
    links: list[str],
    base_url: str,
) -> None:
    """Walk ``tokens`` (recursively for blockquotes), appending blocks in document order."""
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        t = tok.type

        if t == "heading_open":
            text = flatten_inline(tokens[i + 1], links, base_url)
            if text:
                content_blocks.append({
                    "type": "heading", "level": int(tok.tag[1]), "text": text,
                    "items": None, "rows": None, "code_block_index": None,
                })
            i += 3
        elif t == "paragraph_open":
            text = flatten_inline(tokens[i + 1], links, base_url)
            if text:
                content_blocks.append({
                    "type": "paragraph", "level": None, "text": text,
                    "items": None, "rows": None, "code_block_index": None,
                })
            i += 3
        elif t in {"bullet_list_open", "ordered_list_open"}:
            end = find_matching_close(tokens, i, t.replace("_open", "_close"))
            items = collect_list_items(tokens[i + 1:end], links, base_url)
            if items:
                content_blocks.append({
                    "type": "list", "level": None, "text": "",
                    "items": items, "rows": None, "code_block_index": None,
                })
            i = end + 1
        elif t == "table_open":
            end = find_matching_close(tokens, i, "table_close")
            rows = collect_table_rows(tokens[i + 1:end], links, base_url)
            if rows:
                content_blocks.append({
                    "type": "table", "level": None, "text": "",
                    "items": None, "rows": rows, "code_block_index": None,
                })
            i = end + 1
        elif t in {"fence", "code_block"}:
            language = (tok.info or "").strip().split()[0] if tok.info else None
            code_block_index = len(code_blocks)
            code_blocks.append({"language": language or None, "text": tok.content})
            content_blocks.append({
                "type": "code", "level": None, "text": "",
                "items": None, "rows": None, "code_block_index": code_block_index,
            })
            i += 1
        elif t == "blockquote_open":
            end = find_matching_close(tokens, i, "blockquote_close")
            walk_tokens(tokens[i + 1:end], content_blocks, code_blocks, links, base_url)
            i = end + 1
        elif t == "html_block":
            text = strip_html(tok.content).strip()
            if text:
                content_blocks.append({
                    "type": "paragraph", "level": None, "text": text,
                    "items": None, "rows": None, "code_block_index": None,
                })
            i += 1
        else:
            i += 1


__all__ = ["walk_tokens"]
