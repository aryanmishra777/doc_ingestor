"""Cleaning layer: normalize extracted records before rendering.

Public API is a single function, :func:`clean_record`. The implementation is split into
:mod:`cleaning.text` (string-level normalization) and :mod:`cleaning.blocks` (structural
cleaning + de-duplication). Import as ``from cleaning import clean_record`` exactly as
before the refactor.
"""
from __future__ import annotations

from cleaning.record import clean_record

__all__ = ["clean_record"]
