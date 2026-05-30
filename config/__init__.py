"""Configuration layer: ``.env`` loading and live environment accessors.

Single source of truth for endpoints, default model names, timeouts, and secret/flag
lookups. Import the live accessors (``from config import gemini_api_key,
llm_timeout_seconds``) so behavior tracks ``os.environ`` changes at call time.
"""
from __future__ import annotations

from config.env import load_env_file
from config.settings import (
    DEFAULT_CLOUD_MODEL,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_LLM_TIMEOUT_SECONDS,
    DEFAULT_LOCAL_MODEL,
    DEFAULT_WEB_SEARCH_PROVIDER,
    GEMINI_API_BASE_URL,
    LOCAL_OLLAMA_HOST,
    MIN_LLM_TIMEOUT_SECONDS,
    Settings,
    gemini_api_key,
    llm_timeout_seconds,
    ollama_api_key,
    ollama_host,
    web_search_provider,
)

__all__ = [
    "load_env_file",
    "Settings",
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
]
