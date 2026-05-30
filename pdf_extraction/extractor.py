"""Public PDF extractor: download a PDF and route it to a density strategy.

Entry point :func:`extract_pdf` orchestrates: lazily require PyMuPDF, download bytes, open
the document, skip scanned PDFs (no extractable text), then dispatch to the ``light`` /
``medium`` / ``dense`` strategy based on :func:`pdf_extraction.density.analyze_density`.
Each failure mode returns an error record (or an empty list for scanned PDFs) so the crawl
keeps going.
"""
from __future__ import annotations

import sys
import urllib.request

from domain.records import DocPageRecord
from domain.record_factory import make_error_record
from pdf_extraction.density import analyze_density, is_scanned
from pdf_extraction.records import extract_links, pdf_title
from pdf_extraction.strategies import extract_dense, extract_light, extract_medium


def extract_pdf(url: str, depth: int = 0, order_index: int = 0) -> list[DocPageRecord]:
    """Download and extract a PDF into one or more records."""
    try:
        import fitz  # noqa: F401 — presence check only
    except ImportError as exc:
        print(f"PDF skip (pymupdf not installed): {url}", file=sys.stderr)
        return [make_error_record(url, depth, order_index, "pymupdf not installed; run `pip install pymupdf`", exc)]

    try:
        pdf_bytes = _download(url)
    except Exception as exc:
        print(f"PDF skip (download failed): {url}", file=sys.stderr)
        return [make_error_record(url, depth, order_index, "pdf: download failed", exc)]

    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        print(f"PDF skip (could not open): {url}", file=sys.stderr)
        return [make_error_record(url, depth, order_index, "pdf: could not open", exc)]

    try:
        if is_scanned(doc):
            print(f"PDF skip (scanned, no extractable text): {url}", file=sys.stderr)
            return []

        density = analyze_density(doc)
        base_title = pdf_title(doc, url)
        outbound_links = extract_links(doc)

        if density == "light":
            return extract_light(doc, url, depth, order_index, base_title, outbound_links)
        if density == "medium":
            return extract_medium(doc, url, depth, order_index, base_title, outbound_links)
        return extract_dense(doc, url, depth, order_index, base_title, outbound_links)
    finally:
        doc.close()


def _download(url: str) -> bytes:
    """Fetch raw PDF bytes with the project User-Agent."""
    req = urllib.request.Request(url, headers={"User-Agent": "doc-ingestor/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


__all__ = ["extract_pdf"]
