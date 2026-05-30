"""HTML → record orchestration: the public :func:`extract_from_html`.

Implements the escalating extraction strategy (a Chain-of-Responsibility over extractors):

1. Structure-aware parse capturing only inside detected content roots.
2. If that found nothing, or found only a sliver while the bulk lives in a non-standard
   container, re-parse the whole document (``capture_all``) and keep it if richer.
3. If still sparse, hand off to the trafilatura density-based fallback.
4. If still sparse but anchors were collected, emit a "Discovered links" section so a
   navigation page is at least usable for crawling.

Whatever strategy wins, the native parser's links/canonical/breadcrumbs are preserved so
downstream crawling and rendering behave identically.
"""
from __future__ import annotations

from urllib.parse import urlparse

from domain.records import DocPageRecord
from extraction.html import DocumentationHTMLParser, is_sparse_content
from extraction.trafilatura_adapter import extract_via_trafilatura


def extract_from_html(html: str, url: str, depth: int = 0, order_index: int = 0) -> DocPageRecord:
    """Parse a page's HTML into a structured :class:`DocPageRecord`."""
    parser = _best_native_parse(html, url)

    fallback = _maybe_trafilatura(parser, html, url, depth, order_index)
    if fallback is not None:
        return fallback

    _maybe_append_discovered_links(parser)

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


def _best_native_parse(html: str, url: str) -> DocumentationHTMLParser:
    """Run the content-root parse, escalating to a full-page parse when it's richer."""
    parser = DocumentationHTMLParser(url=url, capture_all=False)
    parser.feed(html)
    parser.close()

    if not parser.content_blocks and not parser.code_blocks:
        parser = DocumentationHTMLParser(url=url, capture_all=True)
        parser.feed(html)
        parser.close()
    elif is_sparse_content(parser):
        full_parser = DocumentationHTMLParser(url=url, capture_all=True)
        full_parser.feed(html)
        full_parser.close()
        if not is_sparse_content(full_parser):
            parser = full_parser
    return parser


def _maybe_trafilatura(
    parser: DocumentationHTMLParser, html: str, url: str, depth: int, order_index: int
) -> DocPageRecord | None:
    """Return a trafilatura record when the native parse is still sparse, else ``None``.

    The native parser's links/canonical/breadcrumbs are merged in because trafilatura
    drops links by design but downstream crawling still needs them.
    """
    if not is_sparse_content(parser):
        return None
    fallback = extract_via_trafilatura(html, url, depth, order_index)
    if fallback is None:
        return None
    fallback["links"] = sorted(set(parser.links))
    fallback["canonical_url"] = parser.canonical_url
    if parser.breadcrumbs:
        fallback["metadata"]["breadcrumbs"] = parser.breadcrumbs
    return fallback


def _maybe_append_discovered_links(parser: DocumentationHTMLParser) -> None:
    """For a still-sparse page with collected anchors, add a 'Discovered links' section."""
    if not (is_sparse_content(parser) and parser.sparse_link_items):
        return
    parser.content_blocks.append({
        "type": "heading", "level": 2, "text": "Discovered links",
        "items": None, "rows": None, "code_block_index": None,
    })
    parser.content_blocks.append({
        "type": "list", "level": None, "text": "",
        "items": parser.sparse_link_items, "rows": None, "code_block_index": None,
    })


__all__ = ["extract_from_html"]
