from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from typing import Any

import requests

API_URL = "https://ws.audioscrobbler.com/2.0/"
PAGE_SIZE = 200
MAX_RETRIES = 4
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
RETRY_ERROR_CODES = {16, 29}


class LastFmError(Exception):
    """Raised when Last.fm cannot be queried successfully."""

    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class LastFmClient:
    def __init__(
        self,
        api_key: str,
        username: str,
        *,
        session: requests.Session | None = None,
        page_size: int = PAGE_SIZE,
        request_delay: float = 0.2,
        timeout: float = 15.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api_key = api_key
        self.username = username
        self.page_size = page_size
        self.request_delay = request_delay
        self.timeout = timeout
        self._sleep = sleep
        self._session = session or requests.Session()

    def get_user_info(self) -> dict[str, Any]:
        payload = self._request("user.getInfo", user=self.username)
        user = payload.get("user")
        if not isinstance(user, dict):
            raise LastFmError("Unexpected response from user.getInfo")

        try:
            playcount = int(user["playcount"])
        except (KeyError, TypeError, ValueError) as exc:
            raise LastFmError("Last.fm response did not include a play count") from exc

        name = user.get("name") or self.username
        return {"username": str(name), "playcount": playcount}

    def iter_recent_tracks(
        self,
        from_ts: int | None = None,
        to_ts: int | None = None,
        *,
        progress: Callable[[int, int | None], None] | None = None,
        max_pages: int = 10_000,
    ) -> Iterator[dict[str, Any]]:
        page = 1
        while page <= max_pages:
            params: dict[str, Any] = {
                "user": self.username,
                "limit": self.page_size,
                "page": page,
            }
            if from_ts is not None:
                params["from"] = int(from_ts)
            if to_ts is not None:
                params["to"] = int(to_ts)

            payload = self._request("user.getRecentTracks", **params)
            recent = payload.get("recenttracks")
            if not isinstance(recent, dict):
                recent = {}

            raw_tracks = _as_list(recent.get("track"))
            total_pages = _as_int(_as_dict(recent.get("@attr")).get("totalPages"))

            if progress is not None:
                progress(page, total_pages)

            for track in raw_tracks:
                if not isinstance(track, dict) or _is_now_playing(track):
                    continue
                timestamp = track_timestamp(track)
                if timestamp is None:
                    continue
                if from_ts is not None and timestamp < from_ts:
                    continue
                if to_ts is not None and timestamp > to_ts:
                    continue
                yield track

            if not raw_tracks or len(raw_tracks) < self.page_size:
                break
            if total_pages is not None and page >= total_pages:
                break

            page += 1
            if self.request_delay:
                self._sleep(self.request_delay)

    def _request(self, method: str, **params: Any) -> dict[str, Any]:
        query = {
            "method": method,
            "api_key": self.api_key,
            "format": "json",
            **params,
        }
        headers = {"User-Agent": "lastfm-stats/0.1"}

        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self._session.get(
                    API_URL,
                    params=query,
                    headers=headers,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                if attempt >= MAX_RETRIES:
                    raise LastFmError(f"Network error talking to Last.fm: {exc}") from exc
                self._sleep(_backoff(attempt))
                continue

            if response.status_code in RETRY_STATUS_CODES:
                if attempt >= MAX_RETRIES:
                    raise LastFmError(
                        f"Last.fm request failed with HTTP {response.status_code}"
                    )
                self._sleep(_backoff(attempt))
                continue

            try:
                payload = response.json()
            except ValueError as exc:
                raise LastFmError(
                    f"Last.fm returned invalid JSON (HTTP {response.status_code})"
                ) from exc

            if not isinstance(payload, dict):
                raise LastFmError("Last.fm returned an unexpected response")

            if "error" in payload:
                code = _as_int(payload.get("error"))
                message = str(payload.get("message") or "Unknown Last.fm error")
                if code in RETRY_ERROR_CODES and attempt < MAX_RETRIES:
                    self._sleep(_backoff(attempt))
                    continue
                if code is None:
                    raise LastFmError(message)
                raise LastFmError(f"Last.fm error {code}: {message}", code)

            if not response.ok:
                raise LastFmError(
                    f"Last.fm request failed with HTTP {response.status_code}"
                )

            return payload

        raise LastFmError("Last.fm request failed after retries")


def track_timestamp(track: dict[str, Any]) -> int | None:
    if _is_now_playing(track):
        return None
    date = track.get("date")
    if isinstance(date, dict):
        return _as_int(date.get("uts"))
    return None


def _is_now_playing(track: dict[str, Any]) -> bool:
    attr = _as_dict(track.get("@attr"))
    return str(attr.get("nowplaying", "")).lower() == "true"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _backoff(attempt: int) -> float:
    return min(0.5 * (2**attempt), 8.0)
