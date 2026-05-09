"""
Claude AI MCP Server
Exposes Claude's capabilities as MCP tools for use by any MCP-compatible client —
coding editors (Cursor, VS Code + Copilot), other agents, or automated pipelines.

Requirements:
  pip install fastmcp anthropic

Usage:
  ANTHROPIC_API_KEY=sk-... python claude_server.py

The model defaults to claude-sonnet-4-6. Override with:
  CLAUDE_MODEL=claude-opus-4-7 python claude_server.py
"""

import os
from typing import Optional

import anthropic
from fastmcp import FastMCP

mcp = FastMCP("Claude AI")

_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set.")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def _call(system: str, user: str, max_tokens: int = 4096) -> str:
    client = _get_client()
    msg = client.messages.create(
        model=_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text


# ── General Q&A ────────────────────────────────────────────────────────────

@mcp.tool
def ask(question: str, context: Optional[str] = None) -> str:
    """Ask Claude any question. Provide optional context to ground the answer."""
    prompt = f"Context:\n{context}\n\nQuestion: {question}" if context else question
    return _call("You are a helpful, knowledgeable assistant.", prompt)


@mcp.tool
def explain(concept: str, detail_level: str = "medium") -> str:
    """Explain a concept at a chosen depth.
    detail_level: 'brief' (one paragraph), 'medium' (with examples), 'deep' (technical + edge cases)."""
    depth_map = {
        "brief":  "Give a one-paragraph, plain-language explanation.",
        "medium": "Give a clear explanation with concrete examples, suitable for a developer.",
        "deep":   "Give an in-depth technical explanation covering nuances and edge cases.",
    }
    system = f"You are a knowledgeable teacher. {depth_map.get(detail_level, depth_map['medium'])}"
    return _call(system, f"Explain: {concept}")


@mcp.tool
def summarize(text: str, style: str = "bullets") -> str:
    """Summarize text. style: 'bullets' (key-point list) or 'prose' (short paragraph)."""
    if style == "prose":
        system = "Summarize the following into one concise paragraph that preserves all key information."
    else:
        system = "Summarize the following as a tight bulleted list. Preserve every key point."
    return _call(system, text)


# ── Code tools ─────────────────────────────────────────────────────────────

@mcp.tool
def analyze_code(code: str, language: Optional[str] = None, question: Optional[str] = None) -> str:
    """Analyze code: explain what it does, find bugs, suggest improvements.
    Optionally specify language and a focused question."""
    lang = f" ({language})" if language else ""
    q = question or "Explain what this code does, identify any bugs, and suggest improvements."
    return _call(
        "You are an expert software engineer. Be precise and concise.",
        f"Code{lang}:\n```\n{code}\n```\n\n{q}",
    )


@mcp.tool
def write_code(description: str, language: Optional[str] = None) -> str:
    """Generate code from a plain-English description. Specify language or let Claude choose."""
    lang_hint = f"Write the solution in {language}." if language else "Choose the most appropriate language."
    return _call(
        "You are an expert programmer. Write clean, correct, idiomatic code. Include brief inline comments only where non-obvious.",
        f"{lang_hint}\n\nTask: {description}",
    )


@mcp.tool
def review_code(code: str, language: Optional[str] = None) -> str:
    """Perform a thorough code review covering correctness, style, security, and performance."""
    lang = f"Language: {language}.\n\n" if language else ""
    return _call(
        "You are a senior software engineer doing a code review. Be thorough, specific, and constructive. "
        "Structure your response as: Summary, Issues (with severity), Suggestions.",
        f"{lang}Review this code:\n```\n{code}\n```",
    )


@mcp.tool
def debug_code(code: str, error: str, language: Optional[str] = None) -> str:
    """Debug code given an error message or description of unexpected behavior.
    Returns root cause analysis and a corrected version."""
    lang = f"Language: {language}.\n\n" if language else ""
    return _call(
        "You are an expert debugger. Identify the root cause, explain it clearly, then provide the corrected code.",
        f"{lang}Code:\n```\n{code}\n```\n\nError / Issue:\n{error}",
    )


@mcp.tool
def refactor_code(code: str, goal: str, language: Optional[str] = None) -> str:
    """Refactor code toward a specific goal (e.g., 'improve readability', 'reduce duplication', 'add type hints')."""
    lang = f"Language: {language}.\n\n" if language else ""
    return _call(
        "You are a senior engineer. Refactor the code to meet the stated goal without changing external behavior. "
        "Return the refactored code followed by a brief explanation of what changed.",
        f"{lang}Goal: {goal}\n\nCode:\n```\n{code}\n```",
    )


@mcp.tool
def write_tests(code: str, framework: Optional[str] = None, language: Optional[str] = None) -> str:
    """Generate unit tests for the given code. Specify test framework (e.g., pytest, jest, unittest) if desired."""
    lang = f"Language: {language}. " if language else ""
    fw = f"Test framework: {framework}." if framework else "Choose the idiomatic test framework."
    return _call(
        "You are a QA engineer. Write thorough unit tests covering happy paths, edge cases, and error conditions.",
        f"{lang}{fw}\n\nCode to test:\n```\n{code}\n```",
    )


# ── Documentation ──────────────────────────────────────────────────────────

@mcp.tool
def document_code(code: str, style: str = "docstring", language: Optional[str] = None) -> str:
    """Add documentation to code. style: 'docstring' (inline docs) or 'readme' (external markdown)."""
    lang = f"Language: {language}.\n\n" if language else ""
    if style == "readme":
        system = "Write a clear, developer-friendly README section explaining this code's purpose, usage, and API."
    else:
        system = "Add clear, concise docstrings/comments to the code. Do not over-document obvious lines."
    return _call(system, f"{lang}Code:\n```\n{code}\n```")


if __name__ == "__main__":
    mcp.run()
