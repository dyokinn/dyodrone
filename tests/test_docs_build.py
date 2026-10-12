"""The documentation builds with warnings treated as errors. Opt in with ``pytest -m docs``."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.docs

DOCS = Path(__file__).resolve().parent.parent / "docs"


def test_sphinx_builds_without_warnings(tmp_path):
    pytest.importorskip("sphinx")
    pytest.importorskip("furo")
    from sphinx.cmd.build import build_main

    status = build_main(["-b", "html", "-W", "--keep-going", "-q", str(DOCS), str(tmp_path / "html")])
    assert status == 0
    assert (tmp_path / "html" / "index.html").exists()
