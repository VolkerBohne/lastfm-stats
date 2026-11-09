---
name: run-lastfm-stats
description: Build, run, test and drive lastfm-stats - the Last.fm CLI/library and its Home Assistant integration. Use when asked to run or start the CLI, call collect_year_stats, start Home Assistant with the integration, read its sensor states, take a screenshot of the dashboard / apexcharts card, or run the unit and HA tests.
---

lastfm-stats is a Python library + CLI (`lastfm_stats/`) and a Home Assistant
custom integration (`custom_components/lastfm_stats/`). Agents drive it with
`.claude/skills/run-lastfm-stats/driver.py` (offline library calls; a real HA
instance in the background whose sensor states it reads from the recorder DB)
and `.claude/skills/run-lastfm-stats/screenshot.py` (headless Chromium
screenshot of a dashboard built from the README card examples).

All paths are relative to the repo root (the directory with `pyproject.toml`).

## Prerequisites

Verified on Debian 12 (bookworm, arm64) with Python 3.11. Chromium for
screenshots needs these libraries (`playwright install-deps` fails on Debian,
it asks for Ubuntu font packages):

```bash
sudo apt-get install -y libglib2.0-0 libnspr4 libnss3 libatk1.0-0 libdbus-1-3 libx11-6 libxcomposite1 libxdamage1 libxext6 libxfixes3 libxrandr2 libgbm1 libxcb1 libxkbcommon0 libasound2 libatspi2.0-0 fonts-dejavu-core
```

## Setup

```bash
bash .claude/skills/run-lastfm-stats/setup.sh
```

Creates `/tmp/lastfm-tools` (uv, Playwright + Chromium), `.venv` (library,
CLI, unit tests) and `.venv-ha` (Python 3.13 via uv, Home Assistant, HA tests,
the frontend and the packages HA's frontend needs under `--skip-pip`). First
run takes about 5 minutes; most of it is the ~50 MB frontend wheel. Re-running
is safe.

Credentials (the CLI and all `ha-*` commands make **live** Last.fm requests;
`offline` and the tests do not):

```bash
cp .env.example .env   # then set LASTFM_USERNAME and LASTFM_API_KEY
```

## Run (agent path)

### Library internals - no API key, no HA

Most changes touch `lastfm_stats/` (`service.py`, `cache.py`, `api.py`). Call
`collect_year_stats` with a fake client that answers like Last.fm (one scrobble
per day) and prints every request, run twice against one in-memory cache:

```bash
.venv/bin/python .claude/skills/run-lastfm-stats/driver.py offline --now 2026-11-02T12:00:00+00:00
```

Expected: `run 1: 12 requests` (getInfo + one count per month), `run 2: 3
requests` (October and November are not settled yet), and `cache:` with
2026-01 … 2026-09.

### CLI - live

```bash
.venv/bin/lastfm-stats --json
.venv/bin/lastfm-stats --year 2025 --no-cache --json
```

### Home Assistant integration - live

```bash
.venv-ha/bin/python .claude/skills/run-lastfm-stats/driver.py ha-start
.venv-ha/bin/python .claude/skills/run-lastfm-stats/driver.py ha-states
/tmp/lastfm-tools/bin/python .claude/skills/run-lastfm-stats/screenshot.py
.venv-ha/bin/python .claude/skills/run-lastfm-stats/driver.py ha-stop
```

`ha-start` prints `READY` after the integration's first update (~7 s). It runs
`hass --skip-pip` in the background with a config entry written directly to
`.storage` (no UI flow), the recorder, history, and a YAML dashboard
`/lastfm-stats` whose cards are **the two ```yaml card examples from
README.md** (user `rj` replaced by yours). So a screenshot checks the
documented YAML, and editing the README changes the dashboard.

| command | what it does |
|---|---|
| `driver.py ha-start [--language de] [--interval 30]` | start HA on :8123, wait for the first update, exit 1 on failure |
| `driver.py ha-states` | latest state of every `sensor.lastfm_*` (with `months`) and the cached months in the store |
| `screenshot.py [--path /lastfm-stats/0] [--dark]` | onboards HA on first use (user `driver`), loads apexcharts-card v2.1.2 into `www/`, saves the screenshot; prints bar count, HTTP errors, page errors |
| `driver.py ha-stop [--keep]` | stop HA; without `--keep` delete the config dir (it holds the API key) |

Artifacts: config dir `/tmp/lastfm-stats-ha/` (`run.log`,
`home-assistant_v2.db`, `.storage/lastfm_stats.01DRIVERENTRY`,
`dashboard.yaml`); screenshots `/tmp/lastfm-stats-shots/dashboard.png`, or
`failed.png` if the chart did not render.

Iterating on the integration or the README cards: `ha-stop --keep` then
`ha-start` (rewrites `configuration.yaml` and `dashboard.yaml`, keeps the
config entry, the store and the onboarded user), then `screenshot.py` again.

## Run (human path)

`.venv/bin/lastfm-stats` prints the table. For HA, `ha-start` leaves a normal
instance at http://127.0.0.1:8123 (login `driver` / `driver-password` once
`screenshot.py` has onboarded it).

## Test

```bash
.venv/bin/pytest
.venv-ha/bin/pytest tests_ha
```

52 and 19 tests pass. Both mock all HTTP; neither contacts Last.fm.

## Gotchas

- **No frontend package → recovery mode.** `hass --skip-pip` without
  `home-assistant-frontend` updates the integration once, logs `Detected that
  frontend did not load. Activating recovery mode`, and restarts without custom
  integrations or recorder. Looks like success in the log; `ha-states` then
  finds nothing. `setup.sh` installs the pinned frontend.
- **Frontend hangs on "Loading data"** with auth OK and no console errors:
  `get_services` fails server-side because validating `services.yaml` selectors
  imports `conversation`/`tts`/`camera`, whose packages (`hassil`, `turbojpeg`,
  `mutagen`, `haffmpeg`, `pymicro_vad`, `pyspeex_noise`) `--skip-pip` never
  installs. Playwright only reports `page error: Object`; the real error is in
  `run.log` under `Error handling message: Unknown error`.
- **Hidden apexcharts series still scale the axis.** A header-only series
  (`in_chart: false`) with recorder history pushed the y-axis to the yearly
  total and flattened the bars; a separate hidden `yaxis_id` did not help. The
  README example therefore uses `show_states: false`. Without `history:` in the
  config the bug is invisible (the history request 404s) - keep `history:` in
  the driver config.
- **apexcharts `yaxis.decimals: 0` does not round the labels** (shows 464.2);
  the README uses `apex_config.labels.formatter` instead.
- **`wait_for_selector` on the bars** must use `state="attached"`: apexcharts
  adds invisible bar paths, and the default `visible` check times out on a
  rendered chart.
- **Don't `pkill -f "hass -c ..."`** - the pattern matches the agent's own
  shell command line and kills it (exit 144). The driver stops HA via
  `/tmp/lastfm-stats-ha/driver.pid`.
- **HA tests: `freezer.tick()` does not fire coordinator timers.** They run on
  the event-loop clock; use `async_fire_time_changed(hass, dt_util.utcnow() +
  delta)` (see `tests_ha/test_init.py`). With `freezer.tick` plus a bare
  `async_fire_time_changed(hass)` the test passed or failed depending on the
  installed HA packages.
- **Moving the repo breaks the venvs**: script shebangs and the editable
  install keep the old path. Re-run `setup.sh` after deleting `.venv`/`.venv-ha`.
- `page error: Transition was skipped. New ViewTransition started` in the
  screenshot output is harmless.

## Troubleshooting

- **`ha-states`: `no lastfm sensors recorded yet`** - HA fell into recovery
  mode: `grep "recovery mode" /tmp/lastfm-stats-ha/run.log`. Run `setup.sh`.
- **`chart did not render; see /tmp/lastfm-stats-shots/failed.png`** showing
  the HA logo and "Loading data" - see the "Loading data" gotcha; check
  `grep -A120 "Error handling message" /tmp/lastfm-stats-ha/run.log | grep "No module named"`
  and install that package at the version in HA's `package_constraints.txt`.
- **`already running (pid N); run ha-stop first`** - a previous `ha-start` is
  still up; `driver.py ha-stop` (or `--keep`).
