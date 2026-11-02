from __future__ import annotations

import argparse
import json
import os
import sys
from calendar import month_name
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .api import LastFmClient, LastFmError
from .cache import MonthCache, default_cache_dir
from .env import merge_dotenv
from .service import collect_year_stats
from .stats import month_names

MIN_YEAR = 2002


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


def current_utc_year() -> int:
    return datetime.now(timezone.utc).year


def load_config(
    args: argparse.Namespace, environ: Mapping[str, str]
) -> tuple[str, str]:
    username = (args.user or environ.get("LASTFM_USERNAME") or "").strip()
    api_key = (environ.get("LASTFM_API_KEY") or "").strip()

    missing = []
    if not username:
        missing.append("LASTFM_USERNAME (or --user)")
    if not api_key:
        missing.append("LASTFM_API_KEY")

    if missing:
        raise ConfigError(
            "Missing required configuration: " + ", ".join(missing) + ". "
            "See .env.example for the expected variables."
        )

    return username, api_key


def year_bounds(year: int) -> tuple[int, int]:
    """Return inclusive-ish UNIX bounds for a UTC calendar year."""
    current_year = current_utc_year()
    if year > current_year:
        raise ValueError(f"year {year} is in the future")

    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    if year == current_year:
        end = datetime.now(timezone.utc)
    else:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)

    return int(start.timestamp()), int(end.timestamp())


def build_payload(
    username: str,
    year: int,
    total_plays: int,
    year_plays: int,
    counts: dict[int, int],
) -> dict[str, Any]:
    return {
        "username": username,
        "year": year,
        "total_plays": total_plays,
        "year_plays": year_plays,
        "months": month_names(counts),
    }


def render_table(
    username: str,
    year: int,
    total_plays: int,
    year_plays: int,
    counts: dict[int, int],
) -> str:
    now = datetime.now(timezone.utc)
    last_month = now.month if year == now.year else 12

    lines = [
        f"Last.fm stats for {username} ({year})",
        "",
        f"All-time scrobbles : {total_plays:>12,}",
        f"Scrobbles in {year}  : {year_plays:>12,}",
        "",
        f"{'Month':<12}{'Plays':>12}",
        f"{'-' * 12} {'-' * 12}",
    ]
    for month in range(1, last_month + 1):
        lines.append(f"{month_name[month]:<12}{counts[month]:>12,}")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lastfm-stats",
        description=(
            "Show Last.fm listening stats: all-time plays and plays by month "
            "for a calendar year."
        ),
        epilog=(
            "Environment variables: LASTFM_USERNAME and LASTFM_API_KEY. "
            "Create an API key at https://www.last.fm/api/account/create"
        ),
    )
    parser.add_argument(
        "--user",
        help="Last.fm username (defaults to LASTFM_USERNAME)",
    )
    parser.add_argument(
        "--year",
        type=_year_arg,
        help=f"calendar year to break down (default: {current_utc_year()})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON instead of a table",
    )
    cache_group = parser.add_mutually_exclusive_group()
    cache_group.add_argument(
        "--refresh",
        action="store_true",
        help="ignore cached monthly counts and fetch them again",
    )
    cache_group.add_argument(
        "--no-cache",
        action="store_true",
        help="neither read nor write the monthly count cache",
    )
    return parser


def collect_stats(
    username: str,
    api_key: str,
    year: int,
    *,
    show_progress: bool,
    cache_dir: Path | None = None,
    refresh: bool = False,
) -> tuple[dict[str, Any], dict[int, int], int]:
    client = LastFmClient(api_key, username)
    cache = (
        MonthCache(cache_dir, username, load=not refresh)
        if cache_dir is not None
        else None
    )

    progress = None
    if show_progress:

        def progress(month: int) -> None:
            print(
                f"\rCounting {month_name[month]:<9}...",
                end="",
                file=sys.stderr,
                flush=True,
            )

    stats = collect_year_stats(client, year, cache=cache, progress=progress)

    if show_progress:
        print(file=sys.stderr)

    if cache is not None:
        try:
            cache.save()
        except OSError as exc:
            print(f"warning: could not write cache: {exc}", file=sys.stderr)

    info = {"username": stats.username, "playcount": stats.total_plays}
    return info, stats.months, stats.year_plays


def main(
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    env = merge_dotenv(os.environ) if environ is None else environ

    try:
        username, api_key = load_config(args, env)
        year = args.year or current_utc_year()
        info, counts, year_plays = collect_stats(
            username,
            api_key,
            year,
            show_progress=not args.json,
            cache_dir=None if args.no_cache else default_cache_dir(env),
            refresh=args.refresh,
        )
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except LastFmError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(file=sys.stderr)
        return 130

    canonical_username = info["username"]
    payload = build_payload(
        canonical_username,
        year,
        info["playcount"],
        year_plays,
        counts,
    )

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(
            render_table(
                canonical_username,
                year,
                info["playcount"],
                year_plays,
                counts,
            )
        )

    return 0


def _year_arg(value: str) -> int:
    try:
        year = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("year must be an integer") from exc

    current_year = current_utc_year()
    if year < MIN_YEAR or year > current_year:
        raise argparse.ArgumentTypeError(
            f"year must be between {MIN_YEAR} and {current_year}"
        )
    return year


if __name__ == "__main__":
    raise SystemExit(main())
