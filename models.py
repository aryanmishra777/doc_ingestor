"""Backward-compatibility shim for the historical ``models`` module.

The domain model moved into the :mod:`domain` package during the production refactor.
This module re-exports the exact same names so existing imports such as
``from models import DocPageRecord, make_error_record`` and ``import models`` keep
working unchanged. New code should import from :mod:`domain` directly.
"""
from __future__ import annotations

from domain.record_factory import make_error_record
from domain.records import (
    BlockType,
    CodeBlock,
    ContentBlock,
    DocPageRecord,
    Metadata,
)

__all__ = [
    "BlockType",
    "ContentBlock",
    "CodeBlock",
    "Metadata",
    "DocPageRecord",
    "make_error_record",
]
