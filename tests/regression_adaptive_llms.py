"""Adaptive llms.txt source selection: richer-source upgrade and anchor handling."""
from __future__ import annotations

from regression_util import Checker, repeated_words

import adaptive
from adaptive import AgentState, CrawlerPhase, DetectionResult, DetectionType

c = Checker("Adaptive llms.txt source selection")

root_content = f"""
# Example Docs

{repeated_words("overview", 350)}

## Documentation

- [Full Documentation](https://example.com/docs/llms-full.txt): Complete docs.
"""

full_content = f"""
# Full Example Docs

## Getting Started

{repeated_words("start", 420)}

## API Reference

{repeated_words("api", 420)}
"""

calls: list[str] = []
original_http_get = adaptive._http_get


def fake_http_get(url: str, read_limit: int = 65536, timeout: float = adaptive.PROBE_TIMEOUT):
    calls.append(url)
    if url == "https://example.com/docs/llms-full.txt":
        return {"status": 200, "content_type": "text/plain", "headers": {}, "body": full_content}
    return None


try:
    adaptive._http_get = fake_http_get
    logs: list[str] = []
    state = AgentState(
        target_url="https://example.com",
        detection=DetectionResult(
            type=DetectionType.LLMS_TXT,
            url="https://example.com/llms.txt",
            prefetched_content=root_content,
        ),
    )

    adaptive._handle_fetch_llms_txt(state, logs.append)

    c.check("fetched nested llms-full.txt", calls == ["https://example.com/docs/llms-full.txt"], str(calls))
    c.check("updated detection URL to richer source", state.detection.url == "https://example.com/docs/llms-full.txt")
    c.check("parsed records from richer source", [r["title"] for r in state.doc_records] == ["Getting Started", "API Reference"])
    c.check("advanced to quality evaluation", state.phase == CrawlerPhase.EVALUATE_QUALITY)
    c.check("logged richer source selection", any("using richer llms-full source" in msg for msg in logs))
finally:
    adaptive._http_get = original_http_get


anchor_content = f"""
# Full Docs

## New Features

{repeated_words("feature", 420)}

[New Features](https://reactflow.dev/llms-full.txt#new-features)
[Do sound to it](https://reactflow.dev/llms-full.txt#do-sound-to-it)

## API

{repeated_words("api", 420)}
"""

anchor_calls: list[str] = []


def fake_anchor_http_get(url: str, read_limit: int = 65536, timeout: float = adaptive.PROBE_TIMEOUT):
    anchor_calls.append(url)
    if url == "https://reactflow.dev/llms-full.txt":
        return {"status": 200, "content_type": "text/plain", "headers": {}, "body": anchor_content}
    return None


try:
    adaptive._http_get = fake_anchor_http_get
    anchor_logs: list[str] = []
    state = AgentState(
        target_url="https://reactflow.dev",
        detection=DetectionResult(
            type=DetectionType.LLMS_TXT,
            url="https://reactflow.dev/llms-full.txt",
            prefetched_content=anchor_content,
        ),
    )

    adaptive._handle_fetch_llms_txt(state, anchor_logs.append)

    c.check("refetched full llms source once", anchor_calls == ["https://reactflow.dev/llms-full.txt"], str(anchor_calls))
    c.check("ignored same-file llms-full anchors", not any("#" in url for url in anchor_calls), str(anchor_calls))
    c.check("did not log anchors as richer sources", not any("discovered richer llms-full source" in msg for msg in anchor_logs))
    c.check("kept current llms-full URL", state.detection.url == "https://reactflow.dev/llms-full.txt")
finally:
    adaptive._http_get = original_http_get

c.finish()
