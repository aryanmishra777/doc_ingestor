from __future__ import annotations

from typing import Literal, TypedDict
from urllib.parse import urlparse


BlockType = Literal["heading", "paragraph", "list", "table", "code"]


class ContentBlock(TypedDict, total=False):
    type: BlockType
    level: int | None
    text: str
    items: list[str] | None
    rows: list[list[str]] | None
    code_block_index: int | None


class CodeBlock(TypedDict, total=False):
    language: str | None
    text: str


class Metadata(TypedDict, total=False):
    breadcrumbs: list[str]
    source_domain: str | None


class DocPageRecord(TypedDict, total=False):
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


def make_error_record(url: str, depth: int, order_index: int, message: str, exc: Exception) -> "DocPageRecord":
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

