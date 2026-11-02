import pytest
import requests

from lastfm_stats.api import (
    LastFmClient,
    LastFmError,
    track_timestamp,
)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.ok = status_code < 400

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(params)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def dated_track(uts, name="Song"):
    return {"name": name, "date": {"uts": str(uts)}}


def test_get_user_info_returns_name_and_playcount():
    session = FakeSession(
        [FakeResponse({"user": {"name": "rj", "playcount": "54189"}})]
    )
    client = LastFmClient("key", "rj", session=session)

    info = client.get_user_info()

    assert info == {"username": "rj", "playcount": 54189}
    assert session.calls[0]["method"] == "user.getInfo"
    assert session.calls[0]["user"] == "rj"
    assert session.calls[0]["api_key"] == "key"


def test_get_user_info_rejects_unexpected_response():
    session = FakeSession([FakeResponse({"user": None})])
    client = LastFmClient("key", "rj", session=session)

    with pytest.raises(LastFmError, match="Unexpected response"):
        client.get_user_info()


def test_iter_recent_tracks_paginates_and_skips_now_playing():
    first_page = {
        "recenttracks": {
            "track": [
                {"@attr": {"nowplaying": "true"}, "name": "Live"},
                dated_track(100, "A"),
                dated_track(90, "B"),
            ],
            "@attr": {"page": "1", "totalPages": "2"},
        }
    }
    second_page = {
        "recenttracks": {
            "track": [dated_track(80, "C")],
            "@attr": {"page": "2", "totalPages": "2"},
        }
    }
    session = FakeSession([FakeResponse(first_page), FakeResponse(second_page)])
    client = LastFmClient("key", "rj", session=session, page_size=2, request_delay=0)
    progress = []

    tracks = list(
        client.iter_recent_tracks(
            from_ts=50,
            to_ts=110,
            progress=lambda page, total: progress.append((page, total)),
        )
    )

    assert [track["name"] for track in tracks] == ["A", "B", "C"]
    assert progress == [(1, 2), (2, 2)]
    assert session.calls[0]["from"] == 50
    assert session.calls[0]["to"] == 110
    assert [call["page"] for call in session.calls] == [1, 2]


def test_iter_recent_tracks_stops_on_short_page_without_total_pages():
    page = {
        "recenttracks": {
            "track": [dated_track(100)],
            "@attr": {"page": "1"},
        }
    }
    session = FakeSession([FakeResponse(page)])
    client = LastFmClient("key", "rj", session=session, page_size=2, request_delay=0)

    tracks = list(client.iter_recent_tracks())

    assert len(tracks) == 1
    assert len(session.calls) == 1


def test_count_scrobbles_reads_total_from_single_request():
    page = {
        "recenttracks": {
            "track": [dated_track(100)],
            "@attr": {"page": "1", "totalPages": "557", "total": "557"},
        }
    }
    session = FakeSession([FakeResponse(page)])
    client = LastFmClient("key", "rj", session=session)

    assert client.count_scrobbles(50, 110) == 557
    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["method"] == "user.getRecentTracks"
    assert (call["from"], call["to"], call["limit"], call["page"]) == (50, 110, 1, 1)


def test_count_scrobbles_handles_empty_range():
    page = {"recenttracks": {"track": [], "@attr": {"total": "0"}}}
    client = LastFmClient("key", "rj", session=FakeSession([FakeResponse(page)]))

    assert client.count_scrobbles(50, 110) == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"recenttracks": {"track": [], "@attr": {}}},
        {"recenttracks": {"track": [], "@attr": {"total": "many"}}},
        {"recenttracks": {"track": [], "@attr": {"total": "-1"}}},
        {"recenttracks": None},
    ],
)
def test_count_scrobbles_rejects_missing_total(payload):
    client = LastFmClient("key", "rj", session=FakeSession([FakeResponse(payload)]))

    with pytest.raises(LastFmError, match="scrobble total"):
        client.count_scrobbles(50, 110)


def test_count_scrobbles_propagates_api_errors():
    session = FakeSession([FakeResponse({"error": 6, "message": "User not found"})])
    client = LastFmClient("key", "rj", session=session)

    with pytest.raises(LastFmError) as exc_info:
        client.count_scrobbles(50, 110)

    assert exc_info.value.code == 6


def test_request_retries_on_rate_limit_error():
    session = FakeSession(
        [
            FakeResponse({"error": 29, "message": "Rate limit exceeded"}),
            FakeResponse({"user": {"name": "rj", "playcount": 1}}),
        ]
    )
    sleeps = []
    client = LastFmClient("key", "rj", session=session, sleep=sleeps.append)

    info = client.get_user_info()

    assert info["playcount"] == 1
    assert sleeps == [0.5]


def test_request_does_not_retry_invalid_api_key():
    session = FakeSession(
        [FakeResponse({"error": 10, "message": "Invalid API key"})]
    )
    sleeps = []
    client = LastFmClient("key", "rj", session=session, sleep=sleeps.append)

    with pytest.raises(LastFmError) as exc_info:
        client.get_user_info()

    assert exc_info.value.code == 10
    assert "Invalid API key" in str(exc_info.value)
    assert sleeps == []


def test_request_retries_network_errors():
    session = FakeSession(
        [
            requests.ConnectionError("boom"),
            FakeResponse({"user": {"name": "rj", "playcount": 2}}),
        ]
    )
    sleeps = []
    client = LastFmClient("key", "rj", session=session, sleep=sleeps.append)

    info = client.get_user_info()

    assert info["playcount"] == 2
    assert sleeps == [0.5]


def test_track_timestamp():
    assert track_timestamp(dated_track(123)) == 123
    assert track_timestamp({"@attr": {"nowplaying": "true"}}) is None
    assert track_timestamp({"name": "no date"}) is None
