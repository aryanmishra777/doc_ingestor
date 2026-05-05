from __future__ import annotations

try:
    from .models import ContentBlock, DocPageRecord
except ImportError:
    from models import ContentBlock, DocPageRecord


def structure_records_to_markdown(records: list[DocPageRecord], title: str | None = None) -> str:
    sorted_records = sorted(
        records,
        key=lambda record: (
            record.get("order_index", 0),
            record.get("depth", 0),
            record.get("url", ""),
        ),
    )
    document_title = title or derive_title(sorted_records)
    lines: list[str] = [f"# {_escape_heading(document_title)}"]

    for record in sorted_records:
        lines.extend(["", f"## {_escape_heading(record.get('title') or record.get('url') or 'Untitled Page')}", ""])
        source = record.get("canonical_url") or record.get("url")
        if source:
            lines.extend([f"Source: {source}", ""])

        breadcrumbs = (record.get("metadata") or {}).get("breadcrumbs") or []
        if breadcrumbs:
            lines.extend([f"Breadcrumbs: {' > '.join(breadcrumbs)}", ""])

        if not record.get("content_blocks") and record.get("errors"):
            lines.extend([f"Extraction note: {record['errors'][0]}", ""])
            continue

        lines.extend(_render_content_blocks(record.get("content_blocks", []), record.get("code_blocks", [])))

    return _trim_blank_lines(lines) + "\n"


def derive_title(records: list[DocPageRecord]) -> str:
    if not records:
        return "Documentation"
    domain = (records[0].get("metadata") or {}).get("source_domain")
    return f"{domain} Documentation" if domain else records[0].get("title", "Documentation")


def _render_content_blocks(content_blocks: list[ContentBlock], code_blocks: list[dict]) -> list[str]:
    lines: list[str] = []
    last_heading_level = 2
    base_source_heading: int | None = None

    for block in content_blocks:
        block_type = block.get("type")
        if block_type == "heading":
            base_source_heading, last_heading_level = _render_heading_block(
                block,
                lines,
                base_source_heading,
                last_heading_level,
            )
            continue
        if block_type == "paragraph":
            _render_paragraph_block(block, lines)
            continue
        if block_type == "list":
            _render_list_block(block, lines)
            continue
        if block_type == "table":
            _render_table_block(block, lines)
            continue
        if block_type == "code":
            _render_code_block_from_index(block, code_blocks, lines)

    return lines


def _render_heading_block(
    block: ContentBlock,
    lines: list[str],
    base_source_heading: int | None,
    last_heading_level: int,
) -> tuple[int | None, int]:
    source_level = int(block.get("level") or 1)
    if base_source_heading is None:
        base_source_heading = source_level
    desired_level = 3 + max(0, source_level - base_source_heading)
    rendered_level = min(6, max(3, min(desired_level, last_heading_level + 1)))
    last_heading_level = rendered_level
    lines.extend(["", f"{'#' * rendered_level} {_escape_heading(block.get('text', ''))}", ""])
    return base_source_heading, last_heading_level


def _render_paragraph_block(block: ContentBlock, lines: list[str]) -> None:
    lines.extend([block.get("text", ""), ""])


def _render_list_block(block: ContentBlock, lines: list[str]) -> None:
    for item in block.get("items") or []:
        lines.append(f"- {item}")
    lines.append("")


def _render_table_block(block: ContentBlock, lines: list[str]) -> None:
    lines.extend(_render_table(block.get("rows") or []))


def _render_code_block_from_index(block: ContentBlock, code_blocks: list[dict], lines: list[str]) -> None:
    code_block_index = block.get("code_block_index")
    if isinstance(code_block_index, int) and 0 <= code_block_index < len(code_blocks):
        lines.extend(_render_code_block(code_blocks[code_block_index]))


def _render_code_block(code_block: dict) -> list[str]:
    language = code_block.get("language") or ""
    text = code_block.get("text", "")
    return ["", f"```{language}", text.rstrip("\n"), "```", ""]


def _render_table(rows: list[list[str]]) -> list[str]:
    if not rows:
        return []
    width = len(rows[0])
    if width and all(len(row) == width for row in rows):
        header = rows[0]
        body = rows[1:]
        table_lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join("---" for _ in header) + " |",
        ]
        table_lines.extend("| " + " | ".join(row) + " |" for row in body)
        return ["", *table_lines, ""]

    return ["", *[f"- {' | '.join(row)}" for row in rows], ""]


def _escape_heading(text: str) -> str:
    return (text or "Untitled").replace("\n", " ").strip() or "Untitled"


def _trim_blank_lines(lines: list[str]) -> str:
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)

