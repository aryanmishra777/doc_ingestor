"""Ollama chat adapter: client construction and the two chat-call strategies.

Covers both Ollama transports — ``local`` (a running ``ollama serve``) and ``cloud``
(``https://ollama.com`` with a bearer token). The ``ollama`` package is imported lazily
so the project runs fine without it installed when LLM features are unused.

Two call strategies are preserved from the original code because they were tested
separately:

* :func:`chat` — a direct, best-effort call used by the adaptive agent.
* :func:`chat_with_timeout` — runs the call on a worker thread with a hard timeout so a
  hung provider can't stall seed discovery; falls back to ``""`` and a stderr note.
"""
from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any

from config import llm_timeout_seconds, ollama_api_key, ollama_host
from llm.providers import normalize_provider
from llm.responses import extract_content, extract_message_content


def make_client(provider: str) -> Any | None:
    """Construct an Ollama client for ``provider``, or ``None`` if unavailable.

    Mirrors the historical ``_make_llm_client``: ``gemini`` returns a sentinel object
    (the Gemini path doesn't use an Ollama client), ``cloud`` without an API key returns
    ``None``, and any import/construction error degrades to ``None`` so callers fall back
    to heuristics rather than crashing.
    """
    normalized = normalize_provider(provider)
    api_key = ollama_api_key()
    if normalized == "gemini":
        return object()
    if normalized == "cloud" and not api_key:
        return None
    try:
        ollama_module = importlib.import_module("ollama")
        client_cls = getattr(ollama_module, "Client", None)
        if client_cls is None:
            return None
        if normalized == "local":
            return client_cls(host=ollama_host())
        return client_cls(
            host="https://ollama.com",
            headers={"Authorization": f"Bearer {api_key}"},
        )
    except Exception:
        return None


def chat(client: Any, model: str, system: str, user: str, log: Callable[[str], None]) -> str:
    """Best-effort single chat turn; returns ``""`` (and logs) on failure."""
    try:
        response = client.chat(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            stream=False,
        )
        return extract_content(response)
    except Exception as exc:
        log(f"Adaptive: LLM call failed: {exc}")
        return ""


def chat_with_timeout(client: Any, kwargs: dict[str, Any]) -> str:
    """Run ``client.chat(**kwargs)`` with a hard wall-clock timeout.

    A slow/hung provider must not block seed discovery indefinitely, so the call runs on
    a single worker thread bounded by :func:`config.llm_timeout_seconds`. On timeout it
    prints a one-line stderr note and returns ``""`` so the caller falls back to
    heuristic seeds.
    """
    timeout_seconds = llm_timeout_seconds()
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(client.chat, **kwargs)
        try:
            response = future.result(timeout=timeout_seconds)
        except FutureTimeoutError:
            future.cancel()
            print(
                f"Seed discovery: LLM call timed out after {int(timeout_seconds)}s; "
                "falling back to heuristic seeds.",
                file=sys.stderr,
            )
            return ""
        except Exception:
            return ""
    return extract_message_content(response)


__all__ = ["make_client", "chat", "chat_with_timeout"]
