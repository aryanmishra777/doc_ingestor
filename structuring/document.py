"""Assembly of a full Markdown document from a list of records.

This is the final stage of the pipeline. Records are sorted into a stable order
(``order_index`` → ``depth`` → ``url``) and each becomes an ``##`` section with a source
link, optional breadcrumbs, and its rendered content blocks. A record that failed
extraction is rendered as a short "Extraction note" rather than an empty section, so the
output always accounts for every page.
"""
from __future__ import annotations

from domain.records import DocPageRecord
from structuring.blocks import escape_heading, render_content_blocks


def structure_records_to_markdown(records: list[DocPageRecord], title: str | None = None) -> str:
    """Render ``records`` into a single Markdown document string.

    ``title`` overrides the auto-derived document heading (used when writing chunked
    output like "… (Part 2 of 7)").
    """
    sorted_records = sorted(
        records,
        key=lambda record: (
            record.get("order_index", 0),
            record.get("depth", 0),
            record.get("url", ""),
        ),
    )
    document_title = title or derive_title(sorted_records)
    lines: list[str] = [f"# {escape_heading(document_title)}"]

    for record in sorted_records:
        heading = record.get("title") or record.get("url") or "Untitled Page"
        lines.extend(["", f"## {escape_heading(heading)}", ""])
        source = record.get("canonical_url") or record.get("url")
        if source:
            lines.extend([f"Source: {source}", ""])

        breadcrumbs = (record.get("metadata") or {}).get("breadcrumbs") or []
        if breadcrumbs:
            lines.extend([f"Breadcrumbs: {' > '.join(breadcrumbs)}", ""])

        if not record.get("content_blocks") and record.get("errors"):
            lines.extend([f"Extraction note: {record['errors'][0]}", ""])
            continue

        lines.extend(
            render_content_blocks(record.get("content_blocks", []), record.get("code_blocks", []))
        )

    return _trim_blank_lines(lines) + "\n"


def derive_title(records: list[DocPageRecord]) -> str:
    """Pick a document title: the source domain if known, else the first page's title."""
    if not records:
        return "Documentation"
    domain = (records[0].get("metadata") or {}).get("source_domain")
    return f"{domain} Documentation" if domain else records[0].get("title", "Documentation")


def _trim_blank_lines(lines: list[str]) -> str:
    """Drop trailing blank lines and join into a single string."""
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


__all__ = ["structure_records_to_markdown", "derive_title"]
