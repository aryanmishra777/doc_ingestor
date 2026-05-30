"""
Smoke tests for the --include-sparse / include_sparse_pages feature.
Run with: python test_include_sparse.py
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from extraction import extract_from_html
from pipeline import (
    _is_navigation_only_record,
    _process_raw_record,
    collect_records,
    run_pipeline,
    run_pipeline_result,
)


PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, condition, detail))
    status = PASS if condition else FAIL
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


# ---------------------------------------------------------------------------
# HTML fixtures
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Section 1: Import smoke test
# ---------------------------------------------------------------------------
print("\n=== Section 1: Imports ===")
try:
    from pipeline import run_pipeline, run_pipeline_result, collect_records  # noqa: F811
    check("pipeline imports cleanly", True)
except Exception as exc:
    check("pipeline imports cleanly", False, str(exc))

try:
    from cli import collect_records_for_seeds, write_outputs_per_seed, _collect_seed_records
    check("cli imports cleanly", True)
except Exception as exc:
    check("cli imports cleanly", False, str(exc))


# ---------------------------------------------------------------------------
# Section 2: extract_from_html baseline
# ---------------------------------------------------------------------------
print("\n=== Section 2: extract_from_html baselines ===")

rich = extract_from_html(RICH_HTML, url="https://example.com/docs/col")
check("rich page has content_blocks", bool(rich["content_blocks"]))
check("rich page has code_blocks", bool(rich["code_blocks"]))
check("rich page not navigation-only", not _is_navigation_only_record(rich))

nav_no_text = extract_from_html(NAV_ONLY_NO_TEXT_HTML, url="https://example.com/docs/nav")
check("nav-no-text page has links", bool(nav_no_text["links"]))

nav_links = extract_from_html(NAV_LINKS_WITH_TEXT_HTML, url="https://example.com/docs/navlinks")
check("nav-with-text page: sparse_link_items populated -> has content_blocks",
      bool(nav_links["content_blocks"]),
      f"blocks={len(nav_links['content_blocks'])}")

sparse = extract_from_html(SPARSE_HTML, url="https://example.com/docs/sparse")
check("sparse page has content_blocks", bool(sparse["content_blocks"]))


# ---------------------------------------------------------------------------
# Section 3: _is_navigation_only_record
# ---------------------------------------------------------------------------
print("\n=== Section 3: _is_navigation_only_record ===")

check("rich record ->not navigation-only", not _is_navigation_only_record(rich))
check("sparse record ->not navigation-only", not _is_navigation_only_record(sparse))

# Craft a synthetic navigation-only record (no content, no code, has links, no errors)
nav_only_record: dict = {
    "url": "https://example.com/nav",
    "content_blocks": [],
    "code_blocks": [],
    "links": ["https://example.com/docs/a", "https://example.com/docs/b"],
    "errors": [],
}
check("synthetic nav-only record ->is navigation-only", _is_navigation_only_record(nav_only_record))

# Same but with content_blocks ->not navigation-only
not_nav: dict = {**nav_only_record, "content_blocks": [{"type": "paragraph", "text": "hi"}]}
check("record with content_blocks ->not navigation-only", not _is_navigation_only_record(not_nav))

# Errors set ->not navigation-only
with_errors: dict = {**nav_only_record, "errors": ["something failed"]}
check("record with errors ->not navigation-only", not _is_navigation_only_record(with_errors))


# ---------------------------------------------------------------------------
# Section 4: _process_raw_record — default mode skips nav-only
# ---------------------------------------------------------------------------
print("\n=== Section 4: _process_raw_record — default (skip nav-only) ===")

logs: list[str] = []
records: list = []
seen_canonical: set = set()
seen_hashes: set = set()

accepted, _, _ = _process_raw_record(
    nav_only_record, "https://example.com/nav",
    logs.append, records, seen_canonical, seen_hashes, 0, 0,
    include_sparse_pages=False,
)
check("default mode: nav-only record is rejected", not accepted)
check("default mode: rejection logged", any("discovery, not output" in m for m in logs))
check("default mode: records list unchanged", len(records) == 0)

logs.clear()
accepted, _, _ = _process_raw_record(
    rich, "https://example.com/docs/col",
    logs.append, records, seen_canonical, seen_hashes, 0, 0,
    include_sparse_pages=False,
)
check("default mode: rich record is accepted", accepted)
check("default mode: rich record appended", len(records) == 1)


# ---------------------------------------------------------------------------
# Section 5: _process_raw_record — include_sparse_pages=True
# ---------------------------------------------------------------------------
print("\n=== Section 5: _process_raw_record — include_sparse_pages=True ===")

logs2: list[str] = []
records2: list = []
seen_canonical2: set = set()
seen_hashes2: set = set()

accepted2, _, _ = _process_raw_record(
    nav_only_record, "https://example.com/nav",
    logs2.append, records2, seen_canonical2, seen_hashes2, 0, 0,
    include_sparse_pages=True,
)
check("include_sparse mode: nav-only record is accepted", accepted2)
check("include_sparse mode: acceptance logged", any("--include-sparse" in m for m in logs2))
check("include_sparse mode: record appended", len(records2) == 1)

# Rich page still accepted in sparse mode
logs2.clear()
accepted3, _, _ = _process_raw_record(
    rich, "https://example.com/docs/col",
    logs2.append, records2, seen_canonical2, seen_hashes2, 0, 0,
    include_sparse_pages=True,
)
check("include_sparse mode: rich record still accepted", accepted3)
check("include_sparse mode: records now has 2", len(records2) == 2)


# ---------------------------------------------------------------------------
# Section 6: Function signatures accept include_sparse_pages
# ---------------------------------------------------------------------------
print("\n=== Section 6: Signature compatibility ===")

import inspect

for fn_name, fn in [
    ("run_pipeline", run_pipeline),
    ("run_pipeline_result", run_pipeline_result),
    ("collect_records", collect_records),
]:
    params = inspect.signature(fn).parameters
    check(f"{fn_name} has include_sparse_pages param", "include_sparse_pages" in params)

from cli import collect_records_for_seeds, write_outputs_per_seed, _collect_seed_records
for fn_name, fn in [
    ("collect_records_for_seeds", collect_records_for_seeds),
    ("write_outputs_per_seed", write_outputs_per_seed),
    ("_collect_seed_records", _collect_seed_records),
]:
    params = inspect.signature(fn).parameters
    check(f"{fn_name} has include_sparse_pages param", "include_sparse_pages" in params)


# ---------------------------------------------------------------------------
# Section 7: CLI --help includes the flag
# ---------------------------------------------------------------------------
print("\n=== Section 7: CLI --help ===")
import subprocess
import sys as _sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
result = subprocess.run(
    [_sys.executable, "-m", "doc_ingestor.cli", "--help"],
    capture_output=True,
    text=True,
    cwd=str(PROJECT_ROOT),
)
if result.returncode != 0:
    result = subprocess.run(
        [_sys.executable, "cli.py", "--help"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
check("--help exits 0", result.returncode == 0, f"rc={result.returncode}")
check("--include-sparse appears in --help", "--include-sparse" in result.stdout, result.stdout[:300] if "--include-sparse" not in result.stdout else "")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n=== Summary ===")
passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
failed_tests = [(n, d) for n, ok, d in results if not ok]
print(f"  {passed}/{total} tests passed")
if failed_tests:
    print("\nFailed:")
    for name, detail in failed_tests:
        print(f"  - {name}" + (f": {detail}" if detail else ""))
    sys.exit(1)
else:
    print("  All tests passed.")
