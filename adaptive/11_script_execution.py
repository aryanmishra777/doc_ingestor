

"""Generated-script execution and JSONL conversion.

Executes adaptive fetch scripts in a temporary process, parses their JSON Lines output,
and converts emitted page objects into the shared record shape.
"""

def _extract_gemini_content(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        return ""
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        parts = content.get("parts")
        if not isinstance(parts, list):
            continue
        texts = [part.get("text", "") for part in parts if isinstance(part, dict) and isinstance(part.get("text"), str)]
        joined = "".join(texts).strip()
        if joined:
            return joined
    return ""


def _resolve_llm_timeout_seconds() -> float:
    raw = os.environ.get("DOC_INGESTOR_LLM_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return 90.0
    try:
        value = float(raw)
    except ValueError:
        return 90.0
    return max(5.0, value)


def _extract_content(response: Any) -> str:
    if isinstance(response, dict):
        msg = response.get("message") or {}
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            return msg["content"]
        content = response.get("content")
        return content if isinstance(content, str) else ""

    msg = getattr(response, "message", None)
    if msg is not None:
        content = getattr(msg, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            return msg["content"]

    content = getattr(response, "content", None)
    return content if isinstance(content, str) else ""


# ---------------------------------------------------------------------------
# Script execution
# ---------------------------------------------------------------------------

def _scrubbed_env() -> dict[str, str]:
    """Environment for generated scripts: inherited, minus anything secret-shaped.

    The script source comes from an LLM; it must never see the operator's API keys.
    """
    secret_markers = ("API_KEY", "APIKEY", "SECRET", "TOKEN", "PASSWORD", "CREDENTIAL")
    return {
        key: value
        for key, value in os.environ.items()
        if not any(marker in key.upper() for marker in secret_markers)
    }


def _execute_script(code: str) -> tuple[list[str], str, int]:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        tmp_path = f.name
    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=120,
            env=_scrubbed_env(),
        )
        stdout_lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
        return stdout_lines, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return [], "script timed out after 120s", 1
    except Exception as exc:
        return [], str(exc), 1
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# JSONL → DocPageRecord adapter (script path output)
# ---------------------------------------------------------------------------

def _convert_script_output(lines: list[str]) -> list[DocPageRecord]:
    records: list[DocPageRecord] = []
    for idx, line in enumerate(lines):
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        content = raw.get("content", "")
        content_blocks, code_blocks = _parse_content(content)
        meta = raw.get("metadata") or {}
        record: DocPageRecord = {
            "url": raw.get("url", ""),
            "canonical_url": raw.get("url") or None,
            "depth": int(meta.get("depth", 0)),
            "order_index": idx,
            "title": raw.get("title", f"Page {idx + 1}"),
            "content_blocks": content_blocks,
            "code_blocks": code_blocks,
            "links": [],
            "metadata": {
                "source_domain": urlparse(raw.get("url", "")).netloc or None,
                "breadcrumbs": [],
            },
            "errors": [],
        }
        records.append(record)
    return records
