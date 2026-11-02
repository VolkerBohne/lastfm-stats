from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lastfm_stats.const import DOMAIN
from lastfm_stats import LastFmClient

pytest_plugins = "pytest_homeassistant_custom_component"

NOW = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
API_KEY = "0123456789abcdef0123456789abcdef"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


class FakeLastFm:
    """Replaces the Last.fm requests of LastFmClient and records them."""

    def __init__(self):
        self.timestamps = []
        self.playcount = 75970
        self.error = None
        self.requests = []

    def add(self, *moments):
        self.timestamps.extend(int(moment.timestamp()) for moment in moments)

    def get_user_info(self, client):
        self.requests.append("user.getInfo")
        if self.error is not None:
            raise self.error
        return {"username": "RJ", "playcount": self.playcount}

    def count_scrobbles(self, client, from_ts, to_ts):
        self.requests.append("count")
        if self.error is not None:
            raise self.error
        return sum(1 for ts in self.timestamps if from_ts <= ts < to_ts)


@pytest.fixture
def lastfm():
    fake = FakeLastFm()
    with (
        patch.object(LastFmClient, "get_user_info", autospec=True, side_effect=fake.get_user_info),
        patch.object(LastFmClient, "count_scrobbles", autospec=True, side_effect=fake.count_scrobbles),
    ):
        yield fake


@pytest.fixture
def config_entry():
    return MockConfigEntry(
        domain=DOMAIN,
        title="Last.fm RJ",
        unique_id="rj",
        data={"username": "RJ", "api_key": API_KEY},
    )
