"""Project-wide exception hierarchy.

The crawler is deliberately fault-tolerant: a single page that fails to fetch or
parse must never abort a multi-thousand-page crawl. Most failures are therefore
*captured as data* (see :func:`domain.record_factory.make_error_record`) rather than
raised. This small hierarchy exists for the cases where raising is the right call
(programmer errors, exhausted retries, misconfiguration) and to give callers a single
base class (:class:`DocIngestorError`) to catch when they want to distinguish "our"
errors from unexpected ones.
"""
from __future__ import annotations


class DocIngestorError(Exception):
    """Base class for every error raised intentionally by this package."""


class FetchError(DocIngestorError):
    """A network resource could not be retrieved after exhausting retries."""


class ExtractionError(DocIngestorError):
    """Page content could not be parsed into structured blocks."""


class LLMUnavailableError(DocIngestorError):
    """An LLM provider was requested but is not usable.

    Carries a human-readable ``reason`` (missing API key, provider package absent,
    local server down, …) so callers can log *why* they fell back to heuristics.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ConfigurationError(DocIngestorError):
    """A required setting or environment value is missing or invalid."""


__all__ = [
    "DocIngestorError",
    "FetchError",
    "ExtractionError",
    "LLMUnavailableError",
    "ConfigurationError",
]
