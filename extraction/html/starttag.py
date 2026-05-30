"""Opening-tag handling for :class:`DocumentationHTMLParser`.

Defined as a mixin so the parser's start-tag logic lives in one readable file. Every
method here reads/writes ``self`` state declared in ``parser.py``'s ``__init__``.
"""
from __future__ import annotations

from urllib.parse import urljoin

from extraction.heuristics import CONTENT_ROOT_TAGS, VOID_TAGS


class StartTagMixin:
    """Opening-tag dispatch: skip detection, content roots, captures, links."""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Process an opening tag, updating skip/content state and starting captures."""
        attrs_dict = {name.lower(): value or "" for name, value in attrs}
        self.tag_stack.append(tag)
        self._capture_links_and_canonical(tag, attrs_dict)

        if self._handle_skip_or_boilerplate(tag, attrs_dict):
            return

        self._handle_content_root_and_breadcrumb(tag, attrs_dict)
        self._handle_anchor_buffer(tag, attrs_dict)

        if tag == "title":
            self._text_capture = {"kind": "title", "parts": []}
            return

        if not self._capturing_content:
            return

        self._handle_content_tag_start(tag, attrs_dict)

        if tag in VOID_TAGS and self.tag_stack:
            self.tag_stack.pop()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Self-closing tag: treat as start, then end (unless it's a void element)."""
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def _handle_skip_or_boilerplate(self, tag: str, attrs_dict: dict[str, str]) -> bool:
        """Maintain ``skip_depth`` for chrome subtrees; return True to stop processing.

        Void tags inside a skipped region don't deepen the skip (they have no close), so
        their pushed stack entry is popped immediately to keep ``tag_stack`` balanced.
        """
        if self.skip_depth:
            if tag not in VOID_TAGS:
                self.skip_depth += 1
            elif self.tag_stack:
                self.tag_stack.pop()
            return True

        if self._is_boilerplate(tag, attrs_dict):
            if tag not in VOID_TAGS:
                self.skip_depth += 1
            elif self.tag_stack:
                self.tag_stack.pop()
            return True

        return False

    def _handle_content_root_and_breadcrumb(self, tag: str, attrs_dict: dict[str, str]) -> None:
        """Track entry into content roots and breadcrumb containers."""
        is_content_root = self._is_content_root(tag, attrs_dict)
        self._content_root_stack.append(is_content_root)
        if is_content_root:
            self.content_depth += 1
        if self._looks_like_breadcrumb(tag, attrs_dict):
            self._breadcrumb_depth += 1
            self._breadcrumb_buffer = []

    def _handle_anchor_buffer(self, tag: str, attrs_dict: dict[str, str]) -> None:
        """Begin buffering an anchor's text so sparse pages can list its link."""
        if tag == "a" and attrs_dict.get("href"):
            self._anchor_buffer = []
            self._anchor_href = urljoin(self._link_base_url, attrs_dict["href"])

    def _handle_content_tag_start(self, tag: str, attrs_dict: dict[str, str]) -> None:
        """Open the right capture buffer for a structural content element."""
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._text_capture = {"kind": "heading", "level": int(tag[1]), "parts": []}
        elif tag in {"p", "blockquote", "dt", "dd", "figcaption"}:
            self._text_capture = {"kind": "paragraph", "parts": []}
        elif tag in {"ul", "ol"}:
            self._list_stack.append([])
        elif tag == "li" and self._list_stack:
            self._li_buffer = []
        elif tag == "table":
            self._table_rows = []
        elif tag == "tr" and self._table_rows is not None:
            self._current_row = []
        elif tag in {"td", "th"} and self._current_row is not None:
            self._cell_buffer = []
        elif tag == "pre":
            self._code_buffer = []
            self._code_language = self._language_from_attrs(attrs_dict)
        elif tag == "code" and self._code_buffer is not None and not self._code_language:
            self._code_language = self._language_from_attrs(attrs_dict)

    def _capture_links_and_canonical(self, tag: str, attrs_dict: dict[str, str]) -> None:
        """Record ``<base>``, anchors/iframes (for crawling), and the canonical URL."""
        if tag == "base" and attrs_dict.get("href"):
            self._link_base_url = urljoin(self.url, attrs_dict["href"])
            return
        if tag == "a" and attrs_dict.get("href"):
            self.links.append(urljoin(self._link_base_url, attrs_dict["href"]))
            return
        if tag in {"iframe", "frame"} and attrs_dict.get("src"):
            self.links.append(urljoin(self._link_base_url, attrs_dict["src"]))
            return
        if tag == "link" and attrs_dict.get("rel", "").lower() == "canonical":
            href = attrs_dict.get("href")
            self.canonical_url = urljoin(self._link_base_url, href) if href else None

    def _is_content_root(self, tag: str, attrs_dict: dict[str, str]) -> bool:
        """Whether this element marks the start of primary page content."""
        return (
            tag in CONTENT_ROOT_TAGS
            or attrs_dict.get("role", "").lower() == "main"
            or self._is_supplemental_content_root(tag, attrs_dict)
        )


__all__ = ["StartTagMixin"]
