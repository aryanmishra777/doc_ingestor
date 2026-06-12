"""Shared helpers for the standalone regression check scripts in this directory.

Each regression_*.py script is a self-contained narrative: it monkeypatches package
internals, runs scenarios, and exits non-zero on failure. This module holds only the
boilerplate they all repeat (path bootstrap, colored check output, urlopen fakes,
summary/exit) so each scenario file stays small.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"


def repeated_words(prefix: str, count: int) -> str:
    """Generate filler prose long enough to pass density thresholds in fixtures."""
    return " ".join(f"{prefix}{idx}" for idx in range(count))


class FakeResponse:
    """Minimal context-manager stand-in for ``urlopen`` responses."""

    def __init__(self, body: str):
        self._body = body

    def read(self) -> bytes:
        return self._body.encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class Checker:
    """Collects named pass/fail checks and renders the script summary."""

    def __init__(self, suite: str) -> None:
        self.suite = suite
        self.results: list[tuple[str, bool, str]] = []
        print(f"\n=== {suite} ===")

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        self.results.append((name, bool(condition), detail))
        status = PASS if condition else FAIL
        print(f"  [{status}] {name}" + (f" - {detail}" if detail else ""))

    def finish(self) -> None:
        failed = [name for name, ok, _ in self.results if not ok]
        if failed:
            print(f"\n{len(failed)} failed: {', '.join(failed)}")
            raise SystemExit(1)
        print(f"\nAll {len(self.results)} {self.suite} checks passed.")
