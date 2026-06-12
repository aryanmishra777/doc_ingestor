

"""Script-pipeline phase handlers.

Generates the targeted fetch script (reusing a playbook-cached script for the domain
when one previously succeeded) and executes it, converting JSONL output into records.
"""

from adaptive.playbook import cached_script, domain_of


def _phase_generate_script(state: AgentState, log: Callable[[str], None]) -> None:
    if state.retry_count == 0 and not state.generation_context:
        cached = cached_script(
            domain_of(state.target_url),
            state.detection.framework if state.detection else None,
        )
        if cached:
            log("Adaptive: reusing fetch script that previously succeeded for this domain...")
            state.generated_code = cached
            state.phase = CrawlerPhase.EXECUTE_SCRIPT
            return
    log(f"Adaptive: generating fetch script via {state.llm_provider}...")
    code, err = _generate_fetch_script(state, log)
    if err:
        log(f"Adaptive: script generation failed ({err}), falling back to crawler")
        state.phase = CrawlerPhase.CRAWLER_FALLBACK
    else:
        state.generated_code = code
        state.phase = CrawlerPhase.EXECUTE_SCRIPT


def _phase_execute_script(state: AgentState, log: Callable[[str], None]) -> None:
    log("Adaptive: executing fetch script...")
    lines, stderr, returncode = _execute_script(state.generated_code or "")
    state.script_stdout = lines
    state.script_stderr = stderr
    state.script_returncode = returncode
    if returncode != 0:
        log(f"Adaptive: script exited with code {returncode}")
    state.doc_records = _convert_script_output(lines)
    log(f"Adaptive: script produced {len(state.doc_records)} records")
    state.phase = CrawlerPhase.EVALUATE_QUALITY