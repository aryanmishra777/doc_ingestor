"""Buffer-flushing logic for :class:`DocumentationHTMLParser`.

Turns the parser's transient text buffers into finished output: a captured title updates
``document_title``; captured headings/paragraphs become content blocks (and the first
``<h1>`` becomes ``primary_h1``); and a captured anchor becomes a de-duplicated Markdown
link in ``sparse_link_items`` for navigation-only pages.
"""
from __future__ import annotations

from extraction.text_utils import escape_markdown_link_text, squash_text


class FlushMixin:
    """Convert captured buffers into content blocks / link items."""

    def _flush_text_capture(self) -> None:
        """Emit the currently-captured title, heading, or paragraph, then reset."""
        if self._text_capture is None:
            return
        parts = self._text_capture["parts"]
        if not isinstance(parts, list):
            self._text_capture = None
            return
        text = squash_text("".join(parts))
        kind = self._text_capture["kind"]

        if kind == "title":
            self.document_title = text
        elif kind == "heading" and text and self._capturing_content:
            level = self._text_capture["level"]
            if not isinstance(level, int):
                self._text_capture = None
                return
            if level == 1 and not self.primary_h1:
                self.primary_h1 = text
            self.content_blocks.append(
                {"type": "heading", "level": level, "text": text, "items": None,
                 "rows": None, "code_block_index": None}
            )
        elif kind == "paragraph" and text and self._capturing_content:
            self.content_blocks.append(
                {"type": "paragraph", "level": None, "text": text, "items": None,
                 "rows": None, "code_block_index": None}
            )
        self._text_capture = None

    def _flush_sparse_anchor(self) -> None:
        """Append the buffered anchor as a Markdown link to ``sparse_link_items``.

        Fragment-only (``#...``) and duplicate links are skipped. These items are only
        materialized into output when a page turns out to be navigation-only.
        """
        text = squash_text("".join(self._anchor_buffer or []))
        href = self._anchor_href
        self._anchor_buffer = None
        self._anchor_href = None
        if not text or not href:
            return
        if href.startswith("#"):
            return
        item = f"[{escape_markdown_link_text(text)}]({href})"
        if item in self._seen_sparse_link_items:
            return
        self._seen_sparse_link_items.add(item)
        self.sparse_link_items.append(item)


__all__ = ["FlushMixin"]
