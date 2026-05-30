"""Domain layer: the shared data model and errors, with no project dependencies.

This package is the stable core every other layer builds on. Import the record schema
and factories from here (``from domain import DocPageRecord, make_error_record``); the
legacy top-level :mod:`models` module re-exports the same names for backward
compatibility.
"""
from __future__ import annotations

from domain.exceptions import (
    ConfigurationError,
    DocIngestorError,
    ExtractionError,
    FetchError,
    LLMUnavailableError,
)
from domain.record_factory import make_error_record, new_record
from domain.records import (
    BlockType,
    CodeBlock,
    ContentBlock,
    DocPageRecord,
    Metadata,
)

__all__ = [
    "BlockType",
    "CodeBlock",
    "ContentBlock",
    "DocPageRecord",
    "Metadata",
    "new_record",
    "make_error_record",
    "DocIngestorError",
    "FetchError",
    "ExtractionError",
    "LLMUnavailableError",
    "ConfigurationError",
]
