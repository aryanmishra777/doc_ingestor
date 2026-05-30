

"""OpenAPI/framework probing and shared HTTP fetches.

Detects structured documentation endpoints, recognizes framework-specific API affordances,
and provides the adaptive crawler's bounded ``_http_get`` helper.
"""

def _detect_openapi(
    responses: dict[str, dict[str, Any] | None],
    probe_paths: dict[str, str],
    base: str,
) -> DetectionResult | None:
    for key in ("openapi_1", "openapi_2", "openapi_3", "openapi_4"):
        r = responses.get(key)
        if not r or r["status"] != 200:
            continue
        ct = r["content_type"].lower()
        body = r["body"]
        if ("json" in ct or "yaml" in ct) and (
            '"openapi"' in body or '"swagger"' in body or "openapi:" in body
        ):
            return DetectionResult(
                type=DetectionType.OPENAPI,
                url=base + probe_paths[key],
                prefetched_content=body,
            )
    return None


def _detect_framework(
    responses: dict[str, dict[str, Any] | None],
    url: str,
) -> DetectionResult | None:
    r = responses.get("homepage")
    if not r or r["status"] != 200:
        return None
    html = r["body"]
    if "X-ReadTheDocs-Project" in r["headers"]:
        return DetectionResult(type=DetectionType.FRAMEWORK, url=url, framework="readthedocs")
    for framework, signals in _FRAMEWORK_SIGNALS.items():
        if any(s in html for s in signals):
            return DetectionResult(type=DetectionType.FRAMEWORK, url=url, framework=framework)
    return None


def _probe_for_api(url: str) -> DetectionResult | None:
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    probe_paths: dict[str, str] = {
        "llms_full_1": "/llms-full.txt",
        "llms_full_2": "/.well-known/llms-full.txt",
        "llms_1":      "/llms.txt",
        "llms_2":      "/.well-known/llms.txt",
        "sitemap_1":   "/sitemap.xml",
        "sitemap_2":   "/sitemap_index.xml",
        "openapi_1":   "/openapi.json",
        "openapi_2":   "/swagger.json",
        "openapi_3":   "/api-docs",
        "openapi_4":   "/.well-known/openapi.yaml",
        "homepage":    "/",
    }

    responses: dict[str, dict[str, Any] | None] = {}
    with ThreadPoolExecutor(max_workers=len(probe_paths)) as executor:
        future_to_key = {
            executor.submit(_http_get, base + path): key
            for key, path in probe_paths.items()
        }
        for future in as_completed(future_to_key):
            key = future_to_key[future]
            try:
                responses[key] = future.result()
            except Exception:
                responses[key] = None

    return (
        _detect_llms_txt(responses, probe_paths, base)
        or _detect_sitemap(responses, probe_paths, base)
        or _detect_openapi(responses, probe_paths, base)
        or _detect_framework(responses, url)
    )


def _http_get(
    url: str, read_limit: int = 65536, timeout: float = PROBE_TIMEOUT
) -> dict[str, Any] | None:
    req = Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "*/*"}, method="GET")
    try:
        with urlopen(req, timeout=timeout) as resp:
            ct = resp.headers.get("Content-Type", "")
            ce = resp.headers.get("Content-Encoding", "")
            headers = dict(resp.headers)
            needs_decompress = (
                url.lower().endswith(".gz")
                or "gzip" in ce.lower()
                or "application/gzip" in ct.lower()
                or "application/x-gzip" in ct.lower()
            )
            # For gzip streams, read the full body before decompressing; otherwise
            # a partial read would leave the gzip member incomplete and fail.
            raw = resp.read() if needs_decompress else resp.read(read_limit)
            if needs_decompress:
                try:
                    raw = gzip.open(io.BytesIO(raw)).read()
                except Exception:
                    pass
            return {
                "status": resp.getcode(),
                "content_type": ct,
                "headers": headers,
                "body": raw[:read_limit].decode("utf-8", errors="ignore"),
            }
    except Exception:
        return None
