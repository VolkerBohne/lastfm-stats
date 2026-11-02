from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path

CACHE_VERSION = 1
CACHE_DIR_ENV = "LASTFM_STATS_CACHE_DIR"
# Last.fm accepts scrobbles timestamped up to two weeks in the past, so a month
# can still change shortly after it ends. Only months older than this are cached.
SETTLE_PERIOD = timedelta(days=14)


def default_cache_dir(environ: Mapping[str, str]) -> Path:
    override = environ.get(CACHE_DIR_ENV)
    if override:
        return Path(override).expanduser()
    xdg = environ.get("XDG_CACHE_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".cache"
    return base / "lastfm-stats"


def month_start(year: int, month: int) -> datetime:
    return datetime(year, month, 1, tzinfo=timezone.utc)


def month_end(year: int, month: int) -> datetime:
    if month == 12:
        return month_start(year + 1, 1)
    return month_start(year, month + 1)


def is_month_final(year: int, month: int, now: datetime) -> bool:
    """Whether a month's play count can no longer change."""
    return month_end(year, month) + SETTLE_PERIOD <= now


class MonthCache:
    """Per-user JSON store of finalized monthly play counts."""

    def __init__(self, directory: Path, username: str, *, load: bool = True) -> None:
        self.path = Path(directory) / f"{_safe_name(username)}.json"
        self._months: dict[str, int] = self._read() if load else {}
        self._dirty = False

    def get(self, year: int, month: int) -> int | None:
        return self._months.get(_key(year, month))

    def put(self, year: int, month: int, count: int) -> None:
        key = _key(year, month)
        if self._months.get(key) != count:
            self._months[key] = count
            self._dirty = True

    def save(self) -> None:
        if not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"version": CACHE_VERSION, "months": dict(sorted(self._months.items()))}
        tmp_path = self.path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp_path, self.path)
        self._dirty = False

    def _read(self) -> dict[str, int]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict) or data.get("version") != CACHE_VERSION:
            return {}
        months = data.get("months")
        if not isinstance(months, dict):
            return {}
        return {
            key: value
            for key, value in months.items()
            if isinstance(key, str) and isinstance(value, int) and value >= 0
        }


def _key(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def _safe_name(username: str) -> str:
    # Last.fm usernames are case-insensitive.
    return re.sub(r"[^a-z0-9_-]", "_", username.lower()) or "_"
