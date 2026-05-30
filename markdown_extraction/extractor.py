"""Public Markdown extractor: fetch a ``.md`` URL and parse it into records.

Used by the pipeline when a crawl encounters a ``.md``/``.markdown`` link. Parses with
markdown-it (CommonMark + tables + strikethrough), derives a title from YAML front matter
→ first ``# H1`` → prettified filename, and returns a single-element list (matching the
multi-record extractors' signature). Like every extractor it returns an error record
rather than raising.
"""
from __future__ import annotations

import re
import sys
import urllib.request
from urllib.parse import urlparse

from domain.records import CodeBlock, ContentBlock, DocPageRecord
from domain.record_factory import make_error_record
from markdown_extraction.walk import walk_tokens

_FRONT_MATTER_RE = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n", re.DOTALL)
_FRONT_MATTER_TITLE_RE = re.compile(r"^\s*title\s*:\s*(.+?)\s*$", re.MULTILINE)


def extract_markdown(url: str, depth: int = 0, order_index: int = 0) -> list[DocPageRecord]:
    """Download and parse a Markdown document into a one-element record list."""
    try:
        from markdown_it import MarkdownIt  # noqa: F401 — presence check only
    except ImportError as exc:
        print(f"Markdown skip (markdown-it-py not installed): {url}", file=sys.stderr)
        return [make_error_record(
            url, depth, order_index,
            "markdown-it-py not installed; run `pip install markdown-it-py`", exc,
        )]

    try:
        raw_bytes = _download(url)
    except Exception as exc:
        print(f"Markdown skip (download failed): {url}", file=sys.stderr)
        return [make_error_record(url, depth, order_index, "markdown: download failed", exc)]

    frontmatter_title, body = _split_front_matter(_decode(raw_bytes))

    from markdown_it import MarkdownIt
    md = MarkdownIt("commonmark").enable(["table", "strikethrough"])
    tokens = md.parse(body)

    content_blocks: list[ContentBlock] = []
    code_blocks: list[CodeBlock] = []
    links: list[str] = []
    walk_tokens(tokens, content_blocks, code_blocks, links, base_url=url)

    title = frontmatter_title or _first_h1(content_blocks) or _filename_title(url)
    return [{
        "url": url,
        "canonical_url": None,
        "depth": depth,
        "order_index": order_index,
        "title": title,
        "content_blocks": content_blocks,
        "code_blocks": code_blocks,
        "links": sorted(set(links)),
        "metadata": {
            "breadcrumbs": [],
            "source_domain": urlparse(url).netloc or None,
            "extractor": "markdown",
        },
        "errors": [],
    }]


def _download(url: str) -> bytes:
    """Fetch raw bytes for a Markdown URL with the project User-Agent."""
    req = urllib.request.Request(url, headers={"User-Agent": "doc-ingestor/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def _decode(raw: bytes) -> str:
    """Decode bytes, trying common encodings before a lossy UTF-8 fallback."""
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _split_front_matter(text: str) -> tuple[str | None, str]:
    """Split leading YAML front matter, returning ``(title or None, body)``."""
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        return None, text
    front = match.group(0)
    body = text[match.end():]
    title_match = _FRONT_MATTER_TITLE_RE.search(front)
    title = title_match.group(1).strip().strip('"').strip("'") if title_match else None
    return title or None, body


def _first_h1(content_blocks: list[ContentBlock]) -> str | None:
    """Return the first level-1 heading text, if any."""
    for block in content_blocks:
        if block.get("type") == "heading" and block.get("level") == 1:
            text = block.get("text") or ""
            if text:
                return text
    return None


def _filename_title(url: str) -> str:
    """Derive a human title from the file name when no better title exists."""
    name = urlparse(url).path.rsplit("/", 1)[-1] or url
    return (
        name.removesuffix(".md").removesuffix(".markdown")
        .replace("-", " ").replace("_", " ").strip().title()
        or url
    )


__all__ = ["extract_markdown"]
