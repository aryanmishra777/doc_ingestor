

"""Per-seed output path construction and script entrypoint hook."""

def _build_seed_output_path(output: Path, seed_url: str, index: int, total: int) -> Path:
    parsed = urlparse(seed_url)
    slug = (parsed.path.strip("/") or "root").replace("/", "_").replace(".", "_")
    suffix = output.suffix or ".md"

    if output.suffix:
        filename = f"{output.stem}_seed_{index:02d}_of_{total:02d}_{slug}{suffix}"
        return output.parent / filename

    output.mkdir(parents=True, exist_ok=True)
    filename = f"seed_{index:02d}_of_{total:02d}_{slug}{suffix}"
    return output / filename


if __name__ == "__main__":
    main()
