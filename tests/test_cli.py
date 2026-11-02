import argparse
import json
from datetime import datetime, timezone

import pytest

from lastfm_stats import cli
from lastfm_stats.api import LastFmError


def namespace(**kwargs):
    defaults = {"user": None, "year": None, "json": False}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def test_load_config_requires_both_values():
    with pytest.raises(cli.ConfigError) as exc_info:
        cli.load_config(namespace(), {})

    message = str(exc_info.value)
    assert "LASTFM_USERNAME" in message
    assert "LASTFM_API_KEY" in message


def test_load_config_reads_environment():
    username, api_key = cli.load_config(
        namespace(),
        {"LASTFM_USERNAME": "rj", "LASTFM_API_KEY": "secret"},
    )

    assert username == "rj"
    assert api_key == "secret"


def test_load_config_prefers_user_argument():
    username, api_key = cli.load_config(
        namespace(user="override"),
        {"LASTFM_USERNAME": "rj", "LASTFM_API_KEY": "secret"},
    )

    assert username == "override"
    assert api_key == "secret"


def test_year_bounds_for_past_year():
    start, end = cli.year_bounds(2024)

    assert start == int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp())
    assert end == int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())


def test_year_bounds_rejects_future_year():
    with pytest.raises(ValueError):
        cli.year_bounds(cli.current_utc_year() + 1)


def test_build_payload_has_named_months():
    counts = {month: month for month in range(1, 13)}

    payload = cli.build_payload("rj", 2026, 1000, 78, counts)

    assert payload == {
        "username": "rj",
        "year": 2026,
        "total_plays": 1000,
        "year_plays": 78,
        "months": {
            "January": 1,
            "February": 2,
            "March": 3,
            "April": 4,
            "May": 5,
            "June": 6,
            "July": 7,
            "August": 8,
            "September": 9,
            "October": 10,
            "November": 11,
            "December": 12,
        },
    }


def test_render_table_includes_all_months_for_past_year():
    year = cli.current_utc_year() - 1
    counts = {month: month * 100 for month in range(1, 13)}

    table = cli.render_table("rj", year, 12345, 7800, counts)

    assert "Last.fm stats for rj" in table
    assert "12,345" in table
    assert "January" in table
    assert "December" in table
    assert "1,200" in table


def test_main_missing_configuration_returns_2(capsys):
    code = cli.main([], {})

    assert code == 2
    assert "Missing required configuration" in capsys.readouterr().err


def test_main_outputs_json(monkeypatch, capsys):
    year = cli.current_utc_year()
    counts = {month: month for month in range(1, 13)}

    def fake_collect(username, api_key, requested_year, *, show_progress):
        assert username == "rj"
        assert api_key == "secret"
        assert requested_year == year
        assert show_progress is False
        return {"username": "rj", "playcount": 9999}, counts, 78

    monkeypatch.setattr(cli, "collect_stats", fake_collect)

    code = cli.main(
        ["--json"],
        {"LASTFM_USERNAME": "rj", "LASTFM_API_KEY": "secret"},
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["username"] == "rj"
    assert payload["year"] == year
    assert payload["total_plays"] == 9999
    assert payload["year_plays"] == 78
    assert payload["months"]["December"] == 12


def test_main_autoloads_dotenv_from_cwd(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text(
        "LASTFM_USERNAME=rj\nLASTFM_API_KEY=secret\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LASTFM_USERNAME", raising=False)
    monkeypatch.delenv("LASTFM_API_KEY", raising=False)
    captured = {}

    def fake_collect(username, api_key, requested_year, *, show_progress):
        captured["username"] = username
        captured["api_key"] = api_key
        counts = {month: 0 for month in range(1, 13)}
        return {"username": username, "playcount": 1}, counts, 0

    monkeypatch.setattr(cli, "collect_stats", fake_collect)

    code = cli.main(["--json"])

    assert code == 0
    assert captured == {"username": "rj", "api_key": "secret"}


def test_main_explicit_environment_ignores_dotenv(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text(
        "LASTFM_USERNAME=file\nLASTFM_API_KEY=file\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    captured = {}

    def fake_collect(username, api_key, requested_year, *, show_progress):
        captured["username"] = username
        captured["api_key"] = api_key
        counts = {month: 0 for month in range(1, 13)}
        return {"username": username, "playcount": 1}, counts, 0

    monkeypatch.setattr(cli, "collect_stats", fake_collect)

    code = cli.main(
        ["--json"],
        {"LASTFM_USERNAME": "explicit", "LASTFM_API_KEY": "explicit"},
    )

    assert code == 0
    assert captured == {"username": "explicit", "api_key": "explicit"}


def test_main_handles_lastfm_error(monkeypatch, capsys):
    def fake_collect(*args, **kwargs):
        raise LastFmError("Last.fm error 10: Invalid API key", code=10)

    monkeypatch.setattr(cli, "collect_stats", fake_collect)

    code = cli.main(
        [],
        {"LASTFM_USERNAME": "rj", "LASTFM_API_KEY": "bad"},
    )

    assert code == 1
    assert "Invalid API key" in capsys.readouterr().err
