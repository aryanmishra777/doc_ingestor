from __future__ import annotations

import copy
import re
import unicodedata

try:
    from .models import ContentBlock, DocPageRecord
except ImportError:
    from models import ContentBlock, DocPageRecord


ZERO_WIDTH_CHARS = {
    "\u200b",
    "\u200c",
    "\u200d",
    "\ufeff",
}

MULTI_BLANK_LINE_RE = re.compile(r"\n{3,}")
SPACES_TABS_RE = re.compile(r"[ \t]+")


def clean_record(record: DocPageRecord) -> DocPageRecord:
    cleaned = copy.deepcopy(record)
    cleaned.setdefault("errors", [])
    cleaned["title"] = _clean_prose(cleaned.get("title", ""))
    cleaned["content_blocks"] = _clean_content_blocks(cleaned.get("content_blocks", []))
    cleaned["code_blocks"] = [
        {
            "language": _clean_prose(code_block.get("language") or "") or None,
            "text": _clean_code(code_block.get("text", "")),
        }
        for code_block in cleaned.get("code_blocks", [])
    ]

    if not cleaned["content_blocks"] and not cleaned["code_blocks"]:
        cleaned["errors"].append("cleaner: empty content after cleaning")

    return cleaned


def _clean_content_blocks(blocks: list[ContentBlock]) -> list[ContentBlock]:
    cleaned_blocks: list[ContentBlock] = []
    seen_prose: set[tuple[str, str]] = set()

    for block in blocks:
        cleaned_block: ContentBlock = copy.deepcopy(block)
        block_type = cleaned_block.get("type")

        if block_type in {"heading", "paragraph"}:
            cleaned_block["text"] = _clean_prose(cleaned_block.get("text", ""))
        elif block_type == "list":
            cleaned_block["items"] = [
                item
                for item in (_clean_prose(item) for item in cleaned_block.get("items") or [])
                if item
            ]
            cleaned_block["text"] = _clean_prose(cleaned_block.get("text", ""))
        elif block_type == "table":
            rows = cleaned_block.get("rows") or []
            cleaned_block["rows"] = [[_clean_prose(cell) for cell in row] for row in rows]
            cleaned_block["text"] = _clean_prose(cleaned_block.get("text", ""))
        elif block_type == "code":
            cleaned_blocks.append(cleaned_block)
            continue

        if not _has_content(cleaned_block):
            continue
        if _is_duplicate_prose(cleaned_block, seen_prose):
            continue

        cleaned_blocks.append(cleaned_block)

    return cleaned_blocks


def _is_duplicate_prose(block: ContentBlock, seen_prose: set[tuple[str, str]]) -> bool:
    block_type = block.get("type")
    if block_type == "paragraph":
        text = block.get("text", "")
        if len(text) < 40:
            return False
        key = ("paragraph", text)
    elif block_type == "list":
        items = block.get("items") or []
        text = "\n".join(items)
        if len(text) < 40:
            return False
        key = ("list", text)
    else:
        return False

    if key in seen_prose:
        return True
    seen_prose.add(key)
    return False


def _has_content(block: ContentBlock) -> bool:
    block_type = block.get("type")
    if block_type in {"heading", "paragraph"}:
        return bool(block.get("text"))
    if block_type == "list":
        return bool(block.get("items"))
    if block_type == "table":
        return any(any(row) for row in block.get("rows") or [])
    return True


def _clean_prose(value: str) -> str:
    text = _normalize_unicode(value)
    text = _strip_control_chars(text, keep_newline=True, keep_tab=False)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = SPACES_TABS_RE.sub(" ", text)
    text = MULTI_BLANK_LINE_RE.sub("\n\n", text)
    return text.strip()


def _clean_code(value: str) -> str:
    text = _normalize_unicode(value)
    text = _strip_control_chars(text, keep_newline=True, keep_tab=True)
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _normalize_unicode(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def _strip_control_chars(value: str, keep_newline: bool, keep_tab: bool) -> str:
    chars: list[str] = []
    for char in value:
        if char in ZERO_WIDTH_CHARS:
            continue
        if char == "\n" and keep_newline:
            chars.append(char)
            continue
        if char == "\t" and keep_tab:
            chars.append(char)
            continue
        category = unicodedata.category(char)
        if category.startswith("C"):
            continue
        chars.append(char)
    return "".join(chars)

