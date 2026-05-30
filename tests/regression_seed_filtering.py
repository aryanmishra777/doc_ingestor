from __future__ import annotations

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


print("\n=== LLM seed filtering ===")

original_probe = seeds._is_live_doc_candidate

try:
    live_urls = {
        "https://example.com/docs/reference/",
        "https://example.com/docs/tutorial/",
    }

    def fake_probe(candidate: str, start_parsed):  # type: ignore[no-untyped-def]
        return candidate in live_urls

    seeds._is_live_doc_candidate = fake_probe
    selected = seeds._select_live_candidates(
        [
            "https://example.com/docs/reference/",
            "https://example.com/docs/not-real/",
            "https://example.com/docs/tutorial/",
        ],
        urlparse("https://example.com/docs/"),
        max_count=5,
        allow_unverified_fallback=False,
    )

    check("kept live LLM seeds", selected == ["https://example.com/docs/reference/", "https://example.com/docs/tutorial/"], str(selected))

    selected_none = seeds._select_live_candidates(
        ["https://example.com/docs/not-real/"],
        urlparse("https://example.com/docs/"),
        max_count=5,
        allow_unverified_fallback=False,
    )
    check("dropped unverified LLM seeds", selected_none == [], str(selected_none))
finally:
    seeds._is_live_doc_candidate = original_probe


failed = [name for name, ok, _ in results if not ok]
if failed:
    print(f"\n{len(failed)} failed: {', '.join(failed)}")
    raise SystemExit(1)

print(f"\nAll {len(results)} LLM seed filtering checks passed.")
