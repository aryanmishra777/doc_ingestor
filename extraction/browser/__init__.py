"""Browser-rendering extraction strategy (Playwright).

Public entry points: :func:`extract_page` and :func:`extract_page_in_browser`. Use these
for JavaScript-heavy sites where the static HTML lacks content until scripts run.
"""
from __future__ import annotations

from extraction.browser.page import extract_page, extract_page_in_browser

__all__ = ["extract_page", "extract_page_in_browser"]
