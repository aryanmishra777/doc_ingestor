"""
Smoke tests for adaptive sitemap traversal.
Run with: python test_adaptive_sitemap.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import adaptive
from adaptive import AgentState, CrawlerPhase, DetectionResult, DetectionType


PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, condition, detail))
    status = PASS if condition else FAIL
    print(f"  [{status}] {name}" + (f" - {detail}" if detail else ""))


print("\n=== Adaptive sitemap traversal ===")

root_sitemap = """<?xml version="1.0" encoding="utf-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://kubernetes.io/en/sitemap.xml</loc></sitemap>
  <sitemap><loc>https://kubernetes.io/fr/sitemap.xml</loc></sitemap>
</sitemapindex>
"""

english_sitemap = """<?xml version="1.0" encoding="utf-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://kubernetes.io/docs/home/</loc></url>
  <url><loc>https://kubernetes.io/docs/concepts/overview/</loc></url>
  <url><loc>https://kubernetes.io/docs/tasks/tools/</loc></url>
  <url><loc>https://kubernetes.io/releases/1.36/</loc></url>
</urlset>
"""

french_sitemap = """<?xml version="1.0" encoding="utf-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://kubernetes.io/fr/docs/home/</loc></url>
</urlset>
"""

calls: list[str] = []
original_http_get = adaptive._http_get


def fake_http_get(url: str, read_limit: int = 65536, timeout: float = adaptive.PROBE_TIMEOUT):
    calls.append(url)
    body = {
        "https://kubernetes.io/en/sitemap.xml": english_sitemap,
        "https://kubernetes.io/fr/sitemap.xml": french_sitemap,
    }.get(url)
    if body is None:
        return None
    return {"status": 200, "content_type": "application/xml", "headers": {}, "body": body}


try:
    adaptive._http_get = fake_http_get
    urls = adaptive._parse_sitemap_urls(
        "https://kubernetes.io/sitemap.xml",
        "https://kubernetes.io/docs/home/",
        initial_body=root_sitemap,
    )
finally:
    adaptive._http_get = original_http_get

check("followed sitemap refs", "https://kubernetes.io/en/sitemap.xml" in calls, str(calls))
check("broadened docs home prefix to docs tree", "https://kubernetes.io/docs/concepts/overview/" in urls, str(urls))
check("kept docs URLs from same domain", "https://kubernetes.io/docs/tasks/tools/" in urls, str(urls))
check("filtered non-docs URLs for docs start page", "https://kubernetes.io/releases/1.36/" not in urls, str(urls))
check("filtered localized docs outside prefix", "https://kubernetes.io/fr/docs/home/" not in urls, str(urls))

logs: list[str] = []
state = AgentState(
    target_url="https://kubernetes.io/docs/home/",
    detection=DetectionResult(type=DetectionType.SITEMAP, url="https://kubernetes.io/sitemap.xml"),
    doc_records=[],
    eval_metrics={"structural": 1.0, "density": 0.12, "scope": 0.4, "passed": False},
)
adaptive._self_correct(state, logs.append)
check("low-quality sitemap falls back to crawler", state.phase == CrawlerPhase.CRAWLER_FALLBACK)
check("cleared sitemap detection before fallback", state.detection is None)
check("logged sitemap fallback", any("sitemap produced low-quality" in msg for msg in logs))


# Regression: when the user passes the sitemap URL itself as the start URL,
# the leaf "sitemap.xml" must not become a path-prefix that rejects every
# real URL inside the sitemap.
alloy_sitemap = """<?xml version="1.0" encoding="utf-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://alloy.readthedocs.io/en/latest/</loc></url>
</urlset>
"""

try:
    adaptive._http_get = lambda url, **_: None
    urls = adaptive._parse_sitemap_urls(
        "https://alloy.readthedocs.io/sitemap.xml",
        "https://alloy.readthedocs.io/sitemap.xml",
        initial_body=alloy_sitemap,
    )
finally:
    adaptive._http_get = original_http_get

check(
    "sitemap-as-start-url yields the listed URL",
    "https://alloy.readthedocs.io/en/latest/" in urls,
    str(urls),
)

check("file leaf stripped from prefix", adaptive._sitemap_start_prefix("/sitemap.xml") == "/")
check("nested file leaf strips to parent", adaptive._sitemap_start_prefix("/en/latest/index.html") == "/en/latest/")
check("directory paths unchanged", adaptive._sitemap_start_prefix("/docs/home/") == "/docs/")

check("recognizes /sitemap.xml as sitemap file URL", adaptive._is_sitemap_file_url("https://x.io/sitemap.xml"))
check("recognizes /sitemap_index.xml as sitemap file URL", adaptive._is_sitemap_file_url("https://x.io/sitemap_index.xml"))
check("rejects doc URLs as sitemap files", not adaptive._is_sitemap_file_url("https://x.io/docs/home/"))
check("rejects unrelated xml as sitemap files", not adaptive._is_sitemap_file_url("https://x.io/data/feed.xml"))

# When the start URL itself is a sitemap, the sitemap handler must rewrite
# target_url to a real doc page so any later crawler fallback can succeed.
single_url_sitemap = """<?xml version="1.0" encoding="utf-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://alloy.readthedocs.io/en/latest/</loc></url>
</urlset>
"""

try:
    adaptive._http_get = lambda url, **_: None
    fetch_calls: list[str] = []
    original_fetch_url_list = adaptive._fetch_url_list
    adaptive._fetch_url_list = lambda urls, **_: (fetch_calls.extend(urls) or [])
    state = AgentState(
        target_url="https://alloy.readthedocs.io/sitemap.xml",
        detection=DetectionResult(
            type=DetectionType.SITEMAP,
            url="https://alloy.readthedocs.io/sitemap.xml",
            prefetched_content=single_url_sitemap,
        ),
    )
    logs2: list[str] = []
    adaptive._handle_fetch_sitemap(state, logs2.append)
finally:
    adaptive._http_get = original_http_get
    adaptive._fetch_url_list = original_fetch_url_list

check(
    "rewrote target_url away from sitemap file",
    state.target_url == "https://alloy.readthedocs.io/en/latest/",
    state.target_url,
)
check("logged the target rewrite", any("crawl entry point" in m for m in logs2))


failed = [name for name, ok, _ in results if not ok]
if failed:
    print(f"\n{len(failed)} failed: {', '.join(failed)}")
    raise SystemExit(1)

print(f"\nAll {len(results)} adaptive sitemap checks passed.")
