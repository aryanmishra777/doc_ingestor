

# ---------------------------------------------------------------------------
# Script generation via Ollama (framework path only)
# ---------------------------------------------------------------------------

"""LLM client construction and adaptive script generation.

Centralizes Ollama/Gemini client setup, provider normalization, chat calls, timeout
handling, and the prompt used to generate targeted fetch scripts.
"""

def _generate_fetch_script(
    state: AgentState, log: Callable[[str], None]
) -> tuple[str | None, str | None]:
    client = _make_llm_client(state.llm_provider)
    if state.llm_provider != "gemini" and client is None:
        return None, _llm_unavailable_reason(state.llm_provider)
    if state.llm_provider == "gemini" and not os.environ.get("GEMINI_API_KEY", "").strip():
        return None, _llm_unavailable_reason(state.llm_provider)

    det = state.detection
    user_prompt = (
        f"Target URL: {state.target_url}\n"
        f"Detection type: {det.type.value if det else 'none'}\n"
        f"Detection URL: {det.url if det else 'n/a'}\n"
        f"Framework: {det.framework if det and det.framework else 'unknown'}\n"
    )
    if state.generation_context:
        user_prompt += f"\nPrevious attempt(s) failed. Error context:\n{state.generation_context}\n"
    user_prompt += "\nWrite the Python extraction script now."

    text = _llm_chat(client, state.llm_provider, state.llm_model, _SCRIPT_SYSTEM, user_prompt, log)
    if not text:
        return None, "empty response from LLM"

    code = re.sub(r"^```(?:python)?\n?", "", text.strip())
    code = re.sub(r"\n?```$", "", code.strip())
    return code.strip(), None


def _make_llm_client(llm_provider: str = DEFAULT_OLLAMA_PROVIDER) -> Any | None:
    provider = _normalize_llm_provider(llm_provider)
    api_key = os.environ.get("OLLAMA_API_KEY", "").strip()
    if provider == "gemini":
        return object()
    if provider == "cloud" and not api_key:
        return None
    try:
        ollama_module = importlib.import_module("ollama")
        client_cls = getattr(ollama_module, "Client", None)
        if client_cls is None:
            return None
        if provider == "local":
            return client_cls(host=os.environ.get("OLLAMA_HOST", LOCAL_OLLAMA_HOST))
        return client_cls(
            host="https://ollama.com",
            headers={"Authorization": f"Bearer {api_key}"},
        )
    except Exception:
        return None


def _normalize_llm_provider(llm_provider: str) -> str:
    return llm_provider if llm_provider in {"cloud", "local", "gemini"} else DEFAULT_OLLAMA_PROVIDER


def _llm_unavailable_reason(llm_provider: str) -> str:
    if _normalize_llm_provider(llm_provider) == "gemini":
        return "Gemini not available (missing GEMINI_API_KEY)"
    if _normalize_llm_provider(llm_provider) == "local":
        return "Ollama local server not available (start ollama or install ollama package)"
    return "Ollama cloud not available (missing OLLAMA_API_KEY or ollama package)"


def _llm_chat(
    client: Any,
    llm_provider: str,
    model: str,
    system: str,
    user: str,
    log: Callable[[str], None],
) -> str:
    if llm_provider == "gemini":
        return _gemini_chat(model, system, user, log)
    try:
        response = client.chat(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            stream=False,
        )
        return _extract_content(response)
    except Exception as exc:
        log(f"Adaptive: LLM call failed: {exc}")
        return ""


def _gemini_chat(
    model: str,
    system: str,
    user: str,
    log: Callable[[str], None],
) -> str:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return ""

    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"parts": [{"text": user}]}],
    }
    timeout_seconds = _resolve_llm_timeout_seconds()
    try:
        response = requests.post(
            f"{GEMINI_API_BASE_URL}/models/{model}:generateContent",
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout_seconds,
        )
        response.raise_for_status()
    except Exception as exc:
        log(f"Adaptive: Gemini call failed: {exc}")
        return ""
    return _extract_gemini_content(response.json())
