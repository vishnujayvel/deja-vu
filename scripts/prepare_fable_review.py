#!/usr/bin/env python3
"""Prepare one sealed Claude Fable 5 review job without submitting it."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import stat
import subprocess  # Imported so tests can prove this module never invokes it.
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import fable_review_gate


DEFAULT_DELEGATE = Path.home() / "workplace" / "gc-router" / "bin" / "delegate-job"
MAX_ARTIFACT_BYTES = 512 * 1024


def _absolute_lexical(path: Path) -> Path:
    return Path(os.path.abspath(path))


_DIRECTORY_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)


def _open_directory_chain(root: Path, path: Path) -> int:
    """Open a descendant directory through no-follow directory descriptors."""
    root = root.resolve(strict=True)
    path = _absolute_lexical(path)
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise ValueError(f"private state path escapes repository: {path}") from error

    descriptor = os.open(root, _DIRECTORY_FLAGS)
    try:
        for part in relative.parts:
            child = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _private_directory(root: Path, path: Path) -> Path:
    """Create a private directory below repository .scratch without symlinks."""
    root = root.resolve(strict=True)
    path = _absolute_lexical(path)
    scratch = root / ".scratch"
    try:
        relative = path.relative_to(scratch)
    except ValueError as error:
        raise ValueError(f"state root must be inside {scratch}") from error

    descriptor = os.open(root, _DIRECTORY_FLAGS)
    current = root
    try:
        for part in (".scratch", *relative.parts):
            current = current / part
            try:
                os.mkdir(part, mode=0o700, dir_fd=descriptor)
            except FileExistsError:
                pass
            try:
                child = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
            except OSError as error:
                raise ValueError(
                    f"private state path is not a no-follow directory: {current}"
                ) from error
            os.close(descriptor)
            descriptor = child
            metadata = os.fstat(descriptor)
            if not stat.S_ISDIR(metadata.st_mode):
                raise ValueError(
                    f"private state path is not a directory: {current}"
                )
            os.fchmod(descriptor, 0o700)
    finally:
        os.close(descriptor)
    return path


def _read_no_follow(
    parent_descriptor: int, name: str, display_path: Path
) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(name, flags, dir_fd=parent_descriptor)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(
                f"private output is not a regular file: {display_path}"
            )
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            contents = stream.read()
        return contents, os.fstat(descriptor)
    finally:
        os.close(descriptor)


def _write_private(root: Path, path: Path, text: str) -> int:
    """Create an immutable private file, or accept identical existing bytes."""
    encoded = text.encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    parent_descriptor = _open_directory_chain(root, path.parent)
    try:
        try:
            descriptor = os.open(
                path.name, flags, 0o600, dir_fd=parent_descriptor
            )
        except FileExistsError:
            try:
                metadata = os.stat(
                    path.name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
            except OSError as error:
                raise ValueError(f"cannot inspect private output: {path}") from error
            if stat.S_ISLNK(metadata.st_mode):
                raise ValueError(f"private output path is a symlink: {path}")
            try:
                existing, existing_metadata = _read_no_follow(
                    parent_descriptor, path.name, path
                )
            except OSError as error:
                raise ValueError(f"cannot safely read private output: {path}") from error
            if existing != encoded:
                raise ValueError(
                    f"private output already exists with different content: {path}"
                )
            return existing_metadata.st_mtime_ns
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            metadata = os.fstat(descriptor)
        finally:
            os.close(descriptor)
    finally:
        os.close(parent_descriptor)
    return metadata.st_mtime_ns


def _iso_timestamp_from_ns(timestamp_ns: int) -> str:
    seconds, nanoseconds = divmod(timestamp_ns, 1_000_000_000)
    return datetime.fromtimestamp(seconds, tz=timezone.utc).replace(
        microsecond=nanoseconds // 1_000
    ).isoformat()


def _module_slug(module: str) -> str:
    readable = re.sub(r"[^A-Za-z0-9]+", "-", module).strip("-").lower()
    path_hash = hashlib.sha256(module.encode("utf-8")).hexdigest()[:10]
    return f"{readable[:40]}-{path_hash}"


def _review_prompt(
    module: str,
    artifact_text: str,
    artifact_sha256: str,
    contract: str,
    contract_sha256: str,
    governing_contract_sha256: str,
    round_number: int,
) -> str:
    payload = {
        "module_path": module,
        "artifact_sha256": artifact_sha256,
        "contract": contract,
        "contract_sha256": contract_sha256,
        "governing_contract_sha256": governing_contract_sha256,
        "review_round": round_number,
        "artifact_text": artifact_text,
    }
    payload["artifact_length_bytes"] = len(artifact_text.encode("utf-8"))
    return (
        "ARTIFACT_AND_CONTRACT_JSON:\n"
        + json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )


def prepare_review(
    root: Path,
    module: str,
    state_root: Path,
    *,
    round_number: int,
    attempt_number: int = 1,
    delegate: Path = DEFAULT_DELEGATE,
) -> dict[str, Any]:
    """Create private prompt and manifest files for one governed module."""
    root = root.resolve()
    state_root = _absolute_lexical(state_root)
    if round_number not in {1, 2, 3}:
        raise ValueError("round must be 1, 2, or 3")
    if attempt_number not in {1, 2, 3}:
        raise ValueError("attempt must be 1, 2, or 3")
    if module not in fable_review_gate.discover_modules(root):
        raise ValueError(f"not a governed module: {module}")

    contracts = fable_review_gate.load_canonical_module_contracts(root)
    contract = contracts.get(module)
    if contract is None:
        raise ValueError(f"missing canonical contract: {module}")

    artifact_bytes = fable_review_gate.read_governed_bytes(root, module)
    if len(artifact_bytes) > MAX_ARTIFACT_BYTES:
        raise ValueError(
            f"artifact exceeds {MAX_ARTIFACT_BYTES} byte review limit: {module}"
        )
    artifact_text = artifact_bytes.decode("utf-8")
    artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
    contract_sha256 = fable_review_gate.sha256_contract(contract)
    governing_sha256 = fable_review_gate.governing_contract_sha256(
        root, module, contract
    )

    state_root = _private_directory(root, state_root)
    review_dir = (
        state_root
        / _module_slug(module)
        / artifact_sha256[:12]
        / governing_sha256[:12]
        / f"round-{round_number}"
        / f"attempt-{attempt_number}"
    )
    _private_directory(root, review_dir)
    prompt_path = review_dir / "prompt.md"
    manifest_path = review_dir / "manifest.json"
    prompt_created_ns = _write_private(
        root,
        prompt_path,
        _review_prompt(
            module,
            artifact_text,
            artifact_sha256,
            contract,
            contract_sha256,
            governing_sha256,
            round_number,
        ),
    )

    job_id = (
        f"job-fable-{_module_slug(module)[:32]}-"
        f"{artifact_sha256[:12]}-{governing_sha256[:12]}-"
        f"r{round_number}-a{attempt_number}"
    )
    manifest = {
        "schema_version": 2,
        "job_id": job_id,
        "created_at": _iso_timestamp_from_ns(prompt_created_ns),
        "workdir": str(root),
        "prompt_file": str(prompt_path),
        "features": {
            "dependent_steps": False,
            "worker_count": 1,
            "retry_required": False,
            "resume_required": False,
            "scheduled": False,
            "unattended": False,
            "expected_minutes": 15,
        },
        "route": "direct",
        "executor": "claude",
        "model": "claude-fable-5",
        "target": "deja-vu/claude-fable-review",
        "permissions": {
            "read_roots": [str(root)],
            "write_roots": [],
            "shell": "none",
            "network": "none",
            "secret_references": [],
            "remote_git": False,
            "deploy": False,
            "purchase": False,
            "external_messages": False,
        },
        "retry_policy": {"max_attempts": 1, "backoff_seconds": 0},
        "timeout_policy": {"attempt_seconds": 900},
    }
    _write_private(
        root,
        manifest_path,
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )

    return {
        "schema_version": "deja-vu.fable-review-preparation/v1",
        "module": module,
        "artifact_sha256": artifact_sha256,
        "contract_sha256": contract_sha256,
        "governing_contract_sha256": governing_sha256,
        "round": round_number,
        "transport_attempt": attempt_number,
        "job_id": job_id,
        "prompt_path": str(prompt_path),
        "manifest_path": str(manifest_path),
        "validate_command": [
            str(delegate),
            "validate",
            "--manifest",
            str(manifest_path),
            "--json",
        ],
        "submit_command": [
            str(delegate),
            "submit",
            "--manifest",
            str(manifest_path),
            "--json",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Prepare, but do not submit, one Claude Fable 5 review."
    )
    parser.add_argument("module", help="Governed repository-relative module path.")
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument(
        "--state-root",
        type=Path,
        default=root / ".scratch" / "fable-reviews",
    )
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument(
        "--attempt",
        type=int,
        default=1,
        help="Transport attempt within the review round (1-3).",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = prepare_review(
            args.root,
            args.module,
            args.state_root,
            round_number=args.round,
            attempt_number=args.attempt,
        )
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        print(f"FABLE_REVIEW_PREPARE: ERROR -- {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("FABLE_REVIEW_PREPARE: READY -- external call not submitted")
        print("FABLE_REVIEW_VALIDATE:")
        print(shlex.join(result["validate_command"]))
        print("FABLE_REVIEW_SUBMIT_REQUIRES_AUTHORIZATION:")
        print(shlex.join(result["submit_command"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
