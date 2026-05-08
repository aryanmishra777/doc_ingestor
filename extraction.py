from __future__ import annotations

import sys
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

try:
    from .models import CodeBlock, ContentBlock, DocPageRecord, make_error_record
except ImportError:
    from models import CodeBlock, ContentBlock, DocPageRecord, make_error_record

BOILERPLATE_TAGS = {"nav", "footer", "aside", "header", "script", "style", "noscript"}
CONTENT_ROOT_TAGS = {"main", "article"}
BOILERPLATE_HINTS = ("cookie", "consent", "sidebar", "menu", "navbar", "footer")
SPARSE_CONTENT_CHAR_THRESHOLD = 120
# Class/id tokens that suggest a div or section is the primary content container.
_CONTENT_DIV_CLASS_HINTS = frozenset({
    "content", "main", "docs", "documentation", "markdown",
    "prose", "readme", "body", "entry", "post",
})
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


def extract_page(url: str, depth: int = 0, order_index: int = 0) -> DocPageRecord:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return _error_record(
            url,
            depth,
            order_index,
            "playwright is not installed; run `pip install -r requirements.txt`",
            exc,
        )

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            try:
                page.wait_for_load_state("networkidle", timeout=5_000)
            except Exception:
                pass
            final_url = page.url or url
            html = page.content()
            browser.close()
        return extract_from_html(html, url=final_url, depth=depth, order_index=order_index)
    except Exception as exc:
        print(f"Failed: {url}: {exc}", file=sys.stderr)
        return _error_record(url, depth, order_index, "extractor: page extraction failed", exc)


def extract_page_in_browser(browser, url: str, depth: int = 0, order_index: int = 0) -> DocPageRecord:
    """Extract a page using an existing Playwright browser (new context per call, thread-safe)."""
    try:
        context = browser.new_context()
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            try:
                page.wait_for_load_state("networkidle", timeout=5_000)
            except Exception:
                pass
            final_url = page.url or url
            html = page.content()
        finally:
            context.close()
        return extract_from_html(html, url=final_url, depth=depth, order_index=order_index)
    except Exception as exc:
        print(f"Failed: {url}: {exc}", file=sys.stderr)
        return _error_record(url, depth, order_index, "extractor: page extraction failed", exc)


def extract_from_html(
    html: str,
    url: str,
    depth: int = 0,
    order_index: int = 0,
) -> DocPageRecord:
    parser = _DocumentationHTMLParser(url=url, capture_all=False)
    parser.feed(html)
    parser.close()

    if not parser.content_blocks and not parser.code_blocks:
        parser = _DocumentationHTMLParser(url=url, capture_all=True)
        parser.feed(html)
        parser.close()
    elif _is_sparse_content(parser):
        # First pass found some blocks (e.g. a heading inside <main>) but the
        # bulk of the content lives in a non-standard container outside that
        # root.  Try a full-page parse; switch to it only if richer.
        full_parser = _DocumentationHTMLParser(url=url, capture_all=True)
        full_parser.feed(html)
        full_parser.close()
        if not _is_sparse_content(full_parser):
            parser = full_parser

    if _is_sparse_content(parser) and parser.sparse_link_items:
        parser.content_blocks.append(
            {
                "type": "heading",
                "level": 2,
                "text": "Discovered links",
                "items": None,
                "rows": None,
                "code_block_index": None,
            }
        )
        parser.content_blocks.append(
            {
                "type": "list",
                "level": None,
                "text": "",
                "items": parser.sparse_link_items,
                "rows": None,
                "code_block_index": None,
            }
        )

    title = parser.primary_h1 or parser.document_title or url
    return {
        "url": url,
        "canonical_url": parser.canonical_url,
        "depth": depth,
        "order_index": order_index,
        "title": title,
        "content_blocks": parser.content_blocks,
        "code_blocks": parser.code_blocks,
        "links": sorted(set(parser.links)),
        "metadata": {
            "breadcrumbs": parser.breadcrumbs,
            "source_domain": urlparse(url).netloc or None,
        },
        "errors": [],
    }


class _DocumentationHTMLParser(HTMLParser):
    def __init__(self, url: str, capture_all: bool):
        super().__init__(convert_charrefs=True)
        self.url = url
        self._link_base_url = url
        self.capture_all = capture_all
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

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {name.lower(): value or "" for name, value in attrs}
        self.tag_stack.append(tag)
        self._capture_links_and_canonical(tag, attrs_dict)

        if self._handle_skip_or_boilerplate(tag, attrs_dict):
            return

        self._handle_content_root_and_breadcrumb(tag, attrs_dict)
        self._handle_anchor_buffer(tag, attrs_dict)

        # content capturing
        if not self._capturing_content:
            if tag == "title":
                self._text_capture = {"kind": "title", "parts": []}
            return

        self._handle_content_tag_start(tag, attrs_dict)

        if tag in VOID_TAGS and self.tag_stack:
            self.tag_stack.pop()

    def _handle_skip_or_boilerplate(self, tag: str, attrs_dict: dict[str, str]) -> bool:
        """Return True if parsing should return early due to skip or boilerplate."""
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
        is_content_root = self._is_content_root(tag, attrs_dict)
        self._content_root_stack.append(is_content_root)
        if is_content_root:
            self.content_depth += 1
        if self._looks_like_breadcrumb(tag, attrs_dict):
            self._breadcrumb_depth += 1
            self._breadcrumb_buffer = []

    def _handle_anchor_buffer(self, tag: str, attrs_dict: dict[str, str]) -> None:
        if tag == "a" and attrs_dict.get("href"):
            self._anchor_buffer = []
            self._anchor_href = urljoin(self._link_base_url, attrs_dict["href"])

    def _handle_content_tag_start(self, tag: str, attrs_dict: dict[str, str]) -> None:
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
        # base, links and canonical
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
        return (
            tag in CONTENT_ROOT_TAGS
            or attrs_dict.get("role", "").lower() == "main"
            or self._is_supplemental_content_root(tag, attrs_dict)
        )

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if self._handle_skip_depth():
            return

        self._handle_breadcrumb_end(tag)
        self._handle_content_root_end()
        self._handle_structural_end(tag)

        if self.tag_stack:
            self.tag_stack.pop()

    def _handle_skip_depth(self) -> bool:
        if not self.skip_depth:
            return False
        self.skip_depth -= 1
        if self.tag_stack:
            self.tag_stack.pop()
        return True

    def _handle_breadcrumb_end(self, tag: str) -> None:
        if not (self._breadcrumb_depth and self._looks_like_open_breadcrumb_end(tag)):
            return
        breadcrumb_text = " ".join("".join(self._breadcrumb_buffer).split())
        self.breadcrumbs = [part.strip() for part in breadcrumb_text.split("/") if part.strip()]
        self._breadcrumb_depth -= 1

    def _handle_content_root_end(self) -> None:
        is_content_root = self._content_root_stack.pop() if self._content_root_stack else False
        if is_content_root:
            self.content_depth = max(0, self.content_depth - 1)

    def _handle_structural_end(self, tag: str) -> None:
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
        if tag == "li" and self._li_buffer is not None and self._list_stack:
            item_text = _squash_text("".join(self._li_buffer))
            if item_text:
                self._list_stack[-1].append(item_text)
            self._li_buffer = None
            return True
        if tag in {"ul", "ol"} and self._list_stack:
            items = self._list_stack.pop()
            if self._capturing_content and items:
                self.content_blocks.append(
                    {"type": "list", "level": None, "text": "", "items": items, "rows": None, "code_block_index": None}
                )
            return True
        return False

    def _handle_table_end(self, tag: str) -> bool:
        if tag in {"td", "th"} and self._cell_buffer is not None and self._current_row is not None:
            self._current_row.append(_squash_text("".join(self._cell_buffer)))
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
                    {"type": "table", "level": None, "text": "", "items": None, "rows": self._table_rows, "code_block_index": None}
                )
            self._table_rows = None
            return True
        return False

    def _handle_code_end(self, tag: str) -> bool:
        if tag != "pre" or self._code_buffer is None:
            return False
        code_text = "".join(self._code_buffer)
        code_block_index = len(self.code_blocks)
        self.code_blocks.append({"language": self._code_language, "text": code_text})
        if self._capturing_content:
            self.content_blocks.append(
                {
                    "type": "code",
                    "level": None,
                    "text": "",
                    "items": None,
                    "rows": None,
                    "code_block_index": code_block_index,
                }
            )
        self._code_buffer = None
        self._code_language = None
        return True

    def handle_data(self, data: str) -> None:
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

    @property
    def _capturing_content(self) -> bool:
        return self.capture_all or self.content_depth > 0

    def _flush_text_capture(self) -> None:
        if self._text_capture is None:
            return
        parts = self._text_capture["parts"]
        if not isinstance(parts, list):
            self._text_capture = None
            return
        text = _squash_text("".join(parts))
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
                {"type": "heading", "level": level, "text": text, "items": None, "rows": None, "code_block_index": None}
            )
        elif kind == "paragraph" and text and self._capturing_content:
            self.content_blocks.append(
                {"type": "paragraph", "level": None, "text": text, "items": None, "rows": None, "code_block_index": None}
            )
        self._text_capture = None

    def _flush_sparse_anchor(self) -> None:
        text = _squash_text("".join(self._anchor_buffer or []))
        href = self._anchor_href
        self._anchor_buffer = None
        self._anchor_href = None
        if not text or not href:
            return
        if href.startswith("#"):
            return
        item = f"[{_escape_markdown_link_text(text)}]({href})"
        if item in self._seen_sparse_link_items:
            return
        self._seen_sparse_link_items.add(item)
        self.sparse_link_items.append(item)

    def _is_boilerplate(self, tag: str, attrs: dict[str, str]) -> bool:
        if self._looks_like_breadcrumb(tag, attrs):
            return False
        if self._is_supplemental_content_root(tag, attrs):
            return False
        if tag in BOILERPLATE_TAGS:
            return True
        marker = f"{attrs.get('id', '')} {attrs.get('class', '')}".lower()
        return any(hint in marker for hint in BOILERPLATE_HINTS)

    def _is_supplemental_content_root(self, tag: str, attrs: dict[str, str]) -> bool:
        marker = f"{attrs.get('id', '')} {attrs.get('class', '')}".lower()
        if tag == "nav" and "internal_nav" in marker:
            return True
        if tag in {"div", "section"}:
            # Tokenise on word boundaries so "main-content" → {"main", "content"}.
            tokens = set(marker.replace("-", " ").replace("_", " ").split())
            if tokens & _CONTENT_DIV_CLASS_HINTS and not any(
                h in marker for h in BOILERPLATE_HINTS
            ):
                return True
        return False

    def _looks_like_breadcrumb(self, tag: str, attrs: dict[str, str]) -> bool:
        marker = f"{attrs.get('aria-label', '')} {attrs.get('class', '')} {attrs.get('id', '')}".lower()
        return tag in {"nav", "ol", "ul", "div"} and "breadcrumb" in marker

    def _looks_like_open_breadcrumb_end(self, tag: str) -> bool:
        return tag in {"nav", "ol", "ul", "div"}

    def _language_from_attrs(self, attrs: dict[str, str]) -> str | None:
        marker = f"{attrs.get('class', '')} {attrs.get('data-language', '')}".strip()
        for token in marker.replace(",", " ").split():
            if token.startswith("language-"):
                return token.removeprefix("language-")
            if token.startswith("lang-"):
                return token.removeprefix("lang-")
        return attrs.get("data-language") or None


def _squash_text(text: str) -> str:
    return " ".join(text.split())


def _is_sparse_content(parser: _DocumentationHTMLParser) -> bool:
    prose_parts: list[str] = []
    for block in parser.content_blocks:
        if block.get("type") == "heading":
            continue
        prose_parts.append(block.get("text", ""))
        prose_parts.extend(block.get("items") or [])
        for row in block.get("rows") or []:
            prose_parts.extend(row)
    for code_block in parser.code_blocks:
        prose_parts.append(code_block.get("text", ""))
    prose_text = _squash_text(" ".join(prose_parts))
    return len(prose_text) < SPARSE_CONTENT_CHAR_THRESHOLD


def _escape_markdown_link_text(text: str) -> str:
    return text.replace("[", "\\[").replace("]", "\\]")


_error_record = make_error_record
