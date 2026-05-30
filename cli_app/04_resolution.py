

"""CLI configuration and seed-resolution helpers.

Resolves the start URL, runs seed discovery with diagnostics, loads ``.env`` files, and
chooses provider-specific model defaults.
"""

def resolve_start_url(start_url: str | None) -> str:
    if start_url:
        return start_url

    entered_url = input(f"Documentation URL [{DEFAULT_START_URL}]: ").strip()
    return entered_url or DEFAULT_START_URL


def resolve_seed_urls_and_diagnostics(
    start_url: str,
    seed_mode: str,
    use_llm: bool,
    llm_model: str,
    llm_provider: str,
    use_web_search: bool,
) -> tuple[list[str], SeedDiscoveryDiagnostics]:
    if seed_mode == "single":
        diagnostics = SeedDiscoveryDiagnostics(
            llm_requested=use_llm,
            llm_attempted=False,
            llm_used=False,
            llm_reason="seed-mode-single",
            llm_candidate_count=0,
        )
        return [start_url], diagnostics

    return discover_seed_urls_with_diagnostics(
        start_url,
        use_llm=use_llm,
        llm_model=llm_model,
        llm_provider=llm_provider,
        use_web_search=use_web_search,
    )


def load_env_file(env_path: Path | None = None) -> bool:
    target_path = env_path or Path(__file__).resolve().parent / ".env"
    if not target_path.exists():
        return False

    for raw_line in target_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue

        cleaned_value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, cleaned_value)

    return True


def resolve_provider_model(
    selected_model: str | None,
    provider: str,
    cloud_default: str,
    local_default: str,
    gemini_default: str,
) -> str:
    if selected_model:
        return selected_model
    if provider == "local":
        return local_default
    if provider == "gemini":
        return gemini_default
    return cloud_default
