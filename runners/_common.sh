#!/usr/bin/env bash
# Shared helpers for the scripts in runners/. Sourced by them, not run directly.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

die() {
    echo "error: $*" >&2
    exit 1
}

# Make python3.7 findable (tox's DroneKit environments need it) via pyenv if it
# is installed but not usable on PATH. A pyenv shim can exist on PATH and still
# fail when 3.7 is not the selected version, so check that it actually runs.
find_python37() {
    python3.7 --version >/dev/null 2>&1 && return 0
    if command -v pyenv >/dev/null 2>&1; then
        local v
        for v in $(pyenv versions --bare 2>/dev/null | grep '^3\.7\.'); do
            PATH="$(pyenv prefix "$v")/bin:$PATH"
            export PATH
            return 0
        done
    fi
    return 1
}

# Create (once) a private environment holding tox 4 and set $TOX to its binary.
ensure_tox() {
    local venv="$ROOT/.venv-tox"
    if [ ! -x "$venv/bin/tox" ]; then
        command -v "${PYTHON:-python3.12}" >/dev/null 2>&1 \
            || die "python3.12 not found. Install Python 3.12+ or set PYTHON=/path/to/python."
        echo "Creating tox environment in $venv"
        "${PYTHON:-python3.12}" -m venv "$venv"
        "$venv/bin/python" -m pip install --quiet --upgrade pip tox
    fi
    TOX="$venv/bin/tox"
}

# ensure_venv NAME PYTHON EXTRAS: create .venv-NAME with the package installed
# (editable, with the given extras); reinstalls when pyproject.toml changes.
ensure_venv() {
    local name="$1" python="$2" extras="$3"
    VENV="$ROOT/.venv-$name"
    if [ ! -x "$VENV/bin/python" ]; then
        command -v "$python" >/dev/null 2>&1 \
            || die "$python not found. Install it (for example with pyenv) or set PYTHON37/PYTHON312."
        echo "Creating $VENV with $python"
        "$python" -m venv "$VENV"
    fi
    local stamp="$VENV/.installed-$extras"
    if [ ! -f "$stamp" ] || [ "$ROOT/pyproject.toml" -nt "$stamp" ]; then
        # Python 3.7 cannot run the newest pip/setuptools.
        "$VENV/bin/python" -m pip install --quiet --upgrade "pip<24" "setuptools<69"
        "$VENV/bin/python" -m pip install --quiet -e ".[$extras]"
        touch "$stamp"
    fi
}
