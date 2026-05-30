"""Playwright-backed page extraction (renders JS before parsing the HTML).

Two entry points share the same flow — navigate, wait for the network to settle,
discover interactive links, snapshot the rendered HTML, then delegate to the static
:func:`extraction.document.extract_from_html`:

* :func:`extract_page` launches a throwaway browser (used when no shared browser exists).
* :func:`extract_page_in_browser` reuses a caller-provided browser via a fresh context
  per call, which is thread-safe and far cheaper across a large crawl.

Both never raise: any failure becomes an error record so one bad page can't stop a crawl.
"""
from __future__ import annotations

import sys

from domain.records import DocPageRecord
from domain.record_factory import make_error_record
from extraction.browser.discovery import discover_interactive_links
from extraction.document import extract_from_html


def extract_page(url: str, depth: int = 0, order_index: int = 0) -> DocPageRecord:
    """Render ``url`` in a fresh headless browser and extract its content."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return make_error_record(
            url, depth, order_index,
            "playwright is not installed; run `pip install -r requirements.txt`", exc,
        )

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            _settle(page)
            final_url = page.url or url
            discovered_links = discover_interactive_links(page, final_url)
            html = page.content()
            browser.close()
        return _build(html, final_url, depth, order_index, discovered_links)
    except Exception as exc:
        print(f"Failed: {url}: {exc}", file=sys.stderr)
        return make_error_record(url, depth, order_index, "extractor: page extraction failed", exc)


def extract_page_in_browser(browser, url: str, depth: int = 0, order_index: int = 0) -> DocPageRecord:
    """Extract a page using an existing browser (new context per call, thread-safe)."""
    try:
        context = browser.new_context()
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            _settle(page)
            final_url = page.url or url
            discovered_links = discover_interactive_links(page, final_url)
            html = page.content()
        finally:
            context.close()
        return _build(html, final_url, depth, order_index, discovered_links)
    except Exception as exc:
        print(f"Failed: {url}: {exc}", file=sys.stderr)
        return make_error_record(url, depth, order_index, "extractor: page extraction failed", exc)


def _settle(page) -> None:
    """Best-effort wait for the network to go idle (ignored if it times out)."""
    try:
        page.wait_for_load_state("networkidle", timeout=5_000)
    except Exception:
        pass


def _build(html: str, final_url: str, depth: int, order_index: int, discovered_links: set[str]) -> DocPageRecord:
    """Parse rendered HTML and union in any links found via interaction."""
    record = extract_from_html(html, url=final_url, depth=depth, order_index=order_index)
    if discovered_links:
        record["links"] = sorted(set(record.get("links", [])) | discovered_links)
    return record


__all__ = ["extract_page", "extract_page_in_browser"]
