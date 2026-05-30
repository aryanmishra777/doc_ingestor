"""Interactive link discovery inside a live Playwright page.

Single-page apps and paginated docs hide links behind buttons/tabs/"load more" controls.
After the page settles, this module collects all ``<a href>`` links and then *clicks* a
small, bounded number of pagination-like controls, harvesting any new URLs (and links)
they reveal before navigating back. Everything is best-effort and time-boxed so a
misbehaving page can never hang the crawl.
"""
from __future__ import annotations

from urllib.parse import urljoin

#: Hard cap on how many controls we'll click per page (keeps crawl time bounded).
MAX_DISCOVERY_INTERACTIONS = 6

#: Visible-text hints that mark a control as "show more / next page"-style navigation.
DISCOVERY_TEXT_HINTS = (
    "next", "more", "load more", "show more", "expand", "see more", "older", "continue",
)


def discover_interactive_links(page: object, base_url: str) -> set[str]:
    """Collect static links, then click pagination controls to reveal more."""
    discovered = collect_page_links(page, base_url)
    interaction_count = 0
    try:
        candidates = page.query_selector_all(
            "button, summary, [role='button'], [role='tab'], [aria-controls]"
        )
    except Exception:
        return discovered

    for element in candidates:
        if interaction_count >= MAX_DISCOVERY_INTERACTIONS:
            break
        if not _looks_like_pagination_control(element):
            continue
        if _click_for_discovery(page, element, base_url, discovered):
            interaction_count += 1
    return discovered


def collect_page_links(page: object, base_url: str) -> set[str]:
    """Return all absolute ``http(s)`` hrefs currently present in the DOM."""
    try:
        hrefs = page.eval_on_selector_all("a[href]", "nodes => nodes.map(node => node.href)")
    except Exception:
        return set()
    if not isinstance(hrefs, list):
        return set()
    discovered: set[str] = set()
    for href in hrefs:
        resolved = urljoin(base_url, str(href))
        if resolved.startswith(("http://", "https://")):
            discovered.add(resolved)
    return discovered


def _looks_like_pagination_control(element: object) -> bool:
    """Whether an element's visible text matches a pagination hint."""
    text = _safe_element_text(element)
    if not text:
        return False
    lowered = text.lower()
    return any(hint in lowered for hint in DISCOVERY_TEXT_HINTS)


def _safe_element_text(element: object) -> str:
    """Read an element's inner text within a short timeout, or ``""`` on failure."""
    try:
        return (element.inner_text(timeout=800) or "").strip()
    except Exception:
        return ""


def _click_for_discovery(page: object, element: object, base_url: str, discovered: set[str]) -> bool:
    """Click one control, harvest revealed URLs/links, then navigate back.

    Returns whether the interaction completed (so the caller can count it). All steps are
    wrapped defensively; any failure aborts just this interaction.
    """
    original_url = ""
    try:
        original_url = page.url or base_url
        element.scroll_into_view_if_needed(timeout=1_000)
        element.click(timeout=1_500)
        try:
            page.wait_for_load_state("networkidle", timeout=2_500)
        except Exception:
            page.wait_for_timeout(400)

        current_url = page.url or original_url
        if current_url.startswith(("http://", "https://")):
            discovered.add(current_url)
        discovered.update(collect_page_links(page, current_url or base_url))

        if current_url != original_url:
            try:
                page.go_back(wait_until="domcontentloaded", timeout=5_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=2_500)
                except Exception:
                    pass
            except Exception:
                pass
        return True
    except Exception:
        return False


__all__ = ["discover_interactive_links", "collect_page_links", "MAX_DISCOVERY_INTERACTIONS"]
