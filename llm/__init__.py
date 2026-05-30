"""LLM layer: one home for every Large-Language-Model concern.

Collapses the provider logic that used to be duplicated across ``seeds`` and
``adaptive`` — provider normalization, Gemini REST calls, Ollama client construction,
response parsing, and timeouts. Two ways to use it:

* New/standalone code: ``from llm import create_llm_client`` and call ``.chat(...)``.
* The legacy ``seeds``/``adaptive`` modules: import the focused helpers
  (``gemini_chat``, ``ollama.chat_with_timeout``, ``normalize_provider`` …) and keep
  their thin, separately-tested wrappers.
"""
from __future__ import annotations

from llm import gemini, ollama, responses
from llm.base import LLMClient, create_llm_client
from llm.gemini import extract_gemini_content, gemini_chat
from llm.providers import (
    DEFAULT_PROVIDER,
    VALID_PROVIDERS,
    llm_unavailable_reason,
    normalize_provider,
)
from llm.responses import extract_content, extract_message_content

__all__ = [
    "LLMClient",
    "create_llm_client",
    "gemini_chat",
    "extract_gemini_content",
    "normalize_provider",
    "llm_unavailable_reason",
    "DEFAULT_PROVIDER",
    "VALID_PROVIDERS",
    "extract_content",
    "extract_message_content",
    "gemini",
    "ollama",
    "responses",
]
