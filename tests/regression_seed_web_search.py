"""Routing checks for seed web search: SearXNG, Ollama cloud, TinyFish, and auto."""
from __future__ import annotations

import json
import os
from urllib.parse import urlparse

from regression_util import Checker, FakeResponse

import seeds

START_URL = "https://docs.python.org/3/"
REFERENCE_URL = "https://docs.python.org/3/reference/"
LIBRARY_URL = "https://docs.python.org/3/library/"
TUTORIAL_URL = "https://docs.python.org/3/tutorial/"
OFF_DOMAIN_URL = "https://example.com/off-domain"
TINYFISH_ENDPOINT = "api.search.tinyfish.ai"

c = Checker("Seed web search routing")

original_urlopen = seeds.urlopen
original_env = os.environ.copy()

try:
    calls: list[str] = []

    def fake_urlopen(request, timeout: float = 0):  # type: ignore[no-untyped-def]
        url = request.full_url
        calls.append(url)
        if "format=json" in url:
            return FakeResponse(json.dumps({"results": [{"url": LIBRARY_URL}, {"url": OFF_DOMAIN_URL}]}))
        if TINYFISH_ENDPOINT in url:
            return FakeResponse(
                json.dumps(
                    {
                        "query": "docs",
                        "results": [
                            {"position": 1, "title": "Python docs", "snippet": "docs", "url": REFERENCE_URL},
                            {"position": 2, "title": "Off domain", "snippet": "ignore", "url": OFF_DOMAIN_URL},
                        ],
                        "total_results": 2,
                    }
                )
            )
        if "ollama.com/api/web_search" in url:
            return FakeResponse(json.dumps({"results": [{"url": REFERENCE_URL}, {"url": TUTORIAL_URL}]}))
        raise AssertionError(f"Unexpected URL: {url}")

    seeds.urlopen = fake_urlopen

    os.environ.clear()
    os.environ.update(original_env)
    os.environ["DOC_INGESTOR_WEB_SEARCH_PROVIDER"] = "searxng"
    os.environ["SEARXNG_BASE_URL"] = "http://localhost:8080"

    local_urls, local_native = seeds._llm_optional_web_search(
        use_web_search=True,
        llm_provider="local",
        api_key="",
        start_url=START_URL,
        start_parsed=urlparse(START_URL),
        max_candidates=5,
    )

    c.check("local search used external provider", any("localhost:8080/search" in url for url in calls), str(calls))
    c.check("local search did not request native ollama web_search", not local_native)
    c.check("local search kept same-domain result", LIBRARY_URL in local_urls, str(local_urls))
    c.check("local search filtered off-domain result", OFF_DOMAIN_URL not in local_urls, str(local_urls))

    calls.clear()
    os.environ["DOC_INGESTOR_WEB_SEARCH_PROVIDER"] = "ollama"

    cloud_urls, cloud_native = seeds._llm_optional_web_search(
        use_web_search=True,
        llm_provider="cloud",
        api_key="test-key",
        start_url=START_URL,
        start_parsed=urlparse(START_URL),
        max_candidates=5,
    )

    c.check("cloud search called ollama web_search endpoint", any("ollama.com/api/web_search" in url for url in calls), str(calls))
    c.check("cloud search marked native ollama web_search", cloud_native)
    c.check("cloud search returned same-domain urls", REFERENCE_URL in cloud_urls, str(cloud_urls))

    calls.clear()
    os.environ["DOC_INGESTOR_WEB_SEARCH_PROVIDER"] = "tinyfish"
    os.environ["TINYFISH_API_KEY"] = "tinyfish-key"

    tinyfish_urls, tinyfish_native = seeds._llm_optional_web_search(
        use_web_search=True,
        llm_provider="local",
        api_key="",
        start_url=START_URL,
        start_parsed=urlparse(START_URL),
        max_candidates=5,
    )

    c.check("tinyfish search called tinyfish endpoint", any(TINYFISH_ENDPOINT in url for url in calls), str(calls))
    c.check("tinyfish search did not request native ollama web_search", not tinyfish_native)
    c.check("tinyfish search returned same-domain urls", REFERENCE_URL in tinyfish_urls, str(tinyfish_urls))

    calls.clear()
    os.environ["DOC_INGESTOR_WEB_SEARCH_PROVIDER"] = "auto"

    auto_urls, auto_native = seeds._llm_optional_web_search(
        use_web_search=True,
        llm_provider="local",
        api_key="",
        start_url=START_URL,
        start_parsed=urlparse(START_URL),
        max_candidates=5,
    )

    c.check("auto search preferred tinyfish when key present", any(TINYFISH_ENDPOINT in url for url in calls), str(calls))
    c.check("auto search did not request native ollama web_search", not auto_native)
    c.check("auto search returned same-domain urls", REFERENCE_URL in auto_urls, str(auto_urls))
finally:
    seeds.urlopen = original_urlopen
    os.environ.clear()
    os.environ.update(original_env)

c.finish()
