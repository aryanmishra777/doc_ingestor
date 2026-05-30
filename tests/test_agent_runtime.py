"""Tests for the optional LangChain adaptive-agent runtime."""
from __future__ import annotations

from adaptive import agent_runtime


def _request() -> agent_runtime.AgentRequest:
    return agent_runtime.AgentRequest(
        name="unit-test-agent",
        provider="local",
        model="gemma4:latest",
        system_prompt="Return concise answers.",
        user_prompt="Say hello.",
        tools=[],
    )


def test_agent_mode_direct_uses_fallback(monkeypatch) -> None:
    monkeypatch.setenv("DOC_INGESTOR_AGENT_MODE", "direct")
    monkeypatch.setattr(
        agent_runtime,
        "_run_langchain_agent",
        lambda *_: "agent should not run",
    )

    assert agent_runtime.run_agent_text(_request(), fallback=lambda: "direct", log=lambda _: None) == "direct"


def test_agent_runtime_falls_back_when_langchain_agent_fails(monkeypatch) -> None:
    def fail_agent(*_: object) -> str:
        raise RuntimeError("missing optional stack")

    logs: list[str] = []
    monkeypatch.delenv("DOC_INGESTOR_AGENT_MODE", raising=False)
    monkeypatch.setattr(agent_runtime, "_run_langchain_agent", fail_agent)

    result = agent_runtime.run_agent_text(_request(), fallback=lambda: "fallback", log=logs.append)

    assert result == "fallback"
    assert logs
    assert "unit-test-agent agent unavailable" in logs[0]
