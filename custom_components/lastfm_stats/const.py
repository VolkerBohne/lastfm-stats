"""Constants for the Last.fm Stats integration."""

from __future__ import annotations

import logging

DOMAIN = "lastfm_stats"
LOGGER = logging.getLogger(__package__)

# Minutes between updates. With a filled cache an update costs about three
# Last.fm requests, so even the minimum stays far below the API rate limit.
DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 15
MAX_SCAN_INTERVAL = 1440

STORAGE_VERSION = 1

# Last.fm error codes, see https://www.last.fm/api/errorcodes
ERROR_INVALID_API_KEY = 10
ERROR_USER_NOT_FOUND = 6
