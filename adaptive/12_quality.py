

"""Record parsing, quality scoring, and self-correction decisions.

Parses generated text into content/code blocks, computes structural/density/scope metrics,
accepts dense single-document outputs, and decides when another adaptive retry is useful.
"""

def _parse_content(text: str) -> tuple[list[ContentBlock], list[CodeBlock]]:
    content_blocks: list[ContentBlock] = []
    code_blocks: list[CodeBlock] = []
    last = 0
    for match in re.finditer(r"```(\w+)?\n(.*?)```", text, re.DOTALL):
        prose = text[last : match.start()].strip()
        if prose:
            content_blocks.append({"type": "paragraph", "text": prose})
        code_blocks.append({"language": match.group(1) or None, "text": match.group(2).strip()})
        last = match.end()
    remaining = text[last:].strip()
    if remaining:
        content_blocks.append({"type": "paragraph", "text": remaining})
    return content_blocks, code_blocks


# ---------------------------------------------------------------------------
# Quality evaluation (deterministic, no LLM)
# ---------------------------------------------------------------------------

def _evaluate_quality(records: list[DocPageRecord]) -> dict[str, Any]:
    if not records:
        return {"structural": 0.0, "density": 0.0, "scope": 0.0, "passed": False}

    word_counts = [_word_count(r) for r in records]
    valid = sum(
        1 for r, wc in zip(records, word_counts)
        if r.get("url") and r.get("title") and wc > 10
    )
    structural = valid / len(records)
    density = min(sum(word_counts) / len(records) / 1500.0, 1.0)
    scope = min(len(records) / 5.0, 1.0)
    passed = structural > 0.95 and density > 0.15 and scope >= 1.0
    return {"structural": structural, "density": density, "scope": scope, "passed": passed}


def _word_count(record: DocPageRecord) -> int:
    count = 0
    for block in record.get("content_blocks") or []:
        count += len((block.get("text") or "").split())
        for item in block.get("items") or []:
            count += len(item.split())
    for block in record.get("code_blocks") or []:
        count += len((block.get("text") or "").split())
    return count


def _is_complete_single_document(records: list[DocPageRecord], metrics: dict[str, Any]) -> bool:
    if len(records) != 1:
        return False
    if metrics.get("structural", 0.0) < 0.95:
        return False
    return _word_count(records[0]) >= 1200


def _is_unproductive_crawler_retry(state: AgentState) -> bool:
    return (
        state.detection is None
        and state.retry_count > 0
        and len(state.doc_records) <= 1
        and state.crawler_kwargs.get("include_sparse_pages")
        and state.crawler_kwargs.get("max_depth") is None
    )


# Self-correction lives in the ``14_self_correction`` chunk: it consumes these metrics
# plus the validated feedback report to pick the next corrective action.
