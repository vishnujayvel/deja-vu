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


def test_select_round_attempt_unparseable_job_id_consumes_its_round():
    records = [
        {
            "metadata": {
                "review_artifact_sha256": "a" * 64,
                "review_governing_contract_sha256": "b" * 64,
                "review_delegate_job_id": "not-a-round-attempt-suffix",
                "review_round": "1",
            }
        }
    ]
    # Round 1 is fully consumed by the unparseable record (conservative
    # fallback), so the next free slot is round 2, attempt 1 -- not (1, 1),
    # which the old code would have returned by ignoring the record.
    assert refinery_gate.select_round_attempt(records, "a" * 64, "b" * 64) == (2, 1)


def test_select_round_attempt_unparseable_job_id_with_invalid_round_falls_back_to_one():
    records = [
        {
            "metadata": {
                "review_artifact_sha256": "a" * 64,
                "review_governing_contract_sha256": "b" * 64,
                "review_delegate_job_id": "not-a-round-attempt-suffix",
                "review_round": "not-a-number",
            }
        }
    ]
    assert refinery_gate.select_round_attempt(records, "a" * 64, "b" * 64) == (2, 1)


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


def _make_review(artifact_sha256, governing_sha256, **overrides):
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
    review.update(overrides)
    return review


def test_write_review_record_metadata_satisfies_fable_review_gate(tmp_path, monkeypatch):
    make_workspace(tmp_path)
    artifact_sha256, governing_sha256 = module_hashes(tmp_path)
    review = _make_review(
        artifact_sha256, governing_sha256, permission="read-only", permission_attested=True
    )

    captured = {}

    def fake_run(command, cwd=None, capture_output=True, text=True, check=False, timeout=None):
        assert command[:2] == ["bd", "create"]
        metadata = json.loads(command[command.index("--metadata") + 1])
        captured["metadata"] = metadata
        return FakeCompleted(0, json.dumps({"id": "deja-vu-review-99"}))

    monkeypatch.setattr(refinery_gate.subprocess, "run", fake_run)

    created_id = refinery_gate.write_review_record(tmp_path, "deja-vu-5x6.1", review)

    assert created_id == "deja-vu-review-99"
    assert captured["metadata"]["review_permission"] == "read-only"
    assert captured["metadata"]["review_permission_attested"] == "true"
    record = {
        "id": "deja-vu-review-99",
        "status": "closed",
        "labels": ["fable-review"],
        "metadata": {**captured["metadata"], "review_module": MODULE},
    }
    report = fable_review_gate.check_coverage(tmp_path, [record], {MODULE: CONTRACT})
    assert report["problems"] == []
    assert report["covered"] == [MODULE]


def test_write_review_record_omits_permission_fields_when_verify_review_lacks_them(
    tmp_path, monkeypatch
):
    make_workspace(tmp_path)
    artifact_sha256, governing_sha256 = module_hashes(tmp_path)
    review = _make_review(artifact_sha256, governing_sha256)
    assert "permission" not in review and "permission_attested" not in review

    captured = {}

    def fake_run(command, cwd=None, capture_output=True, text=True, check=False, timeout=None):
        assert command[:2] == ["bd", "create"]
        metadata = json.loads(command[command.index("--metadata") + 1])
        captured["metadata"] = metadata
        return FakeCompleted(0, json.dumps({"id": "deja-vu-review-99"}))

    monkeypatch.setattr(refinery_gate.subprocess, "run", fake_run)

    refinery_gate.write_review_record(tmp_path, "deja-vu-5x6.1", review)

    assert "review_permission" not in captured["metadata"]
    assert "review_permission_attested" not in captured["metadata"]
    # Undeclared permission evidence must not silently count as coverage.
    record = {
        "id": "deja-vu-review-99",
        "status": "closed",
        "labels": ["fable-review"],
        "metadata": {**captured["metadata"], "review_module": MODULE},
    }
    report = fable_review_gate.check_coverage(tmp_path, [record], {MODULE: CONTRACT})
    assert report["covered"] == []
    assert any("not read-only" in problem for problem in report["problems"])


# --- main() orchestration ----------------------------------------------------


def test_skip_when_gc_agent_identifies_non_refinery(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GC_AGENT", "deja-vu/gastown.polecat")

    def forbidden(*args, **kwargs):
        raise AssertionError("must not run any subprocess when skipping")

    monkeypatch.setattr(refinery_gate.subprocess, "run", forbidden)

    code = refinery_gate.main(["--root", str(tmp_path)])

    assert code == 0
    assert "REFINERY_GATE: skip" in capsys.readouterr().out


def test_refuse_when_gc_agent_unset(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GC_AGENT", raising=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("must not run any subprocess when identity is unknown")

    monkeypatch.setattr(refinery_gate.subprocess, "run", forbidden)

    code = refinery_gate.main(["--root", str(tmp_path)])

    assert code == 1
    assert "REFINERY_GATE: refuse reason=identity-unknown" in capsys.readouterr().out


def test_refuse_when_gc_agent_blank(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GC_AGENT", "   ")

    def forbidden(*args, **kwargs):
        raise AssertionError("must not run any subprocess when identity is unknown")

    monkeypatch.setattr(refinery_gate.subprocess, "run", forbidden)

    code = refinery_gate.main(["--root", str(tmp_path)])

    assert code == 1
    assert "REFINERY_GATE: refuse reason=identity-unknown" in capsys.readouterr().out


def test_runs_when_gc_agent_identifies_refinery(tmp_path, monkeypatch, capsys):
    make_workspace(tmp_path)
    monkeypatch.setenv("GC_AGENT", "deja-vu/gastown.refinery")

    def fake_run(command, cwd=None, capture_output=True, text=True, check=False, timeout=None):
        gate = _quality_gates_pass(command)
        if gate is not None:
            return gate
        if command == ["git", "diff", "--name-only", "origin/p1-night...HEAD"]:
            return FakeCompleted(0, "README.md\n")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(refinery_gate.subprocess, "run", fake_run)

    code = refinery_gate.main(["--root", str(tmp_path)])

    assert code == 0
    assert "REFINERY_GATE: allow reason=ok" in capsys.readouterr().out


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


def test_refuse_on_fix_first_verdict_surfaces_note_append_failure(tmp_path, monkeypatch, capsys):
    module_path = make_workspace(tmp_path)
    findings = [
        {
            "finding_id": "finding-1",
            "severity": "high",
            "summary": "Missing input validation.",
            "evidence": "line 12",
            "contract_clause": "deterministic results",
            "classification": "actionable",
            "resolution": "Unresolved.",
        }
    ]
    original_fake_run = _fake_run_full_review(module_path, "fix-first", findings)

    def wrapped(command, **kwargs):
        if command[:2] == ["bd", "update"]:
            return FakeCompleted(1, "", "bd: database locked")
        return original_fake_run(command, **kwargs)

    monkeypatch.setattr(refinery_gate.subprocess, "run", wrapped)

    code = refinery_gate.main(["--root", str(tmp_path), "--force"])

    out = capsys.readouterr().out
    assert code == 1
    # Failure to record the findings note must be visible in the refusal
    # reason, not silently swallowed.
    assert "note-append-failed" in out
    assert out.count("REFINERY_GATE:") == 1


def test_internal_error_after_identity_guard_still_prints_single_line(
    tmp_path, monkeypatch, capsys
):
    make_workspace(tmp_path)

    def fake_run(command, cwd=None, capture_output=True, text=True, check=False, timeout=None):
        gate = _quality_gates_pass(command)
        if gate is not None:
            return gate
        if command == ["git", "diff", "--name-only", "origin/p1-night...HEAD"]:
            return FakeCompleted(0, f"{MODULE}\n")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(refinery_gate.subprocess, "run", fake_run)
    monkeypatch.setattr(
        refinery_gate.fable_review_gate,
        "discover_modules",
        lambda root: (_ for _ in ()).throw(OSError("disk went away")),
    )

    code = refinery_gate.main(["--root", str(tmp_path), "--force"])

    out = capsys.readouterr().out
    assert code == 1
    assert out.count("REFINERY_GATE:") == 1
    assert "REFINERY_GATE: refuse reason=internal-error:disk went away" in out


def test_target_flag_controls_diff_base(tmp_path, monkeypatch, capsys):
    make_workspace(tmp_path)

    def fake_run(command, cwd=None, capture_output=True, text=True, check=False, timeout=None):
        gate = _quality_gates_pass(command)
        if gate is not None:
            return gate
        if command == ["git", "diff", "--name-only", "origin/release...HEAD"]:
            return FakeCompleted(0, "README.md\n")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(refinery_gate.subprocess, "run", fake_run)

    code = refinery_gate.main(["--root", str(tmp_path), "--force", "--target", "release"])

    assert code == 0
    assert "REFINERY_GATE: allow reason=ok" in capsys.readouterr().out


def test_check_final_coverage_refuses_on_stale_problem_even_if_report_lists_module_covered(
    tmp_path, monkeypatch
):
    """Pins finding 1: the recheck must not trust bare 'covered' membership.

    Directly exercises check_final_coverage() against a canned
    fable_review_gate.py report shaped like the real check_coverage() output
    (covered/missing/missing_contracts/problems), asserting each category is
    inspected on its own rather than only "module not in covered".
    """

    def fake_run(command, cwd=None, capture_output=True, text=True, check=False, timeout=None):
        if command[:3] == ["python3", "scripts/fable_review_gate.py", "--root"]:
            return FakeCompleted(
                1,
                json.dumps(
                    {
                        "covered": [],
                        "missing": [],
                        "missing_contracts": [],
                        "problems": [f"{MODULE} (deja-vu-review-1): stale artifact hash"],
                    }
                ),
            )
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(refinery_gate.subprocess, "run", fake_run)

    ok, reason = refinery_gate.check_final_coverage(tmp_path, [MODULE])

    assert ok is False
    assert "stale=" + MODULE in reason


def test_check_final_coverage_refuses_on_missing_and_uncontracted(tmp_path, monkeypatch):
    other_module = "scripts/other_module.py"

    def fake_run(command, cwd=None, capture_output=True, text=True, check=False, timeout=None):
        if command[:3] == ["python3", "scripts/fable_review_gate.py", "--root"]:
            return FakeCompleted(
                1,
                json.dumps(
                    {
                        "covered": [],
                        "missing": [MODULE],
                        "missing_contracts": [other_module],
                        "problems": [],
                    }
                ),
            )
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(refinery_gate.subprocess, "run", fake_run)

    ok, reason = refinery_gate.check_final_coverage(tmp_path, [MODULE, other_module])

    assert ok is False
    assert f"missing={MODULE}" in reason
    assert f"uncontracted={other_module}" in reason


def test_check_final_coverage_allows_when_fully_covered(tmp_path, monkeypatch):
    def fake_run(command, cwd=None, capture_output=True, text=True, check=False, timeout=None):
        if command[:3] == ["python3", "scripts/fable_review_gate.py", "--root"]:
            return FakeCompleted(
                1,
                json.dumps(
                    {
                        "covered": [MODULE],
                        "missing": [],
                        "missing_contracts": [],
                        "problems": [],
                    }
                ),
            )
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(refinery_gate.subprocess, "run", fake_run)

    ok, reason = refinery_gate.check_final_coverage(tmp_path, [MODULE])

    assert ok is True
    assert reason == ""


# --- round-2 finding 1: closed allowlist for non-refinery identities -------


@pytest.mark.parametrize(
    "agent",
    [
        "deja-vu/gastown.polecat",
        "deja-vu/gastown.furiosa",  # real per-instance polecat alias
        "deja-vu/gastown.vg-1jp",
    ],
)
def test_classify_gc_agent_recognizes_polecat_aliases_as_other(agent):
    assert refinery_gate.classify_gc_agent(agent) == "other"


@pytest.mark.parametrize(
    "agent",
    [
        "totally-bogus",
        "rig/gastown.notarole",
        "deja-vu/gastown.witness",
        "deja-vu/gastown.mayor",
        "deja-vu/gastown.deacon",
        "deja-vu/gastown.",
        "other-rig/gastown.polecat",
    ],
)
def test_classify_gc_agent_refuses_unrecognized_identities_as_unknown(agent):
    """Round-2 finding 1: only a polecat-shaped identity for this rig is
    "other" (skip); a reserved role literal, another rig, or an unparseable
    value must all classify as "unknown" (refuse) instead."""
    assert refinery_gate.classify_gc_agent(agent) == "unknown"


def test_skip_when_gc_agent_is_a_polecat_alias_not_the_literal_word(
    tmp_path, monkeypatch, capsys
):
    """Real polecat sessions carry a per-instance alias (e.g. "furiosa"), not
    the literal string "polecat" -- pin that the closed allowlist recognizes
    the shape, not a hardcoded name."""
    monkeypatch.setenv("GC_AGENT", "deja-vu/gastown.furiosa")

    def forbidden(*args, **kwargs):
        raise AssertionError("must not run any subprocess when skipping")

    monkeypatch.setattr(refinery_gate.subprocess, "run", forbidden)

    code = refinery_gate.main(["--root", str(tmp_path)])

    assert code == 0
    assert "REFINERY_GATE: skip" in capsys.readouterr().out


@pytest.mark.parametrize(
    "agent",
    [
        "totally-bogus",
        "deja-vu/gastown.witness",
        "deja-vu/gastown.mayor",
        "deja-vu/gastown.deacon",
        "other-rig/gastown.polecat",
    ],
)
def test_refuse_when_gc_agent_is_unrecognized_not_silently_skipped(
    tmp_path, monkeypatch, capsys, agent
):
    """Round-2 finding 1: an identity that is neither the refinery nor a
    recognized non-refinery pattern must refuse, not skip with exit 0 --
    previously any non-empty trailing token classified as a generic "other"
    role and skipped past the gate."""
    monkeypatch.setenv("GC_AGENT", agent)

    def forbidden(*args, **kwargs):
        raise AssertionError("must not run any subprocess when identity is unknown")

    monkeypatch.setattr(refinery_gate.subprocess, "run", forbidden)

    code = refinery_gate.main(["--root", str(tmp_path)])

    assert code == 1
    assert "REFINERY_GATE: refuse reason=identity-unknown" in capsys.readouterr().out


# --- round-2 finding 2: usage errors print the REFINERY_GATE line ----------


def test_usage_error_on_unrecognized_flag_prints_refinery_gate_line(capsys):
    code = refinery_gate.main(["--not-a-real-flag"])

    out = capsys.readouterr().out
    assert code == 1
    assert "REFINERY_GATE: refuse reason=usage" in out


def test_usage_error_on_missing_option_value_prints_refinery_gate_line(capsys):
    code = refinery_gate.main(["--root"])  # --root requires a value

    out = capsys.readouterr().out
    assert code == 1
    assert "REFINERY_GATE: refuse reason=usage" in out


def test_help_flag_exits_cleanly_without_usage_refusal(capsys):
    """A clean --help exit (code 0) is not a usage error and must not be
    swallowed into a REFINERY_GATE: refuse line."""
    with pytest.raises(SystemExit) as excinfo:
        refinery_gate.main(["--help"])

    assert excinfo.value.code == 0
    assert "REFINERY_GATE: refuse reason=usage" not in capsys.readouterr().out
