"""Screenshot the README dashboard of a running driver HA instance.

Needs a Playwright venv (see SKILL.md) and `driver.py ha-start` first:

    $PW/bin/python .claude/skills/run-lastfm-stats/screenshot.py

Onboards HA through its REST API on first use (user driver/driver), stores
the tokens in <config>/driver-token.json, downloads apexcharts-card.js into
<config>/www and saves the screenshot to /tmp/lastfm-stats-shots/.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8123"
CLIENT_ID = f"{BASE}/"
APEXCHARTS_URL = (
    "https://github.com/RomRider/apexcharts-card/releases/download/v2.1.2/apexcharts-card.js"
)


def request(path: str, data: dict | None = None, *, token: str | None = None, form: bool = False):
    headers = {}
    body = None
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE + path, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        text = response.read().decode()
    return json.loads(text) if text else None


def onboard(ha_dir: Path) -> dict:
    token_file = ha_dir / "driver-token.json"
    if token_file.exists():
        tokens = json.loads(token_file.read_text())
        refreshed = request(
            "/auth/token",
            {"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"],
             "client_id": CLIENT_ID},
            form=True,
        )
        tokens.update(refreshed)
    else:
        user = request(
            "/api/onboarding/users",
            {"client_id": CLIENT_ID, "name": "Driver", "username": "driver",
             "password": "driver-password", "language": "en"},
        )
        tokens = request(
            "/auth/token",
            {"grant_type": "authorization_code", "code": user["auth_code"],
             "client_id": CLIENT_ID},
            form=True,
        )
        access = tokens["access_token"]
        request("/api/onboarding/core_config", {}, token=access)
        request("/api/onboarding/analytics", {}, token=access)
        request("/api/onboarding/integration",
                {"client_id": CLIENT_ID, "redirect_uri": f"{BASE}/?auth_callback=1"},
                token=access)
    token_file.write_text(json.dumps(tokens))
    return tokens


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("/tmp/lastfm-stats-ha"))
    parser.add_argument("--path", default="/lastfm-stats/0")
    parser.add_argument("--out", type=Path, default=Path("/tmp/lastfm-stats-shots/dashboard.png"))
    parser.add_argument("--dark", action="store_true")
    args = parser.parse_args()

    card_js = args.config / "www" / "apexcharts-card.js"
    if not card_js.exists():
        urllib.request.urlretrieve(APEXCHARTS_URL, card_js)

    tokens = onboard(args.config)
    hass_tokens = {
        "hassUrl": BASE,
        "clientId": CLIENT_ID,
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": "Bearer",
        "expires_in": tokens["expires_in"],
        "expires": int(time.time() * 1000) + tokens["expires_in"] * 1000,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1280, "height": 900},
            color_scheme="dark" if args.dark else "light",
        )
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(f"page error: {e}"))
        page.on(
            "response",
            lambda r: errors.append(f"HTTP {r.status} {r.url}") if r.status >= 400 else None,
        )
        page.add_init_script(
            f"localStorage.setItem('hassTokens', {json.dumps(json.dumps(hass_tokens))});"
        )
        page.goto(BASE + args.path)
        try:
            # Cards render inside shadow roots; Playwright's CSS engine pierces them.
            # state="attached": a header-only series adds an invisible bar path first.
            page.wait_for_selector(
                "apexcharts-card .apexcharts-bar-area", state="attached", timeout=60_000
            )
        except Exception:
            page.screenshot(path=str(args.out.with_name("failed.png")), full_page=True)
            print(f"chart did not render; see {args.out.with_name('failed.png')}")
            for error in errors:
                print(error)
            browser.close()
            return 1
        page.wait_for_timeout(1500)  # chart animation
        page.screenshot(path=str(args.out), full_page=True)
        bars = page.locator("apexcharts-card .apexcharts-bar-area").count()
        browser.close()

    print(f"screenshot {args.out} ({bars} bars)")
    for error in errors:
        print(error)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
