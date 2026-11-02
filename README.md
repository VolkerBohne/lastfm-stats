# lastfm-stats

Small Python CLI that shows a Last.fm user's all-time scrobble count and a
month-by-month breakdown for a calendar year (current year by default).

## Authentication

Reading public Last.fm stats uses an **API key plus a username**. It does not
use your Last.fm password, so no password is read, stored, or sent by this app.

1. Create an API key at <https://www.last.fm/api/account/create>.
2. Export your username and key:

```bash
export LASTFM_USERNAME=your_lastfm_username
export LASTFM_API_KEY=your_api_key
```

You can use the included `.env.example` as a template:

```bash
cp .env.example .env
# edit .env
```

The app loads `.env` from the current working directory automatically. Variables
that are already exported take precedence over the file. Values may be quoted,
for example `LASTFM_API_KEY="your_api_key"`.

## Install

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
```

For development:

```bash
pip install -e .[dev]
```

## Usage

```bash
lastfm-stats
```

```text
Last.fm stats for rj (2026)

All-time scrobbles :       54,189
Scrobbles in 2026  :        3,214

Month                Plays
------------ -------------
January                320
February               280
...
```

Useful options:

```bash
lastfm-stats --year 2024       # a previous calendar year
lastfm-stats --user some_user  # override LASTFM_USERNAME
lastfm-stats --json            # machine-readable output
python -m lastfm_stats --json  # same without the console script
```

JSON output:

```json
{
  "username": "rj",
  "year": 2026,
  "total_plays": 54189,
  "year_plays": 3214,
  "months": {
    "January": 320,
    "February": 280,
    "...": 0
  }
}
```

## How it works

- `user.getInfo` supplies the all-time play count.
- `user.getRecentTracks` is paginated (200 per page) from
  `January 1 00:00 UTC` through the end of the selected year.
- The now-playing entry is skipped, and timestamps are bucketed into UTC
  calendar months.
- Requests are rate-limited, and rate-limit/network/server errors are retried
  with exponential backoff.

Because exact monthly counts require reading the year's scrobbles, very large
libraries take a while. The app prints fetch progress on stderr unless `--json`
is used. Month boundaries follow UTC, as required by the Last.fm API.

## Tests

```bash
pytest
```

Tests mock all HTTP calls; they never contact Last.fm.
