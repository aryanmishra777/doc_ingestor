"""Sitemap-as-start-URL and version-root handling checks."""
from __future__ import annotations

from regression_util import Checker

import adaptive
from adaptive import AgentState, CrawlerPhase, DetectionResult, DetectionType

c = Checker("Adaptive sitemap root handling")

original_http_get = adaptive._http_get

# Regression: when the user passes the sitemap URL itself as the start URL,
# the leaf "sitemap.xml" must not become a path-prefix that rejects every
# real URL inside the sitemap.
ALLOY_SITEMAP_URL = "https://alloy.readthedocs.io/sitemap.xml"

alloy_sitemap = """<?xml version="1.0" encoding="utf-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://alloy.readthedocs.io/en/latest/</loc></url>
</urlset>
"""

try:
    adaptive._http_get = lambda url, **_: None
    urls = adaptive._parse_sitemap_urls(
        ALLOY_SITEMAP_URL,
        ALLOY_SITEMAP_URL,
        initial_body=alloy_sitemap,
    )
finally:
    adaptive._http_get = original_http_get

c.check(
    "sitemap-as-start-url yields the listed URL",
    "https://alloy.readthedocs.io/en/latest/" in urls,
    str(urls),
)

PODMAN_LATEST_URL = "https://docs.podman.io/en/latest/"
PODMAN_STABLE_URL = "https://docs.podman.io/en/stable/"
PODMAN_V582_URL = "https://docs.podman.io/en/v5.8.2/"

multi_root_sitemap = """<?xml version="1.0" encoding="utf-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url><loc>{PODMAN_LATEST_URL}</loc></url>
    <url><loc>{PODMAN_STABLE_URL}</loc></url>
    <url><loc>{PODMAN_V582_URL}</loc></url>
</urlset>
""".format(
        PODMAN_LATEST_URL=PODMAN_LATEST_URL,
        PODMAN_STABLE_URL=PODMAN_STABLE_URL,
        PODMAN_V582_URL=PODMAN_V582_URL,
)

try:
    adaptive._http_get = lambda url, **_: None
    urls = adaptive._parse_sitemap_urls(
        "https://docs.podman.io/sitemap.xml",
        PODMAN_LATEST_URL,
        initial_body=multi_root_sitemap,
    )
finally:
    adaptive._http_get = original_http_get

c.check(
    "multi-root sitemap keeps all roots",
    urls == [
        PODMAN_LATEST_URL,
        PODMAN_STABLE_URL,
        PODMAN_V582_URL,
    ],
    str(urls),
)

podman_sitemap = """<?xml version="1.0" encoding="utf-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://docs.podman.io/en/latest/</loc></url>
</urlset>
"""

try:
    adaptive._http_get = lambda url, **_: None
    fetch_calls: list[str] = []
    original_fetch_url_list = adaptive._fetch_url_list
    adaptive._fetch_url_list = lambda urls, **kwargs: fetch_calls.extend(urls) or []
    state = AgentState(
        target_url=PODMAN_LATEST_URL,
        detection=DetectionResult(
            type=DetectionType.SITEMAP,
            url="https://docs.podman.io/sitemap.xml",
            prefetched_content=podman_sitemap,
        ),
    )
    logs3: list[str] = []
    adaptive._handle_fetch_sitemap(state, logs3.append)
finally:
    adaptive._http_get = original_http_get
    adaptive._fetch_url_list = original_fetch_url_list

c.check("seed-only sitemap falls back to crawler", state.phase == CrawlerPhase.CRAWLER_FALLBACK)
c.check("seed-only sitemap clears detection", state.detection is None)
c.check("seed-only sitemap keeps crawl seeds", state.crawl_seed_urls == [PODMAN_LATEST_URL])
c.check("seed-only sitemap does not fetch directly", not fetch_calls)
c.check("logged seed-only sitemap fallback", any("seed page" in m for m in logs3))

c.finish()
