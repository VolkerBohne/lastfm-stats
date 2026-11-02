from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

ENV_FILENAME = ".env"


def parse_dotenv(text: str) -> dict[str, str]:
    """Parse KEY=value lines from dotenv-style text."""
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()

        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not key:
            continue

        values[key] = _parse_value(value.strip())

    return values


def load_dotenv(path: Path | None = None) -> dict[str, str]:
    """Read a .env file, returning an empty mapping when it does not exist."""
    env_path = Path(path) if path is not None else Path.cwd() / ENV_FILENAME
    try:
        text = env_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}

    return parse_dotenv(text)


def merge_dotenv(
    environ: Mapping[str, str], path: Path | None = None
) -> dict[str, str]:
    """Merge .env values below an existing environment mapping."""
    merged = load_dotenv(path)
    merged.update(environ)
    return merged


def _parse_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]

    for marker in (" #", "\t#"):
        index = value.find(marker)
        if index != -1:
            value = value[:index]
            break

    return value.rstrip()
