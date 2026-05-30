"""Provider identity helpers shared by seed discovery and the adaptive agent.

Three providers are supported — Ollama ``cloud``, Ollama ``local``, and ``gemini``.
Before the refactor, ``_normalize_llm_provider`` and the "why is the LLM unavailable"
message were copy-pasted into both ``seeds`` and ``adaptive``. They live here once now.
"""
from __future__ import annotations

#: Fallback provider when an unknown/empty value is supplied.
DEFAULT_PROVIDER = "cloud"

#: The set of recognized provider identifiers.
VALID_PROVIDERS = frozenset({"cloud", "local", "gemini"})


def normalize_provider(provider: str) -> str:
    """Return ``provider`` if recognized, else :data:`DEFAULT_PROVIDER`."""
    return provider if provider in VALID_PROVIDERS else DEFAULT_PROVIDER


def llm_unavailable_reason(provider: str) -> str:
    """Return a human-readable explanation of why a provider can't be used.

    Used for diagnostics when the agent falls back to non-LLM behavior, so logs say
    *why* (missing key, no local server, missing package) rather than just "no LLM".
    """
    normalized = normalize_provider(provider)
    if normalized == "gemini":
        return "Gemini not available (missing GEMINI_API_KEY)"
    if normalized == "local":
        return "Ollama local server not available (start ollama or install ollama package)"
    return "Ollama cloud not available (missing OLLAMA_API_KEY or ollama package)"


__all__ = ["DEFAULT_PROVIDER", "VALID_PROVIDERS", "normalize_provider", "llm_unavailable_reason"]
