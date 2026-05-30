"""The structure-aware HTML parser, composed from focused mixins.

:class:`DocumentationHTMLParser` is a single cohesive ``HTMLParser`` whose behavior is
split across mixins purely for readability and the ≤150-line rule — there is no change in
semantics versus the original monolithic class:

* :class:`StartTagMixin` — opening-tag dispatch (skip/boilerplate, content roots,
  breadcrumbs, anchors, links/canonical, structural captures).
* :class:`EndTagMixin` — closing-tag dispatch and block finalization.
* :class:`FlushMixin` — turning buffered text/anchors into content blocks.
* :class:`ClassificationMixin` — the boilerplate / content-root / breadcrumb heuristics.

This module owns only the shared mutable state (``__init__``), the character-data sink
(``handle_data``), and the ``_capturing_content`` predicate the mixins read.

The parser runs in two modes. In normal mode it captures only inside detected content
roots; in ``capture_all`` mode (the fallback re-parse) it captures the whole document.
"""
from __future__ import annotations

from html.parser import HTMLParser

from domain.records import CodeBlock, ContentBlock
from extraction.html.classification import ClassificationMixin
from extraction.html.endtag import EndTagMixin
from extraction.html.flush import FlushMixin
from extraction.html.starttag import StartTagMixin


class DocumentationHTMLParser(StartTagMixin, EndTagMixin, FlushMixin, ClassificationMixin, HTMLParser):
    """Parse documentation HTML into ordered content/code blocks plus link metadata."""

    def __init__(self, url: str, capture_all: bool):
        super().__init__(convert_charrefs=True)
        self.url = url
        self._link_base_url = url
        self.capture_all = capture_all
        # In capture_all mode we behave as if already inside a content root.
        self.content_depth = 1 if capture_all else 0
        self.skip_depth = 0
        self.tag_stack: list[str] = []
        self._content_root_stack: list[bool] = []

        self.document_title = ""
        self.primary_h1 = ""
        self.canonical_url: str | None = None
        self.links: list[str] = []
        self.breadcrumbs: list[str] = []
        self.content_blocks: list[ContentBlock] = []
        self.code_blocks: list[CodeBlock] = []

        self._text_capture: dict[str, object] | None = None
        self._list_stack: list[list[str]] = []
        self._li_buffer: list[str] | None = None
        self._table_rows: list[list[str]] | None = None
        self._current_row: list[str] | None = None
        self._cell_buffer: list[str] | None = None
        self._code_buffer: list[str] | None = None
        self._code_language: str | None = None
        self._breadcrumb_depth = 0
        self._breadcrumb_buffer: list[str] = []
        self._anchor_buffer: list[str] | None = None
        self._anchor_href: str | None = None
        self.sparse_link_items: list[str] = []
        self._seen_sparse_link_items: set[str] = set()

    @property
    def _capturing_content(self) -> bool:
        """Whether character data should currently be captured as content."""
        return self.capture_all or self.content_depth > 0

    def handle_data(self, data: str) -> None:
        """Route raw text into whichever buffer is currently open (innermost wins)."""
        if self.skip_depth:
            return
        if self._breadcrumb_depth:
            self._breadcrumb_buffer.append(data)
        if self._anchor_buffer is not None:
            self._anchor_buffer.append(data)
        if self._code_buffer is not None:
            self._code_buffer.append(data)
            return
        if self._cell_buffer is not None:
            self._cell_buffer.append(data)
            return
        if self._li_buffer is not None:
            self._li_buffer.append(data)
            return
        if self._text_capture is not None:
            parts = self._text_capture["parts"]
            if isinstance(parts, list):
                parts.append(data)


__all__ = ["DocumentationHTMLParser"]
