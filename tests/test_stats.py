from datetime import datetime, timezone

from lastfm_stats.stats import aggregate_by_month, month_names


def utc_timestamp(year: int, month: int, day: int = 15, hour: int = 12) -> int:
    return int(datetime(year, month, day, hour, tzinfo=timezone.utc).timestamp())


def test_aggregate_by_month_counts_and_filters_year():
    timestamps = [
        utc_timestamp(2026, 1, 1),
        utc_timestamp(2026, 1, 31),
        utc_timestamp(2026, 2, 10),
        utc_timestamp(2026, 12, 31),
        utc_timestamp(2025, 12, 31),
    ]

    counts, total = aggregate_by_month(timestamps, 2026)

    assert total == 4
    assert counts[1] == 2
    assert counts[2] == 1
    assert counts[12] == 1
    assert counts[3] == 0
    assert sum(counts.values()) == total


def test_aggregate_empty_input_returns_zero_months():
    counts, total = aggregate_by_month([], 2026)

    assert total == 0
    assert counts == {month: 0 for month in range(1, 13)}


def test_month_names_maps_all_months_in_order():
    result = month_names({month: month * 10 for month in range(1, 13)})

    assert list(result) == [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    assert result["January"] == 10
    assert result["December"] == 120
