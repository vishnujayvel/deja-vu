import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import fable_review_gate


TEST_CONTRACT = "The module must return deterministic, validated results."


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def review_for(
    module: Path,
    root: Path,
    *,
    status: str = "closed",
    model: str = "claude-fable-5",
    target: str = "deja-vu/claude-fable-review",
    permission: str = "read-only",
    verdict: str = "pass",
    unresolved: str = "0",
    artifact_hash: str | None = None,
    contract: str = TEST_CONTRACT,
    contract_hash: str | None = None,
    governing_hash: str | None = None,
    launch_hash: str = "1" * 64,
    attested: str = "true",
) -> dict:
    relative = module.relative_to(root).as_posix()
    return {
        "id": "deja-vu-review-1",
        "status": status,
        "labels": ["fable-review"],
        "metadata": {
            "review_schema": "deja-vu.fable-review/v1",
            "review_module": relative,
            "review_artifact_sha256": artifact_hash or digest(module),
            "review_contract_sha256": contract_hash
            or hashlib.sha256(contract.encode()).hexdigest(),
            "review_governing_contract_sha256": governing_hash
            or fable_review_gate.governing_contract_sha256(
                root, relative, contract
            ),
            "review_model": model,
            "review_target": target,
            "review_permission": permission,
            "review_permission_attested": attested,
            "review_launch_envelope_sha256": launch_hash,
            "review_delegate_job_id": "job-fable-review-1",
            "review_verdict": verdict,
            "review_round": "1",
            "review_findings_unresolved": unresolved,
            "review_contract_ref": "bead:deja-vu-v2.25",
            "review_implementation_bead": "deja-vu-v2.25",
        },
    }


def test_discover_modules_finds_executable_and_public_contract_files(tmp_path: Path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "worker.py").write_text("VALUE = 1\n")
    (tmp_path / "scripts" / "check.sh").write_text("#!/bin/sh\n")
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas" / "manifest.json").write_text("{}\n")
    (tmp_path / "contracts").mkdir()
    (tmp_path / "contracts" / "module-contracts.json").write_text("{}\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "design.md").write_text("# Design\n")
    (tmp_path / "policy").mkdir()
    (tmp_path / "policy" / "tiers.json").write_text("{}\n")
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "run_evals.py").write_text("VALUE = 1\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_worker.py").write_text("def test_ok(): pass\n")
    (tmp_path / "SKILL.md").write_text("---\nname: example\n---\n")

    assert fable_review_gate.discover_modules(tmp_path) == [
        "SKILL.md",
        "contracts/module-contracts.json",
        "docs/design.md",
        "evals/run_evals.py",
        "policy/tiers.json",
        "schemas/manifest.json",
        "scripts/check.sh",
        "scripts/worker.py",
    ]


def test_discover_modules_rejects_governed_symlink(tmp_path: Path):
    outside = tmp_path / "outside.py"
    outside.write_text("SECRET = 'outside'\n")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "worker.py").symlink_to(outside)

    with pytest.raises(ValueError, match="symlink"):
        fable_review_gate.discover_modules(tmp_path)


def test_check_coverage_accepts_current_terminal_fable_review(tmp_path: Path):
    module = tmp_path / "scripts" / "worker.py"
    module.parent.mkdir()
    module.write_text("VALUE = 1\n")

    report = fable_review_gate.check_coverage(
        tmp_path,
        [review_for(module, tmp_path)],
        {"scripts/worker.py": TEST_CONTRACT},
    )

    assert report["coverage_complete"] is True
    assert report["release_authorized"] is False
    assert report["ok"] is False
    assert report["covered"] == ["scripts/worker.py"]
    assert report["problems"] == []


@pytest.mark.parametrize(
    ("mutation", "problem"),
    [
        ({"status": "open"}, "non-terminal"),
        ({"model": "claude-opus-4"}, "wrong reviewer model"),
        ({"target": "beads/claude-fable-review"}, "wrong review target"),
        ({"permission": "workspace-write"}, "not read-only"),
        ({"attested": "false"}, "permission was not launcher-attested"),
        ({"launch_hash": ""}, "missing launch envelope hash"),
        ({"verdict": "fix-first"}, "non-terminal verdict"),
        ({"unresolved": "2"}, "unresolved findings"),
        ({"artifact_hash": "0" * 64}, "stale artifact hash"),
        ({"contract_hash": "0" * 64}, "stale contract hash"),
        ({"governing_hash": "0" * 64}, "stale governing contract hash"),
    ],
)
def test_check_coverage_rejects_invalid_review(
    tmp_path: Path, mutation: dict, problem: str
):
    module = tmp_path / "scripts" / "worker.py"
    module.parent.mkdir()
    module.write_text("VALUE = 1\n")

    report = fable_review_gate.check_coverage(
        tmp_path,
        [review_for(module, tmp_path, **mutation)],
        {"scripts/worker.py": TEST_CONTRACT},
    )

    assert report["ok"] is False
    assert any(problem in item for item in report["problems"])


def test_check_coverage_reports_missing_module_review(tmp_path: Path):
    module = tmp_path / "scripts" / "worker.py"
    module.parent.mkdir()
    module.write_text("VALUE = 1\n")

    report = fable_review_gate.check_coverage(
        tmp_path, [], {"scripts/worker.py": TEST_CONTRACT}
    )

    assert report["ok"] is False
    assert report["missing"] == ["scripts/worker.py"]


def test_stale_prior_review_does_not_mask_current_review(tmp_path: Path):
    module = tmp_path / "scripts" / "worker.py"
    module.parent.mkdir()
    module.write_text("VALUE = 1\n")
    stale = review_for(module, tmp_path, artifact_hash="0" * 64)
    current = review_for(module, tmp_path)
    current["id"] = "deja-vu-review-2"

    report = fable_review_gate.check_coverage(
        tmp_path,
        [stale, current],
        {"scripts/worker.py": TEST_CONTRACT},
    )

    assert report["coverage_complete"] is True
    assert report["release_authorized"] is False
    assert report["selected_reviews"] == {
        "scripts/worker.py": "deja-vu-review-2"
    }


def test_architecture_change_invalidates_module_review(tmp_path: Path):
    module = tmp_path / "scripts" / "worker.py"
    module.parent.mkdir()
    module.write_text("VALUE = 1\n")
    design = tmp_path / "docs" / "design.md"
    design.parent.mkdir()
    design.write_text("# Contract v1\n")
    contracts = {
        "docs/design.md": "Define the architecture.",
        "scripts/worker.py": TEST_CONTRACT,
    }
    review = review_for(
        module,
        tmp_path,
        governing_hash=fable_review_gate.governing_contract_sha256(
            tmp_path, "scripts/worker.py", TEST_CONTRACT
        ),
    )
    design.write_text("# Contract v2\n")

    report = fable_review_gate.check_coverage(tmp_path, [review], contracts)

    assert report["ok"] is False
    assert any("stale governing contract hash" in item for item in report["problems"])


def test_unrelated_contract_does_not_invalidate_module_review(tmp_path: Path):
    module = tmp_path / "scripts" / "worker.py"
    module.parent.mkdir()
    module.write_text("VALUE = 1\n")
    initial_contracts = {"scripts/worker.py": TEST_CONTRACT}
    review = review_for(module, tmp_path)
    expanded_contracts = initial_contracts | {
        "scripts/another.py": "Another governed behavior."
    }

    report = fable_review_gate.check_coverage(
        tmp_path, [review], expanded_contracts
    )

    assert report["coverage_complete"] is True
    assert report["release_authorized"] is False
    assert report["problems"] == []


def test_cli_reads_exported_beads_json_as_non_authoritative_diagnostic(
    tmp_path: Path,
):
    workspace = tmp_path / "workspace"
    module = workspace / "scripts" / "worker.py"
    module.parent.mkdir(parents=True)
    module.write_text("VALUE = 1\n")
    contracts = workspace / "contracts" / "module-contracts.json"
    contracts.parent.mkdir()
    contracts.write_text(
        json.dumps(
            {
                "schema_version": "deja-vu.module-contracts/v1",
                "modules": [
                    {"path": "scripts/worker.py", "contract": TEST_CONTRACT},
                    {
                        "path": "contracts/module-contracts.json",
                        "contract": "Define canonical module contracts.",
                    },
                ],
            }
        )
    )
    records = tmp_path / "reviews.json"
    records.write_text(
        json.dumps(
            [
                review_for(module, workspace),
                review_for(
                    contracts,
                    workspace,
                    contract="Define canonical module contracts.",
                ),
            ]
        )
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(Path(fable_review_gate.__file__)),
            "--root",
            str(workspace),
            "--records-json",
            str(records),
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    report = json.loads(completed.stdout)
    assert report["coverage_complete"] is True
    assert report["release_authorized"] is False
    assert report["ok"] is False


def test_cli_rejects_caller_selected_contract_map(tmp_path: Path):
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(fable_review_gate.__file__)),
            "--root",
            str(tmp_path),
            "--contracts-json",
            str(tmp_path / "weakened.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "unrecognized arguments" in completed.stderr


@pytest.mark.parametrize(
    "module_path",
    [
        "/tmp/worker.py",
        "scripts/../worker.py",
        "scripts//worker.py",
        "scripts/worker.py.trailing",
        "schemas/schema.json/extra",
        "docs/design.md/extra",
        "scripts\\worker.py",
    ],
)
def test_load_module_contracts_rejects_noncanonical_paths(
    tmp_path: Path, module_path: str
):
    contracts = tmp_path / "module-contracts.json"
    contracts.write_text(
        json.dumps(
            {
                "schema_version": "deja-vu.module-contracts/v1",
                "modules": [{"path": module_path, "contract": TEST_CONTRACT}],
            }
        )
    )

    with pytest.raises(ValueError, match="invalid path"):
        fable_review_gate.load_module_contracts(contracts)


def test_check_coverage_rejects_unsigned_human_override(tmp_path: Path):
    module = tmp_path / "scripts" / "worker.py"
    module.parent.mkdir()
    module.write_text("VALUE = 1\n")

    report = fable_review_gate.check_coverage(
        tmp_path,
        [review_for(module, tmp_path, verdict="human-override")],
        {"scripts/worker.py": TEST_CONTRACT},
    )

    assert report["coverage_complete"] is False
    assert any("human override requires external adjudication" in item for item in report["problems"])


def test_missing_module_contract_fails_closed(tmp_path: Path):
    module = tmp_path / "scripts" / "worker.py"
    module.parent.mkdir()
    module.write_text("VALUE = 1\n")

    report = fable_review_gate.check_coverage(
        tmp_path, [review_for(module, tmp_path)], {}
    )

    assert report["ok"] is False
    assert report["missing_contracts"] == ["scripts/worker.py"]


def test_review_record_schema_encodes_the_gate_contract():
    schema_path = (
        Path(fable_review_gate.__file__).resolve().parents[1]
        / "schemas"
        / "fable-review-record.schema.json"
    )
    schema = json.loads(schema_path.read_text())

    assert schema["$id"] == "https://deja-vu.local/schemas/fable-review-record/v1"
    assert schema["additionalProperties"] is False
    assert {
        "module_path",
        "artifact_sha256",
        "contract_sha256",
        "governing_contract_sha256",
        "contract_ref",
        "implementation_bead",
        "delegate_job_id",
        "launch_envelope_sha256",
        "permission_hash",
        "stdout_sha256",
        "result_evidence_sha256",
        "reviewer",
        "round",
        "verdict",
        "findings",
        "adjudication",
    } <= set(schema["required"])
    assert schema["properties"]["reviewer"]["properties"]["model"]["const"] == (
        "claude-fable-5"
    )
    assert "permission_attestation" not in schema["properties"]
    assert "permission_envelope" not in schema["properties"]
    assert schema["properties"]["adjudication"]["oneOf"][0] == {
        "type": "null"
    }
    finding_schema = schema["properties"]["findings"]["items"]
    assert {"evidence", "contract_clause"} <= set(finding_schema["required"])


def test_module_contract_schema_encodes_canonical_contract_map():
    schema_path = (
        Path(fable_review_gate.__file__).resolve().parents[1]
        / "schemas"
        / "module-contracts.schema.json"
    )
    schema = json.loads(schema_path.read_text())

    assert schema["$id"] == "https://deja-vu.local/schemas/module-contracts/v1"
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["const"] == (
        "deja-vu.module-contracts/v1"
    )
    module_schema = schema["properties"]["modules"]["items"]
    assert module_schema["additionalProperties"] is False
    assert set(module_schema["required"]) == {"path", "contract"}
    assert module_schema["properties"]["path"]["pattern"].endswith("$")


def test_repository_contract_map_exactly_matches_governed_inventory():
    root = Path(fable_review_gate.__file__).resolve().parents[1]
    contracts = fable_review_gate.load_module_contracts(
        root / "contracts" / "module-contracts.json"
    )

    assert sorted(contracts) == fable_review_gate.discover_modules(root)
