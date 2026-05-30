"""The unified LLM abstraction: an :class:`LLMClient` port plus a Strategy/Factory.

This is the clean surface new code should target. It hides the cloud/local/Gemini
differences behind one ``chat(model, system, user, use_web_search=...)`` method so
callers select a provider once (via :func:`create_llm_client`) and never branch again.

Design patterns: **Strategy** (each provider is an interchangeable implementation of the
:class:`LLMClient` protocol) selected by a **Factory** (:func:`create_llm_client`). The
existing ``seeds``/``adaptive`` call sites keep their own thin wrappers for behaviors the
test suite pins exactly; this facade is the forward-looking entry point and is used by
standalone scripts.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from llm import gemini, ollama
from llm.providers import llm_unavailable_reason, normalize_provider


@runtime_checkable
class LLMClient(Protocol):
    """A provider-agnostic chat client."""

    def chat(self, model: str, system: str, user: str, *, use_web_search: bool = False) -> str:
        """Return the model's text reply, or an empty string on failure."""
        ...


class _GeminiClient:
    """Strategy wrapping the Gemini REST adapter."""

    def chat(self, model: str, system: str, user: str, *, use_web_search: bool = False) -> str:
        return gemini.gemini_chat(model, system, user, use_web_search=use_web_search)


class _OllamaClient:
    """Strategy wrapping an Ollama (cloud or local) client handle."""

    def __init__(self, handle: Any, log: Callable[[str], None]) -> None:
        self._handle = handle
        self._log = log

    def chat(self, model: str, system: str, user: str, *, use_web_search: bool = False) -> str:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
        }
        if use_web_search:
            kwargs["options"] = {"web_search": True}
        return ollama.chat_with_timeout(self._handle, kwargs)


def create_llm_client(
    provider: str, *, log: Callable[[str], None] = lambda _msg: None
) -> LLMClient | None:
    """Build the right :class:`LLMClient` for ``provider``.

    Returns ``None`` when the provider is unusable (e.g. Ollama cloud without a key or
    package); ``log`` then receives :func:`llm_unavailable_reason`. Gemini availability
    is checked lazily at call time, so a Gemini client is always returned here.
    """
    normalized = normalize_provider(provider)
    if normalized == "gemini":
        return _GeminiClient()
    handle = ollama.make_client(normalized)
    if handle is None:
        log(llm_unavailable_reason(normalized))
        return None
    return _OllamaClient(handle, log)


__all__ = ["LLMClient", "create_llm_client"]
