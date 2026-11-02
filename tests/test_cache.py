import json
from datetime import datetime, timezone

from lastfm_stats import cli
from lastfm_stats.cache import MonthCache, default_cache_dir, is_month_final


def utc(year, month, day=15, hour=12):
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


class FakeClient:
    """Stands in for LastFmClient and records counted ranges."""

    timestamps: list[int] = []
    calls: list[tuple[int, int]] = []

    def __init__(self, api_key, username):
        self.username = username

    def get_user_info(self):
        return {"username": "RJ", "playcount": 1000}

    def count_scrobbles(self, from_ts, to_ts):
        FakeClient.calls.append((from_ts, to_ts))
        return sum(1 for ts in FakeClient.timestamps if from_ts <= ts < to_ts)


def use_fake_client(monkeypatch, timestamps):
    FakeClient.timestamps = [int(moment.timestamp()) for moment in timestamps]
    FakeClient.calls = []
    monkeypatch.setattr(cli, "LastFmClient", FakeClient)


def test_default_cache_dir_respects_overrides(tmp_path):
    assert default_cache_dir({"LASTFM_STATS_CACHE_DIR": str(tmp_path)}) == tmp_path
    assert (
        default_cache_dir({"XDG_CACHE_HOME": str(tmp_path)})
        == tmp_path / "lastfm-stats"
    )


def test_is_month_final_waits_for_settle_period():
    assert not is_month_final(2026, 10, utc(2026, 11, 2))
    assert is_month_final(2026, 10, utc(2026, 11, 15))
    assert is_month_final(2025, 12, utc(2026, 1, 15))


def test_month_cache_round_trip_is_case_insensitive(tmp_path):
    cache = MonthCache(tmp_path, "RJ")
    cache.put(2024, 3, 42)
    cache.save()

    assert MonthCache(tmp_path, "rj").get(2024, 3) == 42
    assert MonthCache(tmp_path, "rj", load=False).get(2024, 3) is None


def test_month_cache_ignores_corrupt_file(tmp_path):
    (tmp_path / "rj.json").write_text("not json", encoding="utf-8")

    assert MonthCache(tmp_path, "rj").get(2024, 1) is None


def test_past_year_is_fetched_once_then_served_from_cache(monkeypatch, tmp_path):
    use_fake_client(monkeypatch, [utc(2024, 1, 5), utc(2024, 1, 6), utc(2024, 12, 31)])

    first = cli.collect_stats("rj", "key", 2024, show_progress=False, cache_dir=tmp_path)
    second = cli.collect_stats("rj", "key", 2024, show_progress=False, cache_dir=tmp_path)

    assert first == second
    _, counts, year_plays = second
    assert counts[1] == 2 and counts[12] == 1 and year_plays == 3
    assert len(FakeClient.calls) == 12
    data = json.loads((tmp_path / "rj.json").read_text(encoding="utf-8"))
    assert len(data["months"]) == 12


def test_refresh_refetches_cached_year(monkeypatch, tmp_path):
    use_fake_client(monkeypatch, [utc(2024, 1, 5)])
    cli.collect_stats("rj", "key", 2024, show_progress=False, cache_dir=tmp_path)

    FakeClient.timestamps.append(int(utc(2024, 2, 5).timestamp()))
    _, counts, _ = cli.collect_stats(
        "rj", "key", 2024, show_progress=False, cache_dir=tmp_path, refresh=True
    )

    assert counts[2] == 1
    assert len(FakeClient.calls) == 24


def test_current_year_only_fetches_unsettled_months(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    year = now.year
    use_fake_client(monkeypatch, [])
    cache = MonthCache(tmp_path, "rj")
    for month in range(1, now.month + 1):
        if is_month_final(year, month, now):
            cache.put(year, month, 7)
    cache.save()

    _, counts, _ = cli.collect_stats("rj", "key", year, show_progress=False, cache_dir=tmp_path)

    unsettled = [
        month
        for month in range(1, now.month + 1)
        if not is_month_final(year, month, now)
    ]
    assert [from_ts for from_ts, _ in FakeClient.calls] == [
        int(datetime(year, month, 1, tzinfo=timezone.utc).timestamp())
        for month in unsettled
    ]
    assert all(counts[month] == 7 for month in range(1, unsettled[0]))


def test_without_cache_dir_nothing_is_written(monkeypatch, tmp_path):
    use_fake_client(monkeypatch, [utc(2024, 1, 5)])

    cli.collect_stats("rj", "key", 2024, show_progress=False)
    cli.collect_stats("rj", "key", 2024, show_progress=False)

    assert len(FakeClient.calls) == 24
    assert list(tmp_path.iterdir()) == []


def test_in_memory_cache_drops_invalid_entries():
    cache = MonthCache.from_months(
        {
            "2024-01": 5,
            "2024-13": 1,
            "January": 1,
            "2024-02": -1,
            "2024-03": "7",
            "2024-04": True,
        }
    )

    assert cache.path is None
    assert cache.as_dict() == {"2024-01": 5}
    assert MonthCache.from_months(None).as_dict() == {}


def test_in_memory_cache_tracks_changes_without_writing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cache = MonthCache.from_months({"2024-01": 5})

    cache.put(2024, 1, 5)
    assert not cache.dirty

    cache.put(2024, 2, 3)
    assert cache.dirty
    cache.save()

    assert cache.as_dict() == {"2024-01": 5, "2024-02": 3}
    assert list(tmp_path.iterdir()) == []
