"""Last.fm listening statistics."""

from .api import LastFmClient, LastFmError, track_timestamp
from .stats import aggregate_by_month

__all__ = ["LastFmClient", "LastFmError", "aggregate_by_month", "track_timestamp"]
__version__ = "0.1.0"
