"""Centralized configuration: constants plus *live* environment accessors.

Why functions instead of a cached settings object? Several call paths (and their
tests) mutate ``os.environ`` at runtime and expect the very next call to observe the
change — e.g. switching ``DOC_INGESTOR_WEB_SEARCH_PROVIDER`` between requests. So the
accessors here read ``os.environ`` *on every call*; nothing is snapshotted at import
time. The :class:`Settings` dataclass is an optional immutable snapshot for the few
places (startup logging) that genuinely want a frozen view.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# --- Provider endpoints / identity -----------------------------------------------
LOCAL_OLLAMA_HOST = "http://localhost:11434"
GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

# --- Default model names per provider (shared by seed discovery and adaptive) -----
DEFAULT_CLOUD_MODEL = "gemma4:31b-cloud"
DEFAULT_LOCAL_MODEL = "gemma4:latest"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash-lite"

# --- Timeouts --------------------------------------------------------------------
DEFAULT_LLM_TIMEOUT_SECONDS = 90.0
MIN_LLM_TIMEOUT_SECONDS = 5.0

#: Default web-search routing when ``DOC_INGESTOR_WEB_SEARCH_PROVIDER`` is unset.
DEFAULT_WEB_SEARCH_PROVIDER = "auto"


def ollama_api_key() -> str:
    """Return the (stripped) Ollama cloud API key, or ``""`` if unset."""
    return os.environ.get("OLLAMA_API_KEY", "").strip()


def gemini_api_key() -> str:
    """Return the (stripped) Gemini API key, or ``""`` if unset."""
    return os.environ.get("GEMINI_API_KEY", "").strip()


def ollama_host() -> str:
    """Return the local Ollama host, honoring an ``OLLAMA_HOST`` override."""
    return os.environ.get("OLLAMA_HOST", LOCAL_OLLAMA_HOST)


def web_search_provider() -> str:
    """Return the requested web-search provider, lower-cased (``auto`` by default)."""
    return (
        os.environ.get("DOC_INGESTOR_WEB_SEARCH_PROVIDER") or DEFAULT_WEB_SEARCH_PROVIDER
    ).strip().lower()


def llm_timeout_seconds() -> float:
    """Resolve the LLM call timeout from the environment.

    Reads ``DOC_INGESTOR_LLM_TIMEOUT_SECONDS``; falls back to
    :data:`DEFAULT_LLM_TIMEOUT_SECONDS` when unset or unparseable, and clamps to a
    sane floor of :data:`MIN_LLM_TIMEOUT_SECONDS`.
    """
    raw = os.environ.get("DOC_INGESTOR_LLM_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_LLM_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_LLM_TIMEOUT_SECONDS
    return max(MIN_LLM_TIMEOUT_SECONDS, value)


@dataclass(frozen=True)
class Settings:
    """An immutable snapshot of environment-derived configuration.

    Useful for startup diagnostics that want a stable view of "what was configured".
    Build one with :meth:`from_env`; for anything that must react to live env changes,
    call the module-level accessor functions instead.
    """

    ollama_api_key: str
    gemini_api_key: str
    ollama_host: str
    web_search_provider: str
    llm_timeout_seconds: float

    @classmethod
    def from_env(cls) -> "Settings":
        """Snapshot the current environment into an immutable ``Settings``."""
        return cls(
            ollama_api_key=ollama_api_key(),
            gemini_api_key=gemini_api_key(),
            ollama_host=ollama_host(),
            web_search_provider=web_search_provider(),
            llm_timeout_seconds=llm_timeout_seconds(),
        )


__all__ = [
    "LOCAL_OLLAMA_HOST",
    "GEMINI_API_BASE_URL",
    "DEFAULT_CLOUD_MODEL",
    "DEFAULT_LOCAL_MODEL",
    "DEFAULT_GEMINI_MODEL",
    "DEFAULT_LLM_TIMEOUT_SECONDS",
    "MIN_LLM_TIMEOUT_SECONDS",
    "DEFAULT_WEB_SEARCH_PROVIDER",
    "ollama_api_key",
    "gemini_api_key",
    "ollama_host",
    "web_search_provider",
    "llm_timeout_seconds",
    "Settings",
]
