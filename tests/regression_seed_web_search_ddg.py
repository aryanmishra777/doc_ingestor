"""DuckDuckGo web-search provider checks: explicit selection, alias, and auto fallback."""
from __future__ import annotations

import os
from urllib.parse import urlparse

from regression_util import Checker, FakeResponse

import seeds

START_URL = "https://docs.python.org/3/"
REFERENCE_URL = "https://docs.python.org/3/reference/"
LIBRARY_URL = "https://docs.python.org/3/library/"
OFF_DOMAIN_URL = "https://example.com/off-domain"
DDG_ENDPOINT = "html.duckduckgo.com/html"

DDG_HTML = """
<html><body>
<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.python.org%2F3%2Freference%2F&amp;rut=abc">Reference</a>
<a class="result__a" href="https://docs.python.org/3/library/">Library</a>
<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Foff-domain&amp;rut=def">Off domain</a>
<a href="https://duckduckgo.com/about">internal</a>
</body></html>
"""

c = Checker("DuckDuckGo seed web search")

original_urlopen = seeds.urlopen
original_env = os.environ.copy()

try:
    calls: list[str] = []

    def fake_urlopen(request, timeout: float = 0):  # type: ignore[no-untyped-def]
        calls.append(request.full_url)
        if DDG_ENDPOINT in request.full_url:
            return FakeResponse(DDG_HTML)
        raise AssertionError(f"Unexpected URL: {request.full_url}")

    seeds.urlopen = fake_urlopen

    os.environ.clear()
    os.environ.update(original_env)
    for key in ("TINYFISH_API_KEY", "SEARXNG_BASE_URL", "BRAVE_SEARCH_API_KEY", "TAVILY_API_KEY"):
        os.environ.pop(key, None)
    os.environ["DOC_INGESTOR_WEB_SEARCH_PROVIDER"] = "duckduckgo"

    ddg_urls, ddg_native = seeds._llm_optional_web_search(
        use_web_search=True,
        llm_provider="local",
        api_key="",
        start_url=START_URL,
        start_parsed=urlparse(START_URL),
        max_candidates=5,
    )

    c.check("explicit provider called ddg endpoint", any(DDG_ENDPOINT in url for url in calls), str(calls))
    c.check("ddg search did not request native ollama web_search", not ddg_native)
    c.check("decoded uddg redirect target", REFERENCE_URL in ddg_urls, str(ddg_urls))
    c.check("kept direct same-domain link", LIBRARY_URL in ddg_urls, str(ddg_urls))
    c.check("filtered off-domain result", OFF_DOMAIN_URL not in ddg_urls, str(ddg_urls))

    os.environ["DOC_INGESTOR_WEB_SEARCH_PROVIDER"] = "ddg"
    c.check("short alias resolves to duckduckgo", seeds._resolve_external_web_search_provider() == "duckduckgo")

    calls.clear()
    os.environ["DOC_INGESTOR_WEB_SEARCH_PROVIDER"] = "auto"

    auto_urls, _ = seeds._llm_optional_web_search(
        use_web_search=True,
        llm_provider="local",
        api_key="",
        start_url=START_URL,
        start_parsed=urlparse(START_URL),
        max_candidates=5,
    )

    c.check("auto without keys falls back to ddg", any(DDG_ENDPOINT in url for url in calls), str(calls))
    c.check("auto fallback returned same-domain urls", REFERENCE_URL in auto_urls, str(auto_urls))
finally:
    seeds.urlopen = original_urlopen
    os.environ.clear()
    os.environ.update(original_env)

c.finish()
