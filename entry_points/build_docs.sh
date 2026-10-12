#!/usr/bin/env bash
# Build the Sphinx documentation into docs/_build/html.
#
# Usage: ./entry_points/build_docs.sh [--clean] [--open]
#   --clean   remove docs/_build before building
#   --open    open the result in the default browser when done
#
# Creates (once) and reuses a docs-only virtualenv in .venv-docs. Set PYTHON to
# pick the interpreter used to create it (must be Python 3.12+; default python3.12).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv-docs"
PYTHON="${PYTHON:-python3.12}"

clean=0
open_after=0
for arg in "$@"; do
    case "$arg" in
        --clean) clean=1 ;;
        --open) open_after=1 ;;
        -h|--help) sed -n '2,9p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $arg (see --help)" >&2; exit 2 ;;
    esac
done

if [ ! -x "$VENV/bin/python" ]; then
    command -v "$PYTHON" >/dev/null 2>&1 || {
        echo "Interpreter '$PYTHON' not found. Install Python 3.12+ or set PYTHON=/path/to/python." >&2
        exit 1
    }
    echo "Creating docs virtualenv in $VENV"
    "$PYTHON" -m venv "$VENV"
fi

# Re-install only when requirements.txt changed since the last successful install.
stamp="$VENV/.requirements.stamp"
if [ ! -f "$stamp" ] || [ "$ROOT/docs/requirements.txt" -nt "$stamp" ]; then
    "$VENV/bin/python" -m pip install --quiet -r "$ROOT/docs/requirements.txt"
    touch "$stamp"
fi

[ "$clean" -eq 1 ] && rm -rf "$ROOT/docs/_build"

"$VENV/bin/python" -m sphinx -b html -W --keep-going "$ROOT/docs" "$ROOT/docs/_build/html"

index="$ROOT/docs/_build/html/index.html"
echo "Docs built: $index"
if [ "$open_after" -eq 1 ]; then
    case "$(uname)" in
        Darwin) open "$index" ;;
        *) xdg-open "$index" >/dev/null 2>&1 || echo "Open $index in your browser." ;;
    esac
fi
