"""Format dispatch: pick the right extractor for a URL (a small Registry/Strategy).

A crawled URL may be a PDF, a Markdown file, or an HTML page. :func:`page_fetch` inspects
the URL and routes to the matching extractor, preferring the shared browser for HTML and
falling back to the requests-based extractor when no browser is available. Returning a
*list* uniformly (PDF/Markdown can yield several records) keeps the crawl loop simple.
"""
from __future__ import annotations

from urllib.parse import urlparse

from domain.records import DocPageRecord
from extraction import extract_page, extract_page_in_browser
from markdown_extraction import extract_markdown
from pdf_extraction import extract_pdf
from pipeline.browser_pool import BrowserPool


def page_fetch(url: str, depth: int, order_index: int, pool: BrowserPool) -> list[DocPageRecord]:
    """Fetch and extract ``url`` with the extractor appropriate to its type."""
    if _is_pdf_url(url):
        return extract_pdf(url, depth=depth, order_index=order_index)
    if _is_markdown_url(url):
        return extract_markdown(url, depth=depth, order_index=order_index)
    browser = pool.get()
    if browser is None:
        return [extract_page(url, depth=depth, order_index=order_index)]
    return [extract_page_in_browser(browser, url, depth=depth, order_index=order_index)]


def _is_pdf_url(url: str) -> bool:
    """Whether the URL path ends in ``.pdf``."""
    return urlparse(url).path.lower().endswith(".pdf")


def _is_markdown_url(url: str) -> bool:
    """Whether the URL path ends in ``.md``/``.markdown``."""
    return urlparse(url).path.lower().endswith((".md", ".markdown"))


__all__ = ["page_fetch"]
