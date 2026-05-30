"""Extraction layer: turn a URL or raw HTML into a structured :class:`DocPageRecord`.

Three interchangeable strategies sit behind this facade (a **Strategy**/Chain design):

* static HTML — :func:`extract_from_html` (structure-aware parser → trafilatura fallback);
* rendered HTML — :func:`extract_page` / :func:`extract_page_in_browser` (Playwright);
* (PDF and Markdown live in the sibling ``pdf_extraction`` / ``markdown_extraction`` packages).

Import the same names as before the refactor:
``from extraction import extract_from_html, extract_page, extract_page_in_browser``.
"""
from __future__ import annotations

from extraction.browser import extract_page, extract_page_in_browser
from extraction.document import extract_from_html

__all__ = ["extract_from_html", "extract_page", "extract_page_in_browser"]
