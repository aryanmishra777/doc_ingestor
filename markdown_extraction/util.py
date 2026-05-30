"""Token-stream helpers shared across the Markdown extractor.

markdown-it produces a flat list of ``*_open``/``*_close`` tokens. :func:`find_matching_close`
returns the index of the ``_close`` that balances the ``_open`` at ``start``, accounting
for nesting (e.g. lists within lists), so the walker can slice out a complete sub-block.
"""
from __future__ import annotations


def find_matching_close(tokens: list, start: int, close_type: str) -> int:
    """Index of the ``close_type`` token that balances the open token at ``start``.

    Falls back to the last token index if the stream is unbalanced, so slicing never
    raises on malformed input.
    """
    depth = 0
    open_type = close_type.replace("_close", "_open")
    for j in range(start, len(tokens)):
        if tokens[j].type == open_type:
            depth += 1
        elif tokens[j].type == close_type:
            depth -= 1
            if depth == 0:
                return j
    return len(tokens) - 1


__all__ = ["find_matching_close"]
