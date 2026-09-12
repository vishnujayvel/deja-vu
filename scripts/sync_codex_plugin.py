#!/usr/bin/env python3
"""Regenerate codex-plugin/skills/deja-vu/ from the canonical repo-root sources.

codex-plugin/ is a self-contained plugin package (its own .codex-plugin/plugin.json
and .claude-plugin/plugin.json, both pointing at skills/deja-vu/) kept separate from
the repo root. Marketplace installs copy their source path's entire directory tree
verbatim with no filtering, so pointing a marketplace entry at the repo root would
ship .git/, .beads/, tests/, evals/, and this project's own .scratch/ evidence into
every install — confirmed empirically. Keeping the package self-contained under
codex-plugin/ is what keeps the shipped plugin to only the runtime files below.

Codex's native plugin installer also drops symlinks during install (confirmed
empirically: a skills/deja-vu/SKILL.md symlink back to the repo root became an
empty directory in the installed cache), so this script copies rather than links.
Never hand-edit anything under codex-plugin/skills/deja-vu/ — re-run this script
instead whenever SKILL.md, scripts/{doctor,sweep,provenance}.py, references/*.md,
docs/design.md, docs/tier-matrix.md, policy/tier-matrix.json,
schemas/decision-packet.schema.json, schemas/probe-receipt.schema.json, or
docs/adr/0011-decision-taxonomy-compositional-packet.md change.

This copies exactly the files SKILL.md's own loop instructions reference
(verified via grep against SKILL.md + references/*.md) — not the whole repo —
so the packaged plugin never picks up this repo's own dev-only files.

Usage:
    python3 scripts/sync_codex_plugin.py          # regenerate in place
    python3 scripts/sync_codex_plugin.py --check  # non-mutating: exit nonzero
                                                    # if the packaged copy has
                                                    # drifted from the canonical
                                                    # sources, without writing
                                                    # anything (safe for CI/a
                                                    # pre-commit check).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEST = REPO_ROOT / "codex-plugin" / "skills" / "deja-vu"

RUNTIME_SCRIPTS = ("doctor.py", "sweep.py", "provenance.py")


def desired_files() -> dict[str, Path]:
    """Map DEST-relative path -> canonical source file it must match."""
    files = {"SKILL.md": REPO_ROOT / "SKILL.md"}
    for name in RUNTIME_SCRIPTS:
        files[f"scripts/{name}"] = REPO_ROOT / "scripts" / name
    for path in sorted((REPO_ROOT / "references").glob("*.md")):
        files[f"references/{path.name}"] = path
    files["docs/design.md"] = REPO_ROOT / "docs" / "design.md"
    files["docs/tier-matrix.md"] = REPO_ROOT / "docs" / "tier-matrix.md"
    files["policy/tier-matrix.json"] = REPO_ROOT / "policy" / "tier-matrix.json"
    files["schemas/decision-packet.schema.json"] = (
        REPO_ROOT / "schemas" / "decision-packet.schema.json"
    )
    files["schemas/probe-receipt.schema.json"] = (
        REPO_ROOT / "schemas" / "probe-receipt.schema.json"
    )
    files["docs/adr/0011-decision-taxonomy-compositional-packet.md"] = (
        REPO_ROOT / "docs" / "adr" / "0011-decision-taxonomy-compositional-packet.md"
    )
    return files


def _first_symlinked_component(path: Path, boundary: Path) -> Path | None:
    """Return the first symlink among `path` and its ancestors up to `boundary`.

    `sync()` deletes everything under DEST before rewriting it. If DEST (or one
    of the path components between it and `boundary`) is a symlink, that delete
    follows the link and destroys whatever it actually points at instead of the
    packaged copy -- this catches that before any deletion happens.
    """
    current = path
    while True:
        if current.is_symlink():
            return current
        if current == boundary:
            return None
        current = current.parent


def _first_symlink_below(root: Path) -> Path | None:
    """Return the first symlink among root's descendants, without descending
    into any symlinked directory.

    Used to preflight DEST before either reading (check) or deleting (sync)
    anything under it, so a symlinked payload file or a nested symlinked
    directory is detected -- and reported/refused -- instead of silently
    followed.
    """
    if not root.is_dir():
        return None
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            children = sorted(current.iterdir())
        except OSError:
            continue
        for child in children:
            if child.is_symlink():
                return child
            if child.is_dir():
                stack.append(child)
    return None


def sync() -> int:
    unsafe = _first_symlinked_component(DEST, REPO_ROOT / "codex-plugin")
    if unsafe is not None:
        print(
            f"refusing to regenerate: {unsafe} is a symlink, not a real directory; "
            "codex-plugin/skills/deja-vu was not touched",
            file=sys.stderr,
        )
        return 1

    if DEST.exists():
        symlinked = _first_symlink_below(DEST)
        if symlinked is not None:
            print(
                f"refusing to regenerate: {symlinked} is a symlink; "
                "codex-plugin/skills/deja-vu was not touched",
                file=sys.stderr,
            )
            return 1
        for path in sorted(DEST.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
        for path in sorted(DEST.rglob("*"), reverse=True):
            if path.is_dir():
                path.rmdir()
    DEST.mkdir(parents=True, exist_ok=True)

    for relative, source in desired_files().items():
        dest_path = DEST / relative
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(source.read_bytes())

    print(f"Synced Codex plugin payload: {DEST}")
    return 0


def _plugin_manifest_paths() -> tuple[Path, Path]:
    return (
        REPO_ROOT / "codex-plugin" / ".claude-plugin" / "plugin.json",
        REPO_ROOT / "codex-plugin" / ".codex-plugin" / "plugin.json",
    )


def _skill_version() -> str | None:
    """Read the `version:` line from canonical SKILL.md's frontmatter."""
    match = re.search(r"(?m)^version:\s*(\S+)\s*$", (REPO_ROOT / "SKILL.md").read_text())
    return match.group(1) if match else None


def _manifest_version_problems() -> list[str]:
    """Check the two installer-visible plugin manifests against SKILL.md's
    version -- not a version framework, just a drift check against the one
    existing source of truth."""
    skill_version = _skill_version()
    if skill_version is None:
        return []
    problems = []
    for manifest_path in _plugin_manifest_paths():
        if not manifest_path.is_file():
            problems.append(f"missing plugin manifest: {manifest_path.relative_to(REPO_ROOT)}")
            continue
        try:
            manifest_version = json.loads(manifest_path.read_text()).get("version")
        except json.JSONDecodeError:
            problems.append(f"invalid JSON in plugin manifest: {manifest_path.relative_to(REPO_ROOT)}")
            continue
        if manifest_version != skill_version:
            problems.append(
                f"version drift: {manifest_path.relative_to(REPO_ROOT)} is "
                f"{manifest_version!r}, SKILL.md is {skill_version!r}"
            )
    return problems


def check() -> int:
    """Non-mutating: report drift between DEST and the canonical sources."""
    problems: list[str] = []
    wanted = desired_files()

    unsafe = _first_symlinked_component(DEST, REPO_ROOT / "codex-plugin")
    if unsafe is not None:
        problems.append(f"symlinked: {unsafe} is a symlink, not a real path")
    else:
        symlinked = _first_symlink_below(DEST)
        if symlinked is not None:
            problems.append(
                f"symlinked payload entry (not allowed): {symlinked.relative_to(DEST).as_posix()}"
            )

    if not problems:
        for relative, source in wanted.items():
            dest_path = DEST / relative
            if not dest_path.is_file():
                problems.append(f"missing: {relative}")
                continue
            if dest_path.read_bytes() != source.read_bytes():
                problems.append(f"stale (content differs from {source.relative_to(REPO_ROOT)}): {relative}")

        if DEST.is_dir():
            actual = {p.relative_to(DEST).as_posix() for p in DEST.rglob("*") if p.is_file()}
            for extra in sorted(actual - set(wanted)):
                problems.append(f"unexpected file not in canonical sources: {extra}")

    problems.extend(_manifest_version_problems())

    if problems:
        print("Codex plugin payload has drifted from canonical sources:")
        for problem in problems:
            print(f"  - {problem}")
        print("Run: python3 scripts/sync_codex_plugin.py")
        return 1

    print(f"Codex plugin payload up to date: {DEST}")
    return 0


def main() -> int:
    if "--check" in sys.argv[1:]:
        return check()
    return sync()


if __name__ == "__main__":
    sys.exit(main())
