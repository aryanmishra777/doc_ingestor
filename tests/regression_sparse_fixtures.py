"""Shared HTML fixtures for the include-sparse regression scripts."""
from __future__ import annotations

# Page with real prose content — should never be navigation-only
RICH_HTML = """
<html><body>
<main>
  <h1>Column Rule Width</h1>
  <p>The column-rule-width CSS property sets the width of the rule drawn between columns in a multi-column layout.</p>
  <p>Possible values are thin, medium, thick, or a length value.</p>
  <pre><code class="language-css">column-rule-width: thin;
column-rule-width: 1em;
</code></pre>
  <a href="/docs/other">Other page</a>
</main>
</body></html>
"""

# Navigation-only page: only links, no prose, no anchor text on links
NAV_ONLY_NO_TEXT_HTML = """
<html><body>
<nav>
  <a href="/docs/a"></a>
  <a href="/docs/b"></a>
  <a href="/docs/c"></a>
</nav>
</body></html>
"""

# Sparse page with visible link text outside boilerplate — sparse_link_items populated
NAV_LINKS_WITH_TEXT_HTML = """
<html><body>
<div class="content">
  <a href="/docs/a">Page A</a>
  <a href="/docs/b">Page B</a>
</div>
</body></html>
"""

# Sparse page: a heading + one short sentence + links
SPARSE_HTML = """
<html><body>
<main>
  <h1>Overview</h1>
  <p>Short.</p>
  <a href="/docs/a">Child page</a>
</main>
</body></html>
"""


def nav_only_record() -> dict:
    """Fresh synthetic navigation-only record (no content, no code, links, no errors)."""
    return {
        "url": "https://example.com/nav",
        "content_blocks": [],
        "code_blocks": [],
        "links": ["https://example.com/docs/a", "https://example.com/docs/b"],
        "errors": [],
    }
