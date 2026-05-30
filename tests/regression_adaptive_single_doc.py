from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import adaptive
from adaptive import AgentState, CrawlerPhase


PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, condition, detail))
    status = PASS if condition else FAIL
    print(f"  [{status}] {name}" + (f" - {detail}" if detail else ""))


def repeated_words(prefix: str, count: int) -> str:
    return " ".join(f"{prefix}{idx}" for idx in range(count))


print("\n=== Adaptive single-document acceptance ===")

state = AgentState(
    target_url="https://example.com/spec",
    doc_records=[
        {
            "url": "https://example.com/spec",
            "canonical_url": "https://example.com/spec",
            "depth": 0,
            "order_index": 0,
            "title": "Example Specification",
            "content_blocks": [
                {"type": "paragraph", "text": repeated_words("spec", 1400), "items": None, "rows": None, "code_block_index": None}
            ],
            "code_blocks": [],
            "links": [],
            "metadata": {},
            "errors": [],
        }
    ],
)
logs: list[str] = []
adaptive._phase_evaluate_quality(state, logs.append)

check("dense single page is accepted", state.phase == CrawlerPhase.DONE, str(state.phase))
check("acceptance is logged", any("dense single-document" in log for log in logs), str(logs))


failed = [name for name, ok, _ in results if not ok]
if failed:
    print(f"\n{len(failed)} failed: {', '.join(failed)}")
    raise SystemExit(1)

print(f"\nAll {len(results)} adaptive single-document checks passed.")
