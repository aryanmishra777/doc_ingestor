"""Core domain data structures shared across every layer of the pipeline.

The whole system speaks one currency: the :class:`DocPageRecord`. A record is a
plain ``TypedDict`` (not a class) on purpose — it is created in dozens of places,
serialized to/from JSON Lines by the adaptive script runner, and read with
``record.get(...)`` throughout the codebase. Keeping it a dict means every existing
call site stays valid and there is zero runtime/validation overhead.

Think of the types here as the *schema* for that dict. Layering rule: this module is
a pure leaf — it imports nothing from the project, so every other package may depend
on it without risking an import cycle.
"""
from __future__ import annotations

from typing import Literal, TypedDict


#: The kinds of structured content block the extractors can emit. Renderers and the
#: cleaner branch on this discriminator.
BlockType = Literal["heading", "paragraph", "list", "table", "code"]


class ContentBlock(TypedDict, total=False):
    """One structural unit of a page's prose.

    Only the fields relevant to ``type`` are populated; ``total=False`` lets callers
    omit the rest. For example a ``heading`` uses ``level`` + ``text``; a ``list`` uses
    ``items``; a ``table`` uses ``rows``; and a ``code`` block carries only
    ``code_block_index``, a pointer into the sibling ``DocPageRecord["code_blocks"]``
    list (code is stored out-of-line so the same block can be rendered verbatim).
    """

    type: BlockType
    level: int | None
    text: str
    items: list[str] | None
    rows: list[list[str]] | None
    code_block_index: int | None


class CodeBlock(TypedDict, total=False):
    """A fenced code sample, referenced by ``ContentBlock.code_block_index``."""

    language: str | None
    text: str


class Metadata(TypedDict, total=False):
    """Ancillary, non-content facts about a page."""

    breadcrumbs: list[str]
    source_domain: str | None


class DocPageRecord(TypedDict, total=False):
    """The canonical representation of a single crawled/extracted page.

    Produced by the extraction layer, normalized by the cleaning layer, deduplicated
    by the pipeline, and finally serialized to Markdown by the rendering layer. The
    ``order_index``/``depth`` fields drive stable output ordering; ``links`` feeds the
    crawl frontier; ``errors`` is always present (possibly empty) so consumers can
    branch on extraction failure without a key check.
    """

    url: str
    canonical_url: str | None
    depth: int
    order_index: int
    title: str
    content_blocks: list[ContentBlock]
    code_blocks: list[CodeBlock]
    links: list[str]
    metadata: Metadata
    errors: list[str]


__all__ = [
    "BlockType",
    "ContentBlock",
    "CodeBlock",
    "Metadata",
    "DocPageRecord",
]
