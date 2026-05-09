"""
NotebookLM MCP Server
Exposes NotebookLM notebooks as MCP tools so coding editors and AI agents
(Claude Code, Cursor, etc.) can read, query, and manage notebooks.

Requirements:
  pip install fastmcp "notebooklm-py[browser]"
  playwright install chromium
  notebooklm login   # saves browser session to disk once

Usage:
  python notebooklm_server.py
"""

import asyncio
import os
from typing import Optional

from fastmcp import FastMCP
from notebooklm import NotebookLMClient

mcp = FastMCP("NotebookLM")

_client: Optional[NotebookLMClient] = None
_client_lock = asyncio.Lock()


async def _get_client() -> NotebookLMClient:
    global _client
    if _client is not None:
        return _client
    async with _client_lock:
        if _client is None:
            storage_path = os.environ.get("NOTEBOOKLM_STORAGE_PATH")
            cm = await NotebookLMClient.from_storage(path=storage_path)
            _client = await cm.__aenter__()
    return _client


# ── Notebooks ──────────────────────────────────────────────────────────────

@mcp.tool
async def list_notebooks() -> str:
    """List all NotebookLM notebooks with their IDs and titles."""
    client = await _get_client()
    notebooks = await client.notebooks.list()
    if not notebooks:
        return "No notebooks found."
    return "\n".join(f"ID: {nb.id}  |  Title: {nb.title}" for nb in notebooks)


@mcp.tool
async def create_notebook(title: str) -> str:
    """Create a new NotebookLM notebook. Returns the new notebook ID."""
    client = await _get_client()
    nb = await client.notebooks.create(title)
    return f"Created notebook '{nb.title}'  |  ID: {nb.id}"


@mcp.tool
async def delete_notebook(notebook_id: str) -> str:
    """Delete a NotebookLM notebook by its ID."""
    client = await _get_client()
    success = await client.notebooks.delete(notebook_id)
    return "Notebook deleted." if success else "Failed to delete notebook."


@mcp.tool
async def rename_notebook(notebook_id: str, new_title: str) -> str:
    """Rename an existing notebook."""
    client = await _get_client()
    nb = await client.notebooks.rename(notebook_id, new_title)
    return f"Renamed to '{nb.title}'  |  ID: {nb.id}"


@mcp.tool
async def get_notebook_info(notebook_id: str) -> str:
    """Get the AI-generated description and suggested topics for a notebook."""
    client = await _get_client()
    desc = await client.notebooks.get_description(notebook_id)
    topics = (
        "\n".join(f"  - {t.title}" for t in desc.suggested_topics)
        if desc.suggested_topics
        else "  (none)"
    )
    return f"Summary:\n{desc.summary}\n\nSuggested Topics:\n{topics}"


# ── Sources ────────────────────────────────────────────────────────────────

@mcp.tool
async def list_sources(notebook_id: str) -> str:
    """List all sources in a notebook with their IDs, types, and readiness."""
    client = await _get_client()
    sources = await client.sources.list(notebook_id)
    if not sources:
        return "No sources in this notebook."
    lines = []
    for src in sources:
        status = "ready" if src.is_ready else ("processing" if src.is_processing else "unknown")
        title = getattr(src, "title", "N/A")
        lines.append(f"ID: {src.id}  |  Type: {src.kind}  |  Status: {status}  |  Title: {title}")
    return "\n".join(lines)


@mcp.tool
async def add_url_source(notebook_id: str, url: str) -> str:
    """Add a web URL or YouTube video as a source to a notebook. Waits until the source is ready."""
    client = await _get_client()
    source = await client.sources.add_url(notebook_id, url, wait=True)
    return f"Added source  |  ID: {source.id}  |  Type: {source.kind}"


@mcp.tool
async def add_text_source(notebook_id: str, text: str, title: str) -> str:
    """Add raw text content as a named source to a notebook."""
    client = await _get_client()
    source = await client.sources.add_text(notebook_id, text, title)
    return f"Added text source '{title}'  |  ID: {source.id}"


@mcp.tool
async def add_file_source(notebook_id: str, file_path: str) -> str:
    """Add a local file (PDF, audio, or video) as a source. Waits until ready."""
    client = await _get_client()
    source = await client.sources.add_file(notebook_id, file_path)
    await client.sources.wait_until_ready(notebook_id, source.id)
    return f"Added file source from '{file_path}'  |  ID: {source.id}"


@mcp.tool
async def delete_source(notebook_id: str, source_id: str) -> str:
    """Delete a source from a notebook."""
    client = await _get_client()
    success = await client.sources.delete(notebook_id, source_id)
    return "Source deleted." if success else "Failed to delete source."


@mcp.tool
async def get_source_fulltext(notebook_id: str, source_id: str) -> str:
    """Retrieve the full extracted text of a source."""
    client = await _get_client()
    ft = await client.sources.get_fulltext(notebook_id, source_id)
    return ft.text if hasattr(ft, "text") else str(ft)


# ── Chat ───────────────────────────────────────────────────────────────────

@mcp.tool
async def ask_notebook(
    notebook_id: str,
    question: str,
    conversation_id: Optional[str] = None,
) -> str:
    """Ask a question against a NotebookLM notebook.
    Pass conversation_id (from a prior answer) to continue the same conversation thread.
    Returns the answer, the conversation_id for follow-ups, and cited source IDs."""
    client = await _get_client()
    result = await client.chat.ask(notebook_id, question, conversation_id=conversation_id)
    refs = ""
    if result.references:
        ref_list = "\n".join(f"  - Source {r.source_id}" for r in result.references[:8])
        refs = f"\n\nReferenced Sources:\n{ref_list}"
    return f"Answer:\n{result.answer}\n\nConversation ID: {result.conversation_id}{refs}"


@mcp.tool
async def get_chat_history(notebook_id: str) -> str:
    """Get the full question-and-answer history for a notebook's most recent conversation."""
    client = await _get_client()
    history = await client.chat.get_history(notebook_id)
    if not history:
        return "No chat history found."
    lines = []
    for i, (q, a) in enumerate(history, 1):
        lines.append(f"Q{i}: {q}\nA{i}: {a}")
    return "\n\n".join(lines)


# ── Artifacts ──────────────────────────────────────────────────────────────

@mcp.tool
async def generate_artifact(notebook_id: str, artifact_type: str) -> str:
    """Generate a NotebookLM artifact. artifact_type must be one of:
    AUDIO, VIDEO, QUIZ, FLASHCARDS, SLIDE_DECK, INFOGRAPHIC, MIND_MAP, DATA_TABLE, REPORT.
    Waits for completion."""
    from notebooklm.types import ArtifactType  # type: ignore

    try:
        kind = ArtifactType[artifact_type.upper()]
    except KeyError:
        valid = ", ".join(t.name for t in ArtifactType)
        return f"Unknown artifact type '{artifact_type}'. Valid types: {valid}"

    client = await _get_client()
    artifact = await client.artifacts.generate(notebook_id, kind, wait=True)

    if artifact.is_completed:
        return f"Artifact generated.  |  ID: {artifact.id}  |  Type: {artifact_type}"
    elif artifact.is_rate_limited:
        return "Rate limited by NotebookLM. Try again later."
    else:
        return f"Generation incomplete.  |  Status: {artifact.status}"


if __name__ == "__main__":
    mcp.run()
