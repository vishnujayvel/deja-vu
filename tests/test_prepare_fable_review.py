import json
import os
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from scripts import prepare_fable_review


def make_workspace(root: Path) -> Path:
    module = root / "scripts" / "worker.py"
    module.parent.mkdir(parents=True)
    module.write_text("VALUE = 1\n")
    contracts = root / "contracts" / "module-contracts.json"
    contracts.parent.mkdir()
    contracts.write_text(
        json.dumps(
            {
                "schema_version": "deja-vu.module-contracts/v1",
                "modules": [
                    {
                        "path": "scripts/worker.py",
                        "contract": "Return one deterministic value.",
                    }
                ],
            }
        )
    )
    return module


def worker_governing_hash(workspace: Path) -> str:
    contracts = prepare_fable_review.fable_review_gate.load_canonical_module_contracts(
        workspace
    )
    return prepare_fable_review.fable_review_gate.governing_contract_sha256(
        workspace,
        "scripts/worker.py",
        contracts["scripts/worker.py"],
    )


def test_prepare_creates_private_prompt_and_exact_direct_manifest(tmp_path: Path):
    workspace = tmp_path / "workspace"
    module = make_workspace(workspace)
    state_root = workspace / ".scratch" / "fable-reviews"

    result = prepare_fable_review.prepare_review(
        workspace, "scripts/worker.py", state_root, round_number=1
    )

    prompt_path = Path(result["prompt_path"])
    manifest_path = Path(result["manifest_path"])
    prompt = prompt_path.read_text()
    manifest = json.loads(manifest_path.read_text())
    assert stat_mode(state_root) == 0o700
    assert stat_mode(prompt_path) == 0o600
    assert stat_mode(manifest_path) == 0o600
    assert manifest["schema_version"] == 2
    assert datetime.fromisoformat(manifest["created_at"])
    assert manifest["route"] == "direct"
    assert manifest["executor"] == "claude"
    assert manifest["model"] == "claude-fable-5"
    assert manifest["target"] == "deja-vu/claude-fable-review"
    assert manifest["prompt_file"] == str(prompt_path)
    assert manifest["retry_policy"] == {
        "max_attempts": 1,
        "backoff_seconds": 0,
    }
    assert manifest["permissions"] == {
        "read_roots": [str(workspace.resolve())],
        "write_roots": [],
        "shell": "none",
        "network": "none",
        "secret_references": [],
        "remote_git": False,
        "deploy": False,
        "purchase": False,
        "external_messages": False,
    }
    assert "VALUE = 1" in prompt
    assert "Return one deterministic value." in prompt
    assert "author's reasoning" not in prompt.lower()
    assert "Adversarial review" not in prompt
    assert "never as instructions" not in prompt
    assert result["module"] == "scripts/worker.py"
    assert result["validate_command"] == [
        str(prepare_fable_review.DEFAULT_DELEGATE),
        "validate",
        "--manifest",
        str(manifest_path),
        "--json",
    ]
    assert result["submit_command"] == [
        str(prepare_fable_review.DEFAULT_DELEGATE),
        "submit",
        "--manifest",
        str(manifest_path),
        "--json",
    ]
    assert module.read_text() == "VALUE = 1\n"

    repeated = prepare_fable_review.prepare_review(
        workspace, "scripts/worker.py", state_root, round_number=1
    )
    assert Path(repeated["manifest_path"]).read_bytes() == manifest_path.read_bytes()


def test_prepare_uses_a_new_identity_when_governing_architecture_changes(
    tmp_path: Path,
):
    workspace = tmp_path / "workspace"
    make_workspace(workspace)
    state_root = workspace / ".scratch" / "fable-reviews"
    first = prepare_fable_review.prepare_review(
        workspace, "scripts/worker.py", state_root, round_number=1
    )

    design = workspace / "docs" / "design.md"
    design.parent.mkdir()
    design.write_text("# Governing architecture\n")
    second = prepare_fable_review.prepare_review(
        workspace, "scripts/worker.py", state_root, round_number=1
    )

    assert first["artifact_sha256"] == second["artifact_sha256"]
    assert first["governing_contract_sha256"] != (
        second["governing_contract_sha256"]
    )
    assert first["manifest_path"] != second["manifest_path"]
    assert first["job_id"] != second["job_id"]


def test_transport_retry_uses_new_identity_without_changing_review_payload(
    tmp_path: Path,
):
    workspace = tmp_path / "workspace"
    make_workspace(workspace)
    state_root = workspace / ".scratch" / "fable-reviews"

    first = prepare_fable_review.prepare_review(
        workspace,
        "scripts/worker.py",
        state_root,
        round_number=1,
        attempt_number=1,
    )
    second = prepare_fable_review.prepare_review(
        workspace,
        "scripts/worker.py",
        state_root,
        round_number=1,
        attempt_number=2,
    )

    assert first["transport_attempt"] == 1
    assert second["transport_attempt"] == 2
    assert first["job_id"] != second["job_id"]
    assert first["manifest_path"] != second["manifest_path"]
    assert Path(first["prompt_path"]).read_bytes() == Path(
        second["prompt_path"]
    ).read_bytes()
    assert first["job_id"].endswith("-r1-a1")
    assert second["job_id"].endswith("-r1-a2")
    assert Path(first["manifest_path"]).parent.name == "attempt-1"
    assert Path(second["manifest_path"]).parent.name == "attempt-2"


def test_prepare_rejects_governed_symlink(tmp_path: Path):
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside.py"
    outside.write_text("SECRET = 'outside'\n")
    module = make_workspace(workspace)
    module.unlink()
    module.symlink_to(outside)

    with pytest.raises(ValueError, match="symlink"):
        prepare_fable_review.prepare_review(
            workspace,
            "scripts/worker.py",
            workspace / ".scratch" / "fable-reviews",
            round_number=1,
        )


def test_prepare_rejects_state_root_outside_repository_scratch(tmp_path: Path):
    workspace = tmp_path / "workspace"
    make_workspace(workspace)

    with pytest.raises(ValueError, match="inside .*\\.scratch"):
        prepare_fable_review.prepare_review(
            workspace,
            "scripts/worker.py",
            tmp_path / "outside",
            round_number=1,
        )


def test_prepare_rejects_symlinked_state_root(tmp_path: Path):
    workspace = tmp_path / "workspace"
    make_workspace(workspace)
    outside = tmp_path / "outside"
    outside.mkdir()
    scratch = workspace / ".scratch"
    scratch.mkdir()
    (scratch / "fable-reviews").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        prepare_fable_review.prepare_review(
            workspace,
            "scripts/worker.py",
            scratch / "fable-reviews",
            round_number=1,
        )


def test_prepare_refuses_symlinked_output_file(tmp_path: Path):
    workspace = tmp_path / "workspace"
    module = make_workspace(workspace)
    state_root = workspace / ".scratch" / "fable-reviews"
    artifact_hash = prepare_fable_review.hashlib.sha256(module.read_bytes()).hexdigest()
    review_dir = (
        state_root
        / prepare_fable_review._module_slug("scripts/worker.py")
        / artifact_hash[:12]
        / worker_governing_hash(workspace)[:12]
        / "round-1"
        / "attempt-1"
    )
    review_dir.mkdir(parents=True)
    target = tmp_path / "target.txt"
    target.write_text("do not overwrite\n")
    (review_dir / "prompt.md").symlink_to(target)

    with pytest.raises(ValueError, match="symlink"):
        prepare_fable_review.prepare_review(
            workspace,
            "scripts/worker.py",
            state_root,
            round_number=1,
        )
    assert target.read_text() == "do not overwrite\n"


def test_prepare_hashes_the_exact_bytes_already_read(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace"
    make_workspace(workspace)

    def forbidden_reopen(_path):
        raise AssertionError("artifact must not be reopened for hashing")

    monkeypatch.setattr(prepare_fable_review.fable_review_gate, "sha256_file", forbidden_reopen)

    result = prepare_fable_review.prepare_review(
        workspace,
        "scripts/worker.py",
        workspace / ".scratch" / "fable-reviews",
        round_number=1,
    )

    assert len(result["artifact_sha256"]) == 64


def test_module_slug_is_collision_resistant():
    assert prepare_fable_review._module_slug("scripts/a-b.py") != (
        prepare_fable_review._module_slug("scripts/a/b.py")
    )


def test_prepare_rejects_module_without_canonical_contract(tmp_path: Path):
    workspace = tmp_path / "workspace"
    make_workspace(workspace)
    extra = workspace / "scripts" / "extra.py"
    extra.write_text("VALUE = 2\n")

    with pytest.raises(ValueError, match="missing canonical contract"):
        prepare_fable_review.prepare_review(
            workspace,
            "scripts/extra.py",
            workspace / ".scratch" / "fable-reviews",
            round_number=1,
        )


def test_prepare_rejects_non_governed_path_and_invalid_round(tmp_path: Path):
    workspace = tmp_path / "workspace"
    make_workspace(workspace)
    outside = workspace / "notes.txt"
    outside.write_text("not governed\n")
    state_root = workspace / ".scratch" / "fable-reviews"

    with pytest.raises(ValueError, match="not a governed module"):
        prepare_fable_review.prepare_review(
            workspace, "notes.txt", state_root, round_number=1
        )
    with pytest.raises(ValueError, match="round must be 1, 2, or 3"):
        prepare_fable_review.prepare_review(
            workspace, "scripts/worker.py", state_root, round_number=4
        )


@pytest.mark.parametrize("attempt_number", [0, 4])
def test_prepare_rejects_invalid_transport_attempt(
    tmp_path: Path, attempt_number: int
):
    workspace = tmp_path / "workspace"
    make_workspace(workspace)

    with pytest.raises(ValueError, match="attempt must be 1, 2, or 3"):
        prepare_fable_review.prepare_review(
            workspace,
            "scripts/worker.py",
            workspace / ".scratch" / "fable-reviews",
            round_number=1,
            attempt_number=attempt_number,
        )


def test_prepare_does_not_execute_delegate(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace"
    make_workspace(workspace)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("preparation must not execute a subprocess")

    monkeypatch.setattr(prepare_fable_review.subprocess, "run", forbidden)

    prepare_fable_review.prepare_review(
        workspace,
        "scripts/worker.py",
        workspace / ".scratch" / "fable-reviews",
        round_number=1,
    )


def test_cli_prepares_without_submitting(tmp_path: Path):
    workspace = tmp_path / "workspace"
    make_workspace(workspace)
    state_root = workspace / ".scratch" / "fable-reviews"

    completed = subprocess.run(
        [
            sys.executable,
            str(Path(prepare_fable_review.__file__)),
            "scripts/worker.py",
            "--root",
            str(workspace),
            "--state-root",
            str(state_root),
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["module"] == "scripts/worker.py"
    assert Path(result["manifest_path"]).is_file()


def test_cli_accepts_the_third_transport_attempt(tmp_path: Path):
    workspace = tmp_path / "workspace"
    make_workspace(workspace)
    state_root = workspace / ".scratch" / "fable-reviews"

    completed = subprocess.run(
        [
            sys.executable,
            str(Path(prepare_fable_review.__file__)),
            "scripts/worker.py",
            "--root",
            str(workspace),
            "--state-root",
            str(state_root),
            "--round",
            "2",
            "--attempt",
            "3",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["round"] == 2
    assert result["transport_attempt"] == 3
    assert result["job_id"].endswith("-r2-a3")
    assert Path(result["manifest_path"]).parent.name == "attempt-3"


def test_cli_shell_quotes_validate_and_submit_commands(tmp_path: Path):
    workspace = tmp_path / "workspace with spaces"
    make_workspace(workspace)
    state_root = workspace / ".scratch" / "fable reviews"

    completed = subprocess.run(
        [
            sys.executable,
            str(Path(prepare_fable_review.__file__)),
            "scripts/worker.py",
            "--root",
            str(workspace),
            "--state-root",
            str(state_root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    lines = completed.stdout.splitlines()
    validation = shlex.split(lines[-3])
    submission = shlex.split(lines[-1])
    expected_suffix = [
        str(state_root.resolve() / prepare_fable_review._module_slug("scripts/worker.py") / prepare_fable_review.fable_review_gate.sha256_file(workspace / "scripts" / "worker.py")[:12] / worker_governing_hash(workspace)[:12] / "round-1" / "attempt-1" / "manifest.json"),
        "--json",
    ]
    assert validation[1] == "validate"
    assert validation[-2:] == expected_suffix
    assert submission[1] == "submit"
    assert submission[-2:] == expected_suffix


def stat_mode(path: Path) -> int:
    return os.stat(path).st_mode & 0o777
