"""Tool factories for the adaptive script-generation agent.

Read-only context tools plus act/observe tools: the agent can fetch a page to derive
selectors from real markup and dry-run a candidate script before submitting it, so a
selector mistake costs one tool call instead of one outer retry.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any


def script_generation_tools(
    state: Any,
    http_get: Callable[..., Any] | None = None,
    execute_script: Callable[[str], tuple[list[str], str, int]] | None = None,
) -> list[Callable[..., str]]:
    """Build LangChain tools that expose crawl context and actions to the script agent."""
    tools: list[Callable[..., str]] = [
        _script_output_schema_tool(),
        _detection_context_tool(state),
        _previous_attempt_tool(state),
    ]
    if http_get is not None:
        tools.append(_fetch_page_tool(http_get))
    if execute_script is not None:
        tools.append(_dry_run_script_tool(execute_script))
    return tools


def _fetch_page_tool(http_get: Callable[..., Any]) -> Callable[[str], str]:
    def fetch_page(url: str) -> str:
        """Fetch up to ~3KB of a URL's raw response body to inspect its real markup."""
        response = http_get(url, read_limit=8192)
        if not response:
            return f"fetch failed for {url}"
        body = (response.get("body") or "")[:3000]
        return f"status={response.get('status')}\ncontent_type={response.get('content_type')}\n{body}"

    return fetch_page


def _dry_run_script_tool(
    execute_script: Callable[[str], tuple[list[str], str, int]],
) -> Callable[[str], str]:
    def dry_run_script(code: str) -> str:
        """Execute a candidate fetch script and report its first JSONL lines, stderr tail, and exit code."""
        cleaned = re.sub(r"^```(?:python)?\n?", "", code.strip())
        cleaned = re.sub(r"\n?```$", "", cleaned.strip())
        lines, stderr, returncode = execute_script(cleaned)
        head = "\n".join(lines[:3])[:1500]
        return (
            f"returncode={returncode}\nstdout_lines={len(lines)}\n"
            f"first_lines:\n{head}\nstderr_tail:\n{stderr[-800:]}"
        )

    return dry_run_script


def _script_output_schema_tool() -> Callable[[], str]:
    def script_output_schema() -> str:
        """Describe the JSON Lines schema generated fetch scripts must emit."""
        return (
            "Print JSON Lines only. Each line must be a page object with url, "
            "title, content, and metadata containing at least framework and depth."
        )

    return script_output_schema


def _detection_context_tool(state: Any) -> Callable[[], str]:
    def detection_context() -> str:
        """Inspect the current adaptive detection result."""
        detection = state.detection
        detection_type = detection.type.value if detection else "none"
        detection_url = detection.url if detection else "n/a"
        framework = detection.framework if detection and detection.framework else "unknown"
        return (
            f"target_url={state.target_url}\n"
            f"detection_type={detection_type}\n"
            f"detection_url={detection_url}\n"
            f"framework={framework}"
        )

    return detection_context


def _previous_attempt_tool(state: Any) -> Callable[[], str]:
    def previous_attempt_context() -> str:
        """Inspect prior adaptive generation errors and stderr."""
        if not state.generation_context and not state.script_stderr:
            return "No previous attempt context."
        return "\n".join(part for part in (state.generation_context, state.script_stderr[-1000:]) if part)

    return previous_attempt_context
