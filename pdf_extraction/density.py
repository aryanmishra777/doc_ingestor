"""Density analysis: decide how aggressively to segment a PDF.

A PDF that is mostly images with little text is "scanned" and skipped (we don't OCR). The
rest are classified ``light`` (continuous prose → one record), ``medium`` (chars/tables
suggest sections → split on headings), or ``dense`` (sparse/figure-heavy → one record per
page). The thresholds live in :mod:`pdf_extraction.constants`.
"""
from __future__ import annotations

from pdf_extraction.constants import (
    DensityLevel,
    LIGHT_CHARS_PER_PAGE,
    MEDIUM_CHARS_PER_PAGE,
    SCANNED_CHARS_PER_PAGE,
)


def is_scanned(doc) -> bool:
    """True when average extractable text per page is too low to be a digital PDF."""
    n = len(doc)
    if n == 0:
        return True
    total_chars = sum(len(page.get_text()) for page in doc)
    return (total_chars / n) < SCANNED_CHARS_PER_PAGE


def analyze_density(doc) -> DensityLevel:
    """Classify a document's density into ``light``/``medium``/``dense``."""
    n = len(doc)
    if n == 0:
        return "light"

    total_chars = 0
    total_images = 0
    table_count = 0
    for page in doc:
        total_chars += len(page.get_text())
        total_images += len(page.get_images())
        try:
            table_count += len(page.find_tables().tables)
        except Exception:
            pass

    chars_per_page = total_chars / n
    images_per_page = total_images / n
    tables_per_page = table_count / n

    if chars_per_page >= LIGHT_CHARS_PER_PAGE and images_per_page < 1.0:
        return "light"
    if chars_per_page >= MEDIUM_CHARS_PER_PAGE or tables_per_page >= 0.3:
        return "medium"
    return "dense"


__all__ = ["is_scanned", "analyze_density"]
