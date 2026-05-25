"""
Smoke tests for adaptive llms.txt source selection.
Run with: python test_adaptive_llms.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import adaptive
from adaptive import AgentState, CrawlerPhase, DetectionResult, DetectionType


PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, condition, detail))
    status = PASS if condition else FAIL
    print(f"  [{status}] {name}" + (f" - {detail}" if detail else ""))


def repeated_words(prefix: str, count: int) -> str:
    return " ".join(f"{prefix}{idx}" for idx in range(count))


print("\n=== Adaptive llms.txt source selection ===")

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

    check("fetched nested llms-full.txt", calls == ["https://example.com/docs/llms-full.txt"], str(calls))
    check("updated detection URL to richer source", state.detection.url == "https://example.com/docs/llms-full.txt")
    check("parsed records from richer source", [r["title"] for r in state.doc_records] == ["Getting Started", "API Reference"])
    check("advanced to quality evaluation", state.phase == CrawlerPhase.EVALUATE_QUALITY)
    check("logged richer source selection", any("using richer llms-full source" in msg for msg in logs))
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

    check("refetched full llms source once", anchor_calls == ["https://reactflow.dev/llms-full.txt"], str(anchor_calls))
    check("ignored same-file llms-full anchors", not any("#" in url for url in anchor_calls), str(anchor_calls))
    check("did not log anchors as richer sources", not any("discovered richer llms-full source" in msg for msg in anchor_logs))
    check("kept current llms-full URL", state.detection.url == "https://reactflow.dev/llms-full.txt")
finally:
    adaptive._http_get = original_http_get


page_bundle = """
# Zustand

Full documentation content.

<page path="/learn/getting-started/introduction" title="Introduction"><![CDATA[URL: https://zustand.docs.pmnd.rs/learn/getting-started/introduction
Description: How to use Zustand

# Introduction

Zustand has a comfy API based on hooks.

```ts
const useStore = create(() => ({ count: 0 }))
```
]]></page>
<page path="/reference/apis/create" title="create"><![CDATA[URL: https://zustand.docs.pmnd.rs/reference/apis/create

# create

Creates a React hook from a state creator.
]]></page>
"""

page_records = adaptive._parse_llms_full_content(page_bundle, "https://zustand.docs.pmnd.rs/llms-full.txt")
check("parsed llms page wrappers as separate records", len(page_records) == 2, str(len(page_records)))
check("used page titles from wrapper attrs", [r["title"] for r in page_records] == ["Introduction", "create"])
check("used embedded page URLs", page_records[0]["url"] == "https://zustand.docs.pmnd.rs/learn/getting-started/introduction")
check("removed raw page wrapper markup", "<page" not in page_records[0]["content_blocks"][0]["text"])
check("preserved page code blocks", bool(page_records[0]["code_blocks"]))


huge_section = f"""
# React Flow Documentation

Intro text for React Flow.

## Learn

Overview for learn.

### Quick Start

{repeated_words("quick", 420)}

### Computing Flows

{repeated_words("compute", 420)}

### Custom Nodes

{repeated_words("node", 420)}

### Edges

{repeated_words("edge", 420)}

### Layout

{repeated_words("layout", 420)}

### State

{repeated_words("state", 420)}

### Interaction

{repeated_words("interaction", 420)}

### Accessibility

{repeated_words("access", 420)}

### Testing

{repeated_words("test", 420)}

### Deployment

{repeated_words("deploy", 420)}

## API Reference

{repeated_words("api", 420)}
"""

heading_records = adaptive._parse_llms_full_content(huge_section, "https://reactflow.dev/llms-full.txt")
check("split huge markdown llms files at h3 headings", len(heading_records) >= 10, str(len(heading_records)))
check("included h3 sections as records", "Quick Start" in [r["title"] for r in heading_records])


failed = [name for name, ok, _ in results if not ok]
if failed:
    print(f"\n{len(failed)} failed: {', '.join(failed)}")
    raise SystemExit(1)

print(f"\nAll {len(results)} adaptive llms.txt checks passed.")
