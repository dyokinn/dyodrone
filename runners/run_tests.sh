#!/usr/bin/env bash
# Run the test suite on every supported Python.
#
# Usage: runners/run_tests.sh [--all] [--env NAME]... [-- PYTEST_ARGS...]
#   (no option)  unit tests on Python 3.12 (dyopilot) and 3.7 (dronekit), ~10 s
#   --all        also the live-simulator tests on both Pythons (~3 min, needs the
#                ArduCopter SITL binary) and the strict docs build
#   --env NAME   run only these tox environments (dyopilot, dronekit, sitl,
#                sitl-dronekit, docs); may be repeated
#   -- ARGS      passed to pytest, e.g. `-- -k gui -x`
#
# Needs python3.12 and python3.7 (pyenv installs are found automatically).
# Runs tox; it is installed into .venv-tox on first use.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

envs=()
all=0
while [ $# -gt 0 ]; do
    case "$1" in
        --all) all=1 ;;
        --env) shift; [ $# -gt 0 ] || die "--env needs a name"; envs+=("$1") ;;
        -h|--help) sed -n '2,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        --) shift; break ;;
        *) die "unknown option: $1 (see --help)" ;;
    esac
    shift
done

if [ "${#envs[@]}" -eq 0 ]; then
    envs=(dyopilot dronekit)
    [ "$all" -eq 1 ] && envs+=(docs sitl sitl-dronekit)
fi

case " ${envs[*]} " in
    *" dronekit "*|*" sitl-dronekit "*)
        find_python37 || die "python3.7 not found (needed for the DroneKit environments). Install it, e.g. 'pyenv install 3.7.17', or run '--env dyopilot'."
        ;;
esac

ensure_tox
joined="$(IFS=,; echo "${envs[*]}")"
if [ $# -gt 0 ]; then
    "$TOX" -e "$joined" -- "$@"
else
    "$TOX" -e "$joined"
fi
