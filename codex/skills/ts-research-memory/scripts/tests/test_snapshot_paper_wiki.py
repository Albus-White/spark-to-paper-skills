from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "snapshot_paper_wiki.py"
SPEC = importlib.util.spec_from_file_location("snapshot_paper_wiki", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_snapshot_is_content_addressed_and_excludes_raw_sources(tmp_path):
    (tmp_path / "WIKI.md").write_text("# Contract\n", encoding="utf-8")
    (tmp_path / ".paper-wiki").mkdir()
    (tmp_path / "wiki/papers").mkdir(parents=True)
    (tmp_path / "wiki/concepts").mkdir(parents=True)
    (tmp_path / "raw").mkdir()
    (tmp_path / "wiki/papers/a.md").write_text("paper A\n", encoding="utf-8")
    (tmp_path / "wiki/concepts/c.md").write_text("concept C\n", encoding="utf-8")
    (tmp_path / "raw/source.pdf").write_bytes(b"not copied")

    first = MODULE.build_snapshot(tmp_path)
    second = MODULE.build_snapshot(tmp_path)

    assert first["snapshot_sha256"] == second["snapshot_sha256"]
    assert first["counts"]["papers"] == 1
    assert all(not item["path"].startswith("raw/") for item in first["files"])


def test_snapshot_changes_when_a_wiki_page_changes(tmp_path):
    (tmp_path / "WIKI.md").write_text("# Contract\n", encoding="utf-8")
    (tmp_path / ".paper-wiki").write_text("ready\n", encoding="utf-8")
    (tmp_path / "wiki/gaps").mkdir(parents=True)
    page = tmp_path / "wiki/gaps/g.md"
    page.write_text("gap v1\n", encoding="utf-8")
    first = MODULE.build_snapshot(tmp_path)
    page.write_text("gap v2\n", encoding="utf-8")
    second = MODULE.build_snapshot(tmp_path)
    assert first["snapshot_sha256"] != second["snapshot_sha256"]

