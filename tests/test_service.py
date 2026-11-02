from datetime import datetime, timezone

import pytest

from lastfm_stats.cache import MonthCache
from lastfm_stats.service import YearStats, collect_year_stats


def utc(year, month, day=15, hour=12, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def ts(moment):
    return int(moment.timestamp())


class FakeClient:
    """Counts scrobbles in [from, to) like Last.fm and records every request."""

    def __init__(self, timestamps=(), playcount=1000):
        self.timestamps = [ts(moment) for moment in timestamps]
        self.playcount = playcount
        self.requests = []

    def get_user_info(self):
        self.requests.append(("user.getInfo",))
        return {"username": "RJ", "playcount": self.playcount}

    def count_scrobbles(self, from_ts, to_ts):
        self.requests.append(("count", from_ts, to_ts))
        return sum(1 for value in self.timestamps if from_ts <= value < to_ts)

    @property
    def count_ranges(self):
        return [request[1:] for request in self.requests if request[0] == "count"]


def test_counts_each_month_of_past_year_with_one_request():
    client = FakeClient([utc(2024, 1, 5), utc(2024, 1, 6), utc(2024, 12, 31)])

    stats = collect_year_stats(client, 2024, now=utc(2026, 11, 2))

    assert stats == YearStats(
        username="RJ",
        year=2024,
        total_plays=1000,
        year_plays=3,
        months={1: 2, **{month: 0 for month in range(2, 12)}, 12: 1},
    )
    assert len(client.requests) == 13
    assert client.count_ranges[0] == (ts(utc(2024, 1, 1, 0)), ts(utc(2024, 2, 1, 0)))
    assert client.count_ranges[-1] == (ts(utc(2024, 12, 1, 0)), ts(utc(2025, 1, 1, 0)))


def test_fully_cached_past_year_costs_only_get_info():
    cache = MonthCache.from_months({f"2024-{month:02d}": month for month in range(1, 13)})
    client = FakeClient()

    stats = collect_year_stats(client, 2024, cache=cache, now=utc(2026, 11, 2))

    assert client.requests == [("user.getInfo",)]
    assert stats.year_plays == sum(range(1, 13))
    assert not cache.dirty


def test_current_year_with_cached_months_costs_three_requests():
    now = utc(2026, 11, 2)
    cache = MonthCache.from_months({f"2026-{month:02d}": 7 for month in range(1, 10)})
    client = FakeClient([utc(2026, 10, 20), utc(2026, 11, 1)])

    stats = collect_year_stats(client, 2026, cache=cache, now=now)

    assert len(client.requests) == 3
    assert client.count_ranges == [
        (ts(utc(2026, 10, 1, 0)), ts(utc(2026, 11, 1, 0))),
        (ts(utc(2026, 11, 1, 0)), ts(now)),
    ]
    assert stats.months[10] == 1 and stats.months[11] == 1
    assert stats.months[12] == 0
    assert stats.year_plays == 9 * 7 + 2


def test_only_settled_months_are_written_to_cache():
    cache = MonthCache.from_months({})
    client = FakeClient([utc(2026, 9, 3), utc(2026, 10, 3)])

    collect_year_stats(client, 2026, cache=cache, now=utc(2026, 11, 2))

    months = cache.as_dict()
    assert months["2026-09"] == 1
    assert "2026-10" not in months  # ended less than 14 days ago
    assert "2026-11" not in months
    assert len(months) == 9


def test_month_boundaries_are_half_open_in_utc():
    first_second = utc(2026, 3, 1, 0)
    next_month = utc(2026, 4, 1, 0)
    client = FakeClient([first_second, utc(2026, 3, 31, 23, 59, 59), next_month])

    stats = collect_year_stats(client, 2026, now=utc(2026, 11, 2))

    assert (ts(first_second), ts(next_month)) in client.count_ranges
    assert stats.months[2] == 0
    assert stats.months[3] == 2
    assert stats.months[4] == 1


def test_progress_reports_only_requested_months():
    cache = MonthCache.from_months({f"2026-{month:02d}": 0 for month in range(1, 10)})
    reported = []

    collect_year_stats(
        FakeClient(), 2026, cache=cache, now=utc(2026, 11, 2), progress=reported.append
    )

    assert reported == [10, 11]


def test_rejects_future_year():
    with pytest.raises(ValueError):
        collect_year_stats(FakeClient(), 2027, now=utc(2026, 11, 2))
