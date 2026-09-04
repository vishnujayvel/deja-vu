#!/usr/bin/env python3
"""Diagnose Claude Fable 5 review coverage without authorizing release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any


REVIEW_SCHEMA = "deja-vu.fable-review/v1"
REVIEW_MODEL = "claude-fable-5"
REVIEW_TARGET = "deja-vu/claude-fable-review"
TERMINAL_VERDICTS = {"pass"}
SHA256_LENGTH = 64
MODULE_PATH_PATTERN = re.compile(
    r"^(?:SKILL\.md|docs/design\.md|evals/run_evals\.py|"
    r"(?:scripts|src|deja_vu)/(?:[^/]+/)*[^/]+\.(?:py|sh)|"
    r"(?:schemas|contracts|policy)/(?:[^/]+/)*[^/]+\.json)$"
)


def validate_module_path(module: str) -> str:
    """Return one canonical governed module path or raise ValueError."""
    parts = module.split("/")
    if (
        not MODULE_PATH_PATTERN.fullmatch(module)
        or any(part in {"", ".", ".."} for part in parts)
        or "\\" in module
    ):
        raise ValueError(f"invalid path for governed module: {module!r}")
    return module


def read_governed_bytes(root: Path, module: str) -> bytes:
    """Read a regular governed file once through no-follow directory handles."""
    validate_module_path(module)
    root = root.resolve(strict=True)
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    parent_descriptor = os.open(root, directory_flags)
    try:
        parts = module.split("/")
        for part in parts[:-1]:
            try:
                child_descriptor = os.open(
                    part, directory_flags, dir_fd=parent_descriptor
                )
            except OSError as error:
                raise ValueError(
                    f"governed path contains an unsafe directory: {module}"
                ) from error
            os.close(parent_descriptor)
            parent_descriptor = child_descriptor

        file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(
                parts[-1], file_flags, dir_fd=parent_descriptor
            )
        except OSError as error:
            raise ValueError(f"cannot safely open governed file: {module}") from error
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError(
                    f"governed path is not a regular file: {module}"
                )
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                return stream.read()
        finally:
            os.close(descriptor)
    finally:
        os.close(parent_descriptor)


def discover_modules(root: Path) -> list[str]:
    """Return executable and public-contract modules governed by the review gate."""
    root = root.resolve()
    modules: set[str] = set()

    def add_exact(relative: str) -> None:
        path = root / relative
        if path.is_symlink():
            raise ValueError(f"governed path contains a symlink: {relative}")
        if path.is_file():
            modules.add(relative)

    add_exact("SKILL.md")

    for directory in ("scripts", "src", "deja_vu"):
        base = root / directory
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.is_symlink():
                raise ValueError(
                    "governed path contains a symlink: "
                    f"{path.relative_to(root).as_posix()}"
                )
            if path.is_file() and path.suffix in {".py", ".sh"}:
                modules.add(path.relative_to(root).as_posix())

    add_exact("evals/run_evals.py")

    schemas = root / "schemas"
    if schemas.is_dir():
        for path in schemas.rglob("*.json"):
            if path.is_symlink():
                raise ValueError(
                    "governed path contains a symlink: "
                    f"{path.relative_to(root).as_posix()}"
                )
            if path.is_file():
                modules.add(path.relative_to(root).as_posix())

    contracts = root / "contracts"
    if contracts.is_dir():
        for path in contracts.rglob("*.json"):
            if path.is_symlink():
                raise ValueError(
                    "governed path contains a symlink: "
                    f"{path.relative_to(root).as_posix()}"
                )
            if path.is_file():
                modules.add(path.relative_to(root).as_posix())

    add_exact("docs/design.md")

    policy = root / "policy"
    if policy.is_dir():
        for path in policy.rglob("*.json"):
            if path.is_symlink():
                raise ValueError(
                    "governed path contains a symlink: "
                    f"{path.relative_to(root).as_posix()}"
                )
            if path.is_file():
                modules.add(path.relative_to(root).as_posix())

    discovered = sorted(modules)
    for module in discovered:
        validate_module_path(module)
    return discovered


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest for a file."""
    if path.is_symlink():
        raise ValueError(f"refusing to hash symlink: {path}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"refusing to hash non-regular file: {path}")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            return hashlib.sha256(stream.read()).hexdigest()
    finally:
        os.close(descriptor)


def sha256_contract(contract: str) -> str:
    """Return the SHA-256 digest of the contract's exact UTF-8 text."""
    return hashlib.sha256(contract.encode("utf-8")).hexdigest()


def governing_contract_sha256(
    root: Path,
    module: str,
    contract: str,
) -> str:
    """Bind a review to every project-owned contract that governs it."""
    root = root.resolve()

    def digest_if_file(relative: str) -> str | None:
        path = root / relative
        return (
            hashlib.sha256(read_governed_bytes(root, relative)).hexdigest()
            if path.is_file()
            else None
        )

    policy_digests: dict[str, str] = {}
    policy_root = root / "policy"
    if policy_root.is_dir():
        for path in sorted(policy_root.rglob("*.json")):
            if path.is_file():
                relative = path.relative_to(root).as_posix()
                policy_digests[relative] = hashlib.sha256(
                    read_governed_bytes(root, relative)
                ).hexdigest()

    material = {
        "schema_version": "deja-vu.governing-contract/v1",
        "module": module,
        "module_contract_sha256": sha256_contract(contract),
        "architecture_sha256": digest_if_file("docs/design.md"),
        "inventory_rules_sha256": digest_if_file(
            "scripts/fable_review_gate.py"
        ),
        "policy_artifacts": policy_digests,
    }
    encoded = json.dumps(
        material,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _parse_module_contracts(data: bytes) -> dict[str, str]:
    try:
        decoded = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("module contracts must be valid UTF-8") from error
    loaded = json.loads(decoded)
    if not isinstance(loaded, dict):
        raise ValueError("module contracts must be a JSON object")
    if loaded.get("schema_version") != "deja-vu.module-contracts/v1":
        raise ValueError("unsupported module-contracts schema_version")
    entries = loaded.get("modules")
    if not isinstance(entries, list):
        raise ValueError("module contracts must contain a modules array")

    contracts: dict[str, str] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"module contract {index} must be an object")
        module = entry.get("path")
        contract = entry.get("contract")
        if not isinstance(module, str) or not module:
            raise ValueError(f"module contract {index} has an invalid path")
        try:
            validate_module_path(module)
        except ValueError as error:
            raise ValueError(
                f"module contract {index} has an invalid path: {module!r}"
            ) from error
        if module in contracts:
            raise ValueError(f"duplicate module contract: {module}")
        if not isinstance(contract, str) or not contract.strip():
            raise ValueError(f"module contract {module} is empty")
        contracts[module] = contract
    return contracts


def load_module_contracts(path: Path) -> dict[str, str]:
    """Load a standalone contract map without following a final symlink."""
    if path.is_symlink():
        raise ValueError(f"module contract map must not be a symlink: {path}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("module contract map must be a regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            return _parse_module_contracts(stream.read())
    finally:
        os.close(descriptor)


def load_canonical_module_contracts(root: Path) -> dict[str, str]:
    """Load the repository-owned contract map through governed-file safety."""
    return _parse_module_contracts(
        read_governed_bytes(root, "contracts/module-contracts.json")
    )


def _metadata(record: dict[str, Any]) -> dict[str, Any]:
    metadata = record.get("metadata", {})
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            return {}
    return metadata if isinstance(metadata, dict) else {}


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == SHA256_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _review_problems(
    record: dict[str, Any],
    module: str,
    current_hash: str,
    current_contract_hash: str,
    current_governing_contract_hash: str,
) -> list[str]:
    metadata = _metadata(record)
    review_id = str(record.get("id", "<unknown-review>"))
    prefix = f"{module} ({review_id})"
    problems: list[str] = []

    if "fable-review" not in record.get("labels", []):
        problems.append(f"{prefix}: missing fable-review label")
    if record.get("status") != "closed":
        problems.append(f"{prefix}: non-terminal review issue")
    if metadata.get("review_schema") != REVIEW_SCHEMA:
        problems.append(f"{prefix}: wrong review schema")
    if metadata.get("review_model") != REVIEW_MODEL:
        problems.append(f"{prefix}: wrong reviewer model")
    if metadata.get("review_target") != REVIEW_TARGET:
        problems.append(f"{prefix}: wrong review target")
    if metadata.get("review_permission") != "read-only":
        problems.append(f"{prefix}: review was not read-only")
    if metadata.get("review_verdict") not in TERMINAL_VERDICTS:
        if metadata.get("review_verdict") == "human-override":
            problems.append(
                f"{prefix}: human override requires external adjudication"
            )
        else:
            problems.append(f"{prefix}: non-terminal verdict")
    if metadata.get("review_artifact_sha256") != current_hash:
        problems.append(f"{prefix}: stale artifact hash")
    if metadata.get("review_contract_sha256") != current_contract_hash:
        problems.append(f"{prefix}: stale contract hash")
    if (
        metadata.get("review_governing_contract_sha256")
        != current_governing_contract_hash
    ):
        problems.append(f"{prefix}: stale governing contract hash")
    if not metadata.get("review_contract_ref"):
        problems.append(f"{prefix}: missing contract reference")
    if not metadata.get("review_implementation_bead"):
        problems.append(f"{prefix}: missing implementation Bead")
    if metadata.get("review_permission_attested") != "true":
        problems.append(f"{prefix}: permission was not launcher-attested")
    if not _is_sha256(metadata.get("review_launch_envelope_sha256")):
        problems.append(f"{prefix}: missing launch envelope hash")
    if not metadata.get("review_delegate_job_id"):
        problems.append(f"{prefix}: missing delegate job id")

    try:
        round_number = int(metadata.get("review_round", 0))
    except (TypeError, ValueError):
        round_number = 0
    if round_number not in {1, 2, 3}:
        problems.append(f"{prefix}: review round must be 1, 2, or 3")

    try:
        unresolved = int(metadata.get("review_findings_unresolved", -1))
    except (TypeError, ValueError):
        unresolved = -1
    if unresolved != 0:
        problems.append(f"{prefix}: unresolved findings")

    return problems


def check_coverage(
    root: Path,
    review_records: Iterable[dict[str, Any]],
    module_contracts: dict[str, str],
) -> dict[str, Any]:
    """Check that every governed module has a current terminal Fable review."""
    root = root.resolve()
    modules = discover_modules(root)
    by_module: dict[str, list[dict[str, Any]]] = {}
    for record in review_records:
        module = _metadata(record).get("review_module")
        if isinstance(module, str):
            by_module.setdefault(module, []).append(record)

    covered: list[str] = []
    missing: list[str] = []
    missing_contracts: list[str] = []
    problems: list[str] = []
    selected_reviews: dict[str, str] = {}

    for module in modules:
        contract = module_contracts.get(module)
        if contract is None:
            missing_contracts.append(module)
            continue

        records = by_module.get(module, [])
        if not records:
            missing.append(module)
            continue

        current_hash = hashlib.sha256(read_governed_bytes(root, module)).hexdigest()
        current_contract_hash = sha256_contract(contract)
        current_governing_contract_hash = governing_contract_sha256(
            root, module, contract
        )
        candidates: list[tuple[dict[str, Any], list[str]]] = [
            (
                record,
                _review_problems(
                    record,
                    module,
                    current_hash,
                    current_contract_hash,
                    current_governing_contract_hash,
                ),
            )
            for record in records
        ]
        valid = [record for record, issues in candidates if not issues]
        if valid:
            selected = valid[-1]
            covered.append(module)
            selected_reviews[module] = str(selected.get("id", "<unknown-review>"))
            continue

        for _, issues in candidates:
            problems.extend(issues)

    coverage_complete = not missing and not missing_contracts and not problems
    return {
        "schema_version": "deja-vu.fable-review-coverage/v1",
        "ok": False,
        "coverage_complete": coverage_complete,
        "diagnostic_only": True,
        "release_authorized": False,
        "authority_note": (
            "Local Beads metadata is untrusted coverage input. Only the pinned "
            "external verifier may authorize release."
        ),
        "modules": modules,
        "covered": covered,
        "missing": missing,
        "missing_contracts": missing_contracts,
        "problems": problems,
        "selected_reviews": selected_reviews,
    }


def load_beads_reviews(root: Path) -> list[dict[str, Any]]:
    """Load all Fable review Beads through the stable JSON CLI."""
    completed = subprocess.run(
        [
            "bd",
            "list",
            "--all",
            "--label",
            "fable-review",
            "--limit",
            "0",
            "--json",
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    loaded = json.loads(completed.stdout)
    if not isinstance(loaded, list):
        raise ValueError("bd list did not return a JSON array")
    return loaded


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Diagnose current Claude Fable 5 review coverage; the external "
            "verifier alone may authorize release."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root. Defaults to this script's repository.",
    )
    parser.add_argument(
        "--records-json",
        type=Path,
        help="Read a JSON array exported by bd instead of invoking bd.",
    )
    parser.add_argument("--json", action="store_true", help="Print the full report.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.records_json:
            records = json.loads(args.records_json.read_text())
            if not isinstance(records, list):
                raise ValueError("--records-json must contain a JSON array")
        else:
            records = load_beads_reviews(args.root)
        contracts = load_canonical_module_contracts(args.root)
        report = check_coverage(args.root, records, contracts)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"FABLE_REVIEW_GATE: ERROR -- {error}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif report["coverage_complete"]:
        print(
            "FABLE_REVIEW_GATE: COVERAGE-ONLY -- "
            f"{len(report['covered'])} modules; external verification required"
        )
    else:
        print(
            "FABLE_REVIEW_GATE: FAIL -- "
            f"{len(report['missing'])} missing, "
            f"{len(report['missing_contracts'])} uncontracted, "
            f"{len(report['problems'])} invalid"
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
