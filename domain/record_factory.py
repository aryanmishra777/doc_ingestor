"""Factory helpers for constructing :class:`DocPageRecord` values.

Centralizing record creation keeps the dict shape consistent (every record carries
the same keys, including an always-present ``errors`` list and a ``metadata`` block).
The two helpers here cover the only two ways a record is born:

* :func:`new_record` — a blank-but-complete record the extractors fill in.
* :func:`make_error_record` — a placeholder for a page that could not be fetched or
  parsed, so the failure still flows through the pipeline as data rather than an
  exception.
"""
from __future__ import annotations

from urllib.parse import urlparse

from domain.records import DocPageRecord


def new_record(url: str, depth: int, order_index: int, *, title: str = "") -> DocPageRecord:
    """Return a fully-keyed, empty record ready for an extractor to populate.

    Using this instead of an inline dict guarantees no required key is forgotten and
    that ``source_domain`` is derived consistently from the URL.
    """
    return {
        "url": url,
        "canonical_url": None,
        "depth": depth,
        "order_index": order_index,
        "title": title or url,
        "content_blocks": [],
        "code_blocks": [],
        "links": [],
        "metadata": {"breadcrumbs": [], "source_domain": urlparse(url).netloc or None},
        "errors": [],
    }


def make_error_record(
    url: str, depth: int, order_index: int, message: str, exc: Exception
) -> DocPageRecord:
    """Build a record that records a fetch/parse failure as content-free data.

    The original behavior (and shape) is preserved exactly: the title falls back to
    the URL and ``errors`` holds a single ``"<message>: <exc>"`` string so downstream
    rendering can surface an "Extraction note" instead of crashing the crawl.
    """
    return {
        "url": url,
        "canonical_url": None,
        "depth": depth,
        "order_index": order_index,
        "title": url,
        "content_blocks": [],
        "code_blocks": [],
        "links": [],
        "metadata": {"breadcrumbs": [], "source_domain": urlparse(url).netloc or None},
        "errors": [f"{message}: {exc}"],
    }


__all__ = ["new_record", "make_error_record"]
