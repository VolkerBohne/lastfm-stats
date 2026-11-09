#!/usr/bin/env bash
# Create the environments the run-lastfm-stats skill uses. Run from the repo root.
#   TOOLS (default /tmp/lastfm-tools): uv + Playwright/Chromium for screenshots
#   .venv     Python 3.11+: library, CLI, unit tests
#   .venv-ha  Python 3.13 (via uv): Home Assistant, HA tests, the driver's ha-* commands
set -euo pipefail

TOOLS=${TOOLS:-/tmp/lastfm-tools}
UV="$TOOLS/bin/uv"

if [ ! -x "$TOOLS/bin/playwright" ]; then
  python3 -m venv "$TOOLS"
  "$TOOLS/bin/pip" install -q uv playwright
fi
"$TOOLS/bin/playwright" install chromium >/dev/null

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -e '.[dev]'

"$UV" python install 3.13 >/dev/null 2>&1
if [ ! -x .venv-ha/bin/python ]; then
  "$UV" venv -q -p 3.13 .venv-ha
fi
"$UV" pip install -q -p .venv-ha/bin/python -e '.[ha-test]'

# `hass --skip-pip` does not install integration requirements. Without these the
# frontend falls into recovery mode (no hass_frontend) or hangs on "Loading data"
# (get_services imports conversation/tts/camera). Pins come from HA itself.
CONSTRAINTS=$(.venv-ha/bin/python -c 'import homeassistant, os; print(os.path.dirname(homeassistant.__file__))')/package_constraints.txt
grep -iE '^(home-assistant-frontend|hassil|home-assistant-intents|PyTurboJPEG|mutagen|ha-ffmpeg|pymicro-vad|pyspeex-noise)==' "$CONSTRAINTS" \
  | xargs "$UV" pip install -q -p .venv-ha/bin/python

echo "ready: $TOOLS, .venv, .venv-ha"
