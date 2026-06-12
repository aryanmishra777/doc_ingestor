"""Sitemap path-prefix helpers and start-URL rewrite checks."""
from __future__ import annotations

from regression_util import Checker

import adaptive
from adaptive import AgentState, DetectionResult, DetectionType

c = Checker("Adaptive sitemap helpers")

c.check("file leaf stripped from prefix", adaptive._sitemap_start_prefix("/sitemap.xml") == "/")
c.check("nested file leaf strips to parent", adaptive._sitemap_start_prefix("/en/latest/index.html") == "/en/latest/")
c.check("directory paths unchanged", adaptive._sitemap_start_prefix("/docs/home/") == "/docs/")

c.check("recognizes /sitemap.xml as sitemap file URL", adaptive._is_sitemap_file_url("https://x.io/sitemap.xml"))
c.check("recognizes /sitemap_index.xml as sitemap file URL", adaptive._is_sitemap_file_url("https://x.io/sitemap_index.xml"))
c.check("rejects doc URLs as sitemap files", not adaptive._is_sitemap_file_url("https://x.io/docs/home/"))
c.check("rejects unrelated xml as sitemap files", not adaptive._is_sitemap_file_url("https://x.io/data/feed.xml"))

# When the start URL itself is a sitemap, the sitemap handler must rewrite
# target_url to a real doc page so any later crawler fallback can succeed.
ALLOY_SITEMAP_URL = "https://alloy.readthedocs.io/sitemap.xml"

single_url_sitemap = """<?xml version="1.0" encoding="utf-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://alloy.readthedocs.io/en/latest/</loc></url>
</urlset>
"""

original_http_get = adaptive._http_get

try:
    adaptive._http_get = lambda url, **_: None
    fetch_calls: list[str] = []
    original_fetch_url_list = adaptive._fetch_url_list
    adaptive._fetch_url_list = lambda urls, **_: (fetch_calls.extend(urls) or [])
    state = AgentState(
        target_url=ALLOY_SITEMAP_URL,
        detection=DetectionResult(
            type=DetectionType.SITEMAP,
            url=ALLOY_SITEMAP_URL,
            prefetched_content=single_url_sitemap,
        ),
    )
    logs2: list[str] = []
    adaptive._handle_fetch_sitemap(state, logs2.append)
finally:
    adaptive._http_get = original_http_get
    adaptive._fetch_url_list = original_fetch_url_list

c.check(
    "rewrote target_url away from sitemap file",
    state.target_url == "https://alloy.readthedocs.io/en/latest/",
    state.target_url,
)
c.check("logged the target rewrite", any("crawl entry point" in m for m in logs2))

c.finish()
