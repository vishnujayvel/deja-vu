import json
import shutil
from pathlib import Path

import pytest

import sync_codex_plugin


def make_canonical_sources(root: Path) -> None:
    (root / "SKILL.md").write_text("skill content\n")

    scripts_dir = root / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    for name in sync_codex_plugin.RUNTIME_SCRIPTS:
        (scripts_dir / name).write_text(f"# {name}\n")

    references_dir = root / "references"
    references_dir.mkdir(parents=True, exist_ok=True)
    (references_dir / "framing.md").write_text("framing\n")

    docs_dir = root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "design.md").write_text("design\n")
    (docs_dir / "tier-matrix.md").write_text("tier-matrix\n")

    adr_dir = docs_dir / "adr"
    adr_dir.mkdir(parents=True, exist_ok=True)
    (adr_dir / "0011-decision-taxonomy-compositional-packet.md").write_text("adr-11\n")

    policy_dir = root / "policy"
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "tier-matrix.json").write_text("{}\n")

    schemas_dir = root / "schemas"
    schemas_dir.mkdir(parents=True, exist_ok=True)
    (schemas_dir / "decision-packet.schema.json").write_text("{}\n")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    make_canonical_sources(tmp_path)
    dest = tmp_path / "codex-plugin" / "skills" / "deja-vu"
    monkeypatch.setattr(sync_codex_plugin, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sync_codex_plugin, "DEST", dest)
    return tmp_path, dest


def test_sync_regenerates_normally(repo):
    root, dest = repo

    assert sync_codex_plugin.sync() == 0

    assert (dest / "SKILL.md").read_text() == "skill content\n"
    assert (dest / "references" / "framing.md").read_text() == "framing\n"
    assert (dest / "docs" / "design.md").read_text() == "design\n"
    assert (dest / "docs" / "tier-matrix.md").read_text() == "tier-matrix\n"
    assert (dest / "policy" / "tier-matrix.json").read_text() == "{}\n"
    assert (dest / "schemas" / "decision-packet.schema.json").read_text() == "{}\n"
    assert (
        dest / "docs" / "adr" / "0011-decision-taxonomy-compositional-packet.md"
    ).read_text() == "adr-11\n"
    for name in sync_codex_plugin.RUNTIME_SCRIPTS:
        assert (dest / "scripts" / name).read_text() == f"# {name}\n"

    assert sync_codex_plugin.check() == 0


def test_sync_rejects_symlinked_dest(repo):
    root, dest = repo
    outside = root / "outside-final"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("do not touch\n")

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.symlink_to(outside, target_is_directory=True)

    assert sync_codex_plugin.sync() == 1

    assert sentinel.read_text() == "do not touch\n"
    assert dest.is_symlink()


def test_sync_rejects_symlinked_ancestor(repo):
    root, dest = repo
    outside = root / "outside-ancestor"
    (outside / "deja-vu").mkdir(parents=True)
    sentinel = outside / "deja-vu" / "sentinel.txt"
    sentinel.write_text("do not touch\n")

    skills_dir = dest.parent
    skills_dir.parent.mkdir(parents=True, exist_ok=True)
    skills_dir.symlink_to(outside, target_is_directory=True)

    assert sync_codex_plugin.sync() == 1

    assert sentinel.read_text() == "do not touch\n"
    assert skills_dir.is_symlink()


def test_check_rejects_symlinked_required_file(repo):
    root, dest = repo

    assert sync_codex_plugin.sync() == 0
    assert sync_codex_plugin.check() == 0

    target = dest / "SKILL.md"
    target.unlink()
    target.symlink_to(root / "SKILL.md")

    # Content is byte-identical to the canonical source -- only the payload
    # entry's type (symlink vs. real file) differs. check() must still fail.
    assert target.read_bytes() == (root / "SKILL.md").read_bytes()
    assert sync_codex_plugin.check() == 1


def test_check_rejects_symlinked_nested_directory(repo, capsys):
    root, dest = repo

    assert sync_codex_plugin.sync() == 0

    real_scripts = dest / "scripts"
    shadow = root / "shadow-scripts"
    shadow.mkdir()
    for name in sync_codex_plugin.RUNTIME_SCRIPTS:
        (shadow / name).write_text((real_scripts / name).read_text())
    shutil.rmtree(real_scripts)
    real_scripts.symlink_to(shadow, target_is_directory=True)

    assert sync_codex_plugin.check() == 1
    captured = capsys.readouterr()
    assert "symlink" in captured.out


def test_sync_refuses_nested_symlinked_directory_without_partial_cleanup(repo):
    root, dest = repo

    assert sync_codex_plugin.sync() == 0

    real_scripts = dest / "scripts"
    shadow = root / "shadow-scripts-2"
    shadow.mkdir()
    for name in sync_codex_plugin.RUNTIME_SCRIPTS:
        (shadow / name).write_text((real_scripts / name).read_text())
    shutil.rmtree(real_scripts)
    real_scripts.symlink_to(shadow, target_is_directory=True)

    assert (dest / "SKILL.md").exists()

    assert sync_codex_plugin.sync() == 1

    # Refusal happened before any deletion: the rest of the existing payload
    # is untouched, not partially cleaned up.
    assert (dest / "SKILL.md").exists()
    assert (dest / "docs" / "design.md").exists()
    assert real_scripts.is_symlink()


def _write_plugin_manifests(root: Path, version: str) -> None:
    payload = json.dumps({"name": "deja-vu", "version": version})
    for relative in (
        "codex-plugin/.claude-plugin/plugin.json",
        "codex-plugin/.codex-plugin/plugin.json",
    ):
        manifest = root / relative
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(payload)


def test_check_detects_manifest_version_drift(repo, capsys):
    root, dest = repo
    (root / "SKILL.md").write_text("---\nname: deja-vu\nversion: 0.1.1\n---\nskill content\n")
    _write_plugin_manifests(root, "0.1.1")

    assert sync_codex_plugin.sync() == 0
    assert sync_codex_plugin.check() == 0

    # Bump the skill version without touching the manifests, then regenerate
    # the payload (which copies SKILL.md verbatim, so payload content itself
    # is not stale) -- only the manifest versions should now be flagged.
    (root / "SKILL.md").write_text("---\nname: deja-vu\nversion: 0.2.0\n---\nskill content\n")
    assert sync_codex_plugin.sync() == 0

    assert sync_codex_plugin.check() == 1
    captured = capsys.readouterr()
    assert "version drift" in captured.out
