"""LangChain-backed adaptive agents with optional Intel local runtimes.

The adaptive crawler has two LLM-heavy jobs: generate a targeted fetch script and explain
why adaptive attempts failed. This module turns those jobs into LangChain agents with
tools, while keeping the old direct chat path as a fallback when optional agent packages
are not installed.
"""
from __future__ import annotations

import importlib
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentRequest:
    """Inputs needed to run one adaptive agent task."""

    name: str
    provider: str
    model: str
    system_prompt: str
    user_prompt: str
    tools: Sequence[Callable[..., str]]


def run_agent_text(
    request: AgentRequest,
    fallback: Callable[[], str],
    log: Callable[[str], None],
) -> str:
    """Run a LangChain agent and fall back to direct chat if the agent stack is absent."""
    if os.environ.get("DOC_INGESTOR_AGENT_MODE", "langchain").lower() == "direct":
        return fallback()
    try:
        return _run_langchain_agent(request, log)
    except Exception as exc:
        log(f"Adaptive: {request.name} agent unavailable ({exc}); using direct chat")
        return fallback()


def _run_langchain_agent(request: AgentRequest, log: Callable[[str], None]) -> str:
    create_agent = getattr(importlib.import_module("langchain.agents"), "create_agent")
    model = _build_langchain_model(request.provider, request.model)
    agent = create_agent(model=model, tools=list(request.tools), system_prompt=request.system_prompt)
    log(f"Adaptive: running {request.name} agent via LangChain/{_runtime_preference()}")
    result = agent.invoke({"messages": [{"role": "user", "content": request.user_prompt}]})
    return _extract_agent_text(result)


def _build_langchain_model(provider: str, model: str) -> Any:
    runtime = _runtime_preference()
    if runtime == "openvino":
        return _build_openvino_model(model)
    if runtime == "ipex":
        return _build_ipex_model(model)
    if provider == "local":
        chat_ollama = getattr(importlib.import_module("langchain_ollama"), "ChatOllama")
        return chat_ollama(model=model, base_url=os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    if provider == "cloud":
        return f"ollama:{model}"
    raise RuntimeError(f"LangChain agent runtime does not support provider {provider!r}")


def _build_openvino_model(model: str) -> Any:
    model_id = os.environ.get("DOC_INGESTOR_OPENVINO_MODEL", model)
    device = os.environ.get("DOC_INGESTOR_OPENVINO_DEVICE", "CPU")
    max_tokens = int(os.environ.get("DOC_INGESTOR_AGENT_MAX_NEW_TOKENS", "2048"))
    hf_pipeline = getattr(importlib.import_module("langchain_huggingface"), "HuggingFacePipeline")
    ov_config = {
        "PERFORMANCE_HINT": os.environ.get("DOC_INGESTOR_OPENVINO_PERFORMANCE_HINT", "LATENCY"),
        "NUM_STREAMS": os.environ.get("DOC_INGESTOR_OPENVINO_NUM_STREAMS", "1"),
        "CACHE_DIR": os.environ.get("DOC_INGESTOR_OPENVINO_CACHE_DIR", ""),
    }
    return hf_pipeline.from_model_id(
        model_id=model_id,
        task="text-generation",
        backend="openvino",
        model_kwargs={"device": device, "ov_config": ov_config},
        pipeline_kwargs={"max_new_tokens": max_tokens},
    )


def _build_ipex_model(model: str) -> Any:
    model_id = os.environ.get("DOC_INGESTOR_IPEX_MODEL", model)
    max_tokens = int(os.environ.get("DOC_INGESTOR_AGENT_MAX_NEW_TOKENS", "2048"))
    for module_name in ("langchain_community.llms.ipex_llm", "langchain_community.llms"):
        try:
            model_cls = getattr(importlib.import_module(module_name), "IpexLLM")
        except (ImportError, AttributeError):
            continue
        if hasattr(model_cls, "from_model_id"):
            return model_cls.from_model_id(model_id=model_id, max_new_tokens=max_tokens)
        return model_cls(model_id=model_id, max_new_tokens=max_tokens)
    raise RuntimeError("IPEX-LLM LangChain integration is not installed")


def _runtime_preference() -> str:
    runtime = os.environ.get("DOC_INGESTOR_AGENT_RUNTIME", "ollama").strip().lower()
    return runtime if runtime in {"ollama", "openvino", "ipex"} else "ollama"


def _extract_agent_text(result: Any) -> str:
    if isinstance(result, dict):
        messages = result.get("messages")
        if isinstance(messages, list) and messages:
            return _message_content(messages[-1])
        output = result.get("output")
        return output if isinstance(output, str) else ""
    return _message_content(result)


def _message_content(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return str(content) if content is not None else ""
