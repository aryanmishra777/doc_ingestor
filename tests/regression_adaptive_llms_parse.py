"""llms-full.txt content parsing: <page> wrappers and heading-based splitting."""
from __future__ import annotations

from regression_util import Checker, repeated_words

import adaptive

c = Checker("Adaptive llms.txt parsing")

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
c.check("parsed llms page wrappers as separate records", len(page_records) == 2, str(len(page_records)))
c.check("used page titles from wrapper attrs", [r["title"] for r in page_records] == ["Introduction", "create"])
c.check("used embedded page URLs", page_records[0]["url"] == "https://zustand.docs.pmnd.rs/learn/getting-started/introduction")
c.check("removed raw page wrapper markup", "<page" not in page_records[0]["content_blocks"][0]["text"])
c.check("preserved page code blocks", bool(page_records[0]["code_blocks"]))


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
c.check("split huge markdown llms files at h3 headings", len(heading_records) >= 10, str(len(heading_records)))
c.check("included h3 sections as records", "Quick Start" in [r["title"] for r in heading_records])

c.finish()
