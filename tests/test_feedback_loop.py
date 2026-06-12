"""Unit tests: feedback-before-retry routing, report schema, playbook, env scrubbing."""
from __future__ import annotations

import adaptive
from adaptive import AgentState, CrawlerPhase, DetectionResult, DetectionType, playbook
from adaptive.feedback_schema import validate_feedback_report

def _silent(_message: str) -> None:
    pass

def test_schema_normalizes_known_mode() -> None:
    report = validate_feedback_report(
        {
            "failure_mode": "rate_limited",
            "confidence_score": "0.9",
            "permanent_fix_recommended": True,
            "rationale": "too many 429s",
            "immediate_fix": "slow down",
        }
    )
    assert report is not None
    assert report["failure_mode"] == "RATE_LIMITED"
    assert report["confidence_score"] == 0.9
    assert report["permanent_fix_recommended"] is True

def test_schema_rejects_garbage() -> None:
    assert validate_feedback_report({"failure_mode": "GREMLINS"}) is None
    assert validate_feedback_report("not a dict") is None
    assert validate_feedback_report(None) is None

def test_failed_quality_routes_to_feedback_analysis_first() -> None:
    state = AgentState(target_url="https://example.com", doc_records=[])
    adaptive._phase_evaluate_quality(state, _silent)
    assert state.phase == CrawlerPhase.FEEDBACK_ANALYSIS
    assert state.retry_count == 1
    assert not state.retries_exhausted

def test_feedback_phase_routes_to_self_correct_when_retries_remain(monkeypatch) -> None:
    monkeypatch.setattr(adaptive, "_generate_feedback", lambda _state, _log: None)
    state = AgentState(target_url="https://example.com")
    state.retry_count = 1
    adaptive._phase_feedback_analysis(state, _silent)
    assert state.phase == CrawlerPhase.SELF_CORRECT

def test_feedback_phase_terminal_after_exhaustion(monkeypatch) -> None:
    monkeypatch.setattr(adaptive, "_generate_feedback", lambda _state, _log: None)
    state = AgentState(target_url="https://example.com", doc_records=[])
    state.retries_exhausted = True
    adaptive._phase_feedback_analysis(state, _silent)
    assert state.phase == CrawlerPhase.FAILED

def test_rate_limited_crawler_drops_to_single_worker() -> None:
    state = AgentState(target_url="https://example.com")
    state.feedback_report = {"failure_mode": "RATE_LIMITED"}
    adaptive._self_correct(state, _silent)
    assert state.crawler_kwargs["max_workers"] == 1
    assert state.phase == CrawlerPhase.CRAWLER_FALLBACK

def test_selector_mismatch_feeds_diagnosis_into_regeneration() -> None:
    state = AgentState(
        target_url="https://example.com",
        detection=DetectionResult(
            type=DetectionType.FRAMEWORK, url="https://example.com", framework="docusaurus"
        ),
    )
    state.feedback_report = {"failure_mode": "SELECTOR_MISMATCH", "immediate_fix": "use article.main"}
    adaptive._self_correct(state, _silent)
    assert state.phase == CrawlerPhase.GENERATE_SCRIPT
    assert "SELECTOR_MISMATCH" in state.generation_context
    assert "use article.main" in state.generation_context

def test_no_report_falls_back_to_ladder() -> None:
    state = AgentState(target_url="https://example.com")
    adaptive._self_correct(state, _silent)
    assert state.crawler_kwargs["include_sparse_pages"] is True
    assert state.phase == CrawlerPhase.CRAWLER_FALLBACK

def test_antibot_on_script_path_uses_ladder() -> None:
    state = AgentState(
        target_url="https://example.com",
        detection=DetectionResult(type=DetectionType.FRAMEWORK, url="https://example.com"),
    )
    state.feedback_report = {"failure_mode": "ANTIBOT"}
    adaptive._self_correct(state, _silent)
    # No automated fix for antibot: ladder still rewrites with error context.
    assert state.phase == CrawlerPhase.GENERATE_SCRIPT
    assert "ANTIBOT" not in state.generation_context

def test_playbook_roundtrip_and_script_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DOC_INGESTOR_PLAYBOOK", str(tmp_path / "pb.jsonl"))
    state = AgentState(
        target_url="https://example.com/docs/",
        detection=DetectionResult(
            type=DetectionType.FRAMEWORK, url="https://example.com", framework="docusaurus"
        ),
    )
    state.generated_code = "print('hi')"
    state.eval_metrics = {"structural": 1.0, "density": 0.5, "scope": 1.0, "passed": True}
    playbook.record_outcome(state, succeeded=True)
    assert playbook.cached_script("example.com", "docusaurus") == "print('hi')"
    assert playbook.cached_script("example.com", "mkdocs") is None
    assert playbook.cached_script("other.com", "docusaurus") is None

def test_playbook_skips_repeatedly_failing_detection(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DOC_INGESTOR_PLAYBOOK", str(tmp_path / "pb.jsonl"))
    fail_state = AgentState(
        target_url="https://example.com/",
        detection=DetectionResult(type=DetectionType.SITEMAP, url="https://example.com/sitemap.xml"),
    )
    playbook.record_outcome(fail_state, succeeded=False)
    playbook.record_outcome(fail_state, succeeded=False)
    # Failures alone never trigger a skip — only a proven crawler alternative does.
    assert not playbook.should_skip_detection("example.com", "sitemap")
    crawler_state = AgentState(target_url="https://example.com/")
    playbook.record_outcome(crawler_state, succeeded=True)
    assert playbook.should_skip_detection("example.com", "sitemap")

def test_playbook_disabled_is_inert(monkeypatch) -> None:
    monkeypatch.setenv("DOC_INGESTOR_PLAYBOOK", "0")
    assert playbook.playbook_path() is None
    assert playbook.entries_for_domain("example.com") == []

def test_scrubbed_env_removes_secrets(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_API_KEY", "secret")
    monkeypatch.setenv("MY_SERVICE_TOKEN", "secret")
    monkeypatch.setenv("DOC_INGESTOR_SAFE_VAR", "fine")
    env = adaptive._scrubbed_env()
    assert "OLLAMA_API_KEY" not in env
    assert "MY_SERVICE_TOKEN" not in env
    assert env.get("DOC_INGESTOR_SAFE_VAR") == "fine"
