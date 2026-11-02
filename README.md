# lastfm-stats

Small Python CLI that shows a Last.fm user's all-time scrobble count and a
month-by-month breakdown for a calendar year (current year by default).
It also ships as a [Home Assistant integration](#home-assistant) that shows
this year's scrobbles per month on a dashboard.

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

Month              Plays
------------ ------------
January              320
February             280
...
```

Useful options:

```bash
lastfm-stats --year 2024       # a previous calendar year
lastfm-stats --user some_user  # override LASTFM_USERNAME
lastfm-stats --json            # machine-readable output
lastfm-stats --refresh         # ignore cached months and fetch them again
lastfm-stats --no-cache        # don't read or write the cache
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
- Each month is counted with a single `user.getRecentTracks` request
  (`limit=1`, `from`/`to` set to the month's UTC bounds): Last.fm reports the
  number of scrobbles in that range as `recenttracks.@attr.total`, so no
  scrobbles have to be paged through. `from` is inclusive and `to` exclusive.
- Monthly counts are cached per user once a month is settled (ended more than
  14 days ago, since Last.fm accepts scrobbles up to two weeks late). Cached
  months cost no request at all, so a past year costs a single `user.getInfo`
  request after its first run, and the current year one request plus one per
  unsettled month (usually three in total).
- Rate-limit/network/server errors are retried with exponential backoff.

The app prints which month it is counting on stderr unless `--json` is used.
Month boundaries follow UTC, as required by the Last.fm API.

## Cache

Cached counts live in `$XDG_CACHE_HOME/lastfm-stats/<username>.json`
(default `~/.cache/lastfm-stats/`). Set `LASTFM_STATS_CACHE_DIR` to use a
different directory. Use `--refresh` if you deleted or edited scrobbles in
an already-cached month, or simply delete the file.

The file maps `YYYY-MM` to that month's play count:

```json
{
  "version": 1,
  "months": {
    "2024-01": 530,
    "2024-02": 416
  }
}
```

The current month and the month before it (until it is 14 days old) are never
cached, so recent scrobbles are always picked up.

## Troubleshooting

- **`Last.fm error 10: Invalid API key`**: an API key is 32 *lowercase*
  hexadecimal characters (`0-9`, `a-f`). Check `LASTFM_API_KEY` for typos,
  uppercase letters or stray characters, or copy it again from
  <https://www.last.fm/api/accounts>. An exported `LASTFM_API_KEY` overrides
  the one in `.env`.
- **`Last.fm error 6: User not found`**: check `LASTFM_USERNAME` or `--user`.
- **Numbers for an old month look wrong** after deleting scrobbles: run with
  `--refresh`.

## Home Assistant

The `custom_components/lastfm_stats` integration shows this year's scrobbles
per month as sensors. It reuses this library, so each update costs about three
Last.fm requests (`user.getInfo` plus one per unsettled month).

### Install via HACS

1. In HACS open **⋮ → Custom repositories**, add
   `https://github.com/VolkerBohne/lastfm-stats` with type **Integration**.
2. Search for **Last.fm Stats**, download it and restart Home Assistant.

Home Assistant installs the `lastfm-stats` library itself from this
repository's release archive (see `requirements` in `manifest.json`).

**Manual install:** copy `custom_components/lastfm_stats` into the
`custom_components` folder of your Home Assistant configuration directory and
restart Home Assistant.

### Set up

**Settings → Devices & services → Add integration → Last.fm Stats**, then
enter your Last.fm username and API key (see [Authentication](#authentication)).
Under **Configure** you can change the update interval (default 60 minutes,
15 to 1440).

### Entities

Each configured user gets one device with these sensors (`<user>` is the
lowercase username). Entity IDs are fixed and do not depend on the UI language.

| Entity | State |
|---|---|
| `sensor.lastfm_<user>_year_scrobbles` | Scrobbles in the current year. Attributes: `year`, `months` (`{"January": 499, ...}`, same as `--json`) |
| `sensor.lastfm_<user>_total_scrobbles` | All-time scrobbles |
| `sensor.lastfm_<user>_month_01` … `_month_12` | Scrobbles in that month of the current year (future months are 0) |

The year switches automatically on January 1st (UTC).

Settled monthly counts are cached with Home Assistant's storage helper in
`<config>/.storage/lastfm_stats.<entry_id>`. The file is part of Home Assistant
backups and is deleted when the integration is removed.

### Dashboard

A bar chart per month needs [apexcharts-card](https://github.com/RomRider/apexcharts-card),
which you install from HACS (**Frontend**) first. Replace `rj` with your username:

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: Scrobbles per month
  show_states: true
graph_span: 1y
span:
  start: year
yaxis:
  - min: 0
    decimals: 0
series:
  - entity: sensor.lastfm_rj_year_scrobbles
    name: Scrobbles
    type: column
    data_generator: |
      const year = entity.attributes.year;
      return Object.values(entity.attributes.months).map((count, index) => [
        new Date(year, index, 15).getTime(),
        count,
      ]);
```

Without additional cards, an entities card lists the months:

```yaml
type: entities
title: Scrobbles this year
entities:
  - sensor.lastfm_rj_year_scrobbles
  - sensor.lastfm_rj_month_01
  - sensor.lastfm_rj_month_02
  - sensor.lastfm_rj_month_03
  - sensor.lastfm_rj_month_04
  - sensor.lastfm_rj_month_05
  - sensor.lastfm_rj_month_06
  - sensor.lastfm_rj_month_07
  - sensor.lastfm_rj_month_08
  - sensor.lastfm_rj_month_09
  - sensor.lastfm_rj_month_10
  - sensor.lastfm_rj_month_11
  - sensor.lastfm_rj_month_12
```

## Tests

```bash
pytest
```

Tests mock all HTTP calls; they never contact Last.fm.

The Home Assistant tests need Python 3.13 or newer and a separate virtualenv:

```bash
python3.13 -m venv .venv-ha
.venv-ha/bin/pip install -e .[ha-test]
.venv-ha/bin/pytest tests_ha
```

## Releasing

Home Assistant installs the library from the release archive named in
`custom_components/lastfm_stats/manifest.json`, so a release must keep these
in sync:

1. Bump `version` in `pyproject.toml`, `lastfm_stats/__init__.py` and
   `manifest.json`.
2. Point the URL in `manifest.json` → `requirements` at the new tag
   (`.../archive/refs/tags/vX.Y.Z.zip`).
3. After merging, publish a GitHub release with the tag `vX.Y.Z`. HACS offers
   that release, and without the tag the requirement cannot be installed.
