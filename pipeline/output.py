"""Markdown output writing helpers for the pipeline facade."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from domain.records import DocPageRecord
from pipeline.log import stderr_logger
from structuring import derive_title, structure_records_to_markdown

DEFAULT_CHUNK_PAGES = 50


def write_markdown_outputs(
    records: list[DocPageRecord],
    output: Path,
    chunk_pages: int = DEFAULT_CHUNK_PAGES,
    logger: Callable[[str], None] | None = None,
) -> list[Path]:
    """Write records to one Markdown file or numbered chunks when requested."""
    log = logger or stderr_logger
    if chunk_pages <= 0:
        raise ValueError("chunk_pages must be greater than zero")

    chunks = _chunk_records(records, chunk_pages)
    if len(chunks) <= 1:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(structure_records_to_markdown(records), encoding="utf-8")
        log(f"Output: wrote 1 Markdown file to {output}")
        return [output]

    output_dir = _chunk_output_dir(output)
    output_dir.mkdir(parents=True, exist_ok=True)
    return _write_chunks(records, chunks, output, output_dir, log, chunk_pages)


def _write_chunks(
    records: list[DocPageRecord],
    chunks: list[list[DocPageRecord]],
    output: Path,
    output_dir: Path,
    log: Callable[[str], None],
    chunk_pages: int,
) -> list[Path]:
    """Write each chunk and return the paths created."""
    prefix = output.stem if output.suffix else "documentation"
    written_paths: list[Path] = []
    total_chunks = len(chunks)
    log(f"Output: chunking Markdown into {total_chunks} files with up to {chunk_pages} pages each")
    for index, chunk in enumerate(chunks, start=1):
        chunk_path = output_dir / f"{prefix}_part_{index:03d}_of_{total_chunks:03d}.md"
        title = f"{derive_title(records)} (Part {index} of {total_chunks})"
        chunk_path.write_text(structure_records_to_markdown(chunk, title=title), encoding="utf-8")
        written_paths.append(chunk_path)
        log(f"Output: wrote chunk {index}/{total_chunks}: {chunk_path}")
    log(f"Output complete: wrote {len(written_paths)} Markdown files in {output_dir}")
    return written_paths


def _chunk_records(records: list[DocPageRecord], chunk_pages: int) -> list[list[DocPageRecord]]:
    """Split records into fixed-size page chunks, preserving the empty-output case."""
    if not records:
        return [[]]
    return [records[index : index + chunk_pages] for index in range(0, len(records), chunk_pages)]


def _chunk_output_dir(output: Path) -> Path:
    """Return the output directory used for chunked Markdown."""
    if output.suffix:
        return output.parent / f"{output.stem}_chunks"
    return output


__all__ = ["DEFAULT_CHUNK_PAGES", "write_markdown_outputs"]
