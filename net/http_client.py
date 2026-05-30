"""The single low-level HTTP GET used across the crawler.

Historically this logic lived as ``adaptive._http_get`` and was even imported by the
one-off OpenVINO script. It is the project's one place that knows how to:

* send a polite ``User-Agent``,
* cap how many bytes are read (``read_limit``) so a hostile/huge resource can't
  exhaust memory,
* transparently gunzip ``.gz`` sitemaps and gzip-encoded responses, and
* never raise — every failure collapses to ``None`` so callers can branch simply.

:func:`http_get` returns a small dict (``status``/``content_type``/``headers``/``body``)
to stay drop-in compatible with every existing caller and with the test fakes that
replace it. :class:`HttpClient` is a thin object wrapper for dependency-injection-style
call sites that prefer a port over a free function.
"""
from __future__ import annotations

import gzip
import io
from typing import Any
from urllib.request import Request, urlopen

#: Identifies the crawler to upstream servers.
USER_AGENT = "doc-ingestor/1.0"

#: Default per-request timeout (seconds) for fast existence/probe requests.
DEFAULT_TIMEOUT = 5.0

#: Default cap on bytes read from a response body (64 KiB) unless a caller raises it.
DEFAULT_READ_LIMIT = 65536


def _needs_decompress(url: str, content_type: str, content_encoding: str) -> bool:
    """Decide whether a body must be gunzipped before decoding to text."""
    return (
        url.lower().endswith(".gz")
        or "gzip" in content_encoding.lower()
        or "application/gzip" in content_type.lower()
        or "application/x-gzip" in content_type.lower()
    )


def http_get(
    url: str, read_limit: int = DEFAULT_READ_LIMIT, timeout: float = DEFAULT_TIMEOUT
) -> dict[str, Any] | None:
    """Fetch ``url`` and return a result dict, or ``None`` on any failure.

    The returned dict has keys ``status``, ``content_type``, ``headers`` and ``body``
    (already decoded to ``str`` with ``errors="ignore"``). For gzip streams the full
    body is read before decompression — a partial read would truncate the gzip member
    and fail — and only then is ``read_limit`` applied to the decompressed text.
    """
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"}, method="GET")
    try:
        with urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            content_encoding = resp.headers.get("Content-Encoding", "")
            headers = dict(resp.headers)
            decompress = _needs_decompress(url, content_type, content_encoding)
            raw = resp.read() if decompress else resp.read(read_limit)
            if decompress:
                try:
                    raw = gzip.open(io.BytesIO(raw)).read()
                except Exception:
                    pass
            return {
                "status": resp.getcode(),
                "content_type": content_type,
                "headers": headers,
                "body": raw[:read_limit].decode("utf-8", errors="ignore"),
            }
    except Exception:
        return None


class HttpClient:
    """Object adapter around :func:`http_get` for injectable call sites.

    Lets higher layers depend on a small port (``client.get(url)``) instead of a module
    function, which makes them trivial to stub in tests. Behavior is identical to
    :func:`http_get`.
    """

    def __init__(self, *, default_timeout: float = DEFAULT_TIMEOUT) -> None:
        self._default_timeout = default_timeout

    def get(
        self, url: str, read_limit: int = DEFAULT_READ_LIMIT, timeout: float | None = None
    ) -> dict[str, Any] | None:
        """Fetch ``url``; falls back to the client's configured default timeout."""
        return http_get(url, read_limit=read_limit, timeout=timeout or self._default_timeout)


__all__ = ["http_get", "HttpClient", "USER_AGENT", "DEFAULT_TIMEOUT", "DEFAULT_READ_LIMIT"]
