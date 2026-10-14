#!/usr/bin/env bash
# Launch the web console (dyodrone-gui) in your browser.
#
# Usage: runners/launch_web.sh [--dronekit] [dyodrone-gui options...]
#   (no option)  Python 3.12 environment with the dyopilot driver and voice mode
#                (.venv-dyopilot; installs the dyopilot and voice extras)
#   --dronekit   Python 3.7 environment with the DroneKit driver (.venv-dronekit)
#   other options go to dyodrone-gui, e.g. `--port 9000 --no-browser`
#
# The environment is created and the package installed on first use.
# Override interpreters with PYTHON312 / PYTHON37.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
    sed -n '2,11p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
fi

if [ "${1:-}" = "--dronekit" ]; then
    shift
    find_python37 || true
    ensure_venv dronekit "${PYTHON37:-python3.7}" dronekit
else
    ensure_venv dyopilot "${PYTHON312:-python3.12}" dyopilot,voice
fi

exec "$VENV/bin/dyodrone-gui" "$@"
