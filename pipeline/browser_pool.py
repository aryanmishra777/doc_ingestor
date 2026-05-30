"""A thread-local pool of Playwright browsers.

Launching a browser per page is expensive; sharing one browser across threads is unsafe.
The compromise: one browser *per worker thread*, created lazily on first use and tracked
so they can all be torn down at the end. Launch failures degrade to ``None`` (the caller
then falls back to the requests-based extractor) so a missing/broken Playwright install
never aborts the crawl.
"""
from __future__ import annotations

import threading
from typing import Any


def _silent_call(obj: Any, method: str) -> None:
    """Call ``obj.method()`` swallowing any error (used for best-effort teardown)."""
    try:
        getattr(obj, method)()
    except Exception:
        pass


class BrowserPool:
    """Lazily provisions one headless Chromium per thread and closes them on demand."""

    def __init__(self) -> None:
        self._tls = threading.local()
        self._browsers: list[tuple[Any, Any]] = []
        self._lock = threading.Lock()

    def get(self) -> Any:
        """Return this thread's browser, launching it on first access (or ``None``)."""
        if not hasattr(self._tls, "browser"):
            self._tls.browser = self._launch()
        return self._tls.browser

    def _launch(self) -> Any:
        """Start Playwright + a headless browser for the current thread."""
        try:
            from playwright.sync_api import sync_playwright
            pw = sync_playwright().start()
            browser = pw.chromium.launch(headless=True)
            self._tls.pw = pw
            with self._lock:
                self._browsers.append((pw, browser))
            return browser
        except Exception:
            return None

    def close_all(self) -> None:
        """Close every launched browser and stop its Playwright driver."""
        with self._lock:
            for pw, browser in self._browsers:
                _silent_call(browser, "close")
                _silent_call(pw, "stop")
            self._browsers.clear()


__all__ = ["BrowserPool"]
