from __future__ import annotations

from calendar import month_name
from collections.abc import Iterable
from datetime import datetime, timezone

MONTHS = tuple(month_name[1:])


def aggregate_by_month(
    timestamps: Iterable[int], year: int
) -> tuple[dict[int, int], int]:
    """Count timestamps per UTC month for the given year.

    Returns a mapping of month number (1-12) to play count, plus the total.
    Timestamps from other years are ignored.
    """
    counts = {month: 0 for month in range(1, 13)}
    total = 0

    for timestamp in timestamps:
        moment = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        if moment.year != year:
            continue
        counts[moment.month] += 1
        total += 1

    return counts, total


def month_names(counts: dict[int, int]) -> dict[str, int]:
    return {MONTHS[month - 1]: counts[month] for month in range(1, 13)}
