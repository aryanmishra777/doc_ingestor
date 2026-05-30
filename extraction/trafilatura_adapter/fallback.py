"""The trafilatura extraction fallback.

When the structure-aware parser yields too little prose, this strategy uses trafilatura's
content-density scoring — which ignores class/tag conventions — to recover content from
sites that don't use semantic HTML. It returns ``None`` (so the caller can degrade
further) when trafilatura is absent, the page has no extractable prose, or the XML can't
be parsed. Links are intentionally not extracted here; the caller re-attaches the native
parser's links so crawling still works.
"""
from __future__ import annotations

from urllib.parse import urlparse

from domain.records import CodeBlock, ContentBlock, DocPageRecord
from extraction.trafilatura_adapter.walk import walk_xml


def extract_via_trafilatura(html: str, url: str, depth: int, order_index: int) -> DocPageRecord | None:
    """Best-effort density-based extraction; ``None`` if nothing usable is found."""
    try:
        import trafilatura
        from xml.etree import ElementTree as ET
    except ImportError:
        return None

    try:
        xml_str = trafilatura.extract(
            html,
            url=url,
            output_format="xml",
            include_comments=False,
            include_tables=True,
            include_formatting=True,
            include_links=False,
        )
    except Exception:
        return None
    if not xml_str:
        return None

    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return None

    title = _extract_title(trafilatura, html, url)

    content_blocks: list[ContentBlock] = []
    code_blocks: list[CodeBlock] = []
    walk_xml(root, content_blocks, code_blocks)
    if not content_blocks and not code_blocks:
        return None

    if not title:
        title = _first_heading(content_blocks)

    return {
        "url": url,
        "canonical_url": None,
        "depth": depth,
        "order_index": order_index,
        "title": title or url,
        "content_blocks": content_blocks,
        "code_blocks": code_blocks,
        "links": [],
        "metadata": {
            "breadcrumbs": [],
            "source_domain": urlparse(url).netloc or None,
            "extractor": "trafilatura",
        },
        "errors": [],
    }


def _extract_title(trafilatura, html: str, url: str) -> str:
    """Pull the document title from trafilatura metadata, tolerating failures."""
    try:
        meta = trafilatura.extract_metadata(html, default_url=url)
        return (getattr(meta, "title", "") or "").strip() if meta else ""
    except Exception:
        return ""


def _first_heading(content_blocks: list[ContentBlock]) -> str:
    """Fall back to the first heading's text when no metadata title exists."""
    for block in content_blocks:
        if block.get("type") == "heading" and block.get("text"):
            return block["text"]
    return ""


__all__ = ["extract_via_trafilatura"]
