"""Drive lastfm-stats: offline library calls and a real Home Assistant instance.

Run from the repo root:

    .venv/bin/python .claude/skills/run-lastfm-stats/driver.py offline
    .venv-ha/bin/python .claude/skills/run-lastfm-stats/driver.py ha-start
    .venv-ha/bin/python .claude/skills/run-lastfm-stats/driver.py ha-states
    .venv-ha/bin/python .claude/skills/run-lastfm-stats/driver.py ha-stop

ha-* commands need LASTFM_USERNAME/LASTFM_API_KEY (environment or ./.env) and
make live Last.fm requests (about 12 on the first update of a fresh instance).
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DEFAULT_HA_DIR = Path("/tmp/lastfm-stats-ha")
ENTRY_ID = "01DRIVERENTRY"

sys.path.insert(0, str(REPO))


# --------------------------------------------------------------------------- offline


class FakeClient:
    """Counts scrobbles in [from, to) like Last.fm and records every request."""

    def __init__(self, timestamps: list[int]) -> None:
        self.timestamps = timestamps
        self.requests: list[str] = []

    def get_user_info(self) -> dict:
        self.requests.append("user.getInfo")
        return {"username": "demo", "playcount": 75970}

    def count_scrobbles(self, from_ts: int, to_ts: int) -> int:
        self.requests.append(f"count {_iso(from_ts)} .. {_iso(to_ts)}")
        return sum(1 for ts in self.timestamps if from_ts <= ts < to_ts)


def cmd_offline(args: argparse.Namespace) -> int:
    from lastfm_stats import MonthCache, collect_year_stats

    now = datetime.fromisoformat(args.now) if args.now else datetime.now(timezone.utc)
    year = args.year or now.year
    # One scrobble per day at noon UTC, so every month has a predictable count.
    start = int(datetime(year, 1, 1, 12, tzinfo=timezone.utc).timestamp())
    timestamps = [start + day * 86400 for day in range(366)]
    cache = MonthCache.from_months({})

    for run in (1, 2):
        client = FakeClient(timestamps)
        stats = collect_year_stats(client, year, cache=cache, now=now)
        print(f"run {run}: {len(client.requests)} requests")
        for request in client.requests:
            print(f"  {request}")
    print(f"year_plays={stats.year_plays} total_plays={stats.total_plays}")
    print("months:", json.dumps(stats.months))
    print("cache:", json.dumps(cache.as_dict()))
    return 0


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M")


# --------------------------------------------------------------------------- Home Assistant


def cmd_ha_start(args: argparse.Namespace) -> int:
    from lastfm_stats.env import merge_dotenv

    ha_dir: Path = args.config
    if _pid(ha_dir):
        print(f"already running (pid {_pid(ha_dir)}); run ha-stop first", file=sys.stderr)
        return 1

    env = merge_dotenv(os.environ, REPO / ".env")
    username, api_key = env.get("LASTFM_USERNAME"), env.get("LASTFM_API_KEY")
    if not username or not api_key:
        print("LASTFM_USERNAME and LASTFM_API_KEY are required (env or .env)", file=sys.stderr)
        return 2

    (ha_dir / ".storage").mkdir(parents=True, exist_ok=True)
    (ha_dir / "custom_components").mkdir(exist_ok=True)
    # HA only serves /local/ (www/) if the folder exists at startup;
    # screenshot.py puts apexcharts-card.js there.
    (ha_dir / "www").mkdir(exist_ok=True)
    (ha_dir / "dashboard.yaml").write_text(_readme_dashboard(username), encoding="utf-8")
    link = ha_dir / "custom_components" / "lastfm_stats"
    if not link.exists():
        link.symlink_to(REPO / "custom_components" / "lastfm_stats")

    (ha_dir / "configuration.yaml").write_text(
        "homeassistant:\n"
        "  name: lastfm-stats driver\n"
        "  time_zone: UTC\n"
        "  country: DE\n"
        f"  language: {args.language}\n"
        "recorder:\n"
        "  commit_interval: 1\n"
        "history:\n"
        "lovelace:\n"
        "  resource_mode: yaml\n"
        "  resources:\n"
        "    - url: /local/apexcharts-card.js\n"
        "      type: module\n"
        "  dashboards:\n"
        "    lastfm-stats:\n"
        "      mode: yaml\n"
        "      filename: dashboard.yaml\n"
        "      title: Last.fm\n"
        "      show_in_sidebar: true\n"
        "logger:\n"
        "  default: warning\n"
        "  logs:\n"
        "    custom_components.lastfm_stats: debug\n",
        encoding="utf-8",
    )
    entries_file = ha_dir / ".storage" / "core.config_entries"
    if not entries_file.exists():
        # Same shape the config flow would store; skips the UI setup.
        entry = {
            "entry_id": ENTRY_ID,
            "version": 1,
            "minor_version": 1,
            "domain": "lastfm_stats",
            "title": f"Last.fm {username}",
            "data": {"username": username, "api_key": api_key},
            "options": {"scan_interval": args.interval} if args.interval else {},
            "pref_disable_new_entities": False,
            "pref_disable_polling": False,
            "source": "user",
            "unique_id": username.lower(),
            "disabled_by": None,
            "discovery_keys": {},
            "subentries": [],
            "created_at": "2026-01-01T00:00:00+00:00",
            "modified_at": "2026-01-01T00:00:00+00:00",
        }
        entries_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "minor_version": 5,
                    "key": "core.config_entries",
                    "data": {"entries": [entry]},
                }
            ),
            encoding="utf-8",
        )

    log_path = ha_dir / "run.log"
    log_path.write_text("", encoding="utf-8")
    hass = Path(sys.executable).with_name("hass")
    with log_path.open("ab") as log:
        process = subprocess.Popen(
            [str(hass), "-c", str(ha_dir), "--skip-pip"],
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    (ha_dir / "driver.pid").write_text(str(process.pid), encoding="utf-8")
    print(f"started hass pid {process.pid}, log {log_path}")

    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        text = log_path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if "Finished fetching lastfm_stats" in line:
                print(line.split("] ", 1)[-1])
                ok = "success: True" in line
                print("READY" if ok else "FAILED (see run.log)")
                return 0 if ok else 1
            if "lastfm_stats" in line and ("Error setting up" in line or "Setup failed" in line):
                print(line)
                return 1
        if process.poll() is not None:
            print(f"hass exited with {process.returncode}; see {log_path}", file=sys.stderr)
            return 1
        time.sleep(0.5)
    print(f"timeout after {args.timeout}s; see {log_path}", file=sys.stderr)
    return 1


def _readme_dashboard(username: str) -> str:
    """Build a dashboard from the card examples in README.md (user rj -> username)."""
    from homeassistant.util import slugify

    readme = (REPO / "README.md").read_text(encoding="utf-8")
    blocks = [
        block.split("\n", 1)[1]
        for block in readme.split("```")
        if block.startswith("yaml\ntype: ")
    ]
    if not blocks:
        raise SystemExit("no ```yaml type: ...``` card examples found in README.md")
    lines = ["views:", "  - title: Last.fm", "    path: '0'", "    cards:"]
    for block in blocks:
        block = block.replace("sensor.lastfm_rj_", f"sensor.lastfm_{slugify(username)}_")
        for index, line in enumerate(block.rstrip("\n").splitlines()):
            prefix = "      - " if index == 0 else "        "
            lines.append(prefix + line if line else "")
    return "\n".join(lines) + "\n"


def cmd_ha_states(args: argparse.Namespace) -> int:
    ha_dir: Path = args.config
    db = ha_dir / "home-assistant_v2.db"
    if not db.exists():
        print(f"no recorder database at {db}; is HA running?", file=sys.stderr)
        return 1
    time.sleep(1.5)  # recorder commit_interval is 1s
    connection = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = connection.execute(
        """
        SELECT m.entity_id, s.state, a.shared_attrs
        FROM states s
        JOIN states_meta m ON m.metadata_id = s.metadata_id
        LEFT JOIN state_attributes a ON a.attributes_id = s.attributes_id
        WHERE m.entity_id LIKE 'sensor.lastfm_%'
          AND s.state_id = (
            SELECT MAX(state_id) FROM states WHERE metadata_id = s.metadata_id
          )
        ORDER BY m.entity_id
        """
    ).fetchall()
    if not rows:
        print("no lastfm sensors recorded yet", file=sys.stderr)
        return 1
    for entity_id, state, attrs in rows:
        attributes = json.loads(attrs or "{}")
        print(f"{entity_id:<40} {state:>8}  {attributes.get('friendly_name', '')}")
        if "months" in attributes:
            print(f"{'':<40} months={json.dumps(attributes['months'])}")

    store = ha_dir / ".storage" / f"lastfm_stats.{ENTRY_ID}"
    if store.exists():
        months = json.loads(store.read_text(encoding="utf-8"))["data"]["months"]
        print(f"store {store.name}: {len(months)} cached months {json.dumps(months)}")
    return 0


def cmd_ha_stop(args: argparse.Namespace) -> int:
    ha_dir: Path = args.config
    pid = _pid(ha_dir)
    if pid:
        os.killpg(pid, signal.SIGTERM)
        for _ in range(60):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.5)
        else:
            os.killpg(pid, signal.SIGKILL)
        print(f"stopped hass pid {pid}")
    (ha_dir / "driver.pid").unlink(missing_ok=True)
    if not args.keep and ha_dir.exists():
        # The config dir holds the API key in .storage/core.config_entries.
        subprocess.run(["rm", "-rf", str(ha_dir)], check=True)
        print(f"removed {ha_dir}")
    return 0


def _pid(ha_dir: Path) -> int | None:
    try:
        pid = int((ha_dir / "driver.pid").read_text(encoding="utf-8"))
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    offline = sub.add_parser("offline", help="call collect_year_stats with a fake client")
    offline.add_argument("--year", type=int)
    offline.add_argument("--now", help="ISO time with offset, e.g. 2026-11-02T12:00:00+00:00")
    offline.set_defaults(func=cmd_offline)

    for name, func, text in (
        ("ha-start", cmd_ha_start, "start HA with the integration and wait for the first update"),
        ("ha-states", cmd_ha_states, "print the lastfm sensor states and the cache store"),
        ("ha-stop", cmd_ha_stop, "stop HA and delete its config dir"),
    ):
        command = sub.add_parser(name, help=text)
        command.add_argument("--config", type=Path, default=DEFAULT_HA_DIR)
        command.set_defaults(func=func)
    start = sub.choices["ha-start"]
    start.add_argument("--language", default="en")
    start.add_argument("--interval", type=int, help="scan_interval option in minutes")
    start.add_argument("--timeout", type=int, default=120)
    sub.choices["ha-stop"].add_argument("--keep", action="store_true", help="keep the config dir")

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
