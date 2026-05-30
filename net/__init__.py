"""Networking layer: the project's single HTTP entry point.

Import ``http_get`` (or :class:`HttpClient`) from here rather than re-implementing
``urllib`` calls. Keeping all outbound HTTP in one module makes timeouts, the
``User-Agent``, gzip handling, and read limits consistent and easy to change.
"""
from __future__ import annotations

from net.http_client import (
    DEFAULT_READ_LIMIT,
    DEFAULT_TIMEOUT,
    USER_AGENT,
    HttpClient,
    http_get,
)

__all__ = [
    "http_get",
    "HttpClient",
    "USER_AGENT",
    "DEFAULT_TIMEOUT",
    "DEFAULT_READ_LIMIT",
]
