from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import adaptive
import seeds


PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, condition, detail))
    status = PASS if condition else FAIL
    print(f"  [{status}] {name}" + (f" - {detail}" if detail else ""))


class _FakeResponse:
    def __init__(self, payload: dict[str, object]):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


print("\n=== Gemini integration ===")

original_seed_post = seeds.requests.post
original_adaptive_post = adaptive.requests.post
original_env = os.environ.copy()

try:
    calls: list[dict[str, object]] = []

    def fake_post(url: str, headers: dict[str, str], json: dict[str, object], timeout: float):  # type: ignore[no-untyped-def]
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return _FakeResponse(
            {"candidates": [{"content": {"parts": [{"text": '["https://docs.python.org/3/library/"]'}]}}]}
        )

    seeds.requests.post = fake_post
    adaptive.requests.post = fake_post

    os.environ.clear()
    os.environ.update(original_env)
    os.environ["GEMINI_API_KEY"] = "test-key"

    seed_text = seeds._gemini_generate_text(
        model="gemini-2.5-flash-lite",
        system="sys",
        user="user",
        use_web_search=True,
    )
    check("seed gemini returned response text", seed_text == '["https://docs.python.org/3/library/"]', seed_text)
    check("seed gemini used grounding tool", bool(calls and calls[0]["json"].get("tools")), str(calls[0]["json"]))
    check("seed gemini used api key header", calls[0]["headers"].get("x-goog-api-key") == "test-key", str(calls[0]["headers"]))

    calls.clear()
    adaptive_text = adaptive._gemini_chat("gemini-2.5-flash-lite", "sys", "user", lambda _: None)
    check("adaptive gemini returned response text", adaptive_text == '["https://docs.python.org/3/library/"]', adaptive_text)
    check("adaptive gemini did not send grounding tool by default", "tools" not in calls[0]["json"], str(calls[0]["json"]))
finally:
    seeds.requests.post = original_seed_post
    adaptive.requests.post = original_adaptive_post
    os.environ.clear()
    os.environ.update(original_env)


failed = [name for name, ok, _ in results if not ok]
if failed:
    print(f"\n{len(failed)} failed: {', '.join(failed)}")
    raise SystemExit(1)

print(f"\nAll {len(results)} Gemini integration checks passed.")
