"""Record construction and document-level metadata for PDF extraction."""
from __future__ import annotations

from urllib.parse import urlparse

from domain.records import CodeBlock, ContentBlock, DocPageRecord


def pdf_title(doc, url: str) -> str:
    """Use the PDF's metadata title if present, else prettify the file name."""
    meta = doc.metadata or {}
    title = (meta.get("title") or "").strip()
    if title:
        return title
    name = urlparse(url).path.rsplit("/", 1)[-1]
    return name.removesuffix(".pdf").replace("-", " ").replace("_", " ").title() or url


def extract_links(doc) -> list[str]:
    """Collect unique outbound ``http(s)`` URIs from every page's link annotations."""
    links: list[str] = []
    for page in doc:
        for link in page.get_links():
            uri = link.get("uri", "")
            if uri and uri.startswith(("http://", "https://")):
                links.append(uri)
    return sorted(set(links))


def make_record(
    url: str,
    canonical_url: str | None,
    depth: int,
    order_index: int,
    title: str,
    content_blocks: list[ContentBlock],
    code_blocks: list[CodeBlock],
    links: list[str],
    breadcrumbs: list[str] | None = None,
) -> DocPageRecord:
    """Assemble a fully-keyed :class:`DocPageRecord` for an extracted PDF section/page."""
    return {
        "url": url,
        "canonical_url": canonical_url,
        "depth": depth,
        "order_index": order_index,
        "title": title,
        "content_blocks": content_blocks,
        "code_blocks": code_blocks,
        "links": links,
        "metadata": {
            "breadcrumbs": breadcrumbs or [],
            "source_domain": urlparse(url).netloc or None,
        },
        "errors": [],
    }


__all__ = ["pdf_title", "extract_links", "make_record"]
