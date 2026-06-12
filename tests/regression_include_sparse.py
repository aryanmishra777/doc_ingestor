"""Include-sparse feature: imports, extraction baselines, and nav-only classification."""
from __future__ import annotations

from regression_sparse_fixtures import (
    NAV_LINKS_WITH_TEXT_HTML,
    NAV_ONLY_NO_TEXT_HTML,
    RICH_HTML,
    SPARSE_HTML,
    nav_only_record,
)
from regression_util import Checker

from extraction import extract_from_html
from pipeline import _is_navigation_only_record

c = Checker("Include-sparse extraction baselines")

# --- Section 1: import smoke test ---
try:
    from pipeline import run_pipeline, run_pipeline_result, collect_records  # noqa: F401
    c.check("pipeline imports cleanly", True)
except Exception as exc:
    c.check("pipeline imports cleanly", False, str(exc))

try:
    from cli import collect_records_for_seeds, write_outputs_per_seed, _collect_seed_records  # noqa: F401
    c.check("cli imports cleanly", True)
except Exception as exc:
    c.check("cli imports cleanly", False, str(exc))

# --- Section 2: extract_from_html baselines ---
rich = extract_from_html(RICH_HTML, url="https://example.com/docs/col")
c.check("rich page has content_blocks", bool(rich["content_blocks"]))
c.check("rich page has code_blocks", bool(rich["code_blocks"]))
c.check("rich page not navigation-only", not _is_navigation_only_record(rich))

nav_no_text = extract_from_html(NAV_ONLY_NO_TEXT_HTML, url="https://example.com/docs/nav")
c.check("nav-no-text page has links", bool(nav_no_text["links"]))

nav_links = extract_from_html(NAV_LINKS_WITH_TEXT_HTML, url="https://example.com/docs/navlinks")
c.check(
    "nav-with-text page: sparse_link_items populated -> has content_blocks",
    bool(nav_links["content_blocks"]),
    f"blocks={len(nav_links['content_blocks'])}",
)

sparse = extract_from_html(SPARSE_HTML, url="https://example.com/docs/sparse")
c.check("sparse page has content_blocks", bool(sparse["content_blocks"]))

# --- Section 3: _is_navigation_only_record ---
c.check("rich record ->not navigation-only", not _is_navigation_only_record(rich))
c.check("sparse record ->not navigation-only", not _is_navigation_only_record(sparse))

nav_record = nav_only_record()
c.check("synthetic nav-only record ->is navigation-only", _is_navigation_only_record(nav_record))

not_nav: dict = {**nav_record, "content_blocks": [{"type": "paragraph", "text": "hi"}]}
c.check("record with content_blocks ->not navigation-only", not _is_navigation_only_record(not_nav))

with_errors: dict = {**nav_record, "errors": ["something failed"]}
c.check("record with errors ->not navigation-only", not _is_navigation_only_record(with_errors))

c.finish()
