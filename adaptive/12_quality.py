

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


# ---------------------------------------------------------------------------
# Self-correction
# ---------------------------------------------------------------------------

def _self_correct(state: AgentState, log: Callable[[str], None]) -> None:
    is_script_path = (
        state.detection is not None
        and state.detection.type == DetectionType.FRAMEWORK
    )
    if is_script_path:
        context_parts: list[str] = []
        if state.script_returncode not in (None, 0):
            context_parts.append(f"Exit code: {state.script_returncode}")
        if state.script_stderr:
            trimmed = "\n".join(state.script_stderr.splitlines()[-20:])
            context_parts.append(f"Stderr (last 20 lines):\n{trimmed}")
        m = state.eval_metrics
        context_parts.append(
            f"Quality: structural={m.get('structural', 0):.2f}, "
            f"density={m.get('density', 0):.2f}, "
            f"scope={m.get('scope', 0):.2f}"
        )
        new_context = "\n".join(context_parts)
        state.generation_context = (
            f"{state.generation_context}\n\n--- Retry {state.retry_count} ---\n{new_context}"
            if state.generation_context
            else new_context
        )
        log("Adaptive: rewriting script with accumulated error context...")
        state.phase = CrawlerPhase.GENERATE_SCRIPT
    elif state.detection is not None and state.detection.type == DetectionType.SITEMAP:
        log("Adaptive: sitemap produced low-quality metrics, falling back to crawler...")
        state.detection = None
        state.doc_records = []
        state.phase = CrawlerPhase.CRAWLER_FALLBACK
    elif state.detection is not None:
        # Structured source (sitemap/llms.txt/openapi) was found — accept results as-is
        # rather than falling back to BFS, which would re-crawl the same site differently.
        log("Adaptive: structured source produced low-quality metrics, accepting results as-is...")
        state.phase = CrawlerPhase.DONE
    else:
        # No structured endpoint found — BFS is the only option; tune its parameters.
        if not state.crawler_kwargs.get("include_sparse_pages"):
            state.crawler_kwargs["include_sparse_pages"] = True
            log("Adaptive: retrying crawler with include_sparse_pages=True...")
        elif state.crawler_kwargs.get("max_depth") is not None:
            state.crawler_kwargs["max_depth"] = None
            log("Adaptive: retrying crawler with no depth limit...")
        else:
            log("Adaptive: no further crawler adjustments available, retrying as-is...")
        state.phase = CrawlerPhase.CRAWLER_FALLBACK
