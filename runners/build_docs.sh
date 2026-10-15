#!/usr/bin/env bash
# Build the documentation into docs/_build/html (Sphinx + Furo, warnings are errors).
#
# Usage: runners/build_docs.sh [--clean] [--open]
#   --clean   remove docs/_build first
#   --open    open the result in the default browser when done
#
# Runs `tox -e docs`; tox is installed into .venv-tox on first use.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

clean=0
open_after=0
for arg in "$@"; do
    case "$arg" in
        --clean) clean=1 ;;
        --open) open_after=1 ;;
        -h|--help) sed -n '2,8p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) die "unknown option: $arg (see --help)" ;;
    esac
done

ensure_tox
[ "$clean" -eq 1 ] && rm -rf "$ROOT/docs/_build"
"$TOX" -e docs

index="$ROOT/docs/_build/html/index.html"
echo "Docs built: $index"
if [ "$open_after" -eq 1 ]; then
    case "$(uname)" in
        Darwin) open "$index" ;;
        *) xdg-open "$index" >/dev/null 2>&1 || echo "Open $index in your browser." ;;
    esac
fi
