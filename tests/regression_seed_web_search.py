from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import seeds


PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, condition, detail))
    status = PASS if condition else FAIL
    print(f"  [{status}] {name}" + (f" - {detail}" if detail else ""))


class _FakeResponse:
    def __init__(self, body: str):
        self._body = body

    def read(self) -> bytes:
        return self._body.encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


print("\n=== Seed web search routing ===")

original_urlopen = seeds.urlopen
original_env = os.environ.copy()

try:
    calls: list[str] = []

    def fake_urlopen(request, timeout: float = 0):  # type: ignore[no-untyped-def]
        url = request.full_url
        calls.append(url)
        if "format=json" in url:
            return _FakeResponse(
                '{"results":[{"url":"https://docs.python.org/3/library/"},{"url":"https://example.com/off-domain"}]}'
            )
        if "ollama.com/api/web_search" in url:
            return _FakeResponse(
                '{"results":[{"url":"https://docs.python.org/3/reference/"},{"url":"https://docs.python.org/3/tutorial/"}]}'
            )
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
        start_url="https://docs.python.org/3/",
        start_parsed=urlparse("https://docs.python.org/3/"),
        max_candidates=5,
    )

    check("local search used external provider", any("localhost:8080/search" in url for url in calls), str(calls))
    check("local search did not request native ollama web_search", not local_native)
    check("local search kept same-domain result", "https://docs.python.org/3/library/" in local_urls, str(local_urls))
    check("local search filtered off-domain result", "https://example.com/off-domain" not in local_urls, str(local_urls))

    calls.clear()
    os.environ["DOC_INGESTOR_WEB_SEARCH_PROVIDER"] = "ollama"

    cloud_urls, cloud_native = seeds._llm_optional_web_search(
        use_web_search=True,
        llm_provider="cloud",
        api_key="test-key",
        start_url="https://docs.python.org/3/",
        start_parsed=urlparse("https://docs.python.org/3/"),
        max_candidates=5,
    )

    check("cloud search called ollama web_search endpoint", any("ollama.com/api/web_search" in url for url in calls), str(calls))
    check("cloud search marked native ollama web_search", cloud_native)
    check("cloud search returned same-domain urls", "https://docs.python.org/3/reference/" in cloud_urls, str(cloud_urls))
finally:
    seeds.urlopen = original_urlopen
    os.environ.clear()
    os.environ.update(original_env)


failed = [name for name, ok, _ in results if not ok]
if failed:
    print(f"\n{len(failed)} failed: {', '.join(failed)}")
    raise SystemExit(1)

print(f"\nAll {len(results)} seed web search checks passed.")
