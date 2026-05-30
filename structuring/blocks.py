"""Per-block Markdown renderers.

Each content block type maps to a small renderer that appends lines to a shared list.
The trickiest piece is heading-level remapping: source pages use arbitrary heading
depths, but the output nests every page under an ``##`` section, so headings are clamped
into the ``###``–``######`` range and prevented from jumping more than one level at a
time. Tables degrade gracefully to a bullet list when rows are ragged.
"""
from __future__ import annotations

from domain.records import ContentBlock


def render_content_blocks(content_blocks: list[ContentBlock], code_blocks: list[dict]) -> list[str]:
    """Render an ordered list of content blocks into Markdown lines.

    ``code`` blocks store only an index into ``code_blocks``; the actual fenced text is
    looked up there so identical snippets render verbatim and out-of-line.
    """
    lines: list[str] = []
    last_heading_level = 2
    base_source_heading: int | None = None

    for block in content_blocks:
        block_type = block.get("type")
        if block_type == "heading":
            base_source_heading, last_heading_level = _render_heading_block(
                block, lines, base_source_heading, last_heading_level
            )
        elif block_type == "paragraph":
            lines.extend([block.get("text", ""), ""])
        elif block_type == "list":
            _render_list_block(block, lines)
        elif block_type == "table":
            lines.extend(_render_table(block.get("rows") or []))
        elif block_type == "code":
            _render_code_block_from_index(block, code_blocks, lines)

    return lines


def _render_heading_block(
    block: ContentBlock, lines: list[str], base_source_heading: int | None, last_heading_level: int
) -> tuple[int | None, int]:
    """Emit a heading, remapping its source depth into the ``###``–``######`` band."""
    source_level = int(block.get("level") or 1)
    if base_source_heading is None:
        base_source_heading = source_level
    desired_level = 3 + max(0, source_level - base_source_heading)
    rendered_level = min(6, max(3, min(desired_level, last_heading_level + 1)))
    lines.extend(["", f"{'#' * rendered_level} {escape_heading(block.get('text', ''))}", ""])
    return base_source_heading, rendered_level


def _render_list_block(block: ContentBlock, lines: list[str]) -> None:
    """Emit a list block as Markdown ``-`` bullets."""
    for item in block.get("items") or []:
        lines.append(f"- {item}")
    lines.append("")


def _render_code_block_from_index(block: ContentBlock, code_blocks: list[dict], lines: list[str]) -> None:
    """Resolve a code block's index and emit its fenced form, if valid."""
    code_block_index = block.get("code_block_index")
    if isinstance(code_block_index, int) and 0 <= code_block_index < len(code_blocks):
        lines.extend(_render_code_block(code_blocks[code_block_index]))


def _render_code_block(code_block: dict) -> list[str]:
    """Render one fenced code block, tagging the language when known."""
    language = code_block.get("language") or ""
    text = code_block.get("text", "")
    return ["", f"```{language}", text.rstrip("\n"), "```", ""]


def _render_table(rows: list[list[str]]) -> list[str]:
    """Render a GitHub-flavored table, falling back to bullets for ragged rows."""
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


def escape_heading(text: str) -> str:
    """Flatten newlines and guarantee a non-empty heading label."""
    return (text or "Untitled").replace("\n", " ").strip() or "Untitled"


__all__ = ["render_content_blocks", "escape_heading"]
