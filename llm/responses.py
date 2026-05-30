"""Parsers that pull plain text out of heterogeneous LLM response objects.

The Ollama client may return either a ``dict`` (when ``stream=False`` over HTTP) or a
rich response object with ``.message.content`` attributes, depending on version. These
helpers normalize both shapes to a ``str``. Two entry points are kept because the two
historical call sites accepted subtly different shapes:

* :func:`extract_content` — the adaptive agent's reader (dict-or-object, one pass).
* :func:`extract_message_content` — seed discovery's reader (dict first, then object).

Both are preserved verbatim to keep their exact, separately-tested behavior.
"""
from __future__ import annotations

from typing import Any


def extract_content(response: Any) -> str:
    """Adaptive-agent reader: handle dict responses and attribute-style objects."""
    if isinstance(response, dict):
        msg = response.get("message") or {}
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            return msg["content"]
        content = response.get("content")
        return content if isinstance(content, str) else ""

    msg = getattr(response, "message", None)
    if msg is not None:
        content = getattr(msg, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            return msg["content"]

    content = getattr(response, "content", None)
    return content if isinstance(content, str) else ""


def extract_message_content(response: object) -> str:
    """Seed-discovery reader: try dict extraction first, then object attributes."""
    dict_content = _extract_message_content_from_dict(response)
    if dict_content:
        return dict_content
    object_content = _extract_message_content_from_object(response)
    if object_content:
        return object_content
    return ""


def _extract_message_content_from_dict(response: object) -> str:
    """Pull ``message.content`` (or top-level ``content``) from a dict response."""
    if not isinstance(response, dict):
        return ""
    message = response.get("message") or {}
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
    content = response.get("content")
    return content if isinstance(content, str) else ""


def _extract_message_content_from_object(response: object) -> str:
    """Pull ``.message.content`` (or ``.content``) from an attribute-style response."""
    message_obj = getattr(response, "message", None)
    if message_obj is not None:
        content_attr = getattr(message_obj, "content", None)
        if isinstance(content_attr, str):
            return content_attr
        if isinstance(message_obj, dict):
            content = message_obj.get("content")
            if isinstance(content, str):
                return content
    direct_content = getattr(response, "content", None)
    return direct_content if isinstance(direct_content, str) else ""


__all__ = ["extract_content", "extract_message_content"]
