"""Adapter around the third-party ``trafilatura`` library (the extraction fallback).

Named ``trafilatura_adapter`` (not ``trafilatura``) so it never shadows the real library
on imports. Public entry point: :func:`extract_via_trafilatura`.
"""
from __future__ import annotations

from extraction.trafilatura_adapter.fallback import extract_via_trafilatura

__all__ = ["extract_via_trafilatura"]
