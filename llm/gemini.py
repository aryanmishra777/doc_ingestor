"""Google Gemini chat adapter (the ``generateContent`` REST endpoint).

Unifies the two previously-duplicated Gemini callers. The *only* behavioral difference
between them was a single toggle, now expressed as the ``use_web_search`` flag:

* seed discovery enabled Google Search *grounding* by sending
  ``tools: [{"google_search": {}}]``;
* the adaptive agent sent no ``tools`` key.

The request shape is otherwise byte-for-byte identical to the originals (the test suite
asserts the exact payload/headers), so this module must keep building them the same way.

``requests`` is imported at module scope and called as ``requests.post`` so that tests
which monkeypatch the shared ``requests`` module (via ``seeds.requests.post`` /
``adaptive.requests.post``) transparently intercept these calls.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import requests

from config import GEMINI_API_BASE_URL, gemini_api_key, llm_timeout_seconds


def gemini_chat(
    model: str,
    system: str,
    user: str,
    *,
    use_web_search: bool = False,
    log: Callable[[str], None] | None = None,
) -> str:
    """Call Gemini once and return its text, or ``""`` on any failure.

    Returns ``""`` immediately when ``GEMINI_API_KEY`` is unset. When ``use_web_search``
    is true, the Google Search grounding tool is attached. Errors are swallowed (and,
    if a ``log`` callback is provided, reported through it) to preserve the crawler's
    never-crash contract.
    """
    api_key = gemini_api_key()
    if not api_key:
        return ""

    payload: dict[str, Any] = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"parts": [{"text": user}]}],
    }
    if use_web_search:
        payload["tools"] = [{"google_search": {}}]

    try:
        response = requests.post(
            f"{GEMINI_API_BASE_URL}/models/{model}:generateContent",
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=llm_timeout_seconds(),
        )
        response.raise_for_status()
    except Exception as exc:
        if log is not None:
            log(f"Adaptive: Gemini call failed: {exc}")
        return ""

    return extract_gemini_content(response.json())


def extract_gemini_content(payload: Any) -> str:
    """Extract the first non-empty text span from a Gemini ``generateContent`` body.

    Walks ``candidates[].content.parts[].text``, defensively skipping any element of an
    unexpected type, and returns the first candidate that yields non-empty joined text.
    """
    if not isinstance(payload, dict):
        return ""
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        return ""
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        parts = content.get("parts")
        if not isinstance(parts, list):
            continue
        texts = [
            part.get("text", "")
            for part in parts
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ]
        joined = "".join(texts).strip()
        if joined:
            return joined
    return ""


__all__ = ["gemini_chat", "extract_gemini_content"]
