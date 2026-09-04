import hashlib
import json
from pathlib import Path

import pytest

from scripts import fable_review_gate, refinery_gate

MODULE = "scripts/target_module.py"
CONTRACT = "The module must return deterministic, validated results."


class FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def make_workspace(root: Path) -> Path:
    scripts = root / "scripts"
    scripts.mkdir()
    module_path = scripts / "target_module.py"
    module_path.write_text("VALUE = 1\n")
    contracts = root / "contracts"
    contracts.mkdir()
    (contracts / "module-contracts.json").write_text(
        json.dumps(
            {
                "schema_version": "deja-vu.module-contracts/v1",
                "modules": [{"path": MODULE, "contract": CONTRACT}],
            }
        )
    )
    return module_path


def module_hashes(root: Path) -> tuple[str, str]:
    artifact_sha256 = hashlib.sha256((root / MODULE).read_bytes()).hexdigest()
    governing_sha256 = fable_review_gate.governing_contract_sha256(root, MODULE, CONTRACT)
    return artifact_sha256, governing_sha256


# --- pure unit tests --------------------------------------------------------


@pytest.mark.parametrize(
    ("agent", "expected"),
    [
        ("deja-vu/gastown.refinery", True),
        ("deja-vu/refinery", True),
        ("deja-vu/gastown.polecat", False),
        ("deja-vu/gastown.witness", False),
        (None, False),
        ("", False),
    ],
)
def test_refinery_identity(agent, expected):
    assert refinery_gate.refinery_identity(agent) is expected


def test_resolve_bead_id_prefers_explicit_flag():
    assert (
        refinery_gate.resolve_bead_id("deja-vu-1", {"BEAD": "deja-vu-2"}, "polecat/deja-vu-3")
        == "deja-vu-1"
    )


def test_resolve_bead_id_falls_back_to_env():
    assert refinery_gate.resolve_bead_id(None, {"WORK": "deja-vu-2"}, "polecat/deja-vu-3") == "deja-vu-2"


def test_resolve_bead_id_falls_back_to_branch_name():
    assert refinery_gate.resolve_bead_id(None, {}, "polecat/deja-vu-5x6.1") == "deja-vu-5x6.1"


def test_resolve_bead_id_returns_none_when_unresolvable():
    assert refinery_gate.resolve_bead_id(None, {}, "main") is None


def test_select_round_attempt_returns_first_free_slot():
    assert refinery_gate.select_round_attempt([], "a" * 64, "b" * 64) == (1, 1)


def test_select_round_attempt_skips_used_slots_for_same_hash():
    records = [
        {
            "metadata": {
                "review_artifact_sha256": "a" * 64,
                "review_governing_contract_sha256": "b" * 64,
                "review_delegate_job_id": "job-fable-target-module-abc-def-r1-a1",
            }
        }
    ]
    assert refinery_gate.select_round_attempt(records, "a" * 64, "b" * 64) == (1, 2)


def test_select_round_attempt_ignores_stale_hash_records():
    records = [
        {
            "metadata": {
                "review_artifact_sha256": "0" * 64,
                "review_governing_contract_sha256": "0" * 64,
                "review_delegate_job_id": "job-fable-target-module-abc-def-r1-a1",
            }
        }
    ]
    assert refinery_gate.select_round_attempt(records, "a" * 64, "b" * 64) == (1, 1)


def test_select_round_attempt_exhausted_returns_none():
    records = [
        {
            "metadata": {
                "review_artifact_sha256": "a" * 64,
                "review_governing_contract_sha256": "b" * 64,
                "review_delegate_job_id": f"job-fable-target-module-abc-def-r{r}-a{a}",
            }
        }
        for r in (1, 2, 3)
        for a in (1, 2, 3)
    ]
    assert refinery_gate.select_round_attempt(records, "a" * 64, "b" * 64) is None


def test_write_review_record_metadata_satisfies_fable_review_gate(tmp_path, monkeypatch):
    module_path = make_workspace(tmp_path)
    artifact_sha256, governing_sha256 = module_hashes(tmp_path)
    review = {
        "schema_version": "deja-vu.fable-review/v1",
        "review_id": "review-abc123",
        "module_path": MODULE,
        "artifact_sha256": artifact_sha256,
        "contract_sha256": fable_review_gate.sha256_contract(CONTRACT),
        "governing_contract_sha256": governing_sha256,
        "contract_ref": "contracts/module-contracts.json",
        "implementation_bead": "deja-vu-5x6.1",
        "delegate_job_id": "job-fable-target-module-abc-def-r1-a1",
        "launch_envelope_sha256": "1" * 64,
        "reviewer": {
            "family": "claude",
            "model": "claude-fable-5",
            "target": "deja-vu/claude-fable-review",
        },
        "round": 1,
        "verdict": "pass",
        "findings": [],
        "adjudication": None,
    }

    captured = {}

    def fake_run(command, cwd=None, capture_output=True, text=True, check=False, timeout=None):
        assert command[:2] == ["bd", "create"]
        metadata = json.loads(command[command.index("--metadata") + 1])
        captured["metadata"] = metadata
        return FakeCompleted(0, json.dumps({"id": "deja-vu-review-99"}))

    monkeypatch.setattr(refinery_gate.subprocess, "run", fake_run)

    created_id = refinery_gate.write_review_record(tmp_path, "deja-vu-5x6.1", review)

    assert created_id == "deja-vu-review-99"
    record = {
        "id": "deja-vu-review-99",
        "status": "closed",
        "labels": ["fable-review"],
        "metadata": {**captured["metadata"], "review_module": MODULE},
    }
    report = fable_review_gate.check_coverage(tmp_path, [record], {MODULE: CONTRACT})
    assert report["problems"] == []
    assert report["covered"] == [MODULE]


# --- main() orchestration ----------------------------------------------------


def test_skip_when_not_refinery(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GC_AGENT", raising=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("must not run any subprocess when skipping")

    monkeypatch.setattr(refinery_gate.subprocess, "run", forbidden)

    code = refinery_gate.main(["--root", str(tmp_path)])

    assert code == 0
    assert "REFINERY_GATE: skip" in capsys.readouterr().out


def test_refuse_on_failed_tests(tmp_path, monkeypatch, capsys):
    make_workspace(tmp_path)

    def fake_run(command, cwd=None, capture_output=True, text=True, check=False, timeout=None):
        if command[:3] == ["python3", "-m", "pytest"]:
            return FakeCompleted(1, "1 failed", "")
        raise AssertionError(f"unexpected command after test failure: {command}")

    monkeypatch.setattr(refinery_gate.subprocess, "run", fake_run)

    code = refinery_gate.main(["--root", str(tmp_path), "--force"])

    assert code == 1
    out = capsys.readouterr().out
    assert "REFINERY_GATE: refuse reason=pytest failed" in out


def test_allow_when_no_governed_module_changed(tmp_path, monkeypatch, capsys):
    make_workspace(tmp_path)

    def fake_run(command, cwd=None, capture_output=True, text=True, check=False, timeout=None):
        if command[0] == "python3" and command[1:3] == ["-m", "pytest"]:
            return FakeCompleted(0)
        if command == ["python3", "scripts/doctor.py"]:
            return FakeCompleted(0)
        if command == ["python3", "evals/run_evals.py", "--offline"]:
            return FakeCompleted(0)
        if command == ["bash", "scripts/sanitize_check.sh"]:
            return FakeCompleted(0)
        if command == ["git", "diff", "--name-only", "origin/p1-night...HEAD"]:
            return FakeCompleted(0, "README.md\n")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(refinery_gate.subprocess, "run", fake_run)

    code = refinery_gate.main(["--root", str(tmp_path), "--force"])

    assert code == 0
    assert "REFINERY_GATE: allow reason=ok" in capsys.readouterr().out


def _quality_gates_pass(command):
    if command[0] == "python3" and command[1:3] == ["-m", "pytest"]:
        return FakeCompleted(0)
    if command == ["python3", "scripts/doctor.py"]:
        return FakeCompleted(0)
    if command == ["python3", "evals/run_evals.py", "--offline"]:
        return FakeCompleted(0)
    if command == ["bash", "scripts/sanitize_check.sh"]:
        return FakeCompleted(0)
    return None


def test_round_attempt_exhausted_refuses_without_calling_jobctl(tmp_path, monkeypatch):
    make_workspace(tmp_path)
    artifact_sha256, governing_sha256 = module_hashes(tmp_path)
    exhausted_records = [
        {
            "metadata": {
                "review_artifact_sha256": artifact_sha256,
                "review_governing_contract_sha256": governing_sha256,
                "review_delegate_job_id": f"job-fable-target-module-abc-def-r{r}-a{a}",
            }
        }
        for r in (1, 2, 3)
        for a in (1, 2, 3)
    ]

    def fake_run(command, cwd=None, capture_output=True, text=True, check=False, timeout=None):
        gate = _quality_gates_pass(command)
        if gate is not None:
            return gate
        if command == ["git", "diff", "--name-only", "origin/p1-night...HEAD"]:
            return FakeCompleted(0, f"{MODULE}\n")
        if command[:2] == ["git", "branch"]:
            return FakeCompleted(0, "polecat/deja-vu-5x6.1\n")
        if command[:2] == ["bd", "list"]:
            return FakeCompleted(0, json.dumps(exhausted_records))
        if "jobctl" in command[0] or command[:2] == ["bd", "create"]:
            raise AssertionError(f"must not reach jobctl or bd create: {command}")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(refinery_gate.subprocess, "run", fake_run)

    code = refinery_gate.main(["--root", str(tmp_path), "--force"])

    assert code == 1


def _fake_run_full_review(module_path, verdict, findings=None):
    findings = findings or []

    def fake_run(command, cwd=None, capture_output=True, text=True, check=False, timeout=None):
        gate = _quality_gates_pass(command)
        if gate is not None:
            return gate
        if command == ["git", "diff", "--name-only", "origin/p1-night...HEAD"]:
            return FakeCompleted(0, f"{MODULE}\n")
        if command[:2] == ["git", "branch"]:
            return FakeCompleted(0, "polecat/deja-vu-5x6.1\n")
        if command[:2] == ["bd", "list"]:
            return FakeCompleted(0, "[]")
        if command[:2] == ["python3", "scripts/prepare_fable_review.py"]:
            manifest_path = module_path.parent / "manifest.json"
            manifest_path.write_text("{}\n")
            return FakeCompleted(
                0,
                json.dumps(
                    {
                        "module": MODULE,
                        "manifest_path": str(manifest_path),
                        "job_id": "job-fable-target-module-abc-def-r1-a1",
                    }
                ),
            )
        if command[1:2] == ["validate"]:
            return FakeCompleted(0, json.dumps({"valid": True, "job_id": "job-fable-target-module-abc-def-r1-a1"}))
        if command[1:2] == ["submit"]:
            return FakeCompleted(0, json.dumps({"job_id": "job-fable-target-module-abc-def-r1-a1", "state": "running"}))
        if command[1:2] == ["wait"]:
            return FakeCompleted(0, json.dumps({"job_id": "job-fable-target-module-abc-def-r1-a1", "state": "succeeded"}))
        if command[1:2] == ["verify-review"]:
            artifact_sha256, governing_sha256 = module_hashes(module_path.parent.parent)
            review = {
                "schema_version": "deja-vu.fable-review/v1",
                "review_id": "review-abc123",
                "module_path": MODULE,
                "artifact_sha256": artifact_sha256,
                "contract_sha256": fable_review_gate.sha256_contract(CONTRACT),
                "governing_contract_sha256": governing_sha256,
                "contract_ref": "contracts/module-contracts.json",
                "implementation_bead": "deja-vu-5x6.1",
                "delegate_job_id": "job-fable-target-module-abc-def-r1-a1",
                "launch_envelope_sha256": "1" * 64,
                "reviewer": {
                    "family": "claude",
                    "model": "claude-fable-5",
                    "target": "deja-vu/claude-fable-review",
                },
                "round": 1,
                "verdict": verdict,
                "findings": findings,
                "adjudication": None,
            }
            # Real jobctl verify-review exits 0 whenever evidence is
            # verifiable, regardless of the review's pass/fix-first verdict
            # -- only evidence problems (not verdict content) raise nonzero.
            return FakeCompleted(
                0,
                json.dumps(
                    {
                        "schema_version": "gc-router.deja-vu-review-verification/v1",
                        "evidence_verified": True,
                        "release_eligible": verdict == "pass",
                        "review": review,
                    }
                ),
            )
        if command[:2] == ["bd", "create"]:
            return FakeCompleted(0, json.dumps({"id": "deja-vu-review-99"}))
        if command[:2] == ["bd", "update"]:
            return FakeCompleted(0)
        if command[:3] == ["python3", "scripts/fable_review_gate.py", "--root"]:
            return FakeCompleted(1, json.dumps({"covered": [MODULE], "missing": [], "problems": []}))
        raise AssertionError(f"unexpected command: {command}")

    return fake_run


def test_allow_path_full_governed_review(tmp_path, monkeypatch, capsys):
    module_path = make_workspace(tmp_path)
    monkeypatch.setattr(
        refinery_gate.subprocess, "run", _fake_run_full_review(module_path, "pass")
    )

    code = refinery_gate.main(["--root", str(tmp_path), "--force"])

    assert code == 0
    assert "REFINERY_GATE: allow reason=ok" in capsys.readouterr().out


def test_refuse_on_fix_first_verdict_appends_findings_note(tmp_path, monkeypatch, capsys):
    module_path = make_workspace(tmp_path)
    findings = [
        {
            "finding_id": "finding-1",
            "severity": "high",
            "summary": "Missing input validation.",
            "evidence": "line 12",
            "contract_clause": "deterministic results",
            "classification": "actionable",
            "resolution": "Unresolved: change the artifact and run a fresh review.",
        }
    ]
    fake_run = _fake_run_full_review(module_path, "fix-first", findings)

    note_calls = []
    original_fake_run = fake_run

    def wrapped(command, **kwargs):
        if command[:2] == ["bd", "update"]:
            note_calls.append(command)
        return original_fake_run(command, **kwargs)

    monkeypatch.setattr(refinery_gate.subprocess, "run", wrapped)

    code = refinery_gate.main(["--root", str(tmp_path), "--force"])

    assert code == 1
    assert "REFINERY_GATE: refuse reason=review-verdict" in capsys.readouterr().out
    assert len(note_calls) == 1
    assert "fix-first" in note_calls[0][4]
