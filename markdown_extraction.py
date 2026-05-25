from __future__ import annotations

import re
import sys
import urllib.request
from urllib.parse import urljoin, urlparse

try:
    from .models import CodeBlock, ContentBlock, DocPageRecord, make_error_record
except ImportError:
    from models import CodeBlock, ContentBlock, DocPageRecord, make_error_record


_FRONT_MATTER_RE = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n", re.DOTALL)
_FRONT_MATTER_TITLE_RE = re.compile(r"^\s*title\s*:\s*(.+?)\s*$", re.MULTILINE)


def extract_markdown(url: str, depth: int = 0, order_index: int = 0) -> list[DocPageRecord]:
    try:
        from markdown_it import MarkdownIt  # noqa: F401 — presence check only
    except ImportError as exc:
        print(f"Markdown skip (markdown-it-py not installed): {url}", file=sys.stderr)
        return [_error_record(
            url, depth, order_index,
            "markdown-it-py not installed; run `pip install markdown-it-py`", exc,
        )]

    try:
        raw_bytes = _download(url)
    except Exception as exc:
        print(f"Markdown skip (download failed): {url}", file=sys.stderr)
        return [_error_record(url, depth, order_index, "markdown: download failed", exc)]

    text = _decode(raw_bytes)
    frontmatter_title, body = _split_front_matter(text)

    from markdown_it import MarkdownIt
    md = MarkdownIt("commonmark").enable(["table", "strikethrough"])
    tokens = md.parse(body)

    content_blocks: list[ContentBlock] = []
    code_blocks: list[CodeBlock] = []
    links: list[str] = []
    _walk_tokens(tokens, content_blocks, code_blocks, links, base_url=url)

    title = (
        frontmatter_title
        or _first_h1(content_blocks)
        or _filename_title(url)
    )

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
    req = urllib.request.Request(url, headers={"User-Agent": "doc-ingestor/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _split_front_matter(text: str) -> tuple[str | None, str]:
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        return None, text
    front = match.group(0)
    body = text[match.end():]
    title_match = _FRONT_MATTER_TITLE_RE.search(front)
    title = title_match.group(1).strip().strip('"').strip("'") if title_match else None
    return title or None, body


def _walk_tokens(
    tokens: list,
    content_blocks: list[ContentBlock],
    code_blocks: list[CodeBlock],
    links: list[str],
    base_url: str,
) -> None:
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        t = tok.type

        if t == "heading_open":
            level = int(tok.tag[1])
            inline = tokens[i + 1]
            text = _flatten_inline(inline, links, base_url)
            if text:
                content_blocks.append({
                    "type": "heading", "level": level, "text": text,
                    "items": None, "rows": None, "code_block_index": None,
                })
            i += 3
            continue

        if t == "paragraph_open":
            inline = tokens[i + 1]
            text = _flatten_inline(inline, links, base_url)
            if text:
                content_blocks.append({
                    "type": "paragraph", "level": None, "text": text,
                    "items": None, "rows": None, "code_block_index": None,
                })
            i += 3
            continue

        if t in {"bullet_list_open", "ordered_list_open"}:
            end = _find_matching_close(tokens, i, t.replace("_open", "_close"))
            items = _collect_list_items(tokens[i + 1:end], links, base_url)
            if items:
                content_blocks.append({
                    "type": "list", "level": None, "text": "",
                    "items": items, "rows": None, "code_block_index": None,
                })
            i = end + 1
            continue

        if t == "table_open":
            end = _find_matching_close(tokens, i, "table_close")
            rows = _collect_table_rows(tokens[i + 1:end], links, base_url)
            if rows:
                content_blocks.append({
                    "type": "table", "level": None, "text": "",
                    "items": None, "rows": rows, "code_block_index": None,
                })
            i = end + 1
            continue

        if t in {"fence", "code_block"}:
            language = (tok.info or "").strip().split()[0] if tok.info else None
            code_block_index = len(code_blocks)
            code_blocks.append({"language": language or None, "text": tok.content})
            content_blocks.append({
                "type": "code", "level": None, "text": "",
                "items": None, "rows": None, "code_block_index": code_block_index,
            })
            i += 1
            continue

        if t == "blockquote_open":
            end = _find_matching_close(tokens, i, "blockquote_close")
            _walk_tokens(tokens[i + 1:end], content_blocks, code_blocks, links, base_url)
            i = end + 1
            continue

        if t == "html_block":
            # Markdown can embed raw HTML blocks; treat as paragraph text.
            text = _strip_html(tok.content).strip()
            if text:
                content_blocks.append({
                    "type": "paragraph", "level": None, "text": text,
                    "items": None, "rows": None, "code_block_index": None,
                })
            i += 1
            continue

        i += 1


def _find_matching_close(tokens: list, start: int, close_type: str) -> int:
    depth = 0
    open_type = close_type.replace("_close", "_open")
    for j in range(start, len(tokens)):
        if tokens[j].type == open_type:
            depth += 1
        elif tokens[j].type == close_type:
            depth -= 1
            if depth == 0:
                return j
    return len(tokens) - 1


def _collect_list_items(
    tokens: list,
    links: list[str],
    base_url: str,
) -> list[str]:
    items: list[str] = []
    i = 0
    while i < len(tokens):
        if tokens[i].type == "list_item_open":
            end = _find_matching_close(tokens, i, "list_item_close")
            text = _flatten_item_content(tokens[i + 1:end], links, base_url)
            if text:
                items.append(text)
            i = end + 1
        else:
            i += 1
    return items


def _flatten_item_content(tokens: list, links: list[str], base_url: str) -> str:
    parts: list[str] = []
    for tok in tokens:
        if tok.type == "inline":
            text = _flatten_inline(tok, links, base_url)
            if text:
                parts.append(text)
    return " ".join(parts).strip()


def _collect_table_rows(
    tokens: list,
    links: list[str],
    base_url: str,
) -> list[list[str]]:
    rows: list[list[str]] = []
    i = 0
    while i < len(tokens):
        if tokens[i].type == "tr_open":
            end = _find_matching_close(tokens, i, "tr_close")
            row = _collect_table_cells(tokens[i + 1:end], links, base_url)
            if any(row):
                rows.append(row)
            i = end + 1
        else:
            i += 1
    return rows


def _collect_table_cells(
    tokens: list,
    links: list[str],
    base_url: str,
) -> list[str]:
    cells: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type in {"th_open", "td_open"}:
            close_type = tok.type.replace("_open", "_close")
            end = _find_matching_close(tokens, i, close_type)
            inline_tokens = [t for t in tokens[i + 1:end] if t.type == "inline"]
            text = " ".join(_flatten_inline(t, links, base_url) for t in inline_tokens).strip()
            cells.append(text)
            i = end + 1
        else:
            i += 1
    return cells


def _flatten_inline(inline_token, links: list[str], base_url: str) -> str:
    parts: list[str] = []
    for child in inline_token.children or []:
        t = child.type
        if t == "text":
            parts.append(child.content)
        elif t == "code_inline":
            parts.append(f"`{child.content}`")
        elif t == "softbreak":
            parts.append(" ")
        elif t == "hardbreak":
            parts.append("\n")
        elif t == "link_open":
            href = next((v for k, v in (child.attrs or {}).items() if k == "href"), None)
            if href:
                links.append(urljoin(base_url, href))
        elif t == "image":
            alt = child.content or ""
            if alt:
                parts.append(alt)
        # em/strong/link_close/etc.: ignore the wrapper, keep nested text.
    return " ".join("".join(parts).split())


def _first_h1(content_blocks: list[ContentBlock]) -> str | None:
    for block in content_blocks:
        if block.get("type") == "heading" and block.get("level") == 1:
            text = block.get("text") or ""
            if text:
                return text
    return None


def _filename_title(url: str) -> str:
    name = urlparse(url).path.rsplit("/", 1)[-1] or url
    return name.removesuffix(".md").removesuffix(".markdown").replace("-", " ").replace("_", " ").strip().title() or url


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text)


_error_record = make_error_record
