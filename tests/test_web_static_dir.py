"""Tests for Next.js static bundle path resolution."""

from pathlib import Path

import pytest

from squire.api import app as app_mod


def test_find_static_dir_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setenv("SQUIRE_WEB_STATIC_DIR", str(out))
    assert app_mod._find_static_dir() == out.resolve()
