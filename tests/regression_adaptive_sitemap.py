"""Adaptive sitemap traversal and low-quality self-correction fallback checks."""
from __future__ import annotations

from regression_util import Checker

import adaptive
from adaptive import AgentState, CrawlerPhase, DetectionResult, DetectionType

c = Checker("Adaptive sitemap traversal")

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

c.check("followed sitemap refs", "https://kubernetes.io/en/sitemap.xml" in calls, str(calls))
c.check("broadened docs home prefix to docs tree", "https://kubernetes.io/docs/concepts/overview/" in urls, str(urls))
c.check("kept docs URLs from same domain", "https://kubernetes.io/docs/tasks/tools/" in urls, str(urls))
c.check("filtered non-docs URLs for docs start page", "https://kubernetes.io/releases/1.36/" not in urls, str(urls))
c.check("filtered localized docs outside prefix", "https://kubernetes.io/fr/docs/home/" not in urls, str(urls))

logs: list[str] = []
state = AgentState(
    target_url="https://kubernetes.io/docs/home/",
    detection=DetectionResult(type=DetectionType.SITEMAP, url="https://kubernetes.io/sitemap.xml"),
    doc_records=[],
    eval_metrics={"structural": 1.0, "density": 0.12, "scope": 0.4, "passed": False},
)
adaptive._self_correct(state, logs.append)
c.check("low-quality sitemap falls back to crawler", state.phase == CrawlerPhase.CRAWLER_FALLBACK)
c.check("cleared sitemap detection before fallback", state.detection is None)
c.check("logged sitemap fallback", any("sitemap produced low-quality" in msg for msg in logs))

c.finish()
