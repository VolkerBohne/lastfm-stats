from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from .api import LastFmClient
from .cache import MonthCache, is_month_final, month_end, month_start


@dataclass(frozen=True)
class YearStats:
    username: str
    year: int
    total_plays: int
    year_plays: int
    months: dict[int, int]


def collect_year_stats(
    client: LastFmClient,
    year: int,
    *,
    cache: MonthCache | None = None,
    now: datetime | None = None,
    progress: Callable[[int], None] | None = None,
) -> YearStats:
    """Fetch the all-time play count and the play count per month of ``year``.

    Cached months are reused. Every other month up to ``now`` costs a single
    request; settled months are written to ``cache``, which the caller saves.
    ``progress`` is called with the month number before each request.
    """
    now = now or datetime.now(timezone.utc)
    if year > now.year:
        raise ValueError(f"year {year} is in the future")

    info = client.get_user_info()
    last_month = now.month if year == now.year else 12

    counts = {month: 0 for month in range(1, 13)}
    for month in range(1, last_month + 1):
        cached = cache.get(year, month) if cache is not None else None
        if cached is not None:
            counts[month] = cached
            continue

        if progress is not None:
            progress(month)
        start = month_start(year, month)
        end = min(month_end(year, month), now)
        counts[month] = client.count_scrobbles(
            int(start.timestamp()), int(end.timestamp())
        )
        if cache is not None and is_month_final(year, month, now):
            cache.put(year, month, counts[month])

    return YearStats(
        username=info["username"],
        year=year,
        total_plays=info["playcount"],
        year_plays=sum(counts.values()),
        months=counts,
    )
