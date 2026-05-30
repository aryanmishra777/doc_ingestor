"""Closing-tag handling for :class:`DocumentationHTMLParser`.

Mixin counterpart to :mod:`extraction.html.starttag`. Closing tags finalize whatever
buffer the matching open tag started: text captures become heading/paragraph blocks,
lists/tables/code are appended as structured blocks, and anchors are flushed to the
sparse-link list. Each ``_handle_*_end`` returns ``True`` once it has consumed the tag so
the dispatcher can stop.
"""
from __future__ import annotations

from extraction.text_utils import squash_text


class EndTagMixin:
    """Closing-tag dispatch and block finalization."""

    def handle_endtag(self, tag: str) -> None:
        """Process a closing tag: unwind skip/root state and finalize any open block."""
        if self._handle_skip_depth():
            return

        self._handle_breadcrumb_end(tag)
        self._handle_content_root_end()
        self._handle_structural_end(tag)

        if self.tag_stack:
            self.tag_stack.pop()

    def _handle_skip_depth(self) -> bool:
        """Decrement ``skip_depth`` while inside chrome; return True if still skipping."""
        if not self.skip_depth:
            return False
        self.skip_depth -= 1
        if self.tag_stack:
            self.tag_stack.pop()
        return True

    def _handle_breadcrumb_end(self, tag: str) -> None:
        """Close a breadcrumb container and split its text into trail segments."""
        if not (self._breadcrumb_depth and self._looks_like_open_breadcrumb_end(tag)):
            return
        breadcrumb_text = " ".join("".join(self._breadcrumb_buffer).split())
        self.breadcrumbs = [part.strip() for part in breadcrumb_text.split("/") if part.strip()]
        self._breadcrumb_depth -= 1

    def _handle_content_root_end(self) -> None:
        """Pop the content-root stack and decrement ``content_depth`` accordingly."""
        is_content_root = self._content_root_stack.pop() if self._content_root_stack else False
        if is_content_root:
            self.content_depth = max(0, self.content_depth - 1)

    def _handle_structural_end(self, tag: str) -> None:
        """Dispatch to the finalizer for whichever structural block this tag closes."""
        if self._handle_text_capture_end(tag):
            return
        if self._handle_list_end(tag):
            return
        if self._handle_table_end(tag):
            return
        if self._handle_code_end(tag):
            return
        if tag == "a" and self._anchor_buffer is not None and self._anchor_href:
            self._flush_sparse_anchor()

    def _handle_text_capture_end(self, tag: str) -> bool:
        """Flush a heading/paragraph/title capture when its tag closes."""
        if not self._text_capture:
            return False
        if tag in {
            "title", "h1", "h2", "h3", "h4", "h5", "h6",
            "p", "blockquote", "dt", "dd", "figcaption",
        }:
            self._flush_text_capture()
            return True
        return False

    def _handle_list_end(self, tag: str) -> bool:
        """Finalize a list item or an entire ``<ul>``/``<ol>`` into a list block."""
        if tag == "li" and self._li_buffer is not None and self._list_stack:
            item_text = squash_text("".join(self._li_buffer))
            if item_text:
                self._list_stack[-1].append(item_text)
            self._li_buffer = None
            return True
        if tag in {"ul", "ol"} and self._list_stack:
            items = self._list_stack.pop()
            if self._capturing_content and items:
                self.content_blocks.append(
                    {"type": "list", "level": None, "text": "", "items": items,
                     "rows": None, "code_block_index": None}
                )
            return True
        return False

    def _handle_table_end(self, tag: str) -> bool:
        """Finalize a table cell, row, or whole ``<table>`` into a table block."""
        if tag in {"td", "th"} and self._cell_buffer is not None and self._current_row is not None:
            self._current_row.append(squash_text("".join(self._cell_buffer)))
            self._cell_buffer = None
            return True
        if tag == "tr" and self._table_rows is not None and self._current_row is not None:
            if any(self._current_row):
                self._table_rows.append(self._current_row)
            self._current_row = None
            return True
        if tag == "table" and self._table_rows is not None:
            if self._capturing_content and self._table_rows:
                self.content_blocks.append(
                    {"type": "table", "level": None, "text": "", "items": None,
                     "rows": self._table_rows, "code_block_index": None}
                )
            self._table_rows = None
            return True
        return False

    def _handle_code_end(self, tag: str) -> bool:
        """Finalize a ``<pre>`` into an out-of-line code block plus a code marker block."""
        if tag != "pre" or self._code_buffer is None:
            return False
        code_text = "".join(self._code_buffer)
        code_block_index = len(self.code_blocks)
        self.code_blocks.append({"language": self._code_language, "text": code_text})
        if self._capturing_content:
            self.content_blocks.append(
                {"type": "code", "level": None, "text": "", "items": None,
                 "rows": None, "code_block_index": code_block_index}
            )
        self._code_buffer = None
        self._code_language = None
        return True


__all__ = ["EndTagMixin"]
